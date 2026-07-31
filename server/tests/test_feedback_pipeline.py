"""The shared reactive+proactive pedagogy pipeline (services/feedback.generate_feedback).

Guards the parity that the Phase C extraction relies on: reactive passes a student
message and NO behavior fact; proactive passes an empty message and appends the neutral
fact to the same deterministic situation model. Grounding is now a single pass (no
robot-behavior LLM call). All internals mocked."""
from vex_agent.services import feedback as fb
from vex_agent.domain.feedback_policy import FeedbackClass


def _patch(monkeypatch, captured):
    monkeypatch.setattr(fb, "resolve_task_description", lambda p: "TASK")
    monkeypatch.setattr(fb, "resolve_available_blocks", lambda p: ["b"])
    monkeypatch.setattr(fb, "fetch_events_from_db", lambda **k: ["evt"])
    monkeypatch.setattr(fb, "build_situation_model", lambda events: "Goal progress: 40%.")
    monkeypatch.setattr(fb, "build_current_program", lambda **k: "PROG")
    monkeypatch.setattr(fb, "get_recent_session_messages", lambda *a, **k: [])

    def fake_main(**kwargs):
        captured.update(kwargs)
        return {"response_text": "ok", "model": "m", "prompt": "p"}

    monkeypatch.setattr(fb, "generate_main_llm_response", fake_main)


def test_reactive_mode_passes_student_message_and_no_behavior_fact(monkeypatch):
    captured = {}
    _patch(monkeypatch, captured)
    out = fb.generate_feedback(
        student_id="s", session_id="x", playground="GO-Mars",
        feedback_classes={FeedbackClass.QUESTION},
        student_message="why is my robot stuck?",
    )
    assert out["llm_request"]["response_text"] == "ok"
    assert captured["student_message"] == "why is my robot stuck?"
    # reactive: the situation model is the measured facts, with no fact appended
    assert captured["situation"] == "Goal progress: 40%."
    assert out["situation"] == "Goal progress: 40%."


def test_proactive_mode_appends_behavior_fact_with_empty_student_message(monkeypatch):
    captured = {}
    _patch(monkeypatch, captured)
    fb.generate_feedback(
        student_id="s", session_id="x", playground="GO-Mars",
        feedback_classes={FeedbackClass.REASSURE},
        student_message="", behavior_fact="the student has not done anything for a while",
    )
    assert captured["student_message"] == ""
    assert captured["situation"] == (
        "Goal progress: 40%.\n\nthe student has not done anything for a while"
    )
