## Runner mini-game (Chrome-dino style) with the student's own buddy.
## Jump: tap anywhere, Space, or ANY piano key. Server owns the credits; this screen plays and posts scores.
##
## Layers:  World (Node2D, shakeable, custom-drawn)  →  HUD (chips)  →  overlays (start / countdown / game over)
extends Control

const GROUND_Y := 340.0
const GRAVITY := 2600.0
const JUMP_V := -900.0
const START_SPEED := 300.0
const MAX_SPEED := 760.0
const PLAYER_X := 150.0

var _student: Dictionary = {}
var _credits: Dictionary = {}
var _best := 0
var _state := "loading"        # loading | ready | countdown | running | dying | over
var _speed := START_SPEED
var _distance := 0.0
var _score := 0
var _vy := 0.0
var _y := GROUND_Y
var _obstacles: Array[Dictionary] = []
var _spawn_in := 1.2
var _ground_offset := 0.0
var _elapsed := 0.0
var _clouds: Array[Vector2] = []
var _rng := RandomNumberGenerator.new()

var _world: Node2D
var _buddy: Buddy
var _hud_runs: Label
var _hud_score: Label
var _hud_best: Label
var _flash: ColorRect
var _overlay: Dictionary = {}
var _countdown_lbl: Label


func setup(params: Dictionary) -> void:
	_student = params.get("student", {})


func _ready() -> void:
	_rng.randomize()
	for i in 7:
		_clouds.append(Vector2(_rng.randf_range(0, 800), _rng.randf_range(50, 190)))

	# ---- world
	_world = Node2D.new()
	add_child(_world)
	_world.draw.connect(_draw_world)
	_buddy = Buddy.new()
	_buddy.sprite_scale = 1.15
	_buddy.tap_radius = 0.0          # taps are jumps here, not pokes
	_buddy.set_status(App.buddies.get(int(_student.get("id", -1)), {"level": 1}))
	_buddy.position = Vector2(PLAYER_X, GROUND_Y - 42)
	_world.add_child(_buddy)

	# ---- flash layer (hit feedback)
	_flash = ColorRect.new()
	_flash.color = Color(1, 1, 1, 0)
	_flash.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	_flash.mouse_filter = MOUSE_FILTER_IGNORE
	add_child(_flash)

	# ---- HUD
	var hud := MarginContainer.new()
	hud.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	hud.mouse_filter = MOUSE_FILTER_IGNORE
	for side in ["left", "right"]:
		hud.add_theme_constant_override("margin_" + side, UI.MARGIN)
	hud.add_theme_constant_override("margin_top", 14)
	hud.add_theme_constant_override("margin_bottom", 14)
	add_child(hud)
	var top := HBoxContainer.new()
	top.size_flags_vertical = SIZE_SHRINK_BEGIN
	top.add_theme_constant_override("separation", UI.GAP)
	hud.add_child(top)
	top.add_child(UI.button("‹  Back", "GhostButton", func(): Router.home("slide_right")))
	var runs_chip := UI.chip("", "Chip")
	_hud_runs = runs_chip.get_child(0)
	top.add_child(runs_chip)
	UI.spacer(top, 0, false).size_flags_horizontal = SIZE_EXPAND_FILL
	var best_chip := UI.chip("", "Chip")
	_hud_best = best_chip.get_child(0)
	top.add_child(best_chip)
	var score_chip := UI.chip("", "AccentChip", App.TEXT_PRIMARY)
	_hud_score = score_chip.get_child(0)
	_hud_score.theme_type_variation = "Heading"
	_hud_score.add_theme_color_override("font_color", App.TEXT_PRIMARY)
	top.add_child(score_chip)

	# ---- countdown label
	_countdown_lbl = UI.label("", "TimerLabel", HORIZONTAL_ALIGNMENT_CENTER)
	_countdown_lbl.set_anchors_and_offsets_preset(PRESET_CENTER)
	_countdown_lbl.visible = false
	add_child(_countdown_lbl)

	Midi.note_on.connect(func(_n, _v): _jump())
	await _load_credits()
	_update_hud()
	_show_start()


