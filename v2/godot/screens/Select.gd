## Home: one card per student with a live buddy, plus Guest. Horizontal swipe when there are many.
extends Control

const CARD_W := 232.0

var _cards_box: HBoxContainer
var _status_lbl: Label
var _last_sig := ""           # skip rebuilding (and re-animating) when nothing changed


func _ready() -> void:
	var page := UI.page(self)
	var status_chip := UI.chip("", "Chip")
	_status_lbl = status_chip.get_child(0)
	UI.header(page, "Who's practicing?", Callable(), [
		status_chip,
		UI.button("Scores", "GhostButton", func(): Router.go("Leaderboard", {}, "slide_left")),
		UI.button("Lessons", "GhostButton", func(): Router.go("Lessons", {}, "slide_left")),
	])

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	page.add_child(scroll)
	_cards_box = HBoxContainer.new()
	_cards_box.add_theme_constant_override("separation", 16)
	_cards_box.size_flags_vertical = SIZE_EXPAND_FILL
	scroll.add_child(_cards_box)

	App.students_loaded.connect(_rebuild)
	Midi.connection_changed.connect(func(_c): _update_status())
	Midi.note_on.connect(func(_n, _v): _update_status())
	BuddyLib.updated.connect(_rebuild)
	_rebuild()
	_update_status()


func _update_status() -> void:
	var dev := Midi.device_label()
	var piano := ("●  " + (dev if dev != "" and dev.length() <= 24 else "Piano connected")) if Midi.connected else "○  No piano found"
	_status_lbl.text = piano + ("" if App.online else "   ·   offline")
	_status_lbl.add_theme_color_override("font_color", App.SUCCESS if Midi.connected else App.WARNING)


func _rebuild(force := false) -> void:
	var sig := JSON.stringify([App.students, App.buddies, BuddyLib.manifest.get("manifest_etag", "")])
	if sig == _last_sig and not force:
		return
	_last_sig = sig
	for c in _cards_box.get_children():
		c.queue_free()
	var cards := []
	for s in App.students:
		cards.append(_add_card(s, App.buddies.get(int(s["id"]), {})))
	cards.append(_add_card({}, {}))
	UI.stagger_in(cards, 0.06)


func _add_card(student: Dictionary, buddy: Dictionary) -> Control:
	var is_guest := student.is_empty()
	var p := PanelContainer.new()
	p.theme_type_variation = "Card"
	p.custom_minimum_size = Vector2(CARD_W, 0)
	p.size_flags_vertical = SIZE_EXPAND_FILL
	_cards_box.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	p.add_child(v)

	# name + level chip
	var top := HBoxContainer.new()
	v.add_child(top)
	var name_lbl := UI.label("Guest" if is_guest else str(student["name"]), "Heading")
	name_lbl.size_flags_horizontal = SIZE_EXPAND_FILL
	top.add_child(name_lbl)
	if not is_guest:
		top.add_child(UI.chip("Lv %d" % int(buddy.get("level", 1)), "AccentChip", App.ACCENT))

	# buddy stage
	var stage := Control.new()
	stage.custom_minimum_size = Vector2(0, 130)
	stage.size_flags_vertical = SIZE_EXPAND_FILL
	stage.clip_contents = true
	v.add_child(stage)
	if not is_guest:
		var b := Buddy.new()
		b.sprite_scale = 1.2
		b.set_status(buddy)
		stage.add_child(b)
		var center := func(): b.position = stage.size / 2.0
		stage.resized.connect(center)
		center.call()
		v.add_child(UI.label(str(buddy.get("level_name", "")), "Caption", HORIZONTAL_ALIGNMENT_CENTER))
		var road := RoadBar.new()
		road.set_status(buddy)
		road.size_flags_horizontal = SIZE_SHRINK_CENTER
		v.add_child(road)
		# today's progress
		var goal := App.goal_seconds()
		var done := float(buddy.get("time_practiced_today", 0.0))
		var completed := bool(buddy.get("today_completed", false))
		v.add_child(_progress_bar(minf(done, goal) / goal, App.SUCCESS if completed else App.ACCENT))
		var today := UI.label("Goal done today  ✔" if completed else "%s of %d min today" % [App.fmt_time(done), int(App.settings.get("goal_minutes", 15))], "Caption", HORIZONTAL_ALIGNMENT_CENTER)
		if completed:
			today.add_theme_color_override("font_color", App.SUCCESS)
		v.add_child(today)
	else:
		v.add_child(UI.label("Free play — nothing is saved", "Caption", HORIZONTAL_ALIGNMENT_CENTER, true))
		UI.spacer(v)

	# actions
	var practice := UI.button("Practice", "PrimaryButton" if not is_guest else "Button", func():
		App.start_session(student)
		Router.go("Session", {}, "zoom"))
	practice.size_flags_horizontal = SIZE_EXPAND_FILL
	v.add_child(practice)
	if not is_guest:
		var details := UI.button("Details", "GhostButton", func(): Router.go("BuddyDetail", {"student": student}, "slide_left"))
		details.size_flags_horizontal = SIZE_EXPAND_FILL
		v.add_child(details)
	return p


static func _progress_bar(ratio: float, color: Color) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.custom_minimum_size.y = 8
	bar.show_percentage = false
	bar.max_value = 1.0
	bar.value = clampf(ratio, 0.0, 1.0)
	var bg := StyleBoxFlat.new()
	bg.bg_color = App.BG_SURFACE
	bg.set_corner_radius_all(4)
	var fg := StyleBoxFlat.new()
	fg.bg_color = color
	fg.set_corner_radius_all(4)
	bar.add_theme_stylebox_override("background", bg)
	bar.add_theme_stylebox_override("fill", fg)
	return bar
