## Small layout toolkit so every screen is built the same way and nothing overflows the 800×480 panel.
##
##   var page := UI.page(self)                       # safe margins + VBox
##   UI.header(page, "Title", Router.back, [btn])    # back · title · right actions
##   var body := UI.row(page, true)                  # expands to fill the rest
##   var card := UI.card(body, 1.0)                  # stretch ratio
##   UI.button_row(card, [UI.button("Save", "PrimaryButton", cb), ...])   # wraps when too wide
class_name UI
extends RefCounted

const MARGIN := 20
const GAP := 8
const TOUCH := 48


static func page(root: Control, gap := 12) -> VBoxContainer:
	var m := MarginContainer.new()
	m.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	m.add_theme_constant_override("margin_left", MARGIN)
	m.add_theme_constant_override("margin_right", MARGIN)
	m.add_theme_constant_override("margin_top", 14)
	m.add_theme_constant_override("margin_bottom", 14)
	root.add_child(m)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", gap)
	m.add_child(v)
	return v


## Header bar: optional back button, title (ellipsised), right-aligned actions. Fixed 56 px tall.
static func header(parent: Control, title: String, on_back: Callable = Callable(), actions: Array = [],
		subtitle := "") -> HBoxContainer:
	var h := HBoxContainer.new()
	h.custom_minimum_size.y = 56
	h.add_theme_constant_override("separation", GAP)
	parent.add_child(h)
	if on_back.is_valid():
		var b := button("‹  Back", "GhostButton", on_back)
		b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		h.add_child(b)
	var titles := VBoxContainer.new()
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	titles.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	titles.add_theme_constant_override("separation", 0)
	h.add_child(titles)
	titles.add_child(label(title, "Title", HORIZONTAL_ALIGNMENT_LEFT, false, true))
	if subtitle != "":
		titles.add_child(label(subtitle, "Caption", HORIZONTAL_ALIGNMENT_LEFT, false, true))
	for a in actions:
		if a is Control:
			a.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			h.add_child(a)
	return h


## Labels size to their text. `wrap` → multi-line; `shrink` → may be narrower than its text (ellipsis),
## only safe when the label expands to fill (e.g. the header title).
static func label(text: String, variation := "Body", align := HORIZONTAL_ALIGNMENT_LEFT, wrap := false, shrink := false) -> Label:
	var l := Label.new()
	l.text = text
	l.theme_type_variation = variation
	l.horizontal_alignment = align
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if shrink:
		l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	return l


static func button(text: String, variation := "Button", on_pressed: Callable = Callable()) -> Button:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = variation
	b.custom_minimum_size.y = TOUCH
	b.focus_mode = Control.FOCUS_NONE
	if on_pressed.is_valid():
		b.pressed.connect(on_pressed)
	_press_feedback(b)
	return b


## Buttons laid out left→right that wrap onto a new line instead of overflowing.
static func button_row(parent: Control, buttons: Array, align := FlowContainer.ALIGNMENT_BEGIN) -> HFlowContainer:
	var f := HFlowContainer.new()
	f.alignment = align
	parent.add_child(f)
	for b in buttons:
		if b is Control:
			f.add_child(b)
	return f


## Vertical stack of full-width buttons — the safe choice inside dialogs/cards.
static func button_stack(parent: Control, buttons: Array) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", GAP)
	parent.add_child(v)
	for b in buttons:
		if b is Control:
			b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			v.add_child(b)
	return v


static func row(parent: Control, expand := false, gap := 16) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", gap)
	if expand:
		h.size_flags_vertical = Control.SIZE_EXPAND_FILL
	parent.add_child(h)
	return h


static func column(parent: Control, expand := false, gap := GAP) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", gap)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if expand:
		v.size_flags_vertical = Control.SIZE_EXPAND_FILL
	parent.add_child(v)
	return v


## A card that fills its slot; returns the inner VBox to add content to.
static func card(parent: Control, stretch := 1.0, variation := "Card", min_width := 0.0) -> VBoxContainer:
	var p := PanelContainer.new()
	p.theme_type_variation = variation
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	p.size_flags_vertical = Control.SIZE_EXPAND_FILL
	p.size_flags_stretch_ratio = stretch
	if min_width > 0:
		p.custom_minimum_size.x = min_width
	parent.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", GAP)
	p.add_child(v)
	return v


static func chip(text: String, variation := "Chip", color: Color = Color.TRANSPARENT) -> PanelContainer:
	var p := PanelContainer.new()
	p.theme_type_variation = variation
	p.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	var l := label(text, "Caption")
	if color != Color.TRANSPARENT:
		l.add_theme_color_override("font_color", color)
	p.add_child(l)
	return p


## key ··· value line used for stats.
static func stat(parent: Control, key: String, value: String, value_variation := "Heading") -> HBoxContainer:
	var h := HBoxContainer.new()
	parent.add_child(h)
	var k := label(key, "Caption")
	k.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	k.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	h.add_child(k)
	var v := label(value, value_variation, HORIZONTAL_ALIGNMENT_RIGHT)
	h.add_child(v)
	return h


static func spacer(parent: Control, min_px := 0.0, expand := true) -> Control:
	var c := Control.new()
	c.custom_minimum_size.y = min_px
	if expand:
		c.size_flags_vertical = Control.SIZE_EXPAND_FILL
	parent.add_child(c)
	return c


## Vertical scroll with touch drag; returns the inner VBox.
static func vscroll(parent: Control) -> VBoxContainer:
	var s := ScrollContainer.new()
	s.size_flags_vertical = Control.SIZE_EXPAND_FILL
	s.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	parent.add_child(s)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_theme_constant_override("separation", GAP)
	s.add_child(v)
	return v


## Dimmed full-screen overlay with a centred card (max 460 px wide). Returns the card's VBox.
static func overlay(root: Control, width := 440.0) -> Dictionary:
	var dim := PanelContainer.new()
	dim.theme_type_variation = "Overlay"
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	root.add_child(dim)
	var center := CenterContainer.new()
	dim.add_child(center)
	var card_p := PanelContainer.new()
	card_p.theme_type_variation = "Card"
	card_p.custom_minimum_size.x = width
	center.add_child(card_p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	card_p.add_child(v)
	# entrance
	dim.modulate.a = 0.0
	card_p.pivot_offset = Vector2(width / 2.0, 80)
	card_p.scale = Vector2(0.92, 0.92)
	var tw: Tween = dim.create_tween().set_parallel(true).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_property(dim, "modulate:a", 1.0, 0.22)
	tw.tween_property(card_p, "scale", Vector2.ONE, 0.32)
	return {"root": dim, "box": v}


## Staggered fade/scale-in for a list of controls (scale only — containers own position, not scale).
static func stagger_in(items: Array, step := 0.05) -> void:
	var i := 0
	for item in items:
		if not (item is Control):
			continue
		var c: Control = item
		c.modulate.a = 0.0
		c.scale = Vector2(0.96, 0.96)
		var tw: Tween = c.create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		tw.tween_property(c, "modulate:a", 1.0, 0.28).set_delay(step * i)
		tw.tween_property(c, "scale", Vector2.ONE, 0.32).set_delay(step * i)
		c.resized.connect(func(): c.pivot_offset = c.size / 2.0, CONNECT_ONE_SHOT)
		i += 1


static func _press_feedback(b: Button) -> void:
	b.button_down.connect(func():
		b.pivot_offset = b.size / 2.0
		b.create_tween().tween_property(b, "scale", Vector2(0.96, 0.96), 0.06))
	b.button_up.connect(func():
		b.create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT).tween_property(b, "scale", Vector2.ONE, 0.18))