# --------------------------------------------------------------------------- data
func _load_credits() -> void:
	var c = await Api.get_json("/api/v1/students/%d/game/credits" % int(_student.get("id", 0)))
	_credits = c if c is Dictionary else {}
	var runs = await Api.get_json("/api/v1/students/%d/game/runs?limit=200" % int(_student.get("id", 0)))
	_best = 0
	if runs is Array:
		for r in runs:
			_best = maxi(_best, int(r.get("score", 0)))


func _remaining() -> int:
	return int(_credits.get("remaining", 0))


func _update_hud() -> void:
	var n := _remaining()
	_hud_runs.text = "%d run%s left" % [n, "" if n == 1 else "s"]
	_hud_runs.add_theme_color_override("font_color", App.TEXT_SECONDARY if n > 0 else App.DANGER)
	_hud_best.text = "BEST  %05d" % _best
	_hud_score.text = "%05d" % _score


# --------------------------------------------------------------------------- overlays
func _close_overlay() -> void:
	if _overlay.has("root"):
		_overlay["root"].queue_free()
		_overlay = {}


func _show_start() -> void:
	_close_overlay()
	if _remaining() <= 0:
		_show_game_over(null)
		return
	_state = "ready"
	_overlay = UI.overlay(self, 460)
	var box: VBoxContainer = _overlay["box"]
	box.add_child(UI.label("Runner", "Title", HORIZONTAL_ALIGNMENT_CENTER))
	box.add_child(UI.label("%s runs, jumps over metronomes and notes. The further you go, the higher the score." % _student.get("name", "Your buddy"), "Caption", HORIZONTAL_ALIGNMENT_CENTER, true))
	var tips := UI.card(box, 1.0, "Surface")
	tips.get_parent().size_flags_vertical = SIZE_SHRINK_BEGIN
	UI.stat(tips, "Jump", "tap · Space · any piano key", "Body")
	UI.stat(tips, "Runs today", str(_remaining()), "Body")
	if _best > 0:
		UI.stat(tips, "Your best", "%d" % _best, "Body")
	var start := UI.button("Start", "PrimaryButton", _begin_countdown)
	UI.button_stack(box, [start, UI.button("Leaderboard", "GhostButton", func(): Router.go("Leaderboard", {"student": _student}, "slide_left"))])


func _begin_countdown() -> void:
	if _state != "ready":
		return
	_state = "countdown"
	_close_overlay()
	_reset_run()
	_countdown_lbl.visible = true
	for n in ["3", "2", "1", "GO"]:
		_countdown_lbl.text = n
		_countdown_lbl.pivot_offset = _countdown_lbl.size / 2.0
		_countdown_lbl.scale = Vector2(1.4, 1.4)
		_countdown_lbl.modulate.a = 1.0
		var tw := create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		tw.tween_property(_countdown_lbl, "scale", Vector2.ONE, 0.35)
		tw.tween_property(_countdown_lbl, "modulate:a", 0.0, 0.6).set_delay(0.25)
		await get_tree().create_timer(0.65 if n != "GO" else 0.3).timeout
	_countdown_lbl.visible = false
	_state = "running"
	_buddy.run()


func _show_game_over(res: Variant) -> void:
	_state = "over"
	_close_overlay()
	_overlay = UI.overlay(self, 440)
	var box: VBoxContainer = _overlay["box"]
	if res is Dictionary:
		var s := int(res.get("score", _score))
		box.add_child(UI.label("New best!  ★" if res.get("new_personal_best", false) else "Run over", "Caption", HORIZONTAL_ALIGNMENT_CENTER))
		var big := UI.label("%d" % s, "TimerLabel", HORIZONTAL_ALIGNMENT_CENTER)
		big.add_theme_color_override("font_color", App.WARNING if res.get("new_personal_best", false) else App.TEXT_PRIMARY)
		box.add_child(big)
		box.add_child(UI.label("Rank #%d   ·   best %d" % [int(res.get("rank", 0)), int(res.get("personal_best", 0))], "Caption", HORIZONTAL_ALIGNMENT_CENTER))
	else:
		box.add_child(UI.label("No runs left today", "Title", HORIZONTAL_ALIGNMENT_CENTER))
		box.add_child(UI.label("Finish tomorrow's practice to play again.", "Caption", HORIZONTAL_ALIGNMENT_CENTER, true))

	var actions := []
	if _remaining() > 0:
		actions.append(UI.button("Run again  ·  %d left" % _remaining(), "PrimaryButton", func():
			_state = "ready"
			_begin_countdown()))
	elif _credits.get("bonus_available", false) and not _credits.get("bonus_unlocked", false):
		actions.append(UI.button("Practise %d more minutes for a bonus run" % int(_credits.get("bonus_minutes", 10)), "SuccessButton", func():
			App.start_session(_student, {}, float(_credits.get("bonus_target_seconds", 0)))
			Router.replace("Session", {}, "zoom")))
	actions.append(UI.button("Leaderboard", "Button", func(): Router.go("Leaderboard", {"student": _student}, "slide_left")))
	actions.append(UI.button("Done", "GhostButton", func(): Router.home("fade")))
	UI.button_stack(box, actions)


