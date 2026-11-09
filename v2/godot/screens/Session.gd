## Practice screen. Layout (800×480):
##   header: name + status chip ............................. [Lesson] [End]
##   body:   timer ring (left)  |  buddy + live chord (right)
##   bar:    metronome · tempo · lesson transport (wraps if needed)
##   piano strip
extends Control

var _ring: TimerRing
var _status_chip: Label
var _chord_lbl: Label
var _notes_lbl: Label
var _metro_btn: Button
var _speed_btn: Button
var _play_btn: Button
var _slider: HSlider
var _buddy: Buddy
var _bonus_btn: Button
var _metro_on := false
var _speed_mode := "normal"
var _player_poll := 0.0
var _celebrated := false


func _ready() -> void:
	var page := UI.page(self, 10)
	var status_chip := UI.chip("", "Chip")
	_status_chip = status_chip.get_child(0)
	var lesson_btn := UI.button("Lesson" if App.lesson.is_empty() else str(App.lesson["name"]), "GhostButton",
		func(): Router.go("Lessons", {"pick": true}, "slide_left"))
	lesson_btn.custom_minimum_size.x = 120
	UI.header(page, "%s's practice" % App.student.get("name", "Guest"), Callable(),
		[status_chip, lesson_btn, UI.button("End", "DangerButton", _end)])

	# ---- body
	var body := UI.row(page, true, 20)
	_ring = TimerRing.new()
	_ring.custom_minimum_size = Vector2(230, 230)
	_ring.size_flags_vertical = SIZE_SHRINK_CENTER
	body.add_child(_ring)

	var right := UI.column(body, true, 8)
	var stage := Control.new()
	stage.custom_minimum_size = Vector2(0, 110)
	stage.size_flags_vertical = SIZE_EXPAND_FILL
	stage.clip_contents = true
	right.add_child(stage)
	if not App.student.is_empty():
		_buddy = Buddy.new()
		_buddy.sprite_scale = 1.1
		_buddy.set_status(App.buddies.get(int(App.student["id"]), {}))
		stage.add_child(_buddy)
		var center := func(): _buddy.position = stage.size / 2.0
		stage.resized.connect(center)
		center.call()
	var chord_card := UI.card(right, 0.0, "Surface")
	chord_card.get_parent().size_flags_vertical = SIZE_SHRINK_END
	_chord_lbl = UI.label("—", "Display", HORIZONTAL_ALIGNMENT_CENTER)
	_chord_lbl.add_theme_color_override("font_color", App.TEXT_MUTED)
	chord_card.add_child(_chord_lbl)
	_notes_lbl = UI.label("Play a chord to see it", "Caption", HORIZONTAL_ALIGNMENT_CENTER)
	chord_card.add_child(_notes_lbl)

	# ---- control bar (wraps)
	_metro_btn = UI.button("Metronome  off", "Button", _toggle_metro)
	_speed_btn = UI.button("", "Button", _cycle_speed)
	_play_btn = UI.button("▶  Play lesson", "Button", _toggle_play)
	_play_btn.visible = not App.lesson.is_empty()
	_bonus_btn = UI.button("▶  Play the bonus run", "SuccessButton", func():
		Api.post_json("/api/v1/metronome/stop")
		Api.post_json("/api/v1/player/stop")
		App.end_session())
	_bonus_btn.visible = false
	var bar := UI.button_row(page, [_metro_btn, _speed_btn, _play_btn, _bonus_btn])
	_slider = HSlider.new()
	_slider.custom_minimum_size = Vector2(180, UI.TOUCH)
	_slider.size_flags_horizontal = SIZE_EXPAND_FILL
	_slider.max_value = 1.0
	_slider.step = 0.001
	_slider.visible = not App.lesson.is_empty()
	_slider.drag_ended.connect(func(_changed): Api.post_json("/api/v1/player/seek", {"pct": _slider.value}))
	bar.add_child(_slider)
	_update_speed_label()

	# ---- piano
	var piano := MiniPiano.new()
	piano.custom_minimum_size = Vector2(0, 64)
	page.add_child(piano)

	App.session_tick.connect(_on_tick)
	App.goal_reached.connect(_celebrate)
	App.session_ended.connect(_on_ended)
	App.bonus_reached_signal.connect(_on_bonus_reached)
	Midi.note_on.connect(func(_n, _v): _update_chord())
	Midi.note_off.connect(func(_n): _update_chord())
	_refresh_status()
	if not App.lesson.is_empty():
		Api.post_json("/api/v1/player/load", {"lesson_id": App.lesson["id"], "autoplay": false, "speed": _speed_ratio()})


func setup(params: Dictionary) -> void:
	if params.has("lesson") and App.session_active:
		App.lesson = params["lesson"]


func _process(delta: float) -> void:
	if App.lesson.is_empty():
		return
	_player_poll += delta
	if _player_poll > 0.4:
		_player_poll = 0.0
		var st = await Api.get_json("/api/v1/player/status")
		if st is Dictionary:
			_slider.set_value_no_signal(float(st.get("progress", 0)))
			_play_btn.text = "❚❚  Pause" if st.get("playing", false) else "▶  Play lesson"


