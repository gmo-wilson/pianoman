-- The kiosk block saved by older admin builds carried the previous default of 600 s; the feature shipped with 60 s.
UPDATE settings SET value = json_set(value, '$.idle_sleep_seconds', 60)
 WHERE key = 'kiosk' AND json_extract(value, '$.idle_sleep_seconds') = 600;