# --------------------------------------------------------------------------- run lifecycle
func _reset_run() -> void:
	_speed = START_SPEED
	_distance = 0.0
	_score = 0
	_elapsed = 0.0
	_y = GROUND_Y
	_vy = 0.0
	_obstacles.clear()
	_spawn_in = 1.1
	_buddy.position = Vector2(PLAYER_X, GROUND_Y - 42)
	_buddy.rotation = 0.0
	_world.position = Vector2.ZERO
	_update_hud()


func _jump() -> void:
	if _state == "running" and _y >= GROUND_Y - 0.5:
		_vy = JUMP_V
		_buddy.jump()
		var tw := create_tween()
		tw.tween_property(_buddy, "rotation", -0.22, 0.16)
		tw.tween_property(_buddy, "rotation", 0.0, 0.3)


func _die() -> void:
	_state = "dying"
	_buddy.stop_run()
	# flash + shake + tumble
	_flash.color = Color(1, 1, 1, 0.55)
	create_tween().tween_property(_flash, "color:a", 0.0, 0.35)
	var shake := create_tween()
	for i in 6:
		shake.tween_property(_world, "position", Vector2(_rng.randf_range(-9, 9), _rng.randf_range(-6, 6)), 0.04)
	shake.tween_property(_world, "position", Vector2.ZERO, 0.06)
	create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_IN).tween_property(_buddy, "rotation", 0.8, 0.4)
	var res = await Api.post_json("/api/v1/students/%d/game/runs" % int(_student["id"]),
		{"score": _score, "distance": int(_distance), "duration_s": snapped(_elapsed, 0.1)})
	if res is Dictionary:
		_credits = res.get("credits", _credits)
		_best = maxi(_best, int(res.get("personal_best", 0)))
	await get_tree().create_timer(0.5).timeout
	_update_hud()
	_show_game_over(res)


# --------------------------------------------------------------------------- input
func _unhandled_input(event: InputEvent) -> void:
	var tap: bool = event is InputEventScreenTouch and event.is_pressed()
	var key: bool = event is InputEventKey and event.is_pressed() and not event.is_echo() and event.keycode == KEY_SPACE
	if tap or key:
		if _state == "running":
			_jump()
			get_viewport().set_input_as_handled()
		elif _state == "ready" and key:
			_begin_countdown()


# --------------------------------------------------------------------------- simulation
func _process(delta: float) -> void:
	var scroll := _speed if _state == "running" else START_SPEED * 0.25
	_ground_offset = fmod(_ground_offset + scroll * delta, 48.0)
	for i in _clouds.size():
		_clouds[i].x -= delta * (16.0 + i * 4.0)
		if _clouds[i].x < -90:
			_clouds[i] = Vector2(880, _rng.randf_range(50, 190))
	if _state == "running":
		_elapsed += delta
		_speed = minf(MAX_SPEED, _speed + delta * 10.0)
		_distance += _speed * delta
		_score = int(_distance / 10.0)
		_hud_score.text = "%05d" % _score
		var was_airborne := _y < GROUND_Y - 0.5
		_vy += GRAVITY * delta
		_y = minf(GROUND_Y, _y + _vy * delta)
		if _y >= GROUND_Y:
			_vy = 0.0
			if was_airborne:
				_buddy.land()
		_buddy.position.y = _y - 42
		_spawn_in -= delta
		if _spawn_in <= 0.0:
			_spawn_obstacle()
			_spawn_in = _rng.randf_range(0.85, 1.6) * (START_SPEED / _speed) + 0.4
		var player := Rect2(PLAYER_X - 20, _y - 68, 40, 68)
		for o in _obstacles:
			o["x"] -= _speed * delta
			if Rect2(o["x"], GROUND_Y - o["h"], o["w"], o["h"]).intersects(player.grow(-6)):
				_die()
				break
		_obstacles = _obstacles.filter(func(o): return o["x"] > -90)
	_world.queue_redraw()


