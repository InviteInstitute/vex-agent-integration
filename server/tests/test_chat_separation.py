"""The student chat and the research chat are kept apart: separate recent-turn history
(so a research experiment never reaches the context of a student reply), research rows
stored as origin='research', and proactive check-ins joining both. No database."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from vex_agent.api.turnstile import COOKIE_NAME, sign_cookie
from vex_agent.domain.feedback_policy import FeedbackClass
from vex_agent.services import feedback as fb
from vex_agent.services import proactive, sessions


@pytest.fixture
def api(monkeypatch):
    from vex_agent.app import app

    monkeypatch.setattr("vex_agent.app.warm_up", lambda: None)
    with TestClient(app) as client:
        client.cookies.set(COOKIE_NAME, sign_cookie())
        yield client


def test_each_chat_keeps_its_own_turns():
    ids = ("s-" + uuid4().hex[:6], "GO-Mars", str(uuid4()))
    sessions.append_session_message(*ids, role="student", content="hi from a student")
    sessions.append_session_message(
        *ids, role="student", content="reply in two sentences", chat="research"
    )
    assert [m["content"] for m in sessions.get_recent_session_messages(*ids)] == [
        "hi from a student"
    ]
    assert [m["content"] for m in sessions.get_recent_session_messages(*ids, chat="research")] == [
        "reply in two sentences"
    ]


def test_a_research_message_is_stored_as_research_in_its_own_chat(api, monkeypatch):
    from vex_agent.api import students

    stored = []
    monkeypatch.setattr(students, "insert_message", lambda **row: stored.append(row))
    student, session = "s-" + uuid4().hex[:6], str(uuid4())
    for chat, text in (("research", "try a new prompt"), ("student", "why won't it turn?")):
        response = api.post(
            f"/v1/students/{student}/messages",
            json={"session_id": session, "message": text, "chat": chat},
        )
        assert response.status_code == 200
    assert [(row["message_text"], row["origin"]) for row in stored] == [
        ("try a new prompt", "research"),
        ("why won't it turn?", "reactive"),
    ]
    student_turns = sessions.get_recent_session_messages(student, "GO-Mars", session)
    research_turns = sessions.get_recent_session_messages(
        student, "GO-Mars", session, chat="research"
    )
    assert [m["content"] for m in student_turns] == ["why won't it turn?"]
    assert [m["content"] for m in research_turns] == ["try a new prompt"]


def test_a_reply_reads_only_its_own_chats_history(monkeypatch):
    asked = []
    monkeypatch.setattr(fb, "resolve_task_description", lambda p: "TASK")
    monkeypatch.setattr(fb, "resolve_available_blocks", lambda p: ["b"])
    monkeypatch.setattr(fb, "fetch_events_from_db", lambda **k: ["evt"])
    monkeypatch.setattr(fb, "build_situation_model", lambda events: "facts")
    monkeypatch.setattr(fb, "build_current_program", lambda **k: "PROG")
    monkeypatch.setattr(
        fb, "get_recent_session_messages", lambda *args: asked.append(args[-1]) or []
    )
    monkeypatch.setattr(
        fb, "generate_main_llm_response", lambda **k: {"response_text": "ok", "model": "m"}
    )
    for chat in ("research", "student"):
        fb.generate_feedback(
            student_id="s",
            session_id="x",
            playground="GO-Mars",
            feedback_classes={FeedbackClass.QUESTION},
            student_message="hi",
            chat=chat,
        )
    assert asked == ["research", "student"]


def test_a_check_in_joins_both_chats(monkeypatch):
    student, session = "s-" + uuid4().hex[:6], str(uuid4())
    monkeypatch.setattr(proactive, "track_identity_switches", lambda *a: None)
    monkeypatch.setattr(
        proactive,
        "persist_new_triggers",
        lambda *a: [{"id": 1, "trigger_type": "wheel_spinning", "detail": {}, "run_index": 3}],
    )
    monkeypatch.setattr(
        proactive,
        "generate_proactive_response",
        lambda *a: {"response_text": "What do you expect to change?"},
    )
    monkeypatch.setattr(proactive, "feedback_classes_for_trigger", lambda t: set())
    monkeypatch.setattr(proactive, "insert_message", lambda **row: None)
    monkeypatch.setattr(proactive, "mark_agent_trigger_acted", lambda **k: None)

    proactive.run_proactive_tick(student, session, "GO-Mars")

    for chat in sessions.CHATS:
        turns = sessions.get_recent_session_messages(student, "GO-Mars", session, chat=chat)
        assert [m["content"] for m in turns] == ["What do you expect to change?"]
