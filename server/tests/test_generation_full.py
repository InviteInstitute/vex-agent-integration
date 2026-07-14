"""Covers the generate_proactive_response LLM path and run_proactive_tick's
non-acted branch (the lines the pure/DB tests don't reach), all mocked."""
from src import trigger_service as ts


def test_generate_proactive_response_full_path(monkeypatch):
    monkeypatch.setattr(ts, "build_raw_logs_context", lambda **k: "raw logs")
    monkeypatch.setattr(ts, "generate_robot_behavior_summary",
                        lambda **k: {"response_text": "the robot drives forward"})
    monkeypatch.setattr(ts, "get_recent_session_messages", lambda *a, **k: [])
    captured = {}

    def fake_main(**kwargs):
        captured.update(kwargs)
        return {"response_text": "You're close.", "model": "m", "prompt": "p"}

    monkeypatch.setattr(ts, "generate_main_llm_response", fake_main)

    out = ts.generate_proactive_response("stu", "sess", "wheel_spin", {"value": "6 identical reruns"})
    assert out["response_text"] == "You're close."
    # grounded on the real robot-behavior summary, and no student turn is faked
    assert "the robot drives forward" in captured["robot_behavior_summary"]
    assert captured["student_message"] == ""
    # neutral fact, never the internal label
    assert "wheel" not in captured["robot_behavior_summary"].lower()


def test_run_proactive_tick_skips_non_acted_result(monkeypatch):
    # a persisted trigger whose generation returns None (e.g. not acted) is skipped
    monkeypatch.setattr(ts, "persist_new_triggers",
                        lambda s, sess: [{"id": 1, "trigger_type": "unknown", "run_index": 0, "detail": {}}])
    monkeypatch.setattr(ts, "generate_proactive_response", lambda *a, **k: None)
    out = ts.run_proactive_tick("stu", "sess")
    assert out["acted"] == []
    assert out["detected"][0]["trigger_type"] == "unknown"
