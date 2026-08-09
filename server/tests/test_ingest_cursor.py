"""DB-backed ingest cursor (migration 013): save/get roundtrip and the forward-only
guard that stops a stale writer from moving the cursor backward. DB-gated,
self-cleaning, and scoped to a unique cursor name so it never touches the real
'invite_hub' row."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL"
)


def _delete(name: str) -> None:
    from vex_agent.data.db import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM event_logs.ingest_cursor WHERE name = %s", (name,))


def test_cursor_roundtrip_and_forward_only():
    from vex_agent.data.db import get_ingest_cursor, save_ingest_cursor

    name = f"test_{uuid4().hex[:8]}"
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    try:
        assert get_ingest_cursor(name) == {}  # unseeded

        save_ingest_cursor(100, t1, name=name)
        c = get_ingest_cursor(name)
        assert c["last_source_log_id"] == 100
        assert c["last_event_time"] == t1

        save_ingest_cursor(200, t2, name=name)  # forward advance takes
        assert get_ingest_cursor(name)["last_source_log_id"] == 200

        save_ingest_cursor(150, t1, name=name)  # backward save ignored
        c = get_ingest_cursor(name)
        assert c["last_source_log_id"] == 200
        assert c["last_event_time"] == t2
    finally:
        _delete(name)
