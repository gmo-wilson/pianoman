"""Domain operations on the SQLite store. Stdlib only; FastAPI layer is a thin wrapper."""
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import json
import sqlite3
import time
import uuid
from typing import Any

from . import buddy, config, db


def _row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


def _rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


def _today() -> str:
    return _dt.date.today().isoformat()


# --------------------------------------------------------------------------- settings
def get_settings() -> dict:
    out = json.loads(json.dumps(config.DEFAULT_SETTINGS))
    for r in db.query("SELECT key, value FROM settings"):
        out[r["key"]] = json.loads(r["value"])
    return out


def set_settings(patch: dict) -> dict:
    with db.tx() as c:
        for k, v in patch.items():
            c.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, json.dumps(v)),
            )
    return get_settings()


def goal_seconds() -> int:
    return int(get_settings().get("goal_minutes", 15)) * 60


# --------------------------------------------------------------------------- students
def list_students(include_inactive: bool = False) -> list[dict]:
    sql = "SELECT * FROM students" + ("" if include_inactive else " WHERE active = 1") + " ORDER BY sort_order, id"
    return _rows(db.query(sql))


def get_student(student_id: int) -> dict | None:
    return _row(db.one("SELECT * FROM students WHERE id = ?", (student_id,)))


def get_student_by_name(name: str) -> dict | None:
    return _row(db.one("SELECT * FROM students WHERE name = ?", (name,)))


def create_student(name: str, color: str | None = None, sprite_set: int | None = None) -> dict:
    with db.tx() as c:
        order = c.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM students").fetchone()[0]
        cur = c.execute(
            "INSERT INTO students(name, color, sprite_set, sort_order) VALUES (?, ?, ?, ?)",
            (name.strip(), color, sprite_set, order),
        )
        sid = cur.lastrowid
    return get_student(sid)  # type: ignore[return-value]


_STUDENT_FIELDS = {"name", "color", "sprite_set", "sort_order", "active", "forced_level", "base_color", "fed_date"}


def update_student(student_id: int, patch: dict) -> dict | None:
    fields = {k: v for k, v in patch.items() if k in _STUDENT_FIELDS}
    if not fields:
        return get_student(student_id)
    sets = ", ".join(f"{k} = ?" for k in fields)
    with db.tx() as c:
        c.execute(f"UPDATE students SET {sets} WHERE id = ?", (*fields.values(), student_id))
    return get_student(student_id)


def delete_student(student_id: int) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM students WHERE id = ?", (student_id,))


# --------------------------------------------------------------------------- practice days / buddy
def record_progress(student_id: int, seconds: float, day: str | None = None) -> dict:
    """Idempotent: keeps the max seconds for the day; marks completed once goal is reached."""
    day = day or _today()
    goal = goal_seconds()
    with db.tx() as c:
        c.execute(
            "INSERT INTO practice_days(student_id, day, seconds, completed) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(student_id, day) DO UPDATE SET "
            "  seconds = MAX(practice_days.seconds, excluded.seconds), "
            "  completed = MAX(practice_days.completed, excluded.completed)",
            (student_id, day, float(seconds), 1 if seconds >= goal else 0),
        )
        r = c.execute("SELECT * FROM practice_days WHERE student_id = ? AND day = ?", (student_id, day)).fetchone()
    return dict(r)


def completed_dates(student_id: int) -> set[_dt.date]:
    return {
        _dt.date.fromisoformat(r["day"])
        for r in db.query("SELECT day FROM practice_days WHERE student_id = ? AND completed = 1", (student_id,))
    }


def today_seconds(student_id: int, day: str | None = None) -> float:
    r = db.one("SELECT seconds FROM practice_days WHERE student_id = ? AND day = ?", (student_id, day or _today()))
    return float(r["seconds"]) if r else 0.0


