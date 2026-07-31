-- 011_student_identity.sql
-- Wires the (previously dormant) identity-switch slice onto a live path.
-- Tracks the last-seen spelling + classCode per canonical student, advancing only
-- forward in event time. On each proactive tick the daemon compares a student's
-- newest event identity against this last-seen row; a change records a switch_events
-- row (009) via detect_switches. Forward-only advance makes it idempotent and stops
-- the two spellings of one student from oscillating a switch every tick.
BEGIN;

CREATE TABLE IF NOT EXISTS event_logs.student_identity (
    canon_id TEXT PRIMARY KEY,             -- canon_id() of the studentID (case/space folded)
    last_student_id TEXT NOT NULL,         -- most-recent spelling seen
    last_class_code TEXT,                  -- most-recent classCode seen
    last_event_ts TIMESTAMPTZ NOT NULL,    -- event_ts of that most-recent event
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotency belt-and-suspenders: a tie on last_event_ts across spellings can't
-- double-write the same switch.
ALTER TABLE event_logs.switch_events
    ADD CONSTRAINT switch_events_unique
    UNIQUE (student_id, session_id, switch_kind, from_value, to_value);

COMMIT;
