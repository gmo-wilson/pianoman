"""
Runner mini-game rules (server-authoritative so the kiosk can't be tricked):

  * Unlock: the student has completed today's practice goal.
    (To require an actual evolution instead, change `unlocked` below to `status["can_evolve"]`.)
  * `runs_per_day` base runs (default 3) per completed practice day.
  * One bonus run when, after the last base run, the student practices `bonus_minutes` (default 10) more.
    The anchor is the seconds practiced at the moment the 3rd run was recorded.
  * Leaderboard: best score per student, over all time / this week / today.
"""
from __future__ import annotations

import datetime as _dt

from . import db, repo


def _settings() -> tuple[int, int]:
    s = repo.get_settings().get("game", {}) or {}
    return int(s.get("runs_per_day", 3)), int(s.get("bonus_minutes", 10))


def _credits_row(student_id: int, day: str) -> dict:
    r = db.one("SELECT * FROM game_credits WHERE student_id = ? AND day = ?", (student_id, day))
    return dict(r) if r else {"student_id": student_id, "day": day, "used": 0, "bonus_anchor_s": None, "bonus_used": 0}


def credits(student: dict, today: _dt.date | None = None) -> dict:
    """Everything the kiosk needs to decide what to offer."""
    today = today or _dt.date.today()
    day = today.isoformat()
    runs_per_day, bonus_minutes = _settings()
    status = repo.buddy_status(student, today)
    row = _credits_row(student["id"], day)
    practiced = repo.today_seconds(student["id"], day)

    unlocked = bool(status["today_completed"])
    base_left = max(0, runs_per_day - int(row["used"]))
    bonus_target = None
    bonus_unlocked = False
    bonus_available = False
    if row["bonus_anchor_s"] is not None and not row["bonus_used"]:
        bonus_target = float(row["bonus_anchor_s"]) + bonus_minutes * 60
        bonus_unlocked = practiced >= bonus_target
        bonus_available = True
    remaining = base_left + (1 if bonus_unlocked else 0)
    return {
        "student_id": student["id"],
        "day": day,
        "unlocked": unlocked,
        "runs_per_day": runs_per_day,
        "used": int(row["used"]),
        "base_remaining": base_left,
        "bonus_minutes": bonus_minutes,
        "bonus_available": bonus_available,            # base runs exhausted, bonus not yet used
        "bonus_unlocked": bonus_unlocked,              # extra practice done → one more run
        "bonus_used": bool(row["bonus_used"]),
        "bonus_target_seconds": bonus_target,          # kiosk shows progress toward this in a bonus session
        "practiced_today_seconds": practiced,
        "remaining": remaining if unlocked else 0,
        "can_evolve": status["can_evolve"],
        "level": status["level"],
    }


def record_run(student: dict, score: int, distance: int | None = None, duration_s: float | None = None,
               today: _dt.date | None = None) -> dict:
    today = today or _dt.date.today()
    day = today.isoformat()
    c = credits(student, today)
    if not c["unlocked"]:
        raise PermissionError("finish today's practice first")
    if c["remaining"] <= 0:
        raise PermissionError("no runs left today")
    runs_per_day, _ = _settings()
    is_bonus = c["base_remaining"] == 0
    with db.tx() as conn:
        conn.execute("INSERT INTO game_credits(student_id, day) VALUES (?, ?) ON CONFLICT DO NOTHING", (student["id"], day))
        if is_bonus:
            conn.execute("UPDATE game_credits SET bonus_used = 1 WHERE student_id = ? AND day = ?", (student["id"], day))
        else:
            conn.execute("UPDATE game_credits SET used = used + 1 WHERE student_id = ? AND day = ?", (student["id"], day))
            if c["used"] + 1 >= runs_per_day:
                # last base run → arm the bonus: anchor at the seconds practiced right now
                conn.execute("UPDATE game_credits SET bonus_anchor_s = ? WHERE student_id = ? AND day = ? AND bonus_anchor_s IS NULL",
                             (c["practiced_today_seconds"], student["id"], day))
        cur = conn.execute(
            "INSERT INTO game_runs(student_id, day, score, distance, duration_s, level, is_bonus) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (student["id"], day, int(score), distance, duration_s, c["level"], 1 if is_bonus else 0))
        run_id = cur.lastrowid
    best = db.one("SELECT MAX(score) AS s FROM game_runs WHERE student_id = ?", (student["id"],))["s"]
    rank = db.one("SELECT COUNT(*) + 1 AS r FROM (SELECT student_id, MAX(score) AS s FROM game_runs GROUP BY student_id) "
                  "WHERE s > ?", (best,))["r"]
    return {"run_id": run_id, "score": int(score), "is_bonus": is_bonus, "personal_best": best,
            "new_personal_best": int(score) >= best, "rank": rank, "credits": credits(student, today)}


def leaderboard(period: str = "all", limit: int = 10, today: _dt.date | None = None) -> dict:
    today = today or _dt.date.today()
    where, params = "", []
    if period == "today":
        where, params = "WHERE r.day = ?", [today.isoformat()]
    elif period == "week":
        start = today - _dt.timedelta(days=today.weekday())
        where, params = "WHERE r.day >= ?", [start.isoformat()]
    rows = db.query(
        f"""SELECT s.id AS student_id, s.name, s.color, MAX(r.score) AS best, COUNT(r.id) AS runs,
                   MAX(r.created_at) AS last_run
            FROM game_runs r JOIN students s ON s.id = r.student_id {where}
            GROUP BY s.id ORDER BY best DESC, last_run ASC LIMIT ?""", (*params, limit))
    recent = db.query(
        f"""SELECT r.id, r.student_id, s.name, r.score, r.day, r.is_bonus, r.level, r.created_at
            FROM game_runs r JOIN students s ON s.id = r.student_id {where}
            ORDER BY r.created_at DESC LIMIT ?""", (*params, limit))
    return {"period": period, "entries": [dict(r) for r in rows], "recent": [dict(r) for r in recent]}


def student_runs(student_id: int, limit: int = 50) -> list[dict]:
    return [dict(r) for r in db.query("SELECT * FROM game_runs WHERE student_id = ? ORDER BY created_at DESC LIMIT ?",
                                      (student_id, limit))]


def delete_run(run_id: int) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM game_runs WHERE id = ?", (run_id,))


def reset_credits(student_id: int, day: str | None = None) -> None:
    """Admin: give the student their runs back for the day."""
    day = day or _dt.date.today().isoformat()
    with db.tx() as c:
        c.execute("DELETE FROM game_credits WHERE student_id = ? AND day = ?", (student_id, day))
