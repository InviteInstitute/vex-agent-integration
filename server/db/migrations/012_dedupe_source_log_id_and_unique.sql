-- 012_dedupe_source_log_id_and_unique.sql
-- Make Invite Hub ingestion idempotent at the database.
--
-- Until now parsed_events had only a NON-unique index on source_log_id (migration
-- 003) and insert_rows did a plain INSERT, so dedup lived entirely in the sync
-- cursor plus a client-side filter. With several writers draining against one
-- cursor (boot warm-up, the per-request student-scoped sync, and the daemon),
-- duplicate source_log_ids leaked in -- roughly 15% of rows in prod.
--
-- Step 1 removes existing duplicates, keeping the earliest row (min id) per
-- source_log_id. Step 2 replaces the non-unique index with a UNIQUE constraint so
-- ON CONFLICT (source_log_id) DO NOTHING makes every future insert idempotent.
-- NULL source_log_ids (synthetic / test rows) are left untouched -- NULLs are
-- distinct under a UNIQUE constraint, so they never collide.
--
-- Idempotent: the DELETE is a no-op once deduped, DROP INDEX is guarded, and the
-- constraint is only added when absent, so re-running the whole migrations loop is
-- safe.
BEGIN;

DELETE FROM event_logs.parsed_events a
USING event_logs.parsed_events b
WHERE a.source_log_id IS NOT NULL
  AND a.source_log_id = b.source_log_id
  AND a.id > b.id;

DROP INDEX IF EXISTS event_logs.idx_parsed_events_source_log_id;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_parsed_events_source_log_id'
    ) THEN
        ALTER TABLE event_logs.parsed_events
            ADD CONSTRAINT uq_parsed_events_source_log_id UNIQUE (source_log_id);
    END IF;
END $$;

COMMIT;
