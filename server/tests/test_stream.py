"""Tests for the SSE stream (issue #9): the pure event formatter, and the DB poll
helpers (DB-gated). The infinite stream loop itself is verified by a live curl."""
import json
import os
from uuid import uuid4

import pytest

from src.routes.stream import format_sse_event


def test_format_sse_event_frame():
    frame = format_sse_event({
        "id": 5, "message_text": "You're close!", "response_id": "abc", "created_at": "2026-07-14T00:00:00",
    })
    assert frame.startswith("event: assistant_message\n")
    assert frame.endswith("\n\n")
    data = json.loads(frame.split("data: ", 1)[1].strip())
    assert data["message_id"] == 5
    assert data["message"] == "You're close!"
    assert data["origin"] == "proactive"


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL")
def test_proactive_poll_helpers_filter_and_advance():
    from src.db import (
        insert_message, latest_proactive_message_id, get_proactive_messages_after, get_conn,
    )
    student = f"test_{uuid4().hex[:8]}"
    session = uuid4()
    try:
        start = latest_proactive_message_id(student)
        assert start == 0

        insert_message(session_id=session, student_id=student, role="assistant",
                       message_text="proactive one", origin="proactive")
        insert_message(session_id=session, student_id=student, role="assistant",
                       message_text="reactive one", origin="reactive")

        rows = get_proactive_messages_after(student, start)
        # only the proactive message shows, and after its id the poll is empty
        assert [r["message_text"] for r in rows] == ["proactive one"]
        assert get_proactive_messages_after(student, rows[0]["id"]) == []
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat.messages WHERE student_id = %s", (student,))
