## Live notation: a treble staff with a vector clef, showing the notes currently held on the piano
## (ledger lines, sharps, note names). Distraction-free replacement for the buddy on the Session screen.
class_name StaffView
extends Control

const LINE_GAP := 14.0            # px between staff lines → one diatonic step = 7 px
const STEP := LINE_GAP / 2.0
const CLEF_W := 70.0

var _notes: Array = []            # sorted MIDI numbers currently held
var _flash := {}                  # note -> seconds since pressed (for a soft pop-in)

const DIATONIC := [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]
const SHARP := [false, true, false, true, false, false, true, false, true, false, true, false]


func _ready() -> void:
	custom_minimum_size = Vector2(260, 150)
	Midi.note_on.connect(_on_note_on)
	Midi.note_off.connect(func(_n): _sync())
	Midi.connection_changed.connect(func(_c): _sync())
	_sync()


func _on_note_on(n: int, _v: int) -> void:
	_flash[n] = 0.0
	_sync()


func _sync() -> void:
	_notes = Midi.active_notes.keys()
	_notes.sort()
	queue_redraw()


func _process(delta: float) -> void:
	if _flash.is_empty():
		return
	for n in _flash.keys():
		_flash[n] = float(_flash[n]) + delta
		if _flash[n] > 0.3:
			_flash.erase(n)
	queue_redraw()


## y of the top line is chosen so that middle C (ledger below) and the high A sit inside the control.
func _draw() -> void:
	var w := size.x
	var h := size.y
	var top := h / 2.0 - 2.0 * LINE_GAP - 10.0           # 5 lines centred, biased up to leave room for low ledgers
	var left := 16.0
	var right := w - 16.0
	# staff lines (top = F5, bottom = E4)
	for i in 5:
		var y := top + i * LINE_GAP
		draw_line(Vector2(left, y), Vector2(right, y), Color("#334155"), 1.5, true)
	# middle C guide (dashed)
	var mc_y := top + 4 * LINE_GAP + LINE_GAP            # one ledger below E4
	var x := left + CLEF_W
	while x < right - 8:
		draw_line(Vector2(x, mc_y), Vector2(x + 5, mc_y), Color("#1f2937"), 1.0)
		x += 10
	_draw_treble_clef(Vector2(left + 26, top + 3 * LINE_GAP), 1.0, App.TEXT_PRIMARY)    # G line = 2nd from bottom

	if _notes.is_empty():
		var f := get_theme_default_font()
		draw_string(f, Vector2(left + CLEF_W + 20, top + 2 * LINE_GAP + 6), "Play something…", HORIZONTAL_ALIGNMENT_LEFT, -1, 16, App.TEXT_MUTED)
		return

	# lay notes out left→right in pitch order, stacking seconds (adjacent steps) to the right like a chord
	var base_x := left + CLEF_W + 30.0
	var col_w := 34.0
	var prev_step := -99
	var col := 0
	for n in _notes:
		var octave := int(n / 12.0) - 1
		var pc := int(n) % 12
		var step := (octave - 4) * 7 + DIATONIC[pc]             # 0 = middle C
		var y := mc_y - step * STEP
		if step - prev_step == 1 and col > 0:
			pass                                                   # a second: keep the same column, offset right
		else:
			col += 1
		var nx := base_x + (col - 1) * col_w + (14.0 if (step - prev_step == 1) else 0.0)
		prev_step = step
		var pop := 1.0 + 0.35 * maxf(0.0, 1.0 - float(_flash.get(n, 1.0)) / 0.3)
		# ledger lines
		var ledger_col := App.TEXT_SECONDARY
		if y > top + 4 * LINE_GAP + 1:                          # below the staff
			var ly := top + 5 * LINE_GAP
			while ly <= y + 1:
				draw_line(Vector2(nx - 9, ly), Vector2(nx + 23, ly), ledger_col, 1.5, true)
				ly += LINE_GAP
		elif y < top - 1:                                        # above the staff
			var ly := top - LINE_GAP
			while ly >= y - 1:
				draw_line(Vector2(nx - 9, ly), Vector2(nx + 23, ly), ledger_col, 1.5, true)
				ly -= LINE_GAP
		# accidental
		if SHARP[pc]:
			_draw_sharp(Vector2(nx - 12, y), App.TEXT_PRIMARY)
		# note head (slightly tilted oval)
		draw_set_transform(Vector2(nx + 7, y), -0.35, Vector2(1.0, 0.72) * pop)
		draw_circle(Vector2.ZERO, 8.0, App.ACCENT)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
		# name below the staff
		var f := get_theme_default_font()
		draw_string(f, Vector2(nx - 4, h - 6), Midi.note_name(int(n), false), HORIZONTAL_ALIGNMENT_LEFT, -1, 13, App.TEXT_SECONDARY)


func _draw_sharp(p: Vector2, col: Color) -> void:
	for dx in [-2.5, 2.5]:
		draw_line(p + Vector2(dx, -7), p + Vector2(dx + 1.0, 7), col, 1.6, true)
	for dy in [-2.5, 2.5]:
		draw_line(p + Vector2(-6, dy + 1.0), p + Vector2(6, dy - 1.5), col, 2.2, true)


## Vector treble clef from the v1 control points, smoothed with Catmull-Rom. `g` = point on the G line.
func _draw_treble_clef(g: Vector2, s: float, col: Color) -> void:
	var w := 2.6 * s
	# stem
	draw_line(g + Vector2(0, -36 * s), g + Vector2(0, 22 * s), col, w, true)
	var top_loop := [Vector2(0, -36), Vector2(6, -48), Vector2(2, -62), Vector2(-6, -50), Vector2(0, -36)]
	var right_loop := [Vector2(0, -36), Vector2(13, -24), Vector2(13, -10), Vector2(0, -4)]
	var belly := [Vector2(0, -4), Vector2(-13, 6), Vector2(-6, 16), Vector2(7, 10), Vector2(6, -5), Vector2(-3, 0)]
	var hook := [Vector2(0, 22), Vector2(-2, 32), Vector2(-7, 29)]
	for path in [top_loop, right_loop, belly, hook]:
		var pts := PackedVector2Array()
		for p in path:
			pts.append(g + p * s)
		draw_polyline(_smooth(pts), col, w, true)
	draw_circle(g + Vector2(-7, 29) * s, 3.0 * s, col)


static func _smooth(pts: PackedVector2Array, segments := 8) -> PackedVector2Array:
	var out := PackedVector2Array()
	if pts.size() < 3:
		return pts
	for i in pts.size() - 1:
		var p0 := pts[maxi(i - 1, 0)]
		var p1 := pts[i]
		var p2 := pts[i + 1]
		var p3 := pts[mini(i + 2, pts.size() - 1)]
		for k in segments:
			var t := float(k) / segments
			out.append(0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t))
	out.append(pts[pts.size() - 1])
	return out
