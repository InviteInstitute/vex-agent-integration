"""Tests for the daemon scope + cooldown (issues #11/#12). All monkeypatched -- no
DB, no Ollama, no prod. The safety properties (fail-closed scope, cooldown, no prod
hit when nobody is scoped) are the point."""
from datetime import datetime, timedelta, timezone

from src import trigger_daemon as td


def test_daemon_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TRIGGER_DAEMON_ENABLED", raising=False)
    assert td.daemon_enabled() is False


def test_scope_is_fail_closed(monkeypatch):
    monkeypatch.delenv("PROACTIVE_STUDENT_ALLOWLIST", raising=False)
    monkeypatch.delenv("PROACTIVE_CLASS_CODE", raising=False)
    assert td.in_scope_students() == set()  # unset -> nobody


def test_allowlist_is_parsed(monkeypatch):
    monkeypatch.setenv("PROACTIVE_STUDENT_ALLOWLIST", "a, b ,c")
    monkeypatch.delenv("PROACTIVE_CLASS_CODE", raising=False)
    assert td.in_scope_students() == {"a", "b", "c"}


def test_is_in_cooldown():
    now = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
    assert td.is_in_cooldown(None, now, 240) is False               # never messaged
    assert td.is_in_cooldown(now - timedelta(seconds=100), now, 240) is True   # inside window
    assert td.is_in_cooldown(now - timedelta(seconds=300), now, 240) is False  # window passed


def test_empty_scope_noops_without_touching_prod(monkeypatch):
    monkeypatch.setattr(td, "in_scope_students", lambda: set())

    def boom(*a, **k):
        raise AssertionError("must not sync or tick when nobody is scoped")

    monkeypatch.setattr(td, "sync_invite_hub_logs", boom)
    monkeypatch.setattr(td, "run_proactive_tick", boom)
    assert td.run_daemon_tick() == {"scoped": 0, "skipped_cooldown": 0, "acted": []}


def test_cooldown_skips_recent_student(monkeypatch):
    monkeypatch.setattr(td, "in_scope_students", lambda: {"stu"})
    monkeypatch.setattr(td, "sync_invite_hub_logs", lambda *a, **k: 0)
    monkeypatch.setattr(td, "last_proactive_message_at",
                        lambda s: datetime.now(timezone.utc))  # just messaged
    monkeypatch.setenv("PROACTIVE_COOLDOWN_S", "240")

    def boom(*a, **k):
        raise AssertionError("cooldown must skip the tick")

    monkeypatch.setattr(td, "run_proactive_tick", boom)
    out = td.run_daemon_tick()
    assert out["skipped_cooldown"] == 1 and out["acted"] == []


def test_acts_when_scoped_and_not_in_cooldown(monkeypatch):
    monkeypatch.setattr(td, "in_scope_students", lambda: {"stu"})
    monkeypatch.setattr(td, "sync_invite_hub_logs", lambda *a, **k: 0)
    monkeypatch.setattr(td, "last_proactive_message_at", lambda s: None)
    monkeypatch.setattr(td, "get_latest_session_id_for_student", lambda s: "sess")
    monkeypatch.setattr(td, "run_proactive_tick",
                        lambda s, sid: {"detected": [], "acted": [{"trigger_type": "wheel_spin"}]})
    out = td.run_daemon_tick()
    assert out["scoped"] == 1 and len(out["acted"]) == 1
