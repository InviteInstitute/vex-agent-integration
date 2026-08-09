"""Ingestion idempotency (migration 012): re-inserting a row with the same
source_log_id must not create a duplicate parsed_events row. DB-gated and
self-cleaning, matching the other db-helper tests."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL"
)


def _row(student: str, source_log_id: int, session) -> dict:
    return {
        "session_id": session,
        "student_id": student,
        "class_code": None,
        "event_ts": datetime(2026, 8, 9, tzinfo=timezone.utc),
        "event_type": "runProject",
        "program_type": None,
        "playground": None,
        "project_json": None,
        "block_event_data_json": None,
        "playground_data_json": None,
        "has_orphans": None,
        "switch_block_count": None,
        "error_message": None,
        "source_log_id": source_log_id,
        "source_received_at": None,
        "source_queue": None,
        "source": "test",
    }


def test_repeated_source_log_id_inserts_once():
    from vex_agent.ingest.parse_event_logs import insert_rows
    from vex_agent.data.db import get_conn

    student = f"test_{uuid4().hex[:8]}"
    session = uuid4()
    source_log_id = 900_000_000 + (uuid4().int % 1_000_000)
    try:
        insert_rows([_row(student, source_log_id, session)])
        insert_rows([_row(student, source_log_id, session)])  # duplicate -> no-op
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM event_logs.parsed_events WHERE source_log_id = %s",
                    (source_log_id,),
                )
                assert cur.fetchone()[0] == 1
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM event_logs.parsed_events WHERE student_id = %s",
                    (student,),
                )
