## End-of-session recap. Left: the buddy walks one step on the road (and transforms at a milestone).
## Right: today's stats and the Runner button.
extends Control

var _summary: Dictionary = {}
var _buddy: Buddy
var _road: RoadBar
var _msg: Label
var _game_btn: Button


func setup(params: Dictionary) -> void:
	_summary = params


func _ready() -> void:
	var page := UI.page(self)
	var student: Dictionary = _summary.get("student", {})
	var st: Dictionary = _summary.get("buddy", {})
	UI.header(page, "Great practice, %s!" % student.get("name", ""), Callable(),
		[UI.button("Done", "GhostButton", func(): Router.home("fade"))])

	var body := UI.row(page, true, 16)

	# ---- left: buddy + road
	var left := UI.card(body, 1.1)
	var stage := Control.new()
	stage.custom_minimum_size = Vector2(0, 160)
	stage.size_flags_vertical = SIZE_EXPAND_FILL
	stage.clip_contents = true
	left.add_child(stage)
	_buddy = Buddy.new()
	_buddy.sprite_scale = 1.9
	# start as the level the student HAD when today began, so the transformation is visible
	_buddy.set_level(int(st.get("prev_level", st.get("level", 1))))
	stage.add_child(_buddy)
	var center := func(): _buddy.position = stage.size / 2.0
	stage.resized.connect(center)
	center.call()
	_msg = UI.label(str(st.get("prev_level_name", st.get("level_name", ""))), "Body", HORIZONTAL_ALIGNMENT_CENTER)
	left.add_child(_msg)
	_road = RoadBar.new()
	_road.size_flags_horizontal = SIZE_SHRINK_CENTER
	# show the road as it was before today's step, then animate the new step in
	var before := st.duplicate()
	var spl := maxi(1, int(st.get("steps_per_level", 3)))
	var in_level := int(st.get("steps_in_level", 0))
	before["steps_in_level"] = (in_level - 1) if in_level > 0 else (spl - 1 if st.get("evolved_today", false) else 0)
	before["at_top"] = false
	_road.set_status(before)
	left.add_child(_road)

	# ---- right: stats
	var right := UI.card(body, 1.0)
	right.add_child(UI.label("Today", "Caption"))
	UI.stat(right, "Practice time", App.fmt_time(float(_summary.get("accumulated", 0))))
	UI.stat(right, "Notes played", str(int(_summary.get("total_notes", 0))))
	UI.stat(right, "Road", "%d steps" % int(st.get("steps", 0)))
	UI.stat(right, "Streak", "%d days" % int(st.get("streak", 0)))
	var chords: Dictionary = _summary.get("chords", {})
	if not chords.is_empty():
		var keys := chords.keys()
		keys.sort_custom(func(a, b): return chords[a] > chords[b])
		var top := PackedStringArray()
		for k in keys.slice(0, 4):
			top.append(str(k))
		UI.stat(right, "Top chords", ", ".join(top), "Body")
	UI.spacer(right)
	_game_btn = UI.button("Runner game", "SuccessButton", func(): Router.replace("Runner", {"student": student}, "zoom"))
	_game_btn.size_flags_horizontal = SIZE_EXPAND_FILL
	_game_btn.visible = false
	right.add_child(_game_btn)

	_play_ceremony(st)
	_offer_game()


## +1 step → dot pulses → (milestone) transformation → final road.
func _play_ceremony(st: Dictionary) -> void:
	await get_tree().create_timer(0.6).timeout
	_msg.text = "+1 step on the road!"
	_msg.add_theme_color_override("font_color", App.SUCCESS)
	var evolved := bool(st.get("evolved_today", false))
	var spl := maxi(1, int(st.get("steps_per_level", 3)))
	var in_level := int(st.get("steps_in_level", 0))
	var earned_index := (spl - 1) if (evolved or in_level == 0) else (in_level - 1)
	var after := st.duplicate()
	if evolved:
		after["steps_in_level"] = spl          # show the milestone reached before the reset
		after["at_top"] = false
	_road.set_status(after)
	_road.animate_step(earned_index)
	await _buddy.dance(1.8)
	if evolved:
		_msg.text = "A new evolution!"
		_msg.add_theme_color_override("font_color", App.WARNING)
		await _buddy.transform_to(int(st.get("level", 1)))
		_msg.text = str(st.get("level_name", ""))
		_msg.add_theme_color_override("font_color", App.TEXT_PRIMARY)
		await get_tree().create_timer(0.4).timeout
		_road.set_status(st)                   # fresh milestone: dots reset
	elif st.get("at_top", false):
		_msg.text = "%s  ·  top of the road!" % str(st.get("level_name", ""))
	else:
		_msg.text = str(st.get("level_name", ""))
	Api.post_json("/api/v1/students/%d/celebrate" % int(_summary["student"]["id"]))


func _offer_game() -> void:
	if not App.settings.get("game", {}).get("enabled", true):
		return
	var c = await Api.get_json("/api/v1/students/%d/game/credits" % int(_summary["student"]["id"]))
	if c is Dictionary and int(c.get("remaining", 0)) > 0:
		var n := int(c["remaining"])
		_game_btn.text = "Runner game  ·  %d run%s left" % [n, "" if n == 1 else "s"]
		_game_btn.visible = true
		_game_btn.modulate.a = 0.0
		create_tween().tween_property(_game_btn, "modulate:a", 1.0, 0.4)
