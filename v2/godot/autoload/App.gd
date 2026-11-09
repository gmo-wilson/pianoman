## Global app state: settings, students, the active practice session, and the shared Theme.
extends Node

signal settings_loaded()
signal students_loaded()
signal session_tick(accumulated: float, is_playing: bool)
signal goal_reached()
signal session_ended(summary: Dictionary)
signal bonus_reached_signal()

# ---- palette (v1 colours kept so the kiosk feels familiar)
const BG_DARK := Color("#0f141c")
const BG_CARD := Color("#1a2230")
const BG_CARD_HOVER := Color("#202a3c")
const BG_SURFACE := Color("#243042")
const ACCENT := Color("#38bdf8")
const ACCENT_HOVER := Color("#0ea5e9")
const ACCENT_MUTED := Color("#1e3a5f")
const SUCCESS := Color("#2dd4bf")
const WARNING := Color("#fbbf24")
const DANGER := Color("#fb7185")
const INACTIVE := Color("#475569")
const TEXT_PRIMARY := Color("#f8fafc")
const TEXT_SECONDARY := Color("#94a3b8")
const TEXT_MUTED := Color("#64748b")
const TEXT_DARK := Color("#0f141c")

var settings: Dictionary = {
	"goal_minutes": 15, "metronome": {"slow": 60, "normal": 80, "fast": 120},
	"inactivity_timeout_seconds": 300, "kiosk": {"transition_ms": 320, "idle_sleep_seconds": 600},
}
var students: Array = []                # [{id, name, color, ...}]
var buddies: Dictionary = {}            # student_id -> buddy status
var online := false

# ---- active session
var session_active := false
var student: Dictionary = {}            # {} = Guest
var accumulated := 0.0
var is_playing := false
var goal_done := false
var session_record: Dictionary = {}
var lesson: Dictionary = {}
var bonus_target := 0.0                 # > 0 while practising for a bonus run (seconds practiced today to reach)
var bonus_reached := false
var _last_save := 0.0
var _session_started := 0.0
var _chord_counts: Dictionary = {}
var _last_chord := ""

var theme: Theme


func _ready() -> void:
	theme = preload("res://ui/theme/ThemeBuilder.gd").build()
	Midi.note_on.connect(_on_note_on)
	Midi.note_off.connect(_on_note_off)


func goal_seconds() -> float:
	return float(settings.get("goal_minutes", 15)) * 60.0


func transition_s() -> float:
	return float(settings.get("kiosk", {}).get("transition_ms", 320)) / 1000.0


# --------------------------------------------------------------------------- loading
func refresh_all() -> void:
	online = await Api.is_reachable()
	if online:
		var s = await Api.get_json("/api/v1/settings")
		if s is Dictionary:
			settings.merge(s, true)
			_cache("settings", settings)
		var st = await Api.get_json("/api/v1/students")
		if st is Array:
			students = st
			_cache("students", students)
		var b = await Api.get_json("/api/v1/buddies")
		if b is Array:
			buddies.clear()
			for item in b:
				buddies[int(item["student_id"])] = item
			_cache("buddies", buddies)
	else:
		settings.merge(_cached("settings", {}), true)
		students = _cached("students", [])
		buddies = _cached("buddies", {})
	settings_loaded.emit()
	students_loaded.emit()


# --------------------------------------------------------------------------- session lifecycle
func start_session(p_student: Dictionary, p_lesson: Dictionary = {}, p_bonus_target := 0.0) -> void:
	student = p_student
	lesson = p_lesson
	bonus_target = p_bonus_target
	bonus_reached = false
	var b: Dictionary = buddies.get(int(student.get("id", -1)), {})
	accumulated = float(b.get("time_practiced_today", 0.0)) if not student.is_empty() else 0.0
	goal_done = accumulated >= goal_seconds()
	is_playing = false
	session_active = true
	_chord_counts = {}
	_last_chord = ""
	_last_save = Time.get_unix_time_from_system()
	_session_started = _last_save
	Midi.last_note_time = 0.0
	session_record = {
		"id": _uuid(), "player": student.get("name", "Guest"), "date": Time.get_date_string_from_system(),
		"start_time": Time.get_unix_time_from_system(), "mode": "lesson" if not lesson.is_empty() else "free",
		"lesson_id": lesson.get("id"), "lesson_name": lesson.get("name"), "events": [], "goal_reached": goal_done,
	}
	Api.post_json("/api/v1/live", {"session_active": true, "student": student.get("name", "Guest")})


