## Downloads the sprite manifest + atlases from the backend into user://sprites and turns them into
## SpriteFrames at runtime. Each level has up to 7 animations uploaded separately; missing ones fall back
## along FALLBACKS. Levels without any art use the nearest lower level, else a procedural placeholder.
extends Node

const ANIMS := ["idle", "dance", "run", "jump"]
const FALLBACKS := {"dance": ["idle"], "run": ["dance", "idle"], "jump": ["run", "idle"]}
## Buddies are drawn so that the idle frame is this tall (world px before Buddy.sprite_scale).
const TARGET_HEIGHT := 96.0

signal updated()

const CACHE_DIR := "user://sprites"
const MANIFEST_PATH := "user://sprites/manifest.json"

var manifest: Dictionary = {}          # {"set_id", "manifest_etag", "levels": [...]}
var _frames: Dictionary = {}           # level -> SpriteFrames
var _by_level: Dictionary = {}         # level -> manifest entry


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(CACHE_DIR)
	_load_manifest(_read_json(MANIFEST_PATH))


## Fetch manifest; download any level whose etag changed. Safe to call often (cheap when unchanged).
func sync() -> void:
	var m = await Api.get_json("/api/v1/sprites/manifest")
	if not (m is Dictionary):
		return
	if m.get("manifest_etag", "") == manifest.get("manifest_etag", "x") and _all_present(m):
		return
	for lvl in m.get("levels", []):
		var anims: Dictionary = lvl.get("animations", {})
		for anim_name in anims.keys():
			var a: Dictionary = anims[anim_name]
			var dir := _anim_dir(lvl, anim_name, a)
			if FileAccess.file_exists(dir + "/frames.json") and FileAccess.file_exists(dir + "/atlas.png"):
				continue
			DirAccess.make_dir_recursive_absolute(dir)
			var ok := await Api.download(a["atlas_url"], dir + "/atlas.png")
			ok = ok and await Api.download(a["frames_url"], dir + "/frames.json")
			if not ok:
				push_warning("[BuddyLib] failed to download level %d / %s" % [int(lvl["level"]), anim_name])
	var f := FileAccess.open(MANIFEST_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(m))
	_load_manifest(m)
	_frames.clear()
	updated.emit()


func has_art(level: int) -> bool:
	return _by_level.has(level) and (_by_level[level].get("animations", {}) as Dictionary).has("idle")


func level_count() -> int:
	return int(manifest.get("level_count", _by_level.size()))


func level_name(level: int) -> String:
	var e: Dictionary = _by_level.get(level, {})
	return str(e.get("name", "Level %d" % level))


## SpriteFrames for a level. Uses the nearest lower level with art, else a placeholder.
func get_frames(level: int) -> SpriteFrames:
	level = maxi(1, level)
	if _frames.has(level):
		return _frames[level]
	var use := level
	while use > 0 and not has_art(use):
		use -= 1
	var sf: SpriteFrames
	if use == 0:
		sf = _placeholder_frames(level)
	else:
		sf = _build_frames(_by_level[use])
		if sf == null:
			sf = _placeholder_frames(level)
	_frames[level] = sf
	return sf


func level_color(level: int) -> Color:
	var e: Dictionary = _by_level.get(level, {})
	if e.has("color") and e["color"] != null:
		return Color(str(e["color"]))
	var palette: Array = preload("res://ui/theme/LevelColors.gd").COLORS
	return Color(str(palette[(maxi(1, level) - 1) % palette.size()]))


# --------------------------------------------------------------------------- internals
func _load_manifest(m: Variant) -> void:
	if not (m is Dictionary):
		return
	manifest = m
	_by_level.clear()
	for lvl in manifest.get("levels", []):
		_by_level[int(lvl["level"])] = lvl


func _all_present(m: Dictionary) -> bool:
	for lvl in m.get("levels", []):
		var anims: Dictionary = lvl.get("animations", {})
		for anim_name in anims.keys():
			if not FileAccess.file_exists(_anim_dir(lvl, anim_name, anims[anim_name]) + "/frames.json"):
				return false
	return true


func _anim_dir(lvl: Dictionary, anim_name: String, a: Dictionary) -> String:
	return "%s/%d_%s_%s" % [CACHE_DIR, int(lvl["id"]), anim_name, str(a.get("etag", "0"))]


