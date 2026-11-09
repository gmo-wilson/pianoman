"""
Buddy "road" rules — stateless, computed from practice history every time.

  * Each day the goal was completed            → +1 step
  * Each day since the first practice with no
    completed goal (yesterday and earlier)     → −1 step, floor 0
  * Today counts only once it is completed.
  * Admin can set a position: (anchor_date, anchor_steps) → the walk starts there and earlier history is ignored,
    so the student keeps evolving (or stepping back) from the chosen point.
  * Every `steps_per_level` steps is a milestone: level = steps // steps_per_level + 1, capped at `max_level`
    (the number of levels in the student's sprite set). Reaching a new milestone today → `evolved_today`
    (play the transformation); falling below one → `devolved` (shown as a step back).

Pure functions, stdlib only.
"""
from __future__ import annotations

import datetime as _dt
from typing import Iterable

# Seed used when a new sprite set is created with "seed defaults".
DEFAULT_LEVELS: list[tuple[str, str]] = [
    ("Baby Bean (Do)", "#38bdf8"), ("Sprout Note (Re)", "#0284c7"), ("Starlet Antenna (Mi)", "#059669"),
    ("Clef Tuft (Fa)", "#10b981"), ("Little Bell (Sol)", "#f59e0b"), ("Metronome Pup", "#d97706"),
    ("Keyboard Cat", "#f43f5e"), ("Clef Bunny", "#a855f7"), ("Jazz Frog", "#22c55e"), ("Drummer Hamster", "#fb923c"),
    ("Boombox Bot", "#64748b"), ("Music Box Piggy", "#f472b6"), ("Vinyl DJ Penguin", "#1e293b"),
    ("Accordion Armadillo", "#b45309"), ("Synthwave Glow-Cube", "#ec4899"), ("Amadeus Bear", "#e11d48"),
    ("Rocker Hedgehog", "#8b5cf6"), ("Grand Piano Turtle", "#0d9488"), ("Opera Owl", "#6366f1"),
    ("Golden Baton Maestro", "#eab308"), ("Melody Sprite", "#38bdf8"), ("Chime Golem", "#78716c"),
    ("Harp-Winged Pegasus", "#f8fafc"), ("Crescendo Phoenix", "#ef4444"), ("Crystal Dragonette", "#06b6d4"),
    ("Starlight Seraph", "#facc15"), ("Saturn's Organist", "#818cf8"), ("Nebula Phoenix", "#c084fc"),
    ("Chrono Metronome", "#d97706"), ("Grand Rainbow Virtuoso", "#ec4899"), ("Apollo's Sun-King Lyre", "#fbbf24"),
    ("Omnichord Celestial Sovereign", "#a855f7"),
]


def steps_until(completed: set[_dt.date], upto: _dt.date,
                anchor_date: _dt.date | None = None, anchor_steps: int = 0) -> int:
    """
    Walk the road through `upto` (inclusive).
    Without an anchor: start at 0 on the first completed day.
    With an anchor (admin "set position"): start at `anchor_steps` on `anchor_date`; earlier history is ignored.
    """
    if anchor_date is not None:
        day, steps = anchor_date, max(0, int(anchor_steps))
        if upto < anchor_date:
            return steps
    else:
        if not completed:
            return 0
        day, steps = min(completed), 0
    while day <= upto:
        steps = steps + 1 if day in completed else max(0, steps - 1)
        day += _dt.timedelta(days=1)
    return steps


def level_for(steps: int, steps_per_level: int, max_level: int) -> int:
    return min(max(1, max_level), steps // max(1, steps_per_level) + 1)


def compute_status(
    completed_dates: Iterable[_dt.date],
    today_seconds: float = 0.0,
    goal_seconds: int = 900,
    today: _dt.date | None = None,
    overrides: dict | None = None,
    max_level: int = 32,
    steps_per_level: int = 3,
    anchor_date: _dt.date | None = None,
    anchor_steps: int = 0,
) -> dict:
    today = today or _dt.date.today()
    overrides = overrides or {}
    completed = set(completed_dates)
    if anchor_date is not None:
        completed = {d for d in completed if d >= anchor_date}
    max_level = max(1, int(max_level))
    spl = max(1, int(steps_per_level))

    today_completed = (today in completed) or (today_seconds >= goal_seconds)
    if today_completed:
        completed.add(today)
    else:
        completed.discard(today)

    yesterday = today - _dt.timedelta(days=1)
    walk = lambda upto: steps_until(completed, upto, anchor_date, anchor_steps)  # noqa: E731
    steps_yesterday = walk(yesterday)                                   # road position when today began
    steps = walk(today) if today_completed else steps_yesterday
    level = level_for(steps, spl, max_level)
    prev_level = level_for(steps_yesterday, spl, max_level)
    evolved_today = today_completed and level > prev_level

    # did the road move backwards at the start of today (yesterday was missed)?
    before_yesterday = walk(yesterday - _dt.timedelta(days=1))
    lost_step_yesterday = yesterday not in completed and steps_yesterday < before_yesterday
    devolved = lost_step_yesterday and level_for(before_yesterday, spl, max_level) > prev_level

    streak = 0
    d = today if today_completed else yesterday
    while d in completed:
        streak += 1
        d -= _dt.timedelta(days=1)
    days_since = (today - max(completed)).days if completed else 999

    in_milestone = steps % spl
    return {
        "steps": steps,
        "steps_per_level": spl,
        "steps_in_level": in_milestone,                               # 0..spl-1 progress toward the next milestone
        "steps_to_next": 0 if level >= max_level else spl - in_milestone,
        "level": level,
        "prev_level": prev_level,
        "max_level": max_level,
        "at_top": level >= max_level,
        "evolved_today": evolved_today,
        "can_evolve": evolved_today,                                  # kept for the kiosk's recap flow
        "devolved": devolved,
        "lost_step_yesterday": lost_step_yesterday,
        "streak": streak,
        "days_since_practice": days_since,
        "today_completed": today_completed,
        "time_practiced_today": today_seconds,
        "anchor_date": anchor_date.isoformat() if anchor_date else None,
    }