func _spawn_obstacle() -> void:
	var kind: int = _rng.randi_range(0, 2)
	var o := {"x": 860.0, "kind": kind}
	match kind:
		0: o["w"] = 34.0; o["h"] = 54.0          # metronome
		1: o["w"] = 26.0; o["h"] = 42.0          # quarter note
		_: o["w"] = 58.0; o["h"] = 32.0          # beamed pair: wide and low
	_obstacles.append(o)


# --------------------------------------------------------------------------- drawing (into _world)
func _draw_world() -> void:
	var w := _world
	w.draw_rect(Rect2(-20, -20, size.x + 40, size.y + 40), App.BG_DARK)
	# distant hills
	w.draw_circle(Vector2(180, GROUND_Y + 160), 220, App.BG_CARD.darkened(0.15))
	w.draw_circle(Vector2(620, GROUND_Y + 190), 280, App.BG_CARD.darkened(0.15))
	for c in _clouds:
		w.draw_circle(c, 18, App.BG_CARD)
		w.draw_circle(c + Vector2(20, 6), 14, App.BG_CARD)
		w.draw_circle(c + Vector2(-18, 8), 12, App.BG_CARD)
	# ground: staff line + ticks
	w.draw_rect(Rect2(-20, GROUND_Y + 2, size.x + 40, size.y - GROUND_Y + 40), App.BG_CARD)
	w.draw_line(Vector2(-20, GROUND_Y + 2), Vector2(size.x + 20, GROUND_Y + 2), App.TEXT_MUTED, 3.0)
	var x := -_ground_offset
	while x < size.x + 20:
		w.draw_line(Vector2(x, GROUND_Y + 12), Vector2(x + 16, GROUND_Y + 12), App.BG_SURFACE, 2.0)
		x += 48.0
	# shadow under the buddy
	var sh := clampf(1.0 - (GROUND_Y - _y) / 160.0, 0.35, 1.0)
	w.draw_circle(Vector2(PLAYER_X, GROUND_Y - 2), 22.0 * sh, Color(0, 0, 0, 0.35 * sh))
	for o in _obstacles:
		var base := Vector2(o["x"], GROUND_Y)
		match int(o["kind"]):
			0:
				var pts := PackedVector2Array([base + Vector2(4, 0), base + Vector2(o["w"] - 4, 0), base + Vector2(o["w"] - 10, -o["h"]), base + Vector2(10, -o["h"])])
				w.draw_colored_polygon(pts, App.WARNING)
				w.draw_line(base + Vector2(o["w"] / 2, -6), base + Vector2(o["w"] / 2 + 8, -o["h"] + 8), App.TEXT_DARK, 3.0)
			1:
				w.draw_circle(base + Vector2(11, -9), 10, App.ACCENT)
				w.draw_line(base + Vector2(20, -11), base + Vector2(20, -o["h"]), App.ACCENT, 3.0)
			_:
				w.draw_circle(base + Vector2(11, -9), 10, App.DANGER)
				w.draw_circle(base + Vector2(o["w"] - 11, -9), 10, App.DANGER)
				w.draw_line(base + Vector2(20, -11), base + Vector2(20, -o["h"]), App.DANGER, 3.0)
				w.draw_line(base + Vector2(o["w"] - 2, -11), base + Vector2(o["w"] - 2, -o["h"]), App.DANGER, 3.0)
				w.draw_line(base + Vector2(20, -o["h"]), base + Vector2(o["w"] - 2, -o["h"]), App.DANGER, 5.0)