def buddy_status(student: dict, today: _dt.date | None = None) -> dict:
    sid = student["id"]
    today = today or _dt.date.today()
    set_id = student.get("sprite_set") or default_sprite_set_id()
    levels = list_sprite_levels(set_id) if set_id is not None else []
    settings = get_settings()
    status = buddy.compute_status(
        completed_dates(sid),
        today_seconds=today_seconds(sid, today.isoformat()),
        goal_seconds=int(settings.get("goal_minutes", 15)) * 60,
        today=today,
        overrides={"forced_level": student.get("forced_level")},
        max_level=len(levels) or 1,
        steps_per_level=int((settings.get("road") or {}).get("steps_per_level", 3)),
    )
    by_level = {l["level"]: l for l in levels}
    cur = by_level.get(status["level"], {})
    status["level_name"] = cur.get("display_name") or f"Level {status['level']}"
    status["level_color"] = cur.get("color") or "#38bdf8"
    status["level_id"] = cur.get("id")
    prev = by_level.get(status["prev_level"], {})
    status["prev_level_name"] = prev.get("display_name") or f"Level {status['prev_level']}"
    status["student_id"] = sid
    status["student_name"] = student["name"]
    status["sprite_set"] = set_id
    return status


def celebrate_buddy(student_id: int) -> dict | None:
    """Marks today's celebration as played (so the recap doesn't replay it)."""
    update_student(student_id, {"fed_date": _today()})
    s = get_student(student_id)
    if not s:
        return None
    st = buddy_status(s)
    st["celebrated_today"] = True
    return st


def student_stats(student_id: int) -> dict:
    days = _rows(db.query("SELECT day, seconds, completed FROM practice_days WHERE student_id = ? ORDER BY day", (student_id,)))
    sess = db.one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(practice_seconds), 0) AS practice, COALESCE(SUM(total_notes), 0) AS notes "
        "FROM sessions WHERE student_id = ?",
        (student_id,),
    )
    # best streak over completed days
    best = cur = 0
    prev: _dt.date | None = None
    for d in days:
        if not d["completed"]:
            continue
        day = _dt.date.fromisoformat(d["day"])
        cur = cur + 1 if prev and (day - prev).days == 1 else 1
        best = max(best, cur)
        prev = day
    return {
        "days_practiced": sum(1 for d in days if d["seconds"] > 0),
        "days_completed": sum(1 for d in days if d["completed"]),
        "total_practice_seconds": sum(d["seconds"] for d in days),
        "best_streak": best,
        "sessions": sess["n"] if sess else 0,
        "total_notes": sess["notes"] if sess else 0,
        "last_30_days": days[-30:],
    }


# --------------------------------------------------------------------------- sessions
def save_session(sess: dict) -> dict:
    """`sess` follows v1's shape: id, player, start_time, end_time, events[], chords_played, ..."""
    student = get_student_by_name(sess.get("player", "")) if sess.get("player") else None
    sid = sess.get("id") or str(uuid.uuid4())
    events = sess.get("events") or []
    blob = gzip.compress(json.dumps(events, separators=(",", ":")).encode()) if events else None
    with db.tx() as c:
        c.execute(
            "INSERT OR REPLACE INTO sessions(id, student_id, student_name, mode, lesson_id, lesson_name, started_at, "
            "ended_at, duration_seconds, practice_seconds, total_notes, goal_reached, chords_played, events_gz) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sid,
                student["id"] if student else sess.get("student_id"),
                sess.get("player") or sess.get("student_name") or "Guest",
                sess.get("mode", "free"),
                sess.get("lesson_id") or sess.get("class_id"),
                sess.get("lesson_name") or sess.get("class_name"),
                float(sess.get("start_time") or time.time()),
                sess.get("end_time"),
                sess.get("duration_seconds"),
                sess.get("accumulated_practice_time", sess.get("practice_seconds")),
                sess.get("total_notes", sum(1 for e in events if e.get("type") == "on")),
                1 if sess.get("goal_reached") else 0,
                json.dumps(sess.get("chords_played") or {}),
                blob,
            ),
        )
    prune_sessions()
    return get_session(sid, with_events=False)  # type: ignore[return-value]


