## Circular progress ring with the time readout centred inside. Animates smoothly toward `progress`.
class_name TimerRing
extends Control

@export var thickness := 14.0
@export var progress := 0.0                       # 0..1
@export var active := false : set = _set_active
@export var complete := false : set = _set_complete

var _shown := 0.0
var _color: Color = App.ACCENT
var _time_lbl: Label
var _caption_lbl: Label


func _ready() -> void:
	custom_minimum_size = Vector2(200, 200)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	center.mouse_filter = MOUSE_FILTER_IGNORE
	add_child(center)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 0)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	center.add_child(v)
	_time_lbl = Label.new()
	_time_lbl.theme_type_variation = "TimerLabel"
	_time_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_time_lbl.text = "0:00"
	v.add_child(_time_lbl)
	_caption_lbl = Label.new()
	_caption_lbl.theme_type_variation = "Caption"
	_caption_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_caption_lbl.text = "paused"
	v.add_child(_caption_lbl)
	_set_active(active)


func set_time(seconds: float) -> void:
	_time_lbl.text = App.fmt_time(seconds)


func set_caption(text: String) -> void:
	_caption_lbl.text = text
	_caption_lbl.add_theme_color_override("font_color", _color)


func _process(delta: float) -> void:
	var target := clampf(progress, 0.0, 1.0)
	if absf(_shown - target) > 0.0005:
		_shown = lerpf(_shown, target, minf(1.0, delta * 8.0))
		queue_redraw()


func _draw() -> void:
	var c := size / 2.0
	var r := minf(size.x, size.y) / 2.0 - thickness
	draw_arc(c, r, 0, TAU, 96, App.BG_SURFACE, thickness, true)
	if _shown > 0.001:
		var a0 := -PI / 2.0
		var a1 := a0 + TAU * _shown
		draw_arc(c, r, a0, a1, 96, _color, thickness, true)
		draw_circle(c + Vector2(cos(a0), sin(a0)) * r, thickness / 2.0, _color)
		draw_circle(c + Vector2(cos(a1), sin(a1)) * r, thickness / 2.0, _color)


func _set_active(v: bool) -> void:
	active = v
	_color = App.SUCCESS if complete else (App.ACCENT if active else App.INACTIVE)
	queue_redraw()


func _set_complete(v: bool) -> void:
	complete = v
	_set_active(active)
