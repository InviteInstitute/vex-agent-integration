"""Remaining branch coverage for trigger_service (inactive edges) and the daemon
(start idempotency)."""
from datetime import datetime, timezone

from src import trigger_service as ts
from src import trigger_daemon as td


def test_detect_inactive_no_events(monkeypatch):
    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: [])
    assert ts.detect_inactive_trigger("s", "sess") is None


def test_detect_inactive_recent_event(monkeypatch):
    class _Event:
        event_ts = datetime.now(timezone.utc)

    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: [_Event()])
    assert ts.detect_inactive_trigger("s", "sess") is None  # not idle yet


def test_start_daemon_is_idempotent(monkeypatch):
    monkeypatch.setenv("TRIGGER_DAEMON_ENABLED", "true")
    monkeypatch.setenv("TRIGGER_POLL_INTERVAL_S", "0.02")
    monkeypatch.setattr(td, "run_daemon_tick",
                        lambda: {"scoped": 0, "skipped_cooldown": 0, "acted": []})
    try:
        td.start_daemon()
        first = td._thread
        td.start_daemon()  # already alive -> no second thread
        assert td._thread is first
    finally:
        td.stop_daemon()
