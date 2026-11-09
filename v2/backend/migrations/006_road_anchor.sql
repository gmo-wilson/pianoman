-- Admin can place a student at a position on the road; history before the anchor day is ignored.
ALTER TABLE students ADD COLUMN road_anchor_date TEXT;      -- YYYY-MM-DD: walking resumes from this day (inclusive)
ALTER TABLE students ADD COLUMN road_anchor_steps INTEGER;  -- steps at the start of that day
