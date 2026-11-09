## Kiosk theme, built in code. Tokens are tuned for an 800×480 touchscreen viewed from ~60 cm:
##   type scale  14 / 18 / 22 / 28  (+ 64 for the timer)      spacing grid 8 px
##   touch target ≥ 48 px            radius 16 (cards) / pill (buttons)
## Fonts: drop any .ttf/.otf into res://ui/fonts/ — the first upright (non-italic) file is used.
## Variable fonts (…-VariableFont_wght.ttf) get weight 600 for UI text; a "Bold" file, if present, is used for titles.
extends RefCounted

const FONTS_DIR := "res://ui/fonts"
const UI_WEIGHT := 600.0
const TITLE_WEIGHT := 800.0

const SP := 8                       # spacing unit
const RADIUS := 16
const TOUCH := 48

const FS_CAPTION := 14
const FS_BODY := 18
const FS_HEADING := 22
const FS_TITLE := 28
const FS_DISPLAY := 40
const FS_TIMER := 64


static func build() -> Theme:
	var t := Theme.new()
	var fonts := _find_fonts()
	var body_font: Font = _make_font(fonts, UI_WEIGHT)
	var title_font: Font = _make_font(fonts, TITLE_WEIGHT)
	if body_font:
		t.default_font = body_font
	t.default_font_size = FS_BODY

	# ------------------------------------------------------------------ buttons
	# variation → [bg, bg_hover, bg_pressed, fg]
	var buttons := {
		"Button":        [App.BG_SURFACE, App.BG_CARD_HOVER, App.ACCENT_MUTED, App.TEXT_PRIMARY],
		"PrimaryButton": [App.ACCENT, App.ACCENT_HOVER, App.ACCENT_HOVER, App.TEXT_DARK],
		"DangerButton":  [Color("#2a1d24"), Color("#3a2530"), App.DANGER, App.DANGER],
		"GhostButton":   [Color(0, 0, 0, 0), App.BG_CARD, App.BG_SURFACE, App.TEXT_SECONDARY],
		"SuccessButton": [App.SUCCESS, App.SUCCESS.lightened(0.1), App.SUCCESS.darkened(0.1), App.TEXT_DARK],
	}
	for variant in buttons.keys():
		var c: Array = buttons[variant]
		if variant != "Button":
			t.set_type_variation(variant, "Button")
		var normal := _pill(c[0])
		if variant == "GhostButton":
			normal.set_border_width_all(2)
			normal.border_color = App.BG_SURFACE
		t.set_stylebox("normal", variant, normal)
		t.set_stylebox("hover", variant, _pill(c[1]))
		t.set_stylebox("pressed", variant, _pill(c[2]))
		t.set_stylebox("focus", variant, StyleBoxEmpty.new())
		t.set_stylebox("disabled", variant, _pill(App.BG_CARD))
		t.set_color("font_color", variant, c[3])
		t.set_color("font_hover_color", variant, c[3])
		t.set_color("font_pressed_color", variant, App.TEXT_PRIMARY if variant == "DangerButton" else c[3])
		t.set_color("font_disabled_color", variant, App.TEXT_MUTED)
		t.set_font_size("font_size", variant, FS_BODY)
		t.set_constant("h_separation", variant, SP)
	# compact variant for dense rows (chips, tabs)
	t.set_type_variation("SmallButton", "Button")
	t.set_stylebox("normal", "SmallButton", _pill(App.BG_SURFACE, 14, 6))
	t.set_stylebox("hover", "SmallButton", _pill(App.BG_CARD_HOVER, 14, 6))
	t.set_stylebox("pressed", "SmallButton", _pill(App.ACCENT_MUTED, 14, 6))
	t.set_stylebox("focus", "SmallButton", StyleBoxEmpty.new())
	t.set_stylebox("disabled", "SmallButton", _pill(App.BG_CARD, 14, 6))
	t.set_font_size("font_size", "SmallButton", FS_CAPTION + 1)
	t.set_color("font_color", "SmallButton", App.TEXT_PRIMARY)
	t.set_color("font_disabled_color", "SmallButton", App.TEXT_MUTED)
	t.set_type_variation("SmallPrimaryButton", "SmallButton")
	t.set_stylebox("normal", "SmallPrimaryButton", _pill(App.ACCENT, 14, 6))
	t.set_stylebox("hover", "SmallPrimaryButton", _pill(App.ACCENT_HOVER, 14, 6))
	t.set_stylebox("pressed", "SmallPrimaryButton", _pill(App.ACCENT_HOVER, 14, 6))
	t.set_color("font_color", "SmallPrimaryButton", App.TEXT_DARK)
	t.set_color("font_hover_color", "SmallPrimaryButton", App.TEXT_DARK)
	t.set_color("font_pressed_color", "SmallPrimaryButton", App.TEXT_DARK)

	# ------------------------------------------------------------------ surfaces
	t.set_stylebox("panel", "PanelContainer", _card(App.BG_CARD))
	for v in [["Card", App.BG_CARD, RADIUS, 16], ["Surface", App.BG_SURFACE, 12, 12], ["Chip", App.BG_CARD, 999, 6],
			["AccentChip", App.ACCENT_MUTED, 999, 6], ["Highlight", App.ACCENT_MUTED, RADIUS, 16],
			["Overlay", Color(0.06, 0.08, 0.11, 0.82), 0, 0]]:
		t.set_type_variation(v[0], "PanelContainer")
		var sb := _card(v[1], v[2], v[3])
		if v[0] == "Chip" or v[0] == "AccentChip":
			sb.content_margin_left = 14
			sb.content_margin_right = 14
		t.set_stylebox("panel", v[0], sb)

	# ------------------------------------------------------------------ text
	t.set_color("font_color", "Label", App.TEXT_PRIMARY)
	t.set_font_size("font_size", "Label", FS_BODY)
	for v in [["Caption", FS_CAPTION, App.TEXT_SECONDARY], ["Body", FS_BODY, App.TEXT_PRIMARY],
			["Heading", FS_HEADING, App.TEXT_PRIMARY], ["Title", FS_TITLE, App.TEXT_PRIMARY],
			["Display", FS_DISPLAY, App.TEXT_PRIMARY], ["TimerLabel", FS_TIMER, App.TEXT_PRIMARY],
			["Muted", FS_BODY, App.TEXT_SECONDARY]]:
		t.set_type_variation(v[0], "Label")
		t.set_font_size("font_size", v[0], v[1])
		t.set_color("font_color", v[0], v[2])
		if title_font and v[0] in ["Heading", "Title", "Display", "TimerLabel"]:
			t.set_font("font", v[0], title_font)

	# ------------------------------------------------------------------ misc controls
	var grab := StyleBoxFlat.new()
	grab.bg_color = Color(1, 1, 1, 0.14)
	grab.set_corner_radius_all(4)
	for bar in ["VScrollBar", "HScrollBar"]:
		t.set_stylebox("grabber", bar, grab)
		t.set_stylebox("grabber_highlight", bar, grab)
		t.set_stylebox("grabber_pressed", bar, grab)
		t.set_stylebox("scroll", bar, StyleBoxEmpty.new())
	var track := StyleBoxFlat.new()
	track.bg_color = App.BG_SURFACE
	track.set_corner_radius_all(6)
	track.content_margin_top = 6
	track.content_margin_bottom = 6
	t.set_stylebox("slider", "HSlider", track)
	var fill := track.duplicate()
	fill.bg_color = App.ACCENT
	t.set_stylebox("grabber_area", "HSlider", fill)
	t.set_stylebox("grabber_area_highlight", "HSlider", fill)
	t.set_constant("separation", "HBoxContainer", SP)
	t.set_constant("separation", "VBoxContainer", SP)
	t.set_constant("h_separation", "HFlowContainer", SP)
	t.set_constant("v_separation", "HFlowContainer", SP)
	return t


