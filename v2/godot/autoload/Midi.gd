## Piano input. Two sources feed the same signals:
##   1. the backend's MIDI bridge over WebSocket (ws://<api>/ws/midi) — primary, hot-plug on every OS
##   2. Godot's native InputEventMIDI — fallback when the backend is unreachable
## Plus a developer keyboard in debug builds.
extends Node

signal note_on(note: int, velocity: int)
signal note_off(note: int)
signal activity()
signal connection_changed(connected: bool)

var active_notes: Dictionary = {}          # note -> velocity
var last_note_time := 0.0                   # seconds (Time.get_unix_time_from_system)
var connected := false
var device_names: PackedStringArray = []

var _rescan_accum := 0.0
const RESCAN_EVERY := 2.0

# ---- bridge
var _ws := WebSocketPeer.new()
var _ws_state := "idle"          # idle | connecting | open
var _ws_retry := 0.0
var bridge_connected := false     # backend says a piano is open
var bridge_name := ""

const NOTE_NAMES := ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


func _ready() -> void:
	OS.open_midi_inputs()
	device_names = OS.get_connected_midi_inputs()
	connected = device_names.size() > 0
	print("[Midi] inputs: ", device_names, "  (", OS.get_name(), ")")
	if device_names.is_empty():
		print("[Midi] no inputs enumerated. On macOS plug the piano in BEFORE launching; events arriving anyway will still be used.")


func _process(delta: float) -> void:
	_poll_bridge(delta)
	_rescan_accum += delta
	if _rescan_accum >= RESCAN_EVERY:
		_rescan_accum = 0.0
		var names := OS.get_connected_midi_inputs()
		var now_connected := names.size() > 0
		if names != device_names:
			device_names = names
		if now_connected != connected:
			connected = now_connected
			connection_changed.emit(connected)
			if not connected:
				active_notes.clear()
		# Hot-plug: ALSA (the Pi) can re-enumerate by reopening; CoreMIDI on macOS cannot be reopened.
		if not connected and OS.get_name() == "Linux":
			_open()


func _open() -> void:
	OS.close_midi_inputs()
	OS.open_midi_inputs()
	device_names = OS.get_connected_midi_inputs()
	var was := connected
	connected = device_names.size() > 0
	if connected != was:
		connection_changed.emit(connected)
	if connected:
		print("[Midi] inputs: ", device_names)


## Developer keyboard (debug builds / editor only): the computer keyboard plays a C major octave, like a DAW.
##   white keys  A S D F G H J K L  →  C D E F G A B C D       black keys  W E   T Y U   O P
##   Z / X  shift the octave down / up.  Hold several keys for chords.
const DEV_KEYS := {
	KEY_A: 60, KEY_W: 61, KEY_S: 62, KEY_E: 63, KEY_D: 64, KEY_F: 65, KEY_T: 66, KEY_G: 67, KEY_Y: 68,
	KEY_H: 69, KEY_U: 70, KEY_J: 71, KEY_K: 72, KEY_O: 73, KEY_L: 74, KEY_P: 75,
}
var dev_octave_shift := 0
var _dev_held: Dictionary = {}


func _input(event: InputEvent) -> void:
	if event is InputEventKey and OS.is_debug_build():
		_dev_keyboard(event as InputEventKey)
		return
	if not (event is InputEventMIDI):
		return
	var e := event as InputEventMIDI
	match e.message:
		MIDI_MESSAGE_NOTE_ON:
			if not connected:                       # events prove a device exists even if enumeration was empty
				connected = true
				if device_names.is_empty():
					device_names = PackedStringArray(["MIDI device %d" % e.device])
				connection_changed.emit(true)
			if e.velocity > 0:
				active_notes[e.pitch] = e.velocity
				last_note_time = Time.get_unix_time_from_system()
				note_on.emit(e.pitch, e.velocity)
				activity.emit()
			else:
				_off(e.pitch)
		MIDI_MESSAGE_NOTE_OFF:
			_off(e.pitch)


func _off(note: int) -> void:
	if active_notes.erase(note):
		note_off.emit(note)


func device_label() -> String:
	if bridge_connected and bridge_name != "":
		return bridge_name
	return device_names[0] if device_names.size() > 0 else ""