def prune_sessions() -> int:
    limit = int(get_settings().get("session_history_limit", 500))
    with db.tx() as c:
        cur = c.execute(
            "DELETE FROM sessions WHERE id IN (SELECT id FROM sessions ORDER BY started_at DESC LIMIT -1 OFFSET ?)",
            (limit,),
        )
        return cur.rowcount


def list_sessions(student_id: int | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    cols = ("id, student_id, student_name, mode, lesson_id, lesson_name, started_at, ended_at, duration_seconds, "
            "practice_seconds, total_notes, goal_reached, chords_played")
    if student_id is not None:
        rows = db.query(f"SELECT {cols} FROM sessions WHERE student_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
                        (student_id, limit, offset))
    else:
        rows = db.query(f"SELECT {cols} FROM sessions ORDER BY started_at DESC LIMIT ? OFFSET ?", (limit, offset))
    out = _rows(rows)
    for s in out:
        s["chords_played"] = json.loads(s["chords_played"] or "{}")
    return out


def get_session(session_id: str, with_events: bool = True) -> dict | None:
    r = _row(db.one("SELECT * FROM sessions WHERE id = ?", (session_id,)))
    if not r:
        return None
    r["chords_played"] = json.loads(r.pop("chords_played") or "{}")
    blob = r.pop("events_gz")
    if with_events:
        r["events"] = json.loads(gzip.decompress(blob).decode()) if blob else []
    return r


def delete_session(session_id: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


# --------------------------------------------------------------------------- lessons & songs
def list_lessons() -> list[dict]:
    out = _rows(db.query("SELECT id, name, chords, source_song_id, created_at, updated_at, "
                         "json_array_length(midi_events) AS events_count FROM lessons ORDER BY created_at DESC"))
    for l in out:
        l["chords"] = json.loads(l["chords"])
    return out


def get_lesson(lesson_id: str) -> dict | None:
    r = _row(db.one("SELECT * FROM lessons WHERE id = ?", (lesson_id,)))
    if r:
        r["chords"] = json.loads(r["chords"])
        r["midi_events"] = json.loads(r["midi_events"])
    return r


def upsert_lesson(data: dict) -> dict:
    lid = data.get("id") or str(uuid.uuid4())
    with db.tx() as c:
        c.execute(
            "INSERT INTO lessons(id, name, chords, midi_events, source_song_id) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, chords = excluded.chords, "
            "midi_events = excluded.midi_events, source_song_id = excluded.source_song_id, updated_at = datetime('now')",
            (lid, data["name"], json.dumps(data.get("chords") or []), json.dumps(data.get("midi_events") or []),
             data.get("source_song_id")),
        )
    return get_lesson(lid)  # type: ignore[return-value]


def delete_lesson(lesson_id: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))


def list_songs() -> list[dict]:
    out = _rows(db.query("SELECT id, title, composer, filename, file_size, duration_seconds, notes_count, track_count, "
                         "chords, uploaded_at FROM songs ORDER BY title"))
    for s in out:
        s["chords"] = json.loads(s["chords"])
    return out


def get_song(song_id: str) -> dict | None:
    r = _row(db.one("SELECT * FROM songs WHERE id = ?", (song_id,)))
    if r:
        r["chords"] = json.loads(r["chords"])
        r["midi_events"] = json.loads(r["midi_events"])
    return r


def upsert_song(data: dict) -> dict:
    sid = data.get("id") or str(uuid.uuid4())
    with db.tx() as c:
        c.execute(
            "INSERT OR REPLACE INTO songs(id, title, composer, filename, file_size, duration_seconds, notes_count, "
            "track_count, chords, midi_events, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, data["title"], data.get("composer"), data.get("filename"), data.get("file_size"),
             data.get("duration_seconds"), data.get("notes_count"), data.get("track_count"),
             json.dumps(data.get("chords") or []), json.dumps(data.get("midi_events") or []),
             data.get("upload_date") or data.get("uploaded_at") or _dt.datetime.now().isoformat(timespec="minutes")),
        )
    return get_song(sid)  # type: ignore[return-value]


