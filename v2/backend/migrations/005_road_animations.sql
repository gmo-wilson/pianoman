-- Road model: animations are idle / dance / run / jump. Map older names, drop the rest.
UPDATE sprite_animations SET name = 'idle' WHERE name = 'idle_happy'
    AND NOT EXISTS (SELECT 1 FROM sprite_animations b WHERE b.level_id = sprite_animations.level_id AND b.name = 'idle');
DELETE FROM sprite_animations WHERE name NOT IN ('idle', 'dance', 'run', 'jump');
