-- Piano Timer v2 — initial schema
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL              -- JSON
);

CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    color       TEXT,
    sprite_set  INTEGER REFERENCES sprite_sets(id) ON DELETE SET NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    -- admin overrides (v1 "tamagotchi" block)
    forced_level  INTEGER,
    forced_mood   TEXT,
    forced_streak INTEGER,
    base_color    TEXT,
    fed_date      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per student per calendar day. `completed` = goal reached that day.
CREATE TABLE IF NOT EXISTS practice_days (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    day        TEXT NOT NULL,         -- YYYY-MM-DD (local)
    seconds    REAL NOT NULL DEFAULT 0,
    completed  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (student_id, day)
);

CREATE TABLE IF NOT EXISTS lessons (
    id            TEXT PRIMARY KEY,   -- uuid / v1 class id
    name          TEXT NOT NULL,
    chords        TEXT NOT NULL DEFAULT '[]',   -- JSON
    midi_events   TEXT NOT NULL DEFAULT '[]',   -- JSON
    source_song_id TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS songs (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    composer         TEXT,
    filename         TEXT,            -- relative to DATA_DIR/songs
    file_size        INTEGER,
    duration_seconds REAL,
    notes_count      INTEGER,
    track_count      INTEGER,
    chords           TEXT NOT NULL DEFAULT '[]',
    midi_events      TEXT NOT NULL DEFAULT '[]',
    uploaded_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    student_id      INTEGER REFERENCES students(id) ON DELETE SET NULL,
    student_name    TEXT NOT NULL,    -- denormalised so guest/deleted students keep history
    mode            TEXT NOT NULL DEFAULT 'free',
    lesson_id       TEXT REFERENCES lessons(id) ON DELETE SET NULL,
    lesson_name     TEXT,
    started_at      REAL NOT NULL,    -- unix seconds
    ended_at        REAL,
    duration_seconds REAL,
    practice_seconds REAL,
    total_notes     INTEGER,
    goal_reached    INTEGER NOT NULL DEFAULT 0,
    chords_played   TEXT NOT NULL DEFAULT '{}',
    events_gz       BLOB              -- gzip(JSON list of {t,type,note,vel})
);
CREATE INDEX IF NOT EXISTS idx_sessions_student_started ON sessions(student_id, started_at DESC);

CREATE TABLE IF NOT EXISTS sprite_sets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sprite_levels (
    set_id       INTEGER NOT NULL REFERENCES sprite_sets(id) ON DELETE CASCADE,
    level        INTEGER NOT NULL CHECK (level BETWEEN 1 AND 32),
    display_name TEXT,
    color        TEXT,
    atlas_path   TEXT,                -- relative to DATA_DIR
    frames_path  TEXT,
    etag         TEXT,                -- sha256 of atlas+frames, used by Godot cache
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (set_id, level)
);

CREATE TABLE IF NOT EXISTS releases (
    version    TEXT PRIMARY KEY,
    pck_path   TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    size       INTEGER NOT NULL,
    notes      TEXT,
    is_current INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
