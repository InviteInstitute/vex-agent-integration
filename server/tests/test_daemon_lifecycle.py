"""Covers the daemon thread lifecycle + config getters + run_daemon_tick error
branches (the parts test_trigger_daemon.py's pure tests don't reach)."""
import threading

from src import trigger_daemon as td


def test_config_getters(monkeypatch):
    monkeypatch.setenv("TRIGGER_POLL_INTERVAL_S", "5")
    monkeypatch.setenv("PROACTIVE_COOLDOWN_S", "99")
    monkeypatch.setenv("TRIGGER_DAEMON_ENABLED", "yes")
    assert td.poll_interval_s() == 5.0
    assert td.cooldown_s() == 99.0
    assert td.daemon_enabled() is True


def test_start_daemon_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("TRIGGER_DAEMON_ENABLED", raising=False)
    td.start_daemon()  # should not spawn a thread
    assert td._thread is None or not td._thread.is_alive()


def test_start_and_stop_daemon_runs_a_tick(monkeypatch):
    monkeypatch.setenv("TRIGGER_DAEMON_ENABLED", "true")
    monkeypatch.setenv("TRIGGER_POLL_INTERVAL_S", "0.02")
    ticked = threading.Event()
    monkeypatch.setattr(td, "run_daemon_tick",
                        lambda: (ticked.set(), {"scoped": 0, "skipped_cooldown": 0, "acted": []})[1])
    try:
        td.start_daemon()
        assert ticked.wait(2.0)  # the loop executed at least one tick
    finally:
        td.stop_daemon()
    assert not (td._thread and td._thread.is_alive())


def test_run_daemon_tick_swallows_sync_failure(monkeypatch):
    monkeypatch.setattr(td, "in_scope_students", lambda: {"stu"})

    def boom(*a, **k):
        raise RuntimeError("prod down")

    monkeypatch.setattr(td, "sync_invite_hub_logs", boom)
    monkeypatch.setattr(td, "last_proactive_message_at", lambda s: None)
    monkeypatch.setattr(td, "get_latest_session_id_for_student", lambda s: None)  # no session -> skip
    out = td.run_daemon_tick()  # must not raise despite the sync failure
    assert out["scoped"] == 1 and out["acted"] == []


def test_run_daemon_tick_swallows_tick_failure(monkeypatch):
    monkeypatch.setattr(td, "in_scope_students", lambda: {"stu"})
    monkeypatch.setattr(td, "sync_invite_hub_logs", lambda *a, **k: 0)
    monkeypatch.setattr(td, "last_proactive_message_at", lambda s: None)
    monkeypatch.setattr(td, "get_latest_session_id_for_student", lambda s: "sess")

    def boom(*a, **k):
        raise RuntimeError("tick blew up")

    monkeypatch.setattr(td, "run_proactive_tick", boom)
    out = td.run_daemon_tick()  # per-student failure is logged, not fatal
    assert out["acted"] == []
