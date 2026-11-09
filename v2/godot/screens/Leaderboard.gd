## Runner leaderboard: best score per student. Tabs: All time · This week · Today.
extends Control

var _student: Dictionary = {}
var _period := "all"
var _list: VBoxContainer
var _tabs: Array[Button] = []


func setup(params: Dictionary) -> void:
	_student = params.get("student", {})


func _ready() -> void:
	var page := UI.page(self)
	for p in [["all", "All time"], ["week", "This week"], ["today", "Today"]]:
		var b := UI.button(p[1], "SmallButton", func():
			_period = p[0]
			_load())
		b.set_meta("period", p[0])
		b.custom_minimum_size.y = 40
		_tabs.append(b)
	UI.header(page, "Runner scores", Router.back, _tabs, "Best run per student")
	_list = UI.vscroll(page)
	_load()


func _load() -> void:
	for b in _tabs:
		b.theme_type_variation = "SmallPrimaryButton" if b.get_meta("period") == _period else "SmallButton"
	for c in _list.get_children():
		c.queue_free()
	var data = await Api.get_json("/api/v1/game/leaderboard?period=%s&limit=20" % _period)
	if not (data is Dictionary):
		_list.add_child(UI.label("Leaderboard unavailable", "Caption"))
		return
	var entries: Array = data.get("entries", [])
	if entries.is_empty():
		_list.add_child(UI.label("No runs yet — finish a practice to unlock the game.", "Caption"))
		return
	var rows := []
	var i := 0
	for e in entries:
		i += 1
		var mine := int(e.get("student_id", -1)) == int(_student.get("id", -2))
		var card := UI.card(_list, 1.0, "Highlight" if mine else "Card")
		var p: PanelContainer = card.get_parent()
		p.size_flags_vertical = SIZE_SHRINK_BEGIN
		var h := UI.row(card, false, 14)
		var rank := UI.label("#%d" % i, "Heading")
		rank.custom_minimum_size.x = 52
		if i <= 3:
			rank.add_theme_color_override("font_color", [App.WARNING, App.TEXT_SECONDARY, Color("#b45309")][i - 1])
		h.add_child(rank)
		var name := UI.label(str(e.get("name", "")), "Heading")
		name.size_flags_horizontal = SIZE_EXPAND_FILL
		h.add_child(name)
		h.add_child(UI.label("%d run%s" % [int(e.get("runs", 0)), "" if int(e.get("runs", 0)) == 1 else "s"], "Caption"))
		var score := UI.label("%d" % int(e.get("best", 0)), "Heading", HORIZONTAL_ALIGNMENT_RIGHT)
		score.custom_minimum_size.x = 90
		score.add_theme_color_override("font_color", App.WARNING)
		h.add_child(score)
		rows.append(p)
	UI.stagger_in(rows, 0.04)
