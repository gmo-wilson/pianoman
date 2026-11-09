"""Runtime configuration. Everything persistent lives under DATA_DIR, never in the code tree."""
from __future__ import annotations

import os
from pathlib import Path

# Production default on the Pi: /var/lib/piano-timer (created by deploy/install.sh).
# For local development: PIANO_DATA_DIR=./data
DATA_DIR = Path(os.environ.get("PIANO_DATA_DIR", "/var/lib/piano-timer")).expanduser().resolve()
DB_PATH = DATA_DIR / "piano.db"
SPRITES_DIR = DATA_DIR / "sprites"
SONGS_DIR = DATA_DIR / "songs"
RELEASES_DIR = DATA_DIR / "releases"
BACKUPS_DIR = DATA_DIR / "backups"

CODE_DIR = Path(__file__).resolve().parent.parent          # backend/
MIGRATIONS_DIR = CODE_DIR / "migrations"
ADMIN_DIR = CODE_DIR.parent / "admin"                        # v2/admin (static SPA)

HOST = os.environ.get("PIANO_HOST", "0.0.0.0")
PORT = int(os.environ.get("PIANO_PORT", "8080"))

# Optional shared secret for admin writes (sent as X-Admin-Token). Empty = open on LAN.
ADMIN_TOKEN = os.environ.get("PIANO_ADMIN_TOKEN", "")

MIDI_OUT_PORT_HINT = os.environ.get("PIANO_MIDI_OUT", "")   # substring of the MIDI port name
MIDI_IN_PORT_HINT = os.environ.get("PIANO_MIDI_IN", "")     # substring of the MIDI port name

DEFAULT_SETTINGS = {
    "goal_minutes": 15,
    "metronome": {"slow": 60, "normal": 80, "fast": 120},
    "inactivity_timeout_seconds": 300,
    "session_history_limit": 500,
    "kiosk": {"theme": "dark", "transition_ms": 320, "idle_sleep_seconds": 60, "sleep_when_piano_off": True, "screen_sleep_enabled": True},
    "game": {"runs_per_day": 3, "bonus_minutes": 10, "enabled": True},
    "road": {"steps_per_level": 3},
}


def ensure_dirs() -> None:
    for d in (DATA_DIR, SPRITES_DIR, SONGS_DIR, RELEASES_DIR, BACKUPS_DIR):
        d.mkdir(parents=True, exist_ok=True)
