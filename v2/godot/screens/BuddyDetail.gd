## Student detail: big buddy · lifetime stats · 30-day practice strip.
extends Control

var _student: Dictionary = {}


func setup(params: Dictionary) -> void:
	_student = params.get("student", {})


func _ready() -> void:
	var page := UI.page(self)
	var buddy_status: Dictionary = App.buddies.get(int(_student.get("id", -1)), {})
	UI.header(page, str(_student.get("name", "")), Router.back,
		[UI.button("Practice", "PrimaryButton", func():
			App.start_session(_student)
			Router.go("Session", {}, "zoom"))],
		"Level %d  ·  %s" % [int(buddy_status.get("level", 1)), str(buddy_status.get("level_name", ""))])

	var body := UI.row(page, true, 16)

	var left := UI.card(body, 0.9)
	var stage := Control.new()
	stage.custom_minimum_size = Vector2(0, 170)
	stage.size_flags_vertical = SIZE_EXPAND_FILL
	stage.clip_contents = true
	left.add_child(stage)
	var b := Buddy.new()
	b.sprite_scale = 1.9
	b.set_status(buddy_status)
	stage.add_child(b)
	var center := func(): b.position = stage.size / 2.0
	stage.resized.connect(center)
	center.call()
	# the card panel swallows touches before Node2D._unhandled_input sees them → forward taps on the stage
	stage.gui_input.connect(func(e: InputEvent):
		if (e is InputEventScreenTouch and e.is_pressed()) or (e is InputEventMouseButton and e.is_pressed()):
			b.poke())
	var road := RoadBar.new()
	road.set_status(buddy_status)
	road.size_flags_horizontal = SIZE_SHRINK_CENTER
	left.add_child(road)
	left.add_child(UI.label("%d steps on the road  ·  %d-day streak" % [int(buddy_status.get("steps", 0)), int(buddy_status.get("streak", 0))], "Caption", HORIZONTAL_ALIGNMENT_CENTER))

	var right := UI.card(body, 1.1)
	var loading := UI.label("Loading…", "Caption")
	right.add_child(loading)
	var data = await Api.get_json("/api/v1/students/%d/stats" % int(_student.get("id", 0)))
	loading.queue_free()
	if not (data is Dictionary):
		right.add_child(UI.label("Stats unavailable", "Caption"))
		return
	UI.stat(right, "Days completed", str(int(data.get("days_completed", 0))))
	UI.stat(right, "Best streak", "%d days" % int(data.get("best_streak", 0)))
	UI.stat(right, "Total practice", "%d min" % int(float(data.get("total_practice_seconds", 0)) / 60.0))
	UI.stat(right, "Sessions", str(int(data.get("sessions", 0))))
	UI.stat(right, "Notes played", str(int(data.get("total_notes", 0))))
	UI.spacer(right, 4, false)
	right.add_child(UI.label("Last 30 days", "Caption"))
	var strip := HBoxContainer.new()
	strip.add_theme_constant_override("separation", 3)
	right.add_child(strip)
	var by_day := {}
	for d in data.get("last_30_days", []):
		by_day[d["day"]] = d
	var today := Time.get_unix_time_from_system()
	for i in range(29, -1, -1):
		var day := Time.get_date_string_from_unix_time(int(today - i * 86400))
		var cell := ColorRect.new()
		cell.custom_minimum_size = Vector2(8, 22)
		cell.size_flags_horizontal = SIZE_EXPAND_FILL
		var rec: Dictionary = by_day.get(day, {})
		cell.color = App.SUCCESS if rec.get("completed", 0) else (App.ACCENT_MUTED if rec.get("seconds", 0) > 0 else App.BG_SURFACE)
		strip.add_child(cell)
