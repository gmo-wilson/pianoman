"""Stdlib-only tests: buddy rules, repo/SQLite, sprite ingestion, MIDI parsing, v1 migration.

    cd v2/backend && python3 -m unittest -v
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

_tmp = tempfile.mkdtemp(prefix="piano-v2-test-")
os.environ["PIANO_DATA_DIR"] = _tmp

from app import buddy, config, db, game, midi_parse, repo, sprites  # noqa: E402

D = dt.date


class RoadRules(unittest.TestCase):
    T = D(2026, 11, 9)

    def days(self, *offsets):
        return {self.T - dt.timedelta(days=o) for o in offsets}

    def test_fresh_student(self):
        s = buddy.compute_status(set(), today=self.T)
        self.assertEqual((s["steps"], s["level"], s["steps_to_next"], s["today_completed"]), (0, 1, 3, False))

    def test_three_practices_reach_first_milestone(self):
        # two completed days before, today completed → 3 steps → level 2, transformation today
        s = buddy.compute_status(self.days(1, 2), today_seconds=900, today=self.T)
        self.assertEqual((s["steps"], s["level"], s["prev_level"], s["evolved_today"]), (3, 2, 1, True))
        self.assertEqual((s["steps_in_level"], s["steps_to_next"]), (0, 3))

    def test_today_not_done_yet_keeps_yesterdays_position(self):
        s = buddy.compute_status(self.days(1, 2), today=self.T)
        self.assertEqual((s["steps"], s["level"], s["evolved_today"]), (2, 1, False))

    def test_missed_day_moves_one_step_back(self):
        # practised 5 days ago..2 days ago (4 steps), missed yesterday → 3 steps, today not done
        s = buddy.compute_status(self.days(2, 3, 4, 5), today=self.T)
        self.assertEqual((s["steps"], s["level"], s["lost_step_yesterday"], s["devolved"]), (3, 2, True, False))
        # practised 3 days (3 steps = level 2), missed yesterday → 2 steps → devolved to level 1
        s = buddy.compute_status(self.days(2, 3, 4), today=self.T)
        self.assertEqual((s["steps"], s["level"], s["devolved"]), (2, 1, True))

    def test_steps_never_below_zero_and_gaps_accumulate(self):
        # one practice 10 days ago, nothing since → 0 steps, level 1
        s = buddy.compute_status(self.days(10), today=self.T)
        self.assertEqual((s["steps"], s["level"]), (0, 1))
        # 6 practices, then 2 missed, then today → 6 - 2 + 1 = 5 steps → level 2, 2 steps into it
        s = buddy.compute_status(self.days(3, 4, 5, 6, 7, 8), today_seconds=900, today=self.T)
        self.assertEqual((s["steps"], s["level"], s["steps_in_level"]), (5, 2, 2))

    def test_level_cap_and_custom_milestone_size(self):
        done = self.days(*range(1, 60))
        s = buddy.compute_status(done, today_seconds=900, today=self.T, max_level=5)
        self.assertEqual((s["level"], s["at_top"], s["steps_to_next"]), (5, True, 0))
        s = buddy.compute_status(done, today_seconds=900, today=self.T, max_level=100, steps_per_level=5)
        self.assertEqual((s["steps"], s["level"]), (60, 13))

    def test_forced_level_override(self):
        s = buddy.compute_status(set(), today=self.T, overrides={"forced_level": 7}, max_level=10)
        self.assertEqual(s["level"], 7)


class RepoAndMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.close()
        for p in Path(_tmp).glob("*"):
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        config.ensure_dirs()
        db.connect()
        # Build a fake v1 folder mirroring the real layout
        cls.v1 = Path(_tmp) / "v1"
        (cls.v1 / "songs").mkdir(parents=True)
        (cls.v1 / "config.json").write_text(json.dumps({"goal_minutes": 15, "players": ["Eva", "Mara", "Willy"],
                                                         "metronome": {"slow": 60, "normal": 80, "fast": 120}}))
        (cls.v1 / "progress.json").write_text(json.dumps({
            "Eva": {"date": "2026-10-16", "time": 0.0, "history": ["2026-10-13"]},
            "Mara": {"date": "2026-11-09", "time": 420.5, "history": ["2026-11-07", "2026-11-08"],
                     "tamagotchi": {"fed_date": "2026-11-08", "base_color": "#ff00ff"}},
        }))
        (cls.v1 / "classes.json").write_text(json.dumps([{"id": "demo-fur-elise", "name": "Für Elise",
                                                           "chords": [{"name": "Am", "shape": []}, {"name": "E", "shape": []}],
                                                           "midi_events": [{"time": 0, "type": "on", "note": 76, "vel": 85}]}]))
        (cls.v1 / "songs.json").write_text(json.dumps([{"id": "demo-canon", "title": "Canon in D", "composer": "Pachelbel",
                                                         "filename": "canon.mid", "file_size": 3, "duration_seconds": 18.5,
                                                         "notes_count": 28, "track_count": 1, "chords": ["D", "A"],
                                                         "midi_events": [{"time": 0, "type": "on", "note": 50, "vel": 75}],
                                                         "upload_date": "2026-10-16 15:30"}]))
        (cls.v1 / "songs" / "canon.mid").write_bytes(b"abc")
        (cls.v1 / "sessions.json").write_text(json.dumps([{
            "id": "s1", "player": "Mara", "date": "2026-11-08", "start_time": 1762600000.0, "end_time": 1762600900.0,
            "mode": "free", "class_name": None, "events": [{"t": 0.1, "type": "on", "note": 60, "vel": 90}],
            "chords_played": {"C": 2}, "goal_reached": True, "duration_seconds": 900.0,
            "accumulated_practice_time": 905.0, "total_notes": 1}]))
        sys.path.insert(0, str(HERE.parent))
        import migrate_v1
        cls.report = migrate_v1.migrate(cls.v1)

    def test_01_report(self):
        self.assertEqual(self.report["students_created"], 3)
        self.assertEqual(self.report["lessons"], 1)
        self.assertEqual(self.report["songs"], 1)
        self.assertEqual(self.report["sessions"], 1)

    def test_02_settings(self):
        self.assertEqual(repo.get_settings()["metronome"]["fast"], 120)
        self.assertEqual(repo.goal_seconds(), 900)

    def test_03_buddy_road_from_v1_history(self):
        mara = repo.get_student_by_name("Mara")
        s = repo.buddy_status(mara, today=D(2026, 11, 9))
        # completed Nov 7 + Nov 8 → 2 steps, today not finished (420s < 900s) → level 1, one step to go
        self.assertEqual((s["steps"], s["level"], s["steps_to_next"], s["streak"]), (2, 1, 1, 2))
        self.assertAlmostEqual(s["time_practiced_today"], 420.5)
        eva = repo.get_student_by_name("Eva")
        e = repo.buddy_status(eva, today=D(2026, 11, 9))
        self.assertEqual((e["steps"], e["level"]), (0, 1))

    def test_04_progress_is_idempotent_and_completes(self):
        mara = repo.get_student_by_name("Mara")
        repo.record_progress(mara["id"], 300, day="2026-11-09")       # lower → ignored
        self.assertAlmostEqual(repo.today_seconds(mara["id"], "2026-11-09"), 420.5)
        repo.record_progress(mara["id"], 900, day="2026-11-09")       # reaches goal → 3rd step → milestone
        s = repo.buddy_status(mara, today=D(2026, 11, 9))
        self.assertEqual((s["steps"], s["level"], s["evolved_today"]), (3, 2, True))

    def test_05_sessions_roundtrip(self):
        lst = repo.list_sessions()
        self.assertEqual(len(lst), 1)
        full = repo.get_session("s1")
        self.assertEqual(full["events"][0]["note"], 60)
        self.assertEqual(full["chords_played"], {"C": 2})
        self.assertEqual(full["student_name"], "Mara")

    def test_06_lessons_and_songs(self):
        l = repo.get_lesson("demo-fur-elise")
        self.assertEqual(l["chords"], ["Am", "E"])
        self.assertTrue((config.SONGS_DIR / "canon.mid").exists())
        self.assertEqual(repo.list_songs()[0]["title"], "Canon in D")

    def test_07_rerun_migration_is_safe(self):
        import migrate_v1
        migrate_v1.migrate(self.v1)
        self.assertEqual(len(repo.list_students()), 3)
        self.assertEqual(len(repo.list_sessions()), 1)

    def test_08_stats(self):
        mara = repo.get_student_by_name("Mara")
        st = repo.student_stats(mara["id"])
        self.assertGreaterEqual(st["best_streak"], 2)
        self.assertEqual(st["sessions"], 1)


class SpritePipeline(unittest.TestCase):
    def _blank_png(self, w, h):
        from PIL import Image
        import io
        buf = io.BytesIO(); Image.new("RGBA", (w, h)).save(buf, "PNG"); return buf.getvalue()

    def test_user_generator_format_with_trim(self):
        """The real export from the sprite generator: 25 frames, 256px grid, trim boxes, meta.fps."""
        raw = json.loads((HERE / "fixture_blob_idle.json").read_text())
        png = self._blank_png(1280, 1280)
        c = sprites.normalise_animation(raw, png, "idle")
        self.assertEqual(len(c["frames"]), 25)
        self.assertTrue(c["loop"])
        self.assertAlmostEqual(c["fps"], 10.716)
        self.assertEqual(c["frames"][0]["ms"], 93)                       # 1 frame @ 10.716 fps
        # cropped to the union of trims (+2px pad): x 86..170, y 95..163
        f0 = c["frames"][0]
        self.assertEqual((f0["x"], f0["y"], f0["w"], f0["h"]), (84, 93, 88, 72))
        f6 = c["frames"][6]                                              # second row, second column
        self.assertEqual((f6["x"], f6["y"]), (256 + 84, 256 + 93))
        # frames keep numeric order even though JSON keys are strings
        self.assertEqual(c["frames"][10]["x"], 0 + 84)

    def test_store_single_animation_and_manifest(self):
        set_id = repo.default_sprite_set_id()
        lvl3 = repo.list_sprite_levels(set_id)[2]
        raw = json.loads((HERE / "fixture_blob_idle.json").read_text())
        row = sprites.store_animation(lvl3["id"], "idle_happy", self._blank_png(1280, 1280), json.dumps(raw).encode())   # alias → idle
        self.assertEqual((row["name"], row["frame_count"]), ("idle", 25))
        self.assertIn(f"/{lvl3['id']}/idle/", row["atlas_path"])
        lv = next(l for l in repo.list_sprite_levels(set_id) if l["id"] == lvl3["id"])
        self.assertTrue(lv["ready"])
        m = repo.sprite_manifest(set_id)
        entry = next(l for l in m["levels"] if l["id"] == lvl3["id"])
        self.assertIn("idle", entry["animations"])
        self.assertNotIn("dance", entry["animations"])                   # optional, falls back on the kiosk
        # replace + delete
        sprites.store_animation(lvl3["id"], "dance", self._blank_png(1280, 1280), json.dumps(raw).encode())
        self.assertEqual(len(repo.list_sprite_levels(set_id)[2]["animations"]), 2)
        self.assertTrue(repo.delete_sprite_animation(lvl3["id"], "dance"))
        self.assertFalse(repo.delete_sprite_animation(lvl3["id"], "dance"))

    def test_tagged_aseprite_is_split(self):
        png, frames = sprites.make_placeholder(1, "#38bdf8", "idle")
        raw = json.loads(frames)
        raw["meta"].pop("fps")
        for f in raw["frames"].values():
            f["duration"] = 120
        raw["meta"]["frameTags"] = [{"name": "Front", "from": 0, "to": 1}, {"name": "dance", "from": 2, "to": 3},
                                    {"name": "unknown_tag", "from": 0, "to": 3}]
        parts = sprites.split_tagged(raw, png)
        self.assertEqual(set(parts), {"idle", "dance"})
        self.assertEqual(parts["dance"]["frames"][0]["ms"], 120)

    def test_placeholders_cover_all_animations(self):
        set_id = repo.default_sprite_set_id()
        lvl = repo.list_sprite_levels(set_id)[0]
        for name in sprites.ANIMATIONS:
            png, fr = sprites.make_placeholder(1, "#38bdf8", name)
            sprites.store_animation(lvl["id"], name, png, fr)
        anims = repo.list_sprite_levels(set_id)[0]["animations"]
        self.assertEqual(set(anims), set(sprites.ANIMATIONS))
        spec = json.loads((config.DATA_DIR / anims["jump"]["frames_path"]).read_text())
        self.assertFalse(spec["loop"])

    def test_rejects_bad_input(self):
        with self.assertRaises(sprites.SpriteError):
            sprites.normalise_animation({"frames": {}}, self._blank_png(8, 8), "idle")
        with self.assertRaises(sprites.SpriteError):
            sprites.normalise_animation({"frames": {"0": {"x": 0, "y": 0, "w": 64, "h": 64}}}, self._blank_png(8, 8), "idle")


class DynamicLevels(unittest.TestCase):
    def setUp(self):
        self.set = repo.create_sprite_set(f"Ladder {self._testMethodName}", seed_defaults=False)
        self.sid = self.set["id"]

    def test_add_edit_move_delete(self):
        self.assertEqual(repo.level_count(self.sid), 1)
        b = repo.add_sprite_level(self.sid, "Bee", "#ffcc00")
        c = repo.add_sprite_level(self.sid, "Cat", "#ff00cc")
        a2 = repo.add_sprite_level(self.sid, "Inserted", "#00ccff", position=2)     # between 1 and Bee
        names = [l["display_name"] for l in repo.list_sprite_levels(self.sid)]
        self.assertEqual(names, ["Baby Bean (Do)", "Inserted", "Bee", "Cat"])
        self.assertEqual([l["level"] for l in repo.list_sprite_levels(self.sid)], [1, 2, 3, 4])

        repo.update_sprite_level(b["id"], {"display_name": "Bumblebee", "color": "#123456"})
        self.assertEqual(repo.get_sprite_level(b["id"])["display_name"], "Bumblebee")

        repo.move_sprite_level(c["id"], 1)
        names = [l["display_name"] for l in repo.list_sprite_levels(self.sid)]
        self.assertEqual(names, ["Cat", "Baby Bean (Do)", "Inserted", "Bumblebee"])

        # art survives reordering because paths are keyed by level id
        png, frames = sprites.make_placeholder(2, "#ffcc00", "idle")
        path = sprites.store_animation(b["id"], "idle", png, frames)["atlas_path"]
        repo.move_sprite_level(b["id"], 1)
        anims = next(l for l in repo.list_sprite_levels(self.sid) if l["id"] == b["id"])["animations"]
        self.assertEqual(anims["idle"]["atlas_path"], path)
        self.assertTrue((config.DATA_DIR / path).exists())

        self.assertTrue(repo.delete_sprite_level(a2["id"]))
        self.assertEqual([l["level"] for l in repo.list_sprite_levels(self.sid)], [1, 2, 3])
        self.assertTrue(repo.delete_sprite_level(b["id"]))
        self.assertFalse((config.DATA_DIR / path).exists())        # files removed with the level

        # cannot delete the last one
        for l in repo.list_sprite_levels(self.sid)[1:]:
            repo.delete_sprite_level(l["id"])
        self.assertFalse(repo.delete_sprite_level(repo.list_sprite_levels(self.sid)[0]["id"]))

    def test_buddy_caps_at_set_size_and_uses_set_names(self):
        repo.add_sprite_level(self.sid, "Top", "#ffffff")
        st = repo.create_student("Ladder Kid", sprite_set=self.sid)
        for i in range(1, 15):
            repo.record_progress(st["id"], 900, day=(D(2026, 11, 9) - dt.timedelta(days=i)).isoformat())
        repo.record_progress(st["id"], 900, day="2026-11-09")
        s = repo.buddy_status(repo.get_student(st["id"]), today=D(2026, 11, 9))
        self.assertEqual((s["level"], s["max_level"], s["level_name"], s["steps"]), (2, 2, "Top", 15))
        self.assertFalse(s["evolved_today"])

    def test_delete_level_clamps_forced_levels(self):
        repo.add_sprite_level(self.sid, "B"); top = repo.add_sprite_level(self.sid, "C")
        st = repo.create_student("Forced Kid", sprite_set=self.sid)
        repo.update_student(st["id"], {"forced_level": 3})
        repo.delete_sprite_level(top["id"])
        self.assertEqual(repo.get_student(st["id"])["forced_level"], 2)

    def test_set_delete_rules(self):
        self.assertFalse(repo.delete_sprite_set(repo.default_sprite_set_id()))
        self.assertTrue(repo.delete_sprite_set(self.sid))


class MigrationUpgrade(unittest.TestCase):
    def test_001_then_002_preserves_levels(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript((config.MIGRATIONS_DIR / "001_init.sql").read_text())
        conn.execute("INSERT INTO sprite_sets(name, is_default) VALUES ('old', 1)")
        conn.execute("INSERT INTO sprite_levels(set_id, level, display_name, color, atlas_path) VALUES (1, 1, 'A', '#111', 'sprites/1/01/atlas.png')")
        conn.execute("INSERT INTO sprite_levels(set_id, level, display_name, color) VALUES (1, 2, 'B', '#222')")
        applied = db.migrate(conn)
        self.assertIn(2, applied)
        rows = conn.execute("SELECT id, level, display_name, atlas_path FROM sprite_levels ORDER BY level").fetchall()
        self.assertEqual([(r["level"], r["display_name"]) for r in rows], [(1, "A"), (2, "B")])
        self.assertEqual(rows[0]["atlas_path"], "sprites/1/01/atlas.png")   # old paths still valid
        conn.execute("INSERT INTO sprite_levels(set_id, level, display_name) VALUES (1, 33, 'beyond 32')")  # no CHECK now
        legacy = conn.execute("SELECT name, atlas_path FROM sprite_animations").fetchall()
        self.assertEqual([(r['name'], r['atlas_path']) for r in legacy], [('idle', 'sprites/1/01/atlas.png')])   # 005 renames
        conn.close()


class RunnerGame(unittest.TestCase):
    T = D(2026, 11, 9)

    def setUp(self):
        self.st = repo.create_student(f"Gamer {self._testMethodName}")
        self.sid = self.st["id"]

    def test_locked_until_goal(self):
        c = game.credits(self.st, self.T)
        self.assertFalse(c["unlocked"]); self.assertEqual(c["remaining"], 0)
        with self.assertRaises(PermissionError):
            game.record_run(self.st, 100, today=self.T)

    def test_three_runs_then_bonus_after_ten_minutes(self):
        repo.record_progress(self.sid, 900, day=self.T.isoformat())
        c = game.credits(self.st, self.T)
        self.assertEqual((c["unlocked"], c["remaining"]), (True, 3))
        for score in (120, 300, 210):
            r = game.record_run(self.st, score, today=self.T)
            self.assertFalse(r["is_bonus"])
        c = game.credits(self.st, self.T)
        self.assertEqual((c["remaining"], c["bonus_available"], c["bonus_unlocked"]), (0, True, False))
        self.assertAlmostEqual(c["bonus_target_seconds"], 900 + 600)
        with self.assertRaises(PermissionError):
            game.record_run(self.st, 50, today=self.T)
        repo.record_progress(self.sid, 900 + 599, day=self.T.isoformat())      # not yet
        self.assertFalse(game.credits(self.st, self.T)["bonus_unlocked"])
        repo.record_progress(self.sid, 900 + 600, day=self.T.isoformat())      # 10 more minutes
        c = game.credits(self.st, self.T)
        self.assertEqual((c["bonus_unlocked"], c["remaining"]), (True, 1))
        r = game.record_run(self.st, 999, today=self.T)
        self.assertTrue(r["is_bonus"]); self.assertTrue(r["new_personal_best"]); self.assertEqual(r["rank"], 1)
        c = game.credits(self.st, self.T)
        self.assertEqual((c["remaining"], c["bonus_used"]), (0, True))
        with self.assertRaises(PermissionError):
            game.record_run(self.st, 1, today=self.T)

    def test_leaderboard_best_per_student(self):
        other = repo.create_student("Rival " + self._testMethodName)
        for s in (self.st, other):
            repo.record_progress(s["id"], 900, day=self.T.isoformat())
        game.record_run(self.st, 500, today=self.T); game.record_run(self.st, 400, today=self.T)
        game.record_run(other, 450, today=self.T)
        lb = game.leaderboard("today", today=self.T)
        names = [e["name"] for e in lb["entries"]]
        self.assertEqual(names.index(self.st["name"]) < names.index(other["name"]), True)
        me = next(e for e in lb["entries"] if e["student_id"] == self.sid)
        self.assertEqual((me["best"], me["runs"]), (500, 2))
        game.reset_credits(self.sid, self.T.isoformat())
        self.assertEqual(game.credits(self.st, self.T)["remaining"], 3)


class MidiParse(unittest.TestCase):
    def _smf(self) -> bytes:
        # one track, 480 tpb: C4 on @0, E4 on @0, G4 on @0, all off @480 (one beat = 0.5 s)
        trk = bytes([
            0x00, 0x90, 60, 90, 0x00, 64, 90, 0x00, 67, 90,       # running status
            0x83, 0x60, 0x80, 60, 0, 0x00, 64, 0, 0x00, 67, 0,  # delta 480
            0x00, 0xFF, 0x2F, 0x00,
        ])
        import struct
        return b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + b"MTrk" + struct.pack(">I", len(trk)) + trk

    def test_parse_and_chords(self):
        out = midi_parse.parse_midi_bytes(self._smf())
        self.assertEqual(out["notes_count"], 3)
        self.assertAlmostEqual(out["duration_seconds"], 0.5)
        self.assertEqual(out["chords"], ["C"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
