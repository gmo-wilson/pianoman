## Boot: apply theme → load data → sync sprites → show Select. Periodically checks for releases while idle.
extends Control

@onready var screens: Control = $Screens
@onready var toast: PanelContainer = $Toast
@onready var toast_label: Label = $Toast/Label

const UPDATE_CHECK_EVERY := 15 * 60.0
const CONTENT_SYNC_EVERY := 60.0          # students / settings / sprites, while idle on the home screen
var _update_accum := 0.0
var _sync_accum := 0.0


func _ready() -> void:
	theme = App.theme
	Router.root = screens
	await App.refresh_all()
	BuddyLib.sync()                       # fire and forget; buddies refresh when done
	await Router.go("Select", {}, "fade")
	if not App.online:
		show_toast("Backend offline — using cached data")
	Router.screen_changed.connect(func(screen_name: String):
		if screen_name == "Select":
			_sync_content())
	_check_updates()


func _process(delta: float) -> void:
	_update_accum += delta
	if _update_accum >= UPDATE_CHECK_EVERY:
		_update_accum = 0.0
		_check_updates()
	_sync_accum += delta
	if _sync_accum >= CONTENT_SYNC_EVERY:
		_sync_accum = 0.0
		if Router.current_name == "Select" and not App.session_active:
			_sync_content()


## Pull students, settings and sprites from the admin; cheap when nothing changed.
## Buddies on screen re-skin themselves via BuddyLib.updated; the Select screen rebuilds via App.students_loaded.
func _sync_content() -> void:
	_sync_accum = 0.0
	await App.refresh_all()
	await BuddyLib.sync()


func _check_updates() -> void:
	if App.session_active or not App.online:
		return
	if await Updater.check_and_apply():
		show_toast("Updating…")
		await get_tree().create_timer(1.2).timeout
		Updater.restart_app()


func show_toast(text: String, seconds := 2.5) -> void:
	toast_label.text = text
	toast.visible = true
	toast.modulate.a = 0.0
	var tw := create_tween()
	tw.tween_property(toast, "modulate:a", 1.0, 0.2)
	tw.tween_interval(seconds)
	tw.tween_property(toast, "modulate:a", 0.0, 0.3)
	tw.tween_callback(func(): toast.visible = false)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		get_tree().quit()
