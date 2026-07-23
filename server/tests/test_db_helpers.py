"""Covers the db helpers not exercised elsewhere (DB-gated, self-cleaning)."""
import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL")


def test_all_students():
    from src.db import get_conn, all_students

    student = f"test_{uuid4().hex[:8]}"
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO event_logs.parsed_events "
                    "(session_id, student_id, event_ts, event_type) "
                    "VALUES (%s, %s, NOW(), 'runProject')",
                    (uuid4(), student),
                )
        assert student in all_students()
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM event_logs.parsed_events WHERE student_id = %s", (student,))


def test_message_roundtrip_response_lookup_and_feedback():
    from src.db import (
        get_conn, insert_message, get_message_id_for_response,
        insert_message_feedback,
    )

    student = f"test_{uuid4().hex[:8]}"
    session = uuid4()
    response_id = uuid4()
    try:
        insert_message(session_id=session, student_id=student, role="assistant",
                       message_text="hi", response_id=response_id, origin="proactive")
        message_id = get_message_id_for_response(response_id=response_id, student_id=student)
        assert message_id is not None
        insert_message_feedback(message_id=message_id, student_id=student, thumb="up", comment="nice")
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat.message_feedback WHERE student_id = %s", (student,))
                cur.execute("DELETE FROM chat.messages WHERE student_id = %s", (student,))
