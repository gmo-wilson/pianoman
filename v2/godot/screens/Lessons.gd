## Lesson list. With {"pick": true} the chosen lesson is loaded into the running Session.
extends Control

var _pick := false
var _list: VBoxContainer


func setup(params: Dictionary) -> void:
	_pick = bool(params.get("pick", false))


func _ready() -> void:
	var page := UI.page(self)
	UI.header(page, "Lessons", Router.back, [], "Pick one to practise along with" if _pick else "Listen on the piano")
	_list = UI.vscroll(page)
	_load()


func _load() -> void:
	var lessons = await Api.get_json("/api/v1/lessons")
	if not (lessons is Array):
		_list.add_child(UI.label("Could not load lessons", "Caption"))
		return
	if lessons.is_empty():
		_list.add_child(UI.label("No lessons yet — add one from the admin", "Caption"))
		return
	var rows := []
	for lesson in lessons:
		var card := UI.card(_list, 1.0, "Card")
		card.get_parent().size_flags_vertical = SIZE_SHRINK_BEGIN
		var h := UI.row(card, false, 16)
		var info := UI.column(h)
		info.add_child(UI.label(str(lesson["name"]), "Heading"))
		var chords := PackedStringArray()
		for c in lesson.get("chords", []):
			chords.append(str(c))
		info.add_child(UI.label("%s   ·   %d notes" % [", ".join(chords) if chords.size() else "no chords", int(lesson.get("events_count", 0)) / 2], "Caption"))
		var btn := UI.button("Practise this" if _pick else "▶  Listen", "PrimaryButton" if _pick else "Button", func():
			if _pick:
				App.lesson = lesson
				Router.replace("Session", {"lesson": lesson}, "slide_right")
			else:
				Api.post_json("/api/v1/player/load", {"lesson_id": lesson["id"], "autoplay": true}))
		btn.size_flags_vertical = SIZE_SHRINK_CENTER
		btn.custom_minimum_size.x = 150
		h.add_child(btn)
		rows.append(card.get_parent())
	UI.stagger_in(rows)
