"""Tests for the daemon scope (now: every student with telemetry). All monkeypatched --
no DB, no Ollama, no prod. The properties (scope is all_students, no prod hit when there
is no telemetry) are the point."""
from src import trigger_daemon as td


def test_daemon_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TRIGGER_DAEMON_ENABLED", raising=False)
    assert td.daemon_enabled() is False


def test_scope_is_empty_when_no_telemetry(monkeypatch):
    monkeypatch.setattr(td, "all_students", lambda: [])
    assert td.in_scope_students() == set()  # no telemetry -> nobody


def test_scope_is_every_student(monkeypatch):
    monkeypatch.setattr(td, "all_students", lambda: ["a", "b", "c"])
    assert td.in_scope_students() == {"a", "b", "c"}


def test_empty_scope_noops_without_touching_prod(monkeypatch):
    monkeypatch.setattr(td, "in_scope_students", lambda: set())

    def boom(*a, **k):
        raise AssertionError("must not sync or tick when nobody is scoped")

    monkeypatch.setattr(td, "sync_invite_hub_logs", boom)
    monkeypatch.setattr(td, "run_proactive_tick", boom)
    assert td.run_daemon_tick() == {"scoped": 0, "acted": []}


def test_acts_when_scoped(monkeypatch):
    monkeypatch.setattr(td, "in_scope_students", lambda: {"stu"})
    monkeypatch.setattr(td, "sync_invite_hub_logs", lambda *a, **k: 0)
    monkeypatch.setattr(td, "get_latest_session_id_for_student", lambda s: "sess")
    monkeypatch.setattr(td, "run_proactive_tick",
                        lambda s, sid: {"detected": [], "acted": [{"trigger_type": "wheel_spin"}]})
    out = td.run_daemon_tick()
    assert out["scoped"] == 1 and len(out["acted"]) == 1
