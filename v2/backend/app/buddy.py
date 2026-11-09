"""
Buddy "road" rules — stateless, computed from practice history every time.

  * Each day the goal was completed            → +1 step
  * Each day since the first practice with no
    completed goal (yesterday and earlier)     → −1 step, floor 0
  * Today counts only once it is completed.
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


def steps_until(completed: set[_dt.date], upto: _dt.date) -> int:
    """Walk the road from the first completed day through `upto` (inclusive)."""
    if not completed:
        return 0
    day = min(completed)
    steps = 0
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
) -> dict:
    today = today or _dt.date.today()
    overrides = overrides or {}
    completed = set(completed_dates)
    max_level = max(1, int(max_level))
    spl = max(1, int(steps_per_level))

    today_completed = (today in completed) or (today_seconds >= goal_seconds)
    if today_completed:
        completed.add(today)
    else:
        completed.discard(today)

    yesterday = today - _dt.timedelta(days=1)
    steps_yesterday = steps_until(completed, yesterday)                 # road position when today began
    steps = steps_until(completed, today) if today_completed else steps_yesterday
    level = level_for(steps, spl, max_level)
    prev_level = level_for(steps_yesterday, spl, max_level)
    evolved_today = today_completed and level > prev_level

    # did the road move backwards at the start of today (yesterday was missed)?
    before_yesterday = steps_until(completed, yesterday - _dt.timedelta(days=1))
    lost_step_yesterday = bool(completed) and yesterday not in completed and steps_yesterday < before_yesterday
    devolved = lost_step_yesterday and level_for(before_yesterday, spl, max_level) > prev_level

    streak = 0
    d = today if today_completed else yesterday
    while d in completed:
        streak += 1
        d -= _dt.timedelta(days=1)
    days_since = (today - max(completed)).days if completed else 999

    # admin override
    forced_level = overrides.get("forced_level")
    if forced_level:
        try:
            v = int(forced_level)
            if 1 <= v <= max_level:
                level = v
        except (TypeError, ValueError):
            pass

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
        "forced_level": forced_level,
    }
