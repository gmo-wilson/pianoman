## Screen navigation with animated transitions. Screens are Controls instantiated under `root`.
## Usage:  Router.go("Session", {"student": s}, "slide_left")   Router.back()
extends Node

signal screen_changed(screen_name: String)

const SCREENS := {
	"Select": "res://screens/Select.tscn",
	"Session": "res://screens/Session.tscn",
	"Recap": "res://screens/Recap.tscn",
	"Lessons": "res://screens/Lessons.tscn",
	"BuddyDetail": "res://screens/BuddyDetail.tscn",
	"Runner": "res://screens/Runner.tscn",
	"Leaderboard": "res://screens/Leaderboard.tscn",
}

var root: Control                      # set by main.tscn
var current: Control
var current_name := ""
var busy := false
var _stack: Array[String] = []


func go(screen_name: String, params: Dictionary = {}, transition := "slide_left", push := true) -> void:
	if busy or not SCREENS.has(screen_name):
		return
	busy = true
	var packed: PackedScene = load(SCREENS[screen_name])
	var next: Control = packed.instantiate()
	next.set_meta("params", params)
	if next.has_method("setup"):          # before add_child so _ready() can rely on params
		next.call("setup", params)
	root.add_child(next)
	next.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	next.pivot_offset = root.size / 2.0

	var dur := App.transition_s()
	var w := root.size.x
	var tw := create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	match transition:
		"slide_left", "slide_right":
			var dir := 1.0 if transition == "slide_left" else -1.0
			next.position.x = w * dir
			tw.tween_property(next, "position:x", 0.0, dur)
			if current:
				tw.tween_property(current, "position:x", -w * 0.35 * dir, dur)
				tw.tween_property(current, "modulate:a", 0.0, dur * 0.8)
		"zoom":
			next.scale = Vector2(0.9, 0.9)
			next.modulate.a = 0.0
			tw.tween_property(next, "scale", Vector2.ONE, dur)
			tw.tween_property(next, "modulate:a", 1.0, dur * 0.7)
			if current:
				tw.tween_property(current, "scale", Vector2(1.06, 1.06), dur)
				tw.tween_property(current, "modulate:a", 0.0, dur * 0.6)
		_:  # fade
			next.modulate.a = 0.0
			tw.tween_property(next, "modulate:a", 1.0, dur)
			if current:
				tw.tween_property(current, "modulate:a", 0.0, dur)
	await tw.finished

	if current:
		current.queue_free()
	current = next
	current_name = screen_name
	if push:
		_stack.append(screen_name)
	busy = false
	screen_changed.emit(screen_name)


func replace(screen_name: String, params: Dictionary = {}, transition := "fade") -> void:
	if _stack.size() > 0:
		_stack.pop_back()
	await go(screen_name, params, transition)


func back(transition := "slide_right") -> void:
	if _stack.size() < 2:
		await home()
		return
	_stack.pop_back()
	var prev: String = _stack.pop_back()
	await go(prev, {}, transition)


func home(transition := "slide_right") -> void:
	_stack.clear()
	await go("Select", {}, transition)
