## 61-key piano strip (C2..C7) that lights up held notes. Pure _draw(), no textures.
class_name MiniPiano
extends Control

@export var first_note := 36
@export var last_note := 96
var highlight: Color = App.ACCENT
var teacher_highlight := Color("#818cf8")

var teacher_notes: Dictionary = {}       # note -> true (lesson playback)
const BLACK := [1, 3, 6, 8, 10]


func _ready() -> void:
	custom_minimum_size = Vector2(0, 70)
	Midi.note_on.connect(func(_n, _v): queue_redraw())
	Midi.note_off.connect(func(_n): queue_redraw())


func set_teacher(notes: Array) -> void:
	teacher_notes.clear()
	for n in notes:
		teacher_notes[int(n)] = true
	queue_redraw()


func _draw() -> void:
	var whites := []
	for n in range(first_note, last_note + 1):
		if not (n % 12 in BLACK):
			whites.append(n)
	var ww := size.x / whites.size()
	var h := size.y
	var x := 0.0
	var white_x := {}
	for n in whites:
		var col := Color("#e2e8f0")
		if Midi.active_notes.has(n):
			col = highlight
		elif teacher_notes.has(n):
			col = teacher_highlight
		draw_rect(Rect2(x + 1, 0, ww - 2, h), col)
		white_x[n] = x
		x += ww
	var bw := ww * 0.62
	var bh := h * 0.6
	for n in range(first_note, last_note + 1):
		if n % 12 in BLACK and white_x.has(n - 1):
			var bx: float = white_x[n - 1] + ww - bw / 2.0
			var col := Color("#111827")
			if Midi.active_notes.has(n):
				col = highlight.darkened(0.15)
			elif teacher_notes.has(n):
				col = teacher_highlight.darkened(0.15)
			draw_rect(Rect2(bx, 0, bw, bh), col)