func _read_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _build_frames(lvl: Dictionary) -> SpriteFrames:
	var anims: Dictionary = lvl.get("animations", {})
	var sf := SpriteFrames.new()
	var loaded := {}
	for anim_name in ANIMS:
		if not anims.has(anim_name):
			continue
		var dir := _anim_dir(lvl, anim_name, anims[anim_name])
		var spec = _read_json(dir + "/frames.json")
		if not (spec is Dictionary):
			continue
		var img := Image.new()
		if img.load_png_from_buffer(FileAccess.get_file_as_bytes(dir + "/atlas.png")) != OK:
			continue
		var tex := ImageTexture.create_from_image(img)
		sf.add_animation(anim_name)
		sf.set_animation_loop(anim_name, bool(spec.get("loop", true)))
		sf.set_animation_speed(anim_name, 10.0)          # 1 duration unit = 100 ms
		for fr in spec.get("frames", []):
			var at := AtlasTexture.new()
			at.atlas = tex
			at.region = Rect2(fr["x"], fr["y"], fr["w"], fr["h"])
			sf.add_frame(anim_name, at, float(fr.get("ms", 100)) / 100.0)
		loaded[anim_name] = true
	if not loaded.has("idle"):
		return null
	# fill the gaps with aliases so callers can always play any name
	for anim_name in ANIMS:
		if loaded.has(anim_name):
			continue
		var src := _fallback_for(anim_name, loaded)
		sf.add_animation(anim_name)
		sf.set_animation_loop(anim_name, anim_name != "jump")
		sf.set_animation_speed(anim_name, 10.0)
		for i in sf.get_frame_count(src):
			sf.add_frame(anim_name, sf.get_frame_texture(src, i), sf.get_frame_duration(src, i))
	if sf.has_animation("default"):
		sf.remove_animation("default")
	return sf


func _fallback_for(anim_name: String, loaded: Dictionary) -> String:
	for cand in FALLBACKS.get(anim_name, []):
		if loaded.has(cand):
			return cand
	return "idle"


## Height of the idle frame, so Buddy can normalise display size regardless of source resolution.
static func frame_height(sf: SpriteFrames) -> float:
	if sf and sf.has_animation("idle") and sf.get_frame_count("idle") > 0:
		var t := sf.get_frame_texture("idle", 0)
		if t:
			return float(t.get_height())
	return TARGET_HEIGHT


## Procedural stand-in: coloured circle with a face — idle bob, dance hop, run wobble, jump arc.
func _placeholder_frames(level: int) -> SpriteFrames:
	var col := level_color(level)
	var sf := SpriteFrames.new()
	var size := 96
	for anim_name in ANIMS:
		sf.add_animation(anim_name)
		sf.set_animation_loop(anim_name, anim_name != "jump")
		sf.set_animation_speed(anim_name, 10.0)
		var n := {"idle": 4, "dance": 6, "run": 6, "jump": 5}[anim_name] as int
		for i in n:
			var t := float(i) / maxf(1.0, n - 1)
			var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
			img.fill(Color(0, 0, 0, 0))
			var r := int(size * 0.34)
			var dy := 0
			match anim_name:
				"dance": dy = -int(size * 0.12 * absf(2.0 * t - 1.0))
				"run": dy = int(size * 0.05 * (1 if i % 2 else -1))
				"jump": dy = -int(size * 0.22 * (1.0 - pow(2.0 * t - 1.0, 2)))
			var c := Vector2(size / 2.0, size / 2.0 + dy)
			_fill_circle(img, c, r, col.lightened(0.05 * (i % 2)))
			_fill_circle(img, c + Vector2(-r / 3.0, -r / 4.0), 4, Color("#14141e"))
			_fill_circle(img, c + Vector2(r / 3.0, -r / 4.0), 4, Color("#14141e"))
			var half := int(r / 3.0)
			for x in range(-half, half):
				var y := int(c.y + r / 4.0 + (-float(x * x) / float(r * 2) + r / 6.0))
				for k in 3:
					img.set_pixel(int(c.x) + x, y + k, Color("#14141e"))
			sf.add_frame(anim_name, ImageTexture.create_from_image(img), 1.1 if anim_name != "run" else 0.8)
	if sf.has_animation("default"):
		sf.remove_animation("default")
	return sf


static func _fill_circle(img: Image, c: Vector2, r: int, col: Color) -> void:
	for y in range(max(0, int(c.y) - r), min(img.get_height(), int(c.y) + r + 1)):
		for x in range(max(0, int(c.x) - r), min(img.get_width(), int(c.x) + r + 1)):
			if Vector2(x, y).distance_to(c) <= r:
				img.set_pixel(x, y, col)
