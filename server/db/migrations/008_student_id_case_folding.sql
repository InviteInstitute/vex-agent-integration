-- 008_student_id_case_folding.sql
-- Case-insensitive student identity (ported from lm-dashboard's canon_id model).
-- VEX studentIDs are handles sometimes typed in different casing (cobra3 vs Cobra3);
-- without folding, those land as two students in every daemon scope query. This adds
-- a functional index on lower(student_id) so all_students and lookups by canonical id
-- are fast, and a generated column for the canonical key where helpful.
BEGIN;

CREATE INDEX IF NOT EXISTS idx_parsed_events_student_lower_ts
    ON event_logs.parsed_events (lower(student_id), event_ts);

COMMIT;