static func _pill(col: Color, pad_h := 22, pad_v := 12) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = col
	s.set_corner_radius_all(999)
	s.content_margin_left = pad_h
	s.content_margin_right = pad_h
	s.content_margin_top = pad_v
	s.content_margin_bottom = pad_v
	return s


static func _card(col: Color, radius := RADIUS, pad := 16) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = col
	s.set_corner_radius_all(radius)
	s.set_content_margin_all(pad)
	return s


# ------------------------------------------------------------------ font discovery
static func _find_fonts() -> PackedStringArray:
	var out := PackedStringArray()
	var dir := DirAccess.open(FONTS_DIR)
	if dir == null:
		return out
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var lower := name.to_lower()
		if not dir.current_is_dir() and (lower.ends_with(".ttf") or lower.ends_with(".otf")):
			out.append(FONTS_DIR + "/" + name)
		name = dir.get_next()
	dir.list_dir_end()
	return out


## Picks the best file for the requested weight and returns a Font (FontVariation for variable fonts).
static func _make_font(paths: PackedStringArray, weight: float) -> Font:
	if paths.is_empty():
		return null
	var upright := PackedStringArray()
	for p in paths:
		if not p.to_lower().contains("italic"):
			upright.append(p)
	var pool := upright if not upright.is_empty() else paths
	var chosen := pool[0]
	for p in pool:
		var l := p.to_lower()
		if l.contains("variablefont"):
			chosen = p
			break
	if not chosen.to_lower().contains("variablefont"):
		# static files: prefer Bold for heavy weights, SemiBold/Medium/Regular otherwise
		var want := ["bold"] if weight >= 700 else ["semibold", "medium", "regular"]
		for w in want:
			for p in pool:
				if p.to_lower().contains(w):
					chosen = p
					break
	var base: Font = load(chosen)
	if base == null:
		return null
	var fv := FontVariation.new()
	fv.base_font = base
	if chosen.to_lower().contains("variablefont"):
		var tag := TextServerManager.get_primary_interface().name_to_tag("wght")
		fv.variation_opentype = {tag: weight}
	elif weight >= 700 and not chosen.to_lower().contains("bold"):
		fv.variation_embolden = 0.6
	return fv
