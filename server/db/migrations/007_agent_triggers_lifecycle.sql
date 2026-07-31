-- 007_agent_triggers_lifecycle.sql
-- Inactive-trigger lifecycle (ported from lm-dashboard's trigger_event model).
-- Adds the open/resolve/re-alert columns so a persistently-idle student can be
-- re-alerted after RE_ALERT_SECONDS instead of hearing from the agent exactly once
-- per session, and so a recovered student's inactive trigger is explicitly closed.
--
-- The re-alert itself does NOT need a constraint change: each re-alert uses a new
-- negative run_index (-1, -2, -3, ...), so the existing
-- UNIQUE(student_id, session_id, trigger_type, run_index) from migration 006
-- already dedupes them. These columns add visibility + the resolve-on-recovery path.
BEGIN;

ALTER TABLE event_logs.agent_triggers
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

-- Hot path for "is there an OPEN inactive trigger for this session?" (resolved_at IS NULL).
CREATE INDEX IF NOT EXISTS idx_agent_triggers_type_resolved
    ON event_logs.agent_triggers (student_id, session_id, trigger_type, resolved_at);

COMMIT;
