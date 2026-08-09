-- 013_ingest_cursor.sql
-- Move the Invite Hub sync cursor out of a bind-mounted JSON file and into
-- Postgres. A DB row can never drift from a container mount path (the bug behind
-- migration 012's duplicate mess) and it lives in the same store as the data it
-- tracks.
--
-- The service (services/logsync.py) reads and writes this row. Only full-catalog
-- syncs advance it -- the trigger daemon and the boot warm-up -- while per-student
-- freshness fetches from the request path are cursor-neutral. The standalone
-- vex-fetch-logs CLI keeps its own --state-file and is unaffected.
--
-- Seed from the data itself so cutover is seamless: the newest source_log_id and
-- event_ts already in parsed_events are where ingestion left off, so the first
-- post-deploy sync resumes incrementally instead of re-draining history.
BEGIN;

CREATE TABLE IF NOT EXISTS event_logs.ingest_cursor (
    name TEXT PRIMARY KEY,
    last_source_log_id BIGINT,
    last_event_time TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO event_logs.ingest_cursor (name, last_source_log_id, last_event_time)
SELECT 'invite_hub',
       (SELECT max(source_log_id) FROM event_logs.parsed_events),
       (SELECT max(event_ts) FROM event_logs.parsed_events)
ON CONFLICT (name) DO NOTHING;

COMMIT;
