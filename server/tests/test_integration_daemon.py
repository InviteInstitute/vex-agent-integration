"""End-to-end integration for the push lane (issue #15): daemon -> scope -> cooldown
-> generate -> persist -> SSE-poll delivery. DB-backed but prod/Ollama-free (sync and
LLM are monkeypatched). Uses fixture_07_1 (12 identical reruns -> wheel_spin; old
events -> inactive). Cleans up."""
import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL with fixtures loaded"
)

STUDENT = "fixture_07_1"


def _cleanup():
    from src.db import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat.messages WHERE student_id=%s AND origin='proactive'", (STUDENT,))
            cur.execute("DELETE FROM event_logs.agent_triggers WHERE student_id=%s", (STUDENT,))


def test_daemon_scopes_generates_delivers_and_cools_down(monkeypatch):
    from src import trigger_daemon as td, trigger_service
    from src.db import latest_proactive_message_id, get_proactive_messages_after

    # scope to just this student; no prod sync; canned LLM
    monkeypatch.setenv("PROACTIVE_STUDENT_ALLOWLIST", STUDENT)
    monkeypatch.delenv("PROACTIVE_CLASS_CODE", raising=False)
    monkeypatch.setenv("PROACTIVE_COOLDOWN_S", "240")
    monkeypatch.setattr(td, "sync_invite_hub_logs", lambda *a, **k: 0)
    monkeypatch.setattr(
        trigger_service, "generate_proactive_response",
        lambda *a, **k: {"response_text": "Try changing one block.", "model": "t", "prompt": "p"},
    )

    _cleanup()
    before = latest_proactive_message_id(STUDENT)
    try:
        first = td.run_daemon_tick()
        assert first["scoped"] == 1
        assert any(a["trigger_type"] == "wheel_spin" for a in first["acted"])

        # delivered: what the SSE stream would poll
        delivered = get_proactive_messages_after(STUDENT, before)
        assert len(delivered) >= 1

        # second tick: student is inside the cooldown window -> skipped, nothing new acted
        second = td.run_daemon_tick()
        assert second["skipped_cooldown"] == 1
        assert second["acted"] == []
    finally:
        _cleanup()
