## Hot-update of game content via downloadable .pck releases.
##
## Must be the FIRST autoload: `_init()` mounts the installed pck with replace_files=true
## so every autoload/scene loaded after it comes from the new release.
## This script itself (and project.godot) only change when the base export is replaced —
## keep it small and stable.
extends Node

const PCK_PATH := "user://main.pck"
const META_PATH := "user://release.json"
const TMP_PATH := "user://main.pck.download"

var installed: Dictionary = {}
var mounted := false


func _init() -> void:
	installed = _read_meta()
	if FileAccess.file_exists(PCK_PATH):
		mounted = ProjectSettings.load_resource_pack(PCK_PATH, true)
		print("[Updater] mounted %s (%s): %s" % [PCK_PATH, installed.get("version", "?"), mounted])


## Returns true when a new release was installed (caller should restart the app).
func check_and_apply() -> bool:
	var r: Dictionary = await Api.request("GET", "/api/v1/releases/current")
	if not r.get("ok", false) or r.get("status", 0) == 204 or r.get("data") == null:
		return false
	var rel: Dictionary = r["data"]
	if rel.get("sha256", "") == installed.get("sha256", ""):
		return false
	print("[Updater] new release %s" % rel.get("version"))
	if not await Api.download(Api.base_url + rel["pck_url"], TMP_PATH):
		return false
	if _sha256_file(TMP_PATH) != rel["sha256"]:
		push_warning("[Updater] sha256 mismatch, discarding download")
		DirAccess.remove_absolute(TMP_PATH)
		return false
	if FileAccess.file_exists(PCK_PATH):
		DirAccess.rename_absolute(PCK_PATH, PCK_PATH + ".prev")
	DirAccess.rename_absolute(TMP_PATH, PCK_PATH)
	_write_meta(rel)
	installed = rel
	return true


## Restart through systemd (Restart=always) — the new pck is mounted on the next boot.
func restart_app() -> void:
	OS.set_restart_on_exit(true)
	get_tree().quit()


func _read_meta() -> Dictionary:
	if not FileAccess.file_exists(META_PATH):
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(META_PATH))
	return parsed if parsed is Dictionary else {}


func _write_meta(rel: Dictionary) -> void:
	var f := FileAccess.open(META_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"version": rel.get("version"), "sha256": rel.get("sha256"),
			"installed_at": Time.get_datetime_string_from_system()}))


func _sha256_file(path: String) -> String:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return ""
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	while not f.eof_reached():
		ctx.update(f.get_buffer(1 << 20))
	f.close()
	return ctx.finish().hex_encode()
