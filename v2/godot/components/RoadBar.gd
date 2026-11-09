## The "road": dots for the steps inside the current milestone, with the next evolution at the end.
##   ● ● ○ ▶ Lv 3     set_status(buddy_status) · animate_step() pulses the dot that was just earned
class_name RoadBar
extends Control

var _steps_per_level := 3
var _filled := 0
var _at_top := false
var _pulse := -1
var _pulse_t := 0.0
var _label: Label

const DOT_R := 7.0
const GAP := 26.0


func _ready() -> void:
	custom_minimum_size = Vector2(120, 24)
	_label = Label.new()
	_label.theme_type_variation = "Caption"
	_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_label.set_anchors_and_offsets_preset(PRESET_RIGHT_WIDE)
	add_child(_label)
	_relayout()


func set_status(st: Dictionary) -> void:
	_steps_per_level = maxi(1, int(st.get("steps_per_level", 3)))
	_filled = int(st.get("steps_in_level", 0))
	_at_top = bool(st.get("at_top", false))
	if _at_top:
		_filled = _steps_per_level
	_relayout()
	queue_redraw()


func animate_step(index: int) -> void:
	_pulse = index
	_pulse_t = 0.0


func _relayout() -> void:
	var road_w := _steps_per_level * GAP + 20.0
	custom_minimum_size.x = road_w + 110
	if _label:
		_label.offset_left = road_w
		var to_next := _steps_per_level - _filled
		_label.text = "Top of the road" if _at_top else ("Next evolution!" if to_next == 0 else "%d step%s to evolve" % [to_next, "" if to_next == 1 else "s"])


func _process(delta: float) -> void:
	if _pulse >= 0:
		_pulse_t += delta
		if _pulse_t > 0.8:
			_pulse = -1
		queue_redraw()


func _draw() -> void:
	var cy := size.y / 2.0
	var x0 := DOT_R + 2.0
	# track
	draw_line(Vector2(x0, cy), Vector2(x0 + (_steps_per_level - 1) * GAP + 18.0, cy), App.BG_SURFACE, 4.0)
	for i in _steps_per_level:
		var c := Vector2(x0 + i * GAP, cy)
		var done := i < _filled
		var r := DOT_R
		if i == _pulse:
			r += 5.0 * sin(minf(1.0, _pulse_t / 0.8) * PI)
		draw_circle(c, r, App.SUCCESS if done else App.BG_SURFACE)
		if not done:
			draw_arc(c, r, 0, TAU, 24, App.TEXT_MUTED, 2.0, true)
	# milestone flag
	var fx := x0 + (_steps_per_level - 1) * GAP + 18.0
	var col := App.WARNING if _filled >= _steps_per_level else App.TEXT_MUTED
	draw_colored_polygon(PackedVector2Array([Vector2(fx, cy - 9), Vector2(fx + 12, cy), Vector2(fx, cy + 9)]), col)
