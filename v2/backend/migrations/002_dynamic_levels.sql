-- Levels become an editable, unbounded list per sprite set.
--  * stable `id` per level (files live under sprites/<set>/<level_id>/ so reordering never breaks paths)
--  * no 1..32 CHECK; `level` is the 1-based position in the ladder, kept dense by the repo layer
CREATE TABLE sprite_levels_new (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id       INTEGER NOT NULL REFERENCES sprite_sets(id) ON DELETE CASCADE,
    level        INTEGER NOT NULL CHECK (level >= 1),
    display_name TEXT,
    color        TEXT,
    atlas_path   TEXT,
    frames_path  TEXT,
    etag         TEXT,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (set_id, level)
);
INSERT INTO sprite_levels_new (set_id, level, display_name, color, atlas_path, frames_path, etag, updated_at)
    SELECT set_id, level, display_name, color, atlas_path, frames_path, etag, updated_at
    FROM sprite_levels ORDER BY set_id, level;
DROP TABLE sprite_levels;
ALTER TABLE sprite_levels_new RENAME TO sprite_levels;
CREATE INDEX IF NOT EXISTS idx_sprite_levels_set ON sprite_levels(set_id, level);
