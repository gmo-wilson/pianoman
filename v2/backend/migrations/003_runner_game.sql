-- "Runner" mini game: runs, daily credits and the bonus-run anchor.
CREATE TABLE IF NOT EXISTS game_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    day         TEXT NOT NULL,                 -- YYYY-MM-DD local
    score       INTEGER NOT NULL,
    distance    INTEGER,
    duration_s  REAL,
    level       INTEGER,                       -- buddy level at the time of the run
    is_bonus    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_game_runs_student_day ON game_runs(student_id, day);
CREATE INDEX IF NOT EXISTS idx_game_runs_score ON game_runs(score DESC);

-- One row per student per day once they start playing.
CREATE TABLE IF NOT EXISTS game_credits (
    student_id      INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    day             TEXT NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0,
    -- seconds practiced today at the moment the last base run was consumed; the bonus run unlocks
    -- once practice_days.seconds >= anchor + bonus_minutes*60
    bonus_anchor_s  REAL,
    bonus_used      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (student_id, day)
);
