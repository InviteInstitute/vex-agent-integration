"""End-to-end integration for the push lane (issue #15): daemon -> scope -> generate ->
persist -> SSE-poll delivery, then dedup on a second tick. DB-backed but prod/Ollama-free
(sync and LLM are monkeypatched). Uses fixture_07_1 (12 identical reruns -> wheel_spin;
old events -> inactive). Cleans up."""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL with fixtures loaded"
)

STUDENT = "fixture_07_1"


def _cleanup():
    from src.db import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat.messages WHERE student_id=%s", (STUDENT,))
            cur.execute("DELETE FROM event_logs.agent_triggers WHERE student_id=%s", (STUDENT,))


def test_daemon_scopes_generates_delivers_and_dedups(monkeypatch):
    from src import trigger_daemon as td, trigger_service
    from src.db import latest_proactive_message_id, get_proactive_messages_after

    # pin scope to just this fixture so the tick doesn't fan out to every student
    monkeypatch.setattr(td, "in_scope_students", lambda: {STUDENT})
    monkeypatch.setattr(td, "sync_invite_hub_logs", lambda *a, **k: 0)
    monkeypatch.setattr(
        trigger_service, "generate_proactive_response",
        lambda *a, **k: {"response_text": "Try changing one block.", "model": "t", "prompt": "p"},
    )

    _cleanup()
    before = latest_proactive_message_id(STUDENT)
    try:
        first = td.run_daemon_tick()
        assert first["scoped"] >= 1
        assert any(a["trigger_type"] == "wheel_spin" for a in first["acted"])

        # delivered: what the SSE stream would poll
        delivered = get_proactive_messages_after(STUDENT, before)
        assert len(delivered) >= 1

        # second tick: no NEW behavior -> trigger dedup means nothing new is acted on
        second = td.run_daemon_tick()
        assert second["acted"] == []
    finally:
        _cleanup()
