## 2D buddy: an AnimatedSprite2D showing the sprite of a level. Animations: idle · dance · run · jump
## (missing ones are aliased by BuddyLib). `transform_to()` plays the milestone transformation.
class_name Buddy
extends Node2D

signal tapped()
signal transformed(new_level: int)

@export var level := 1
@export var sprite_scale := 1.0
@export var tap_radius := 64.0

var _sprite: AnimatedSprite2D
var _busy := false
var _norm := 1.0          # normalises any source resolution to BuddyLib.TARGET_HEIGHT


func _ready() -> void:
	_sprite = AnimatedSprite2D.new()
	_sprite.centered = true
	add_child(_sprite)
	_sprite.animation_finished.connect(_on_anim_finished)
	BuddyLib.updated.connect(_refresh)
	_refresh()


func set_status(status: Dictionary) -> void:
	level = int(status.get("level", 1))
	_refresh()


func set_level(p_level: int) -> void:
	level = p_level
	_refresh()


func _refresh() -> void:
	if _sprite == null:
		return
	_sprite.sprite_frames = BuddyLib.get_frames(level)
	_norm = BuddyLib.TARGET_HEIGHT / maxf(1.0, BuddyLib.frame_height(_sprite.sprite_frames))
	_sprite.scale = Vector2.ONE * sprite_scale * _norm
	if not _busy:
		_play("idle")


func _play(anim: String) -> void:
	if _sprite.sprite_frames and _sprite.sprite_frames.has_animation(anim):
		_sprite.play(anim)


func base_scale() -> Vector2:
	return Vector2.ONE * sprite_scale * _norm


## Celebration: play the dance sheet for `seconds`, then back to idle. No extra tweens — the art does the work.
func dance(seconds := 2.4) -> void:
	_busy = true
	_play("dance")
	await get_tree().create_timer(seconds).timeout
	_busy = false
	_play("idle")


## Runner: loop the run cycle until stop_run().
func run() -> void:
	_busy = true
	_play("run")


func stop_run() -> void:
	_busy = false
	_play("idle")


## Runner: show the jump while airborne (holds its last frame if it's shorter than the flight)…
func jump() -> void:
	_play("jump")


## …and go straight back to running the moment the feet touch the ground.
func land() -> void:
	if _busy:
		_play("run")


## Tap: play the dance sheet once through (or ~1.6 s), then idle.
func poke() -> void:
	tapped.emit()
	if _busy:
		return
	dance(_anim_length("dance", 1.6))


## Duration of one pass of an animation in seconds (falls back when unknown).
func _anim_length(anim: String, fallback: float) -> float:
	var sf := _sprite.sprite_frames
	if sf == null or not sf.has_animation(anim) or sf.get_frame_count(anim) == 0:
		return fallback
	var total := 0.0
	for i in sf.get_frame_count(anim):
		total += sf.get_frame_duration(anim, i) / sf.get_animation_speed(anim)
	return maxf(0.6, total)


## Milestone transformation: white flash → shrink + spin → swap to the new level's sprite → pop back out.
func transform_to(to_level: int) -> void:
	_busy = true
	var flash := ColorRect.new()
	flash.color = Color(1, 1, 1, 0)
	flash.size = Vector2(4000, 4000)
	flash.position = -flash.size / 2.0
	flash.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(flash)
	_play("dance")
	var tw := create_tween()
	tw.tween_property(_sprite, "scale", Vector2(0.1, 0.1), 0.45).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_IN)
	tw.parallel().tween_property(flash, "color:a", 0.9, 0.45)
	tw.parallel().tween_property(self, "rotation", TAU, 0.45)
	await tw.finished
	rotation = 0.0
	level = to_level
	_sprite.sprite_frames = BuddyLib.get_frames(level)
	_norm = BuddyLib.TARGET_HEIGHT / maxf(1.0, BuddyLib.frame_height(_sprite.sprite_frames))
	_play("dance")
	var tw2 := create_tween()
	tw2.tween_property(_sprite, "scale", base_scale() * 1.25, 0.5).set_trans(Tween.TRANS_ELASTIC).set_ease(Tween.EASE_OUT)
	tw2.parallel().tween_property(flash, "color:a", 0.0, 0.5)
	tw2.tween_property(_sprite, "scale", base_scale(), 0.25)
	await tw2.finished
	flash.queue_free()
	transformed.emit(level)
	_busy = false
	_play("idle")


func _on_anim_finished() -> void:
	if not _busy:
		_play("idle")



func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch and event.is_pressed() and tap_radius > 0.0:
		if to_local(event.position).length() <= tap_radius * sprite_scale:
			poke()
