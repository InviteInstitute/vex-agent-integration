"""Remaining branch coverage for trigger_service (inactive edges) and the daemon
(start idempotency)."""

from datetime import UTC, datetime, timedelta

from vex_agent.services import daemon as td
from vex_agent.services import proactive as ts


def test_detect_inactive_no_events(monkeypatch):
    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: [])
    assert ts.detect_inactive_trigger("s", "sess") is None


def test_detect_inactive_recent_event(monkeypatch):
    class _Event:
        event_ts = datetime.now(UTC)

    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: [_Event()])
    assert ts.detect_inactive_trigger("s", "sess") is None  # not idle yet


def test_detect_inactive_first_fire_uses_sentinel_run_index(monkeypatch):
    # idle, never fired before -> first fire at run_index -1
    idle_ts = datetime.now(UTC) - timedelta(seconds=400)
    monkeypatch.setattr(
        ts, "fetch_events_from_db", lambda **k: [type("E", (), {"event_ts": idle_ts})()]
    )
    monkeypatch.setattr(ts, "latest_inactive_trigger", lambda *a: None)
    fire = ts.detect_inactive_trigger("s", "sess")
    assert fire is not None and fire[0] == "inactive" and fire[1] == -1


def test_detect_inactive_suppresses_realert_inside_window(monkeypatch):
    # idle, but the last fire was < RE_ALERT_SECONDS ago -> no re-alert yet
    idle_ts = datetime.now(UTC) - timedelta(seconds=400)
    now = datetime.now(UTC)
    monkeypatch.setattr(
        ts, "fetch_events_from_db", lambda **k: [type("E", (), {"event_ts": idle_ts})()]
    )
    monkeypatch.setattr(
        ts, "latest_inactive_trigger", lambda *a: (-1, now - timedelta(seconds=60))
    )  # fired 1 min ago
    assert ts.detect_inactive_trigger("s", "sess") is None  # not due for re-alert


def test_detect_inactive_realerts_past_window(monkeypatch):
    # idle, last fire was > RE_ALERT_SECONDS ago -> re-alert at run_index -2
    idle_ts = datetime.now(UTC) - timedelta(seconds=400)
    now = datetime.now(UTC)
    monkeypatch.setattr(
        ts, "fetch_events_from_db", lambda **k: [type("E", (), {"event_ts": idle_ts})()]
    )
    monkeypatch.setattr(
        ts,
        "latest_inactive_trigger",
        lambda *a: (-1, now - timedelta(seconds=ts.RE_ALERT_SECONDS + 60)),
    )
    fire = ts.detect_inactive_trigger("s", "sess")
    assert fire is not None and fire[1] == -2  # next negative index


def test_start_daemon_is_idempotent(monkeypatch):
    monkeypatch.setenv("TRIGGER_DAEMON_ENABLED", "true")
    monkeypatch.setenv("TRIGGER_POLL_INTERVAL_S", "0.02")
    monkeypatch.setattr(td, "run_daemon_tick", lambda: {"scoped": 0, "acted": []})
    try:
        td.start_daemon()
        first = td._thread
        td.start_daemon()  # already alive -> no second thread
        assert td._thread is first
    finally:
        td.stop_daemon()
