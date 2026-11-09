## Thin async HTTP client for the backend. Every call returns a Dictionary:
##   {"ok": bool, "status": int, "data": Variant (parsed JSON or null), "error": String}
extends Node

var base_url := "http://127.0.0.1:8080"
var timeout_s := 8.0

const _METHODS := {
	"GET": HTTPClient.METHOD_GET, "POST": HTTPClient.METHOD_POST, "PUT": HTTPClient.METHOD_PUT,
	"PATCH": HTTPClient.METHOD_PATCH, "DELETE": HTTPClient.METHOD_DELETE,
}


func _ready() -> void:
	# Optional override: user://kiosk.cfg  [api] base_url="http://192.168.1.50:8080"
	var cfg := ConfigFile.new()
	if cfg.load("user://kiosk.cfg") == OK:
		base_url = cfg.get_value("api", "base_url", base_url)
	var env := OS.get_environment("PIANO_API_BASE")
	if env != "":
		base_url = env


func request(method: String, path: String, body: Variant = null) -> Dictionary:
	var http := HTTPRequest.new()
	http.timeout = timeout_s
	add_child(http)
	var headers := PackedStringArray(["Accept: application/json"])
	var payload := ""
	if body != null:
		headers.append("Content-Type: application/json")
		payload = JSON.stringify(body)
	var url := path if path.begins_with("http") else base_url + path
	var err := http.request(url, headers, _METHODS.get(method, HTTPClient.METHOD_GET), payload)
	if err != OK:
		http.queue_free()
		return {"ok": false, "status": 0, "data": null, "error": "request() failed: %d" % err}
	var res: Array = await http.request_completed
	http.queue_free()
	var result: int = res[0]
	var status: int = res[1]
	var text: String = (res[3] as PackedByteArray).get_string_from_utf8()
	var data: Variant = null
	if text.length() > 0:
		data = JSON.parse_string(text)
	var ok := result == HTTPRequest.RESULT_SUCCESS and status >= 200 and status < 300
	return {"ok": ok, "status": status, "data": data, "error": "" if ok else "HTTP %d (%d)" % [status, result]}


func get_json(path: String) -> Variant:
	var r := await request("GET", path)
	return r["data"] if r["ok"] else null


func post_json(path: String, body: Variant = {}) -> Variant:
	var r := await request("POST", path, body)
	return r["data"] if r["ok"] else null


## Downloads `url` straight to `dest` (user:// path). Returns true on success.
func download(url: String, dest: String) -> bool:
	var http := HTTPRequest.new()
	http.timeout = 120.0
	http.download_file = dest
	add_child(http)
	var full := url if url.begins_with("http") else base_url + url
	if http.request(full) != OK:
		http.queue_free()
		return false
	var res: Array = await http.request_completed
	http.queue_free()
	var ok: bool = res[0] == HTTPRequest.RESULT_SUCCESS and res[1] == 200
	if not ok and FileAccess.file_exists(dest):
		DirAccess.remove_absolute(dest)
	return ok


func is_reachable() -> bool:
	var saved := timeout_s
	timeout_s = 3.0
	var r := await request("GET", "/api/v1/health")
	timeout_s = saved
	return r["ok"]
