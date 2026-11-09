-- A level's art is a set of separately uploaded animations (one sheet each), not one tagged atlas.
CREATE TABLE IF NOT EXISTS sprite_animations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level_id    INTEGER NOT NULL REFERENCES sprite_levels(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,                 -- idle_happy | idle_hungry | idle_sad | dance | evolve | poke | eat
    atlas_path  TEXT NOT NULL,
    frames_path TEXT NOT NULL,
    frame_count INTEGER NOT NULL,
    frame_w     INTEGER NOT NULL,
    frame_h     INTEGER NOT NULL,
    etag        TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (level_id, name)
);

-- Carry over legacy single-atlas levels as one "idle_happy" entry pointing at the same files.
INSERT INTO sprite_animations(level_id, name, atlas_path, frames_path, frame_count, frame_w, frame_h, etag)
    SELECT id, 'idle_happy', atlas_path, COALESCE(frames_path, replace(atlas_path, 'atlas.png', 'frames.json')), 0, 0, 0, COALESCE(etag, 'legacy')
    FROM sprite_levels WHERE atlas_path IS NOT NULL;
