"""Integration test for run_proactive_tick / POST /admin/tick (issue #8).

DB-backed but Ollama-free: the LLM generation is monkeypatched to a canned message,
so this verifies the detect -> persist -> deliver -> mark-acted wiring, not model
quality. Uses fixture_07_1 (12 identical reruns -> a natural wheel_spin). Cleans up.
"""
import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL with fixtures loaded"
)

STUDENT = "fixture_07_1"


def _session_for(student):
    from src.db import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id FROM event_logs.parsed_events "
                "WHERE student_id=%s ORDER BY event_ts DESC LIMIT 1",
                (student,),
            )
            row = cur.fetchone()
    return str(row[0]) if row else None


def _cleanup(student):
    from src.db import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat.messages WHERE student_id=%s AND origin='proactive'", (student,))
            cur.execute("DELETE FROM event_logs.agent_triggers WHERE student_id=%s", (student,))


def test_tick_detects_persists_and_delivers_wheel_spin(monkeypatch):
    from src import trigger_service
    from src.db import get_conn

    session_id = _session_for(STUDENT)
    assert session_id is not None
    _cleanup(STUDENT)  # start clean so dedupe doesn't hide the fire

    # canned generation -- no Ollama in the test path
    monkeypatch.setattr(
        trigger_service, "generate_proactive_response",
        lambda *a, **k: {"response_text": "Try changing one block before you run again.",
                         "model": "test", "prompt": "test"},
    )
    try:
        result = trigger_service.run_proactive_tick(STUDENT, session_id)

        # acted on the wheel_spin
        assert any(a["trigger_type"] == "wheel_spin" for a in result["acted"])

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM chat.messages WHERE student_id=%s AND origin='proactive'",
                    (STUDENT,),
                )
                assert cur.fetchone()[0] == 1  # exactly one proactive message
                cur.execute(
                    "SELECT acted, response_id FROM event_logs.agent_triggers "
                    "WHERE student_id=%s AND trigger_type='wheel_spin'",
                    (STUDENT,),
                )
                acted, response_id = cur.fetchone()
                assert acted is True and response_id is not None

        # second tick is deduped: no new trigger, nothing acted
        again = trigger_service.run_proactive_tick(STUDENT, session_id)
        assert again["acted"] == []
    finally:
        _cleanup(STUDENT)