# --------------------------------------------------------------------------- bridge (backend WebSocket)
func _poll_bridge(delta: float) -> void:
	match _ws_state:
		"idle":
			_ws_retry -= delta
			if _ws_retry <= 0.0:
				var url := Api.base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/midi"
				if _ws.connect_to_url(url) == OK:
					_ws_state = "connecting"
				else:
					_ws_retry = 3.0
		"connecting", "open":
			_ws.poll()
			var st := _ws.get_ready_state()
			if st == WebSocketPeer.STATE_OPEN:
				if _ws_state != "open":
					_ws_state = "open"
					print("[Midi] bridge connected")
				while _ws.get_available_packet_count() > 0:
					var msg = JSON.parse_string(_ws.get_packet().get_string_from_utf8())
					if msg is Dictionary:
						_on_bridge_msg(msg)
			elif st == WebSocketPeer.STATE_CLOSED:
				if _ws_state == "open":
					print("[Midi] bridge disconnected")
				_ws_state = "idle"
				_ws_retry = 2.0
				if bridge_connected:
					bridge_connected = false
					_recompute_connected()


func _on_bridge_msg(m: Dictionary) -> void:
	match str(m.get("t", "")):
		"status":
			bridge_connected = bool(m.get("connected", false))
			bridge_name = str(m.get("name", "")) if m.get("name") != null else ""
			if not bridge_connected:
				for n in active_notes.keys():
					note_off.emit(int(n))
				active_notes.clear()
			_recompute_connected()
		"on":
			var n := int(m.get("n", 0))
			active_notes[n] = int(m.get("v", 0))
			last_note_time = Time.get_unix_time_from_system()
			if not connected:
				_recompute_connected()
			note_on.emit(n, int(m.get("v", 0)))
			activity.emit()
		"off":
			_off(int(m.get("n", 0)))


func _recompute_connected() -> void:
	var now := bridge_connected or device_names.size() > 0
	if now != connected:
		connected = now
		connection_changed.emit(connected)


func seconds_since_last_note() -> float:
	return Time.get_unix_time_from_system() - last_note_time if last_note_time > 0 else INF


func note_name(note: int, with_octave := true) -> String:
	var n: String = NOTE_NAMES[note % 12]
	return n + str(int(note / 12.0) - 1) if with_octave else n


## Same chord dictionary as the backend (midi_parse.py) so kiosk + admin agree.
const CHORDS := {
	"0,4,7": "", "0,3,7": "m", "0,3,6": "dim", "0,4,8": "aug", "0,4,7,10": "7",
	"0,4,7,11": "maj7", "0,3,7,10": "m7", "0,5,7": "sus4", "0,2,7": "sus2",
}


func identify_chord(notes: Array) -> String:
	if notes.size() < 3:
		return ""
	var pcs := {}
	for n in notes:
		pcs[int(n) % 12] = true
	for root in pcs.keys():
		var rel := []
		for p in pcs.keys():
			rel.append((int(p) - int(root) + 12) % 12)
		rel.sort()
		var parts := PackedStringArray()
		for v in rel:
			parts.append(str(v))
		var key := ",".join(parts)
		if CHORDS.has(key):
			var root_name: String = NOTE_NAMES[int(root)]
			var suffix: String = CHORDS[key]
			return root_name + suffix
	return ""


func _dev_keyboard(k: InputEventKey) -> void:
	if k.echo:
		return
	if k.pressed and k.keycode == KEY_Z:
		dev_octave_shift = maxi(-3, dev_octave_shift - 1)
		return
	if k.pressed and k.keycode == KEY_X:
		dev_octave_shift = mini(3, dev_octave_shift + 1)
		return
	if not DEV_KEYS.has(k.keycode):
		return
	if k.pressed:
		var note: int = int(DEV_KEYS[k.keycode]) + dev_octave_shift * 12
		_dev_held[k.keycode] = note
		if not connected:
			connected = true
			device_names = PackedStringArray(["Dev keyboard"])
			connection_changed.emit(true)
		active_notes[note] = 90
		last_note_time = Time.get_unix_time_from_system()
		note_on.emit(note, 90)
		activity.emit()
	elif _dev_held.has(k.keycode):
		var note: int = _dev_held[k.keycode]
		_dev_held.erase(k.keycode)
		_off(note)
