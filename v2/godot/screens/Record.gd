## Teacher's lesson recorder: capture what is played on the piano as a lesson students can practise along to.
## Flow: name → Record (3-beat count-in) → play → Stop → Listen / Save / Discard.
extends Control

enum State { IDLE, COUNTING, RECORDING, REVIEW }

var _state := State.IDLE
var _name := ""
var _events: Array = []               # {time, type, note, vel, channel}
var _started := 0.0
var _elapsed := 0.0
var _note_count := 0

var _name_btn: Button
var _rec_btn: Button
var _stop_btn: Button
var _listen_btn: Button
var _save_btn: Button
var _discard_btn: Button
var _status_chip: Label
var _clock: Label
var _count_lbl: Label
var _hint: Label
var _keyboard: Dictionary = {}


func _ready() -> void:
	_name = "Lesson %s" % Time.get_date_string_from_system()
	var page := UI.page(self)
	var status_chip := UI.chip("", "Chip")
	_status_chip = status_chip.get_child(0)
	_name_btn = UI.button(_name, "GhostButton", _edit_name)
	UI.header(page, "Record a lesson", func(): _leave(), [status_chip, _name_btn], "Play it once on the piano; students will practise along to it")

	var body := UI.row(page, true, 16)
	# ---- left: clock + controls
	var left := UI.card(body, 0.9)
	_clock = UI.label("0:00", "TimerLabel", HORIZONTAL_ALIGNMENT_CENTER)
	left.add_child(_clock)
	_hint = UI.label("Press Record, then start playing after the count-in.", "Caption", HORIZONTAL_ALIGNMENT_CENTER, true)
	left.add_child(_hint)
	UI.spacer(left)
	_rec_btn = UI.button("●  Record", "DangerButton", _start_count_in)
	_stop_btn = UI.button("■  Stop", "PrimaryButton", _stop)
	_listen_btn = UI.button("▶  Listen on the piano", "Button", _listen)
	_save_btn = UI.button("Save lesson", "SuccessButton", _save)
	_discard_btn = UI.button("Discard", "GhostButton", _discard)
	UI.button_stack(left, [_rec_btn, _stop_btn, _listen_btn, _save_btn, _discard_btn])

	# ---- right: live staff + piano
	var right := UI.column(body, true, 8)
	var staff_card := UI.card(right, 1.0, "Surface")
	var staff := StaffView.new()
	staff.size_flags_vertical = SIZE_EXPAND_FILL
	staff_card.add_child(staff)
	var piano := MiniPiano.new()
	piano.custom_minimum_size = Vector2(0, 56)
	right.add_child(piano)

	# count-in number over everything
	_count_lbl = UI.label("", "TimerLabel", HORIZONTAL_ALIGNMENT_CENTER)
	_count_lbl.set_anchors_and_offsets_preset(PRESET_CENTER)
	_count_lbl.visible = false
	add_child(_count_lbl)

	Midi.note_on.connect(_on_note_on)
	Midi.note_off.connect(_on_note_off)
	_set_state(State.IDLE)


func _set_state(s: State) -> void:
	_state = s
	_rec_btn.visible = s == State.IDLE
	_stop_btn.visible = s == State.RECORDING
	_listen_btn.visible = s == State.REVIEW
	_save_btn.visible = s == State.REVIEW
	_discard_btn.visible = s == State.REVIEW
	_name_btn.disabled = s == State.RECORDING or s == State.COUNTING
	match s:
		State.IDLE:
			_status_chip.text = "Ready"
			_status_chip.add_theme_color_override("font_color", App.TEXT_SECONDARY)
		State.COUNTING:
			_status_chip.text = "Get ready…"
			_status_chip.add_theme_color_override("font_color", App.WARNING)
		State.RECORDING:
			_status_chip.text = "●  Recording"
			_status_chip.add_theme_color_override("font_color", App.DANGER)
			_hint.text = "Playing is being recorded. Press Stop when done."
		State.REVIEW:
			_status_chip.text = "Recorded  ·  %d notes" % _note_count
			_status_chip.add_theme_color_override("font_color", App.SUCCESS)
			_hint.text = "Listen to check it, then save it as \"%s\"." % _name


func _process(delta: float) -> void:
	if _state == State.RECORDING:
		_elapsed = Time.get_unix_time_from_system() - _started
		_clock.text = App.fmt_time(_elapsed)


