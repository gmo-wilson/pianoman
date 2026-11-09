#!/usr/bin/env python3
"""
Import v1 data (pi/*.json) into the v2 SQLite store.

    PIANO_DATA_DIR=/var/lib/piano-timer python3 migrate_v1.py ../pi

Safe to re-run: students/lessons/songs/sessions are upserted by id/name,
practice days keep the max seconds, completed flags are never cleared.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from app import config, db, repo


def _load(p: Path, default):
    if not p.exists():
        return default
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def migrate(v1_dir: Path) -> dict:
    config.ensure_dirs()
    db.connect()
    report: dict[str, int] = {}

    # -- settings
    cfg = _load(v1_dir / "config.json", {})
    patch = {}
    if "goal_minutes" in cfg:
        patch["goal_minutes"] = cfg["goal_minutes"]
    if "metronome" in cfg:
        patch["metronome"] = cfg["metronome"]
    if patch:
        repo.set_settings(patch)
    report["settings"] = len(patch)

    # -- students (config.players ∪ progress keys ∪ session players)
    progress = _load(v1_dir / "progress.json", {})
    sessions = _load(v1_dir / "sessions.json", [])
    names = list(cfg.get("players", []))
    for n in list(progress.keys()) + [s.get("player") for s in sessions]:
        if n and n != "Guest" and n not in names:
            names.append(n)
    created = 0
    for name in names:
        if not repo.get_student_by_name(name):
            repo.create_student(name)
            created += 1
    report["students_created"] = created

    # -- practice days + buddy overrides
    days = 0
    for name, p in progress.items():
        st = repo.get_student_by_name(name)
        if not st:
            continue
        goal = float(repo.goal_seconds())
        for d in p.get("history", []):
            # history = days where the goal was reached; v1 didn't keep the exact seconds, so store the goal
            repo.record_progress(st["id"], seconds=goal, day=d)
            days += 1
        if p.get("date") and p.get("time"):
            repo.record_progress(st["id"], seconds=float(p["time"]), day=p["date"])
            days += 1
        t = p.get("tamagotchi") or {}
        if t:
            repo.update_student(st["id"], {
                "forced_level": t.get("version"),
                "forced_mood": t.get("forced_mood"),
                "forced_streak": t.get("forced_streak"),
                "base_color": t.get("base_color"),
                "fed_date": t.get("fed_date"),
            })
    report["practice_days"] = days

    # -- lessons (v1 "classes")
    classes = _load(v1_dir / "classes.json", [])
    for c in classes:
        chords = c.get("chords") or []
        # v1 stored chords as [{"name":..,"shape":[]}] in classes and ["Am", ..] in songs → keep names only
        chord_names = [ch["name"] if isinstance(ch, dict) else ch for ch in chords]
        repo.upsert_lesson({"id": c.get("id"), "name": c.get("name", "Lesson"), "chords": chord_names,
                            "midi_events": c.get("midi_events") or [], "source_song_id": c.get("source_song_id")})
    report["lessons"] = len(classes)

    # -- songs (+ copy .mid files)
    songs = _load(v1_dir / "songs.json", [])
    for s in songs:
        fn = s.get("filename")
        if fn and (v1_dir / "songs" / fn).exists():
            shutil.copy2(v1_dir / "songs" / fn, config.SONGS_DIR / fn)
        repo.upsert_song(s)
    report["songs"] = len(songs)

    # -- sessions
    for s in sessions:
        repo.save_session(s)
    report["sessions"] = len(sessions)

    # -- make sure a default sprite set exists
    if repo.default_sprite_set_id() is None:
        repo.create_sprite_set("Default", make_default=True)
        report["sprite_set_created"] = 1

    return report


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "../pi").resolve()
    if not src.exists():
        sys.exit(f"v1 folder not found: {src}")
    print(f"Importing from {src} into {config.DB_PATH}")
    for k, v in migrate(src).items():
        print(f"  {k:22s} {v}")
    print("done.")
