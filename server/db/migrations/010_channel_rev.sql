-- 010_channel_rev.sql
-- O(1) change signaling for the SSE stream (ported from lm-dashboard's channel_rev
-- + pg_notify pattern). The stream reads 1 row instead of polling chat.messages every
-- 2s; a row-level trigger bumps the counter and fires pg_notify('proactive_msg', ...)
-- so a LISTENing connection wakes instantly instead of sleeping on a fixed poll.
BEGIN;

CREATE TABLE IF NOT EXISTS chat.channel_rev (
    channel TEXT PRIMARY KEY,
    rev BIGINT NOT NULL DEFAULT 0
);

INSERT INTO chat.channel_rev (channel, rev) VALUES ('proactive', 0)
ON CONFLICT (channel) DO NOTHING;

-- Bump the 'proactive' channel revision whenever a proactive message is inserted.
CREATE OR REPLACE FUNCTION chat.bump_proactive_rev() RETURNS trigger AS $$
BEGIN
    UPDATE chat.channel_rev SET rev = rev + 1 WHERE channel = 'proactive';
    PERFORM pg_notify('proactive_msg', NEW.student_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_messages_bump_proactive ON chat.messages;
CREATE TRIGGER trg_messages_bump_proactive
    AFTER INSERT ON chat.messages
    FOR EACH ROW WHEN (NEW.origin = 'proactive')
    EXECUTE FUNCTION chat.bump_proactive_rev();

COMMIT;