# --------------------------------------------------------------------------- recording
func _start_count_in() -> void:
	_events.clear()
	_note_count = 0
	_elapsed = 0.0
	_clock.text = "0:00"
	_set_state(State.COUNTING)
	var bpm := int(App.settings.get("metronome", {}).get("normal", 80))
	Api.post_json("/api/v1/metronome/count-in", {"beats": 4, "bpm": bpm})
	_count_lbl.visible = true
	for n in ["4", "3", "2", "1"]:
		_count_lbl.text = n
		_count_lbl.modulate.a = 1.0
		create_tween().tween_property(_count_lbl, "modulate:a", 0.2, 60.0 / bpm * 0.9)
		await get_tree().create_timer(60.0 / bpm).timeout
		if _state != State.COUNTING:
			return
	_count_lbl.visible = false
	_started = Time.get_unix_time_from_system()
	_set_state(State.RECORDING)


func _on_note_on(note: int, vel: int) -> void:
	if _state == State.COUNTING:                       # eager start: first key during count-in begins the take
		_count_lbl.visible = false
		_started = Time.get_unix_time_from_system()
		_set_state(State.RECORDING)
	if _state != State.RECORDING:
		return
	_events.append({"time": snapped(Time.get_unix_time_from_system() - _started, 0.001), "type": "on", "note": note, "vel": vel, "channel": 0})
	_note_count += 1


func _on_note_off(note: int) -> void:
	if _state != State.RECORDING:
		return
	_events.append({"time": snapped(Time.get_unix_time_from_system() - _started, 0.001), "type": "off", "note": note, "vel": 0, "channel": 0})


func _stop() -> void:
	# close any notes still held
	var t: float = snapped(Time.get_unix_time_from_system() - _started, 0.001)
	for n in Midi.active_notes.keys():
		_events.append({"time": t, "type": "off", "note": int(n), "vel": 0, "channel": 0})
	if _note_count == 0:
		_hint.text = "Nothing was played — try again."
		_set_state(State.IDLE)
		return
	_set_state(State.REVIEW)


func _listen() -> void:
	Api.post_json("/api/v1/player/load", {"events": _events, "label": _name, "autoplay": true})


func _discard() -> void:
	Api.post_json("/api/v1/player/stop")
	_events.clear()
	_note_count = 0
	_clock.text = "0:00"
	_hint.text = "Press Record, then start playing after the count-in."
	_set_state(State.IDLE)


func _save() -> void:
	_save_btn.disabled = true
	_save_btn.text = "Saving…"
	var res = await Api.post_json("/api/v1/lessons", {"name": _name, "midi_events": _events, "source": "kiosk"})
	if res is Dictionary:
		Api.post_json("/api/v1/player/stop")
		Router.replace("Lessons", {}, "slide_right")
	else:
		_save_btn.disabled = false
		_save_btn.text = "Save lesson"
		_hint.text = "Could not save — is the backend running?"


func _leave() -> void:
	Api.post_json("/api/v1/player/stop")
	Router.back()


# --------------------------------------------------------------------------- name entry (on-screen keyboard)
func _edit_name() -> void:
	_keyboard = UI.overlay(self, 640)
	var box: VBoxContainer = _keyboard["box"]
	var field := UI.label(_name, "Heading", HORIZONTAL_ALIGNMENT_CENTER)
	box.add_child(field)
	var rows := ["1234567890", "qwertyuiop", "asdfghjklñ", "zxcvbnm"]
	var type_key := func(ch: String):
		var cap := _name.is_empty() or _name.ends_with(" ")      # auto-capitalise the start of each word
		_name = (_name + (ch.to_upper() if cap else ch)).left(40)
		field.text = _name
	for r in rows:
		var h := HBoxContainer.new()
		h.alignment = BoxContainer.ALIGNMENT_CENTER
		h.add_theme_constant_override("separation", 6)
		box.add_child(h)
		for ch in r:
			var k := UI.button(ch, "SmallButton", type_key.bind(ch))
			k.custom_minimum_size = Vector2(52, 44)
			h.add_child(k)
	var bottom := HBoxContainer.new()
	bottom.alignment = BoxContainer.ALIGNMENT_CENTER
	bottom.add_theme_constant_override("separation", 6)
	box.add_child(bottom)
	var space := UI.button("space", "SmallButton", type_key.bind(" "))
	space.custom_minimum_size = Vector2(240, 44)
	var back := UI.button("⌫", "SmallButton", func():
		_name = _name.left(maxi(0, _name.length() - 1))
		field.text = _name)
	back.custom_minimum_size = Vector2(80, 44)
	var clear := UI.button("clear", "SmallButton", func():
		_name = ""
		field.text = "")
	var done := UI.button("Done", "SmallPrimaryButton", func():
		if _name.strip_edges().is_empty():
			_name = "Lesson %s" % Time.get_date_string_from_system()
		_name = _name.strip_edges()
		_name_btn.text = _name
		_keyboard["root"].queue_free()
		_keyboard = {})
	done.custom_minimum_size = Vector2(110, 44)
	for b in [clear, space, back, done]:
		bottom.add_child(b)
