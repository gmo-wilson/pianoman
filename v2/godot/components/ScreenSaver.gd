## Turns the screen off when the piano is off or nothing has happened for a while; wakes on touch / note / piano on.
## Added by Main (not an autoload) so it ships in content releases.
## Backlight: /sys/class/backlight/*/bl_power (official 7" display and most DSI panels). A black overlay is always
## used too, so HDMI screens without a controllable backlight still go dark and the waking touch is swallowed.
extends Node

signal sleep_changed(asleep: bool)

var asleep := false
var last_activity := 0.0
var _overlay: ColorRect
var _backlight_paths: PackedStringArray = []
var _check_accum := 0.0


func _ready() -> void:
	last_activity = Time.get_unix_time_from_system()
	process_mode = Node.PROCESS_MODE_ALWAYS
	Midi.activity.connect(_on_activity)
	Midi.connection_changed.connect(func(c: bool):
		if c:
			_on_activity())
	_find_backlights()
	# overlay lives on a high CanvasLayer so it covers every screen
	var layer := CanvasLayer.new()
	layer.layer = 100
	add_child(layer)
	_overlay = ColorRect.new()
	_overlay.color = Color.BLACK
	_overlay.visible = false
	_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_overlay.gui_input.connect(func(e: InputEvent):
		if e is InputEventScreenTouch or e is InputEventMouseButton:
			_on_activity())
	layer.add_child(_overlay)


func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch or event is InputEventMouseButton or event is InputEventKey or event is InputEventScreenDrag:
		_on_activity()


func _on_activity() -> void:
	last_activity = Time.get_unix_time_from_system()
	if asleep:
		_set_asleep(false)


func _process(delta: float) -> void:
	_check_accum += delta
	if _check_accum < 1.0:
		return
	_check_accum = 0.0
	var kiosk: Dictionary = App.settings.get("kiosk", {})
	if not bool(kiosk.get("screen_sleep_enabled", true)):
		if asleep:
			_set_asleep(false)
		return
	var idle_limit := float(kiosk.get("idle_sleep_seconds", 60))
	var piano_off_sleeps := bool(kiosk.get("sleep_when_piano_off", true))
	var idle := Time.get_unix_time_from_system() - last_activity
	var should_sleep := idle >= idle_limit or (piano_off_sleeps and not Midi.connected and idle >= 5.0)
	if should_sleep != asleep:
		_set_asleep(should_sleep)


func _set_asleep(v: bool) -> void:
	asleep = v
	_overlay.visible = v
	_set_backlight(not v)
	sleep_changed.emit(v)
	print("[ScreenSaver] ", "sleep" if v else "wake")


# --------------------------------------------------------------------------- backlight
func _find_backlights() -> void:
	_backlight_paths.clear()
	if OS.get_name() != "Linux":
		return
	var dir := DirAccess.open("/sys/class/backlight")
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			_backlight_paths.append("/sys/class/backlight/" + name + "/bl_power")
		name = dir.get_next()
	dir.list_dir_end()
	if _backlight_paths.is_empty():
		print("[ScreenSaver] no backlight device found — using the black overlay only")


func _set_backlight(on: bool) -> void:
	for p in _backlight_paths:
		var f := FileAccess.open(p, FileAccess.WRITE)
		if f:
			f.store_string("0" if on else "1")        # bl_power: 0 = on, 1 (FB_BLANK_POWERDOWN) = off
			f.close()
		else:
			# no write permission (udev rule missing) → try passwordless sudo as a fallback
			OS.execute("sudo", ["-n", "/bin/sh", "-c", "echo %s > %s" % ["0" if on else "1", p]])