func _process(delta: float) -> void:
	if not session_active:
		return
	var now := Time.get_unix_time_from_system()
	if Midi.active_notes.size() > 0:
		is_playing = true
	elif Midi.seconds_since_last_note() > 2.0:
		is_playing = false
	if is_playing:
		accumulated += delta
		if now - _last_save > 10.0:
			_last_save = now
			save_progress()
	if not goal_done and not student.is_empty() and accumulated >= goal_seconds():
		goal_done = true
		session_record["goal_reached"] = true
		save_progress()
		goal_reached.emit()
	if bonus_target > 0.0 and not bonus_reached and accumulated >= bonus_target:
		bonus_reached = true
		save_progress()
		bonus_reached_signal.emit()
	session_tick.emit(accumulated, is_playing)
	# auto-end after N minutes without a note (measured from the session start if no note yet)
	var idle := float(settings.get("inactivity_timeout_seconds", 300))
	var since := now - maxf(Midi.last_note_time, _session_started)
	if since > idle:
		end_session()


func save_progress() -> void:
	if student.is_empty():
		return
	var res = await Api.post_json("/api/v1/students/%d/progress" % int(student["id"]), {"seconds": accumulated})
	if res is Dictionary:
		buddies[int(student["id"])] = res


func end_session() -> Dictionary:
	if not session_active:
		return {}
	session_active = false
	await save_progress()
	var now := Time.get_unix_time_from_system()
	session_record["end_time"] = now
	session_record["duration_seconds"] = snapped(now - float(session_record["start_time"]), 0.1)
	session_record["accumulated_practice_time"] = snapped(accumulated, 0.1)
	session_record["chords_played"] = _chord_counts
	var total := 0
	for e in session_record["events"]:
		if e.get("type") == "on":
			total += 1
	session_record["total_notes"] = total
	if total > 0:
		Api.post_json("/api/v1/sessions", session_record)
	Api.post_json("/api/v1/live", {"session_active": false})
	var summary := {
		"student": student, "accumulated": accumulated, "goal_reached": goal_done, "total_notes": total,
		"chords": _chord_counts, "buddy": buddies.get(int(student.get("id", -1)), {}),
		"bonus_run": bonus_target > 0.0 and bonus_reached,
	}
	bonus_target = 0.0
	session_ended.emit(summary)
	return summary


func _on_note_on(note: int, vel: int) -> void:
	if not session_active:
		return
	session_record["events"].append({"time": snapped(Time.get_unix_time_from_system() - float(session_record["start_time"]), 0.001),
		"type": "on", "note": note, "vel": vel})
	var chord := Midi.identify_chord(Midi.active_notes.keys())
	if chord != "" and chord != _last_chord:
		_chord_counts[chord] = int(_chord_counts.get(chord, 0)) + 1
		_last_chord = chord


func _on_note_off(note: int) -> void:
	if not session_active:
		return
	session_record["events"].append({"time": snapped(Time.get_unix_time_from_system() - float(session_record["start_time"]), 0.001),
		"type": "off", "note": note, "vel": 0})
	if Midi.active_notes.size() < 3:
		_last_chord = ""


# --------------------------------------------------------------------------- offline cache
func _cache(key: String, value: Variant) -> void:
	var f := FileAccess.open("user://cache_%s.json" % key, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(value))


func _cached(key: String, fallback: Variant) -> Variant:
	var p := "user://cache_%s.json" % key
	if not FileAccess.file_exists(p):
		return fallback
	var v = JSON.parse_string(FileAccess.get_file_as_string(p))
	return v if v != null else fallback


static func _uuid() -> String:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	var hex := ""
	for i in 32:
		hex += "%x" % rng.randi_range(0, 15)
	return "%s-%s-4%s-%s-%s" % [hex.substr(0, 8), hex.substr(8, 4), hex.substr(13, 3), hex.substr(16, 4), hex.substr(20, 12)]


static func fmt_time(seconds: float) -> String:
	var s := int(seconds)
	return "%d:%02d" % [int(s / 60.0), s % 60]
