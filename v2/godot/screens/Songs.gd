## Jukebox: anyone can make the piano play a saved song. List on the left, transport at the bottom.
extends Control

var _list: VBoxContainer
var _now_lbl: Label
var _play_btn: Button
var _loop_btn: Button
var _slider: HSlider
var _loop := false
var _poll := 0.0
var _current_id := ""
var _rows: Dictionary = {}       # song id → PanelContainer (to highlight the playing one)


func _ready() -> void:
	var page := UI.page(self)
	UI.header(page, "Songs", _leave, [], "Tap a song and the piano plays it")
	_list = UI.vscroll(page)

	# ---- transport
	var bar := UI.card(page, 0.0, "Surface")
	bar.get_parent().size_flags_vertical = SIZE_SHRINK_END
	var row := UI.row(bar, false, 10)
	_now_lbl = UI.label("Nothing playing", "Body")
	_now_lbl.size_flags_horizontal = SIZE_EXPAND_FILL
	_now_lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(_now_lbl)
	_play_btn = UI.button("❚❚  Pause", "Button", _toggle_play)
	_play_btn.disabled = true
	row.add_child(_play_btn)
	_loop_btn = UI.button("Loop  off", "Button", _toggle_loop)
	row.add_child(_loop_btn)
	row.add_child(UI.button("■  Stop", "GhostButton", _stop))
	_slider = HSlider.new()
	_slider.custom_minimum_size.y = 32
	_slider.max_value = 1.0
	_slider.step = 0.001
	_slider.drag_ended.connect(func(_c): Api.post_json("/api/v1/player/seek", {"pct": _slider.value}))
	bar.add_child(_slider)
	_load()


func _load() -> void:
	var songs = await Api.get_json("/api/v1/songs")
	if not (songs is Array):
		_list.add_child(UI.label("Could not load songs", "Caption"))
		return
	if songs.is_empty():
		_list.add_child(UI.label("No songs yet — upload MIDI files in the admin (Songs page)", "Caption"))
		return
	var rows := []
	for song in songs:
		var card := UI.card(_list, 1.0, "Card")
		var p: PanelContainer = card.get_parent()
		p.size_flags_vertical = SIZE_SHRINK_BEGIN
		_rows[str(song["id"])] = p
		var h := UI.row(card, false, 16)
		var info := UI.column(h)
		info.add_child(UI.label(str(song["title"]), "Heading"))
		var mins := int(float(song.get("duration_seconds", 0)) / 60.0)
		var secs := int(float(song.get("duration_seconds", 0))) % 60
		info.add_child(UI.label("%s   ·   %d:%02d   ·   %d notes" % [str(song.get("composer", "") if song.get("composer") else "Unknown"), mins, secs, int(song.get("notes_count", 0))], "Caption"))
		var btn := UI.button("▶  Play", "PrimaryButton", func(): _play(song))
		btn.size_flags_vertical = SIZE_SHRINK_CENTER
		btn.custom_minimum_size.x = 120
		h.add_child(btn)
		rows.append(p)
	UI.stagger_in(rows)


func _play(song: Dictionary) -> void:
	_current_id = str(song["id"])
	_now_lbl.text = "♪  " + str(song["title"])
	_play_btn.disabled = false
	for id in _rows.keys():
		_rows[id].theme_type_variation = "Highlight" if id == _current_id else "Card"
	Api.post_json("/api/v1/player/load", {"song_id": song["id"], "autoplay": true, "loop": _loop})


func _toggle_play() -> void:
	var st = await Api.get_json("/api/v1/player/status")
	if st is Dictionary and st.get("playing", false):
		Api.post_json("/api/v1/player/pause")
	else:
		Api.post_json("/api/v1/player/play")


func _toggle_loop() -> void:
	_loop = not _loop
	_loop_btn.text = "Loop  %s" % ("on" if _loop else "off")
	_loop_btn.theme_type_variation = "PrimaryButton" if _loop else "Button"
	Api.post_json("/api/v1/player/loop", {"loop": _loop})


func _stop() -> void:
	Api.post_json("/api/v1/player/stop")
	_slider.set_value_no_signal(0.0)


func _leave() -> void:
	Api.post_json("/api/v1/player/stop")
	Router.back()


func _process(delta: float) -> void:
	_poll += delta
	if _poll < 0.4:
		return
	_poll = 0.0
	var st = await Api.get_json("/api/v1/player/status")
	if not (st is Dictionary):
		return
	_slider.set_value_no_signal(float(st.get("progress", 0)))
	if st.get("playing", false):
		_play_btn.text = "❚❚  Pause"
	elif st.get("finished", false):
		_play_btn.text = "▶  Play again"
	else:
		_play_btn.text = "▶  Resume"
	if st.get("label") != null and str(st.get("label", "")) != "" and _current_id == "":
		_now_lbl.text = "♪  " + str(st["label"])
		_play_btn.disabled = false
