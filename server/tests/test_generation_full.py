"""Covers the generate_proactive_response LLM path and run_proactive_tick's
non-acted branch (the lines the pure/DB tests don't reach), all mocked."""

from vex_agent.services import feedback as fb
from vex_agent.services import proactive as ts


def test_generate_proactive_response_full_path(monkeypatch):
    # The pipeline internals now live in the shared feedback module; patch them there.
    monkeypatch.setattr(fb, "fetch_events_from_db", lambda **k: ["evt"])
    monkeypatch.setattr(fb, "build_current_program", lambda **k: "[Active]\n whenStarted")
    monkeypatch.setattr(
        fb, "build_situation_model", lambda events: "Goal progress: 20% (holding steady)."
    )
    monkeypatch.setattr(fb, "get_recent_session_messages", lambda *a, **k: [])
    captured = {}

    def fake_main(**kwargs):
        captured.update(kwargs)
        return {"response_text": "You're close.", "model": "m", "prompt": "p"}

    monkeypatch.setattr(fb, "generate_main_llm_response", fake_main)

    out = ts.generate_proactive_response(
        "stu", "sess", "wheel_spin", {"value": "6 identical reruns"}
    )
    assert out["response_text"] == "You're close."
    # grounded on the measured situation model, plus the neutral trigger fact appended
    assert "Goal progress: 20%" in captured["situation"]
    assert captured["student_message"] == ""
    # neutral fact, never the internal label
    assert "wheel" not in captured["situation"].lower()
    # the current program grounds the prompt (not just the raw-log dump)
    assert captured["current_program"] == "[Active]\n whenStarted"


def test_run_proactive_tick_skips_non_acted_result(monkeypatch):
    # a persisted trigger whose generation returns None (e.g. not acted) is skipped
    monkeypatch.setattr(
        ts,
        "persist_new_triggers",
        lambda s, sess: [{"id": 1, "trigger_type": "unknown", "run_index": 0, "detail": {}}],
    )
    monkeypatch.setattr(ts, "generate_proactive_response", lambda *a, **k: None)
    out = ts.run_proactive_tick("stu", "sess")
    assert out["acted"] == []
    assert out["detected"][0]["trigger_type"] == "unknown"