def delete_song(song_id: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM songs WHERE id = ?", (song_id,))


# --------------------------------------------------------------------------- sprites
def default_sprite_set_id() -> int | None:
    r = db.one("SELECT id FROM sprite_sets WHERE is_default = 1")
    return r["id"] if r else None


def list_sprite_sets() -> list[dict]:
    sets = _rows(db.query("SELECT * FROM sprite_sets ORDER BY id"))
    for s in sets:
        s["levels_total"] = db.one("SELECT COUNT(*) AS n FROM sprite_levels WHERE set_id = ?", (s["id"],))["n"]
        s["levels_ready"] = db.one(
            "SELECT COUNT(DISTINCT l.id) AS n FROM sprite_levels l JOIN sprite_animations a ON a.level_id = l.id "
            "WHERE l.set_id = ? AND a.name = 'idle'", (s["id"],))["n"]
    return sets


def create_sprite_set(name: str, make_default: bool = False, seed_defaults: bool = True) -> dict:
    with db.tx() as c:
        if make_default:
            c.execute("UPDATE sprite_sets SET is_default = 0")
        cur = c.execute("INSERT INTO sprite_sets(name, is_default) VALUES (?, ?)", (name, 1 if make_default else 0))
        set_id = cur.lastrowid
        seed = buddy.DEFAULT_LEVELS if seed_defaults else buddy.DEFAULT_LEVELS[:1]
        for i, (lvl_name, color) in enumerate(seed, start=1):
            c.execute("INSERT INTO sprite_levels(set_id, level, display_name, color) VALUES (?, ?, ?, ?)",
                      (set_id, i, lvl_name, color))
    return _row(db.one("SELECT * FROM sprite_sets WHERE id = ?", (set_id,)))  # type: ignore[return-value]


def rename_sprite_set(set_id: int, name: str) -> None:
    with db.tx() as c:
        c.execute("UPDATE sprite_sets SET name = ? WHERE id = ?", (name, set_id))


def delete_sprite_set(set_id: int) -> bool:
    """Refuses to delete the default set or the last remaining set."""
    sets = list_sprite_sets()
    target = next((s for s in sets if s["id"] == set_id), None)
    if target is None or target["is_default"] or len(sets) <= 1:
        return False
    with db.tx() as c:
        c.execute("UPDATE students SET sprite_set = NULL WHERE sprite_set = ?", (set_id,))
        c.execute("DELETE FROM sprite_sets WHERE id = ?", (set_id,))
    return True


def set_default_sprite_set(set_id: int) -> None:
    with db.tx() as c:
        c.execute("UPDATE sprite_sets SET is_default = 0")
        c.execute("UPDATE sprite_sets SET is_default = 1 WHERE id = ?", (set_id,))


def list_sprite_levels(set_id: int) -> list[dict]:
    levels = _rows(db.query("SELECT * FROM sprite_levels WHERE set_id = ? ORDER BY level", (set_id,)))
    anims = _rows(db.query("SELECT a.* FROM sprite_animations a JOIN sprite_levels l ON l.id = a.level_id WHERE l.set_id = ?",
                           (set_id,)))
    by_level: dict[int, dict] = {}
    for a in anims:
        by_level.setdefault(a["level_id"], {})[a["name"]] = a
    for l in levels:
        l["animations"] = by_level.get(l["id"], {})
        l["ready"] = "idle" in l["animations"]
        l["etag"] = hashlib.sha1("".join(sorted(a["etag"] for a in l["animations"].values())).encode()).hexdigest()[:16] if l["animations"] else None
    return levels


def get_sprite_level(level_id: int) -> dict | None:
    return _row(db.one("SELECT * FROM sprite_levels WHERE id = ?", (level_id,)))


def level_count(set_id: int) -> int:
    return db.one("SELECT COUNT(*) AS n FROM sprite_levels WHERE set_id = ?", (set_id,))["n"]


def _renumber(c: sqlite3.Connection, set_id: int) -> None:
    """Keep `level` dense (1..N) in ladder order."""
    ids = [r["id"] for r in c.execute("SELECT id FROM sprite_levels WHERE set_id = ? ORDER BY level", (set_id,))]
    _assign_positions(c, set_id, ids)


_TMP_OFFSET = 1_000_000


def _assign_positions(c: sqlite3.Connection, set_id: int, ordered_ids: list[int]) -> None:
    """Two-pass update through a high temporary range so UNIQUE(set_id, level) never trips."""
    for i, lid in enumerate(ordered_ids, start=1):
        c.execute("UPDATE sprite_levels SET level = ? WHERE id = ?", (_TMP_OFFSET + i, lid))
    c.execute("UPDATE sprite_levels SET level = level - ? WHERE set_id = ? AND level > ?", (_TMP_OFFSET, set_id, _TMP_OFFSET))


def add_sprite_level(set_id: int, display_name: str | None = None, color: str | None = None,
                     position: int | None = None) -> dict:
    """Append (default) or insert at 1-based `position`, shifting the rest down."""
    with db.tx() as c:
        n = c.execute("SELECT COUNT(*) FROM sprite_levels WHERE set_id = ?", (set_id,)).fetchone()[0]
        pos = n + 1 if position is None else max(1, min(n + 1, int(position)))
        # make room: shift levels >= pos by +1 (descending to respect UNIQUE)
        for r in c.execute("SELECT id, level FROM sprite_levels WHERE set_id = ? AND level >= ? ORDER BY level DESC",
                           (set_id, pos)).fetchall():
            c.execute("UPDATE sprite_levels SET level = ? WHERE id = ?", (r["level"] + 1, r["id"]))
        cur = c.execute("INSERT INTO sprite_levels(set_id, level, display_name, color) VALUES (?, ?, ?, ?)",
                        (set_id, pos, display_name or f"Level {pos}", color or "#38bdf8"))
        lid = cur.lastrowid
    return get_sprite_level(lid)  # type: ignore[return-value]


def update_sprite_level(level_id: int, patch: dict) -> dict | None:
    fields = {k: v for k, v in patch.items() if k in ("display_name", "color")}
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with db.tx() as c:
            c.execute(f"UPDATE sprite_levels SET {sets}, updated_at = datetime('now') WHERE id = ?",
                      (*fields.values(), level_id))
    return get_sprite_level(level_id)


def move_sprite_level(level_id: int, to_position: int) -> list[dict]:
    lvl = get_sprite_level(level_id)
    if not lvl:
        return []
    with db.tx() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM sprite_levels WHERE set_id = ? ORDER BY level", (lvl["set_id"],))]
        ids.remove(level_id)
        ids.insert(max(0, min(len(ids), int(to_position) - 1)), level_id)
        _assign_positions(c, lvl["set_id"], ids)
    return list_sprite_levels(lvl["set_id"])


def delete_sprite_level(level_id: int) -> bool:
    """Deletes a level (and its files), renumbers the ladder, clamps students' forced levels. Keeps >= 1 level."""
    lvl = get_sprite_level(level_id)
    if not lvl or level_count(lvl["set_id"]) <= 1:
        return False
    with db.tx() as c:
        c.execute("DELETE FROM sprite_levels WHERE id = ?", (level_id,))
        _renumber(c, lvl["set_id"])
        n = c.execute("SELECT COUNT(*) FROM sprite_levels WHERE set_id = ?", (lvl["set_id"],)).fetchone()[0]
        c.execute("UPDATE students SET forced_level = ? WHERE forced_level > ? AND COALESCE(sprite_set, "
                  "(SELECT id FROM sprite_sets WHERE is_default = 1)) = ?", (n, n, lvl["set_id"]))
    import shutil
    shutil.rmtree(config.DATA_DIR / "sprites" / str(lvl["set_id"]) / str(level_id), ignore_errors=True)
    return True


def set_sprite_animation(level_id: int, name: str, atlas_rel: str, frames_rel: str, frame_count: int,
                         frame_w: int, frame_h: int, etag: str) -> dict:
    with db.tx() as c:
        c.execute(
            "INSERT INTO sprite_animations(level_id, name, atlas_path, frames_path, frame_count, frame_w, frame_h, etag) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(level_id, name) DO UPDATE SET atlas_path = excluded.atlas_path, "
            "frames_path = excluded.frames_path, frame_count = excluded.frame_count, frame_w = excluded.frame_w, "
            "frame_h = excluded.frame_h, etag = excluded.etag, updated_at = datetime('now')",
            (level_id, name, atlas_rel, frames_rel, frame_count, frame_w, frame_h, etag))
        c.execute("UPDATE sprite_levels SET updated_at = datetime('now') WHERE id = ?", (level_id,))
    return _row(db.one("SELECT * FROM sprite_animations WHERE level_id = ? AND name = ?", (level_id, name)))  # type: ignore[return-value]


def delete_sprite_animation(level_id: int, name: str) -> bool:
    r = db.one("SELECT atlas_path FROM sprite_animations WHERE level_id = ? AND name = ?", (level_id, name))
    if not r:
        return False
    with db.tx() as c:
        c.execute("DELETE FROM sprite_animations WHERE level_id = ? AND name = ?", (level_id, name))
    import shutil
    shutil.rmtree((config.DATA_DIR / r["atlas_path"]).parent, ignore_errors=True)
    return True


def sprite_manifest(set_id: int | None = None, base_url: str = "/files") -> dict:
    """What the kiosk syncs: per level, each available animation with URLs + etag."""
    set_id = set_id or default_sprite_set_id()
    levels = []
    if set_id is not None:
        for l in list_sprite_levels(set_id):
            entry = {"level": l["level"], "id": l["id"], "name": l["display_name"], "color": l["color"], "etag": l["etag"],
                     "animations": {}}
            for name, a in l["animations"].items():
                entry["animations"][name] = {"atlas_url": f"{base_url}/{a['atlas_path']}", "frames_url": f"{base_url}/{a['frames_path']}",
                                             "etag": a["etag"], "frame_h": a["frame_h"]}
            levels.append(entry)
    digest = hashlib.sha1(json.dumps(levels, sort_keys=True).encode()).hexdigest()[:12]
    return {"set_id": set_id, "manifest_etag": digest, "level_count": len(levels), "levels": levels}


# --------------------------------------------------------------------------- releases
def list_releases() -> list[dict]:
    return _rows(db.query("SELECT * FROM releases ORDER BY created_at DESC"))


def add_release(version: str, pck_rel: str, sha256: str, size: int, notes: str | None, make_current: bool) -> dict:
    with db.tx() as c:
        if make_current:
            c.execute("UPDATE releases SET is_current = 0")
        c.execute("INSERT OR REPLACE INTO releases(version, pck_path, sha256, size, notes, is_current) VALUES (?, ?, ?, ?, ?, ?)",
                  (version, pck_rel, sha256, size, notes, 1 if make_current else 0))
    return _row(db.one("SELECT * FROM releases WHERE version = ?", (version,)))  # type: ignore[return-value]


def set_current_release(version: str) -> None:
    with db.tx() as c:
        c.execute("UPDATE releases SET is_current = 0")
        c.execute("UPDATE releases SET is_current = 1 WHERE version = ?", (version,))


def current_release(base_url: str = "/files") -> dict | None:
    r = _row(db.one("SELECT * FROM releases WHERE is_current = 1"))
    if r:
        r["pck_url"] = f"{base_url}/{r['pck_path']}"
    return r


# --------------------------------------------------------------------------- live state (in-memory)
_live: dict[str, Any] = {"session_active": False, "updated_at": 0.0}


def set_live(state: dict) -> dict:
    _live.update(state)
    _live["updated_at"] = time.time()
    return dict(_live)


def get_live() -> dict:
    return dict(_live)