func _on_tick(acc: float, playing: bool) -> void:
	_ring.set_time(acc)
	_ring.progress = acc / (App.bonus_target if App.bonus_target > 0.0 else App.goal_seconds())
	_ring.active = playing
	_ring.complete = App.goal_done and App.bonus_target <= 0.0
	_ring.set_caption("playing" if playing else "paused")


func _refresh_status() -> void:
	if App.bonus_target > 0.0:
		_status_chip.text = "Bonus run  ·  practise until %s" % App.fmt_time(App.bonus_target)
		_status_chip.add_theme_color_override("font_color", App.WARNING)
	elif App.student.is_empty():
		_status_chip.text = "Free play"
	elif App.goal_done:
		_status_chip.text = "Goal completed  ✔"
		_status_chip.add_theme_color_override("font_color", App.SUCCESS)
	else:
		_status_chip.text = "%d-minute goal" % int(App.settings.get("goal_minutes", 15))


func _update_chord() -> void:
	var chord := Midi.identify_chord(Midi.active_notes.keys())
	var names := PackedStringArray()
	var keys := Midi.active_notes.keys()
	keys.sort()
	for n in keys:
		names.append(Midi.note_name(int(n), false))
	if chord != "":
		_chord_lbl.text = chord
		_chord_lbl.add_theme_color_override("font_color", App.ACCENT)
		_chord_lbl.pivot_offset = _chord_lbl.size / 2.0
		_chord_lbl.scale = Vector2(1.12, 1.12)
		create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT).tween_property(_chord_lbl, "scale", Vector2.ONE, 0.25)
		_notes_lbl.text = "  ".join(names)
	elif keys.is_empty():
		_chord_lbl.text = "—"
		_chord_lbl.add_theme_color_override("font_color", App.TEXT_MUTED)
		_notes_lbl.text = "Play a chord to see it"
	else:
		_chord_lbl.text = "  ".join(names) if names.size() <= 4 else "%d notes" % names.size()
		_chord_lbl.add_theme_color_override("font_color", App.TEXT_SECONDARY)
		_notes_lbl.text = "…"


func _celebrate() -> void:
	if _celebrated:
		return
	_celebrated = true
	_refresh_status()
	if _buddy:
		_buddy.dance(2.0)
	var cp := CPUParticles2D.new()
	cp.position = _ring.global_position + _ring.size / 2.0
	cp.amount = 90
	cp.lifetime = 1.6
	cp.one_shot = true
	cp.explosiveness = 0.95
	cp.direction = Vector2(0, -1)
	cp.spread = 80
	cp.initial_velocity_min = 220
	cp.initial_velocity_max = 420
	cp.gravity = Vector2(0, 600)
	cp.scale_amount_min = 3
	cp.scale_amount_max = 6
	var grad := Gradient.new()
	grad.colors = PackedColorArray([App.ACCENT, App.WARNING, App.SUCCESS, App.DANGER])
	cp.color_ramp = grad
	add_child(cp)
	cp.emitting = true
	get_tree().create_timer(2.0).timeout.connect(cp.queue_free)


func _on_bonus_reached() -> void:
	_status_chip.text = "Bonus run unlocked  ★"
	_status_chip.add_theme_color_override("font_color", App.SUCCESS)
	if _buddy:
		_buddy.dance(1.5)
	_bonus_btn.visible = true
	_bonus_btn.modulate.a = 0.0
	create_tween().tween_property(_bonus_btn, "modulate:a", 1.0, 0.3)


func _toggle_metro() -> void:
	_metro_on = not _metro_on
	_metro_btn.text = "Metronome  %s" % ("on" if _metro_on else "off")
	_metro_btn.theme_type_variation = "PrimaryButton" if _metro_on else "Button"
	Api.post_json("/api/v1/metronome/" + ("start" if _metro_on else "stop"), {"bpm": _bpm()})


func _bpm() -> int:
	return int(App.settings.get("metronome", {}).get(_speed_mode, 80))


func _speed_ratio() -> float:
	var m: Dictionary = App.settings.get("metronome", {})
	return float(m.get(_speed_mode, 80)) / float(m.get("normal", 80))


func _cycle_speed() -> void:
	_speed_mode = {"slow": "normal", "normal": "fast", "fast": "slow"}[_speed_mode]
	_update_speed_label()
	if _metro_on:
		Api.post_json("/api/v1/metronome/bpm", {"bpm": _bpm()})
	if not App.lesson.is_empty():
		Api.post_json("/api/v1/player/speed", {"speed": _speed_ratio()})


func _update_speed_label() -> void:
	_speed_btn.text = "Tempo  %s · %d" % [_speed_mode.capitalize(), _bpm()]


func _toggle_play() -> void:
	var st = await Api.get_json("/api/v1/player/status")
	if st is Dictionary and st.get("playing", false):
		Api.post_json("/api/v1/player/pause")
	else:
		Api.post_json("/api/v1/player/play")


func _end() -> void:
	if _metro_on:
		Api.post_json("/api/v1/metronome/stop")
	Api.post_json("/api/v1/player/stop")
	App.end_session()


func _on_ended(summary: Dictionary) -> void:
	if summary.get("bonus_run", false):
		Router.replace("Runner", {"student": summary["student"]}, "zoom")
	elif summary.get("goal_reached", false) and not summary.get("student", {}).is_empty():
		Router.replace("Recap", summary, "zoom")
	else:
		Router.home("slide_right")
