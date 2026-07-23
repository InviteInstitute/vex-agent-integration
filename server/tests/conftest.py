"""Test isolation. The proactive daemon must never arm from the developer's ambient
.env (TRIGGER_DAEMON_ENABLED=true) during the suite -- with the app lifespan booted via
TestClient that would spawn a real thread hitting prod. Default it OFF for every test;
the daemon tests set the flag explicitly in their own bodies."""
import pytest


@pytest.fixture(autouse=True)
def _daemon_off_unless_set(monkeypatch):
    # setenv 'false', not delenv: a hole would get refilled by load_dotenv() (which
    # doesn't override a var that's present). Tests that need it on setenv 'true'.
    monkeypatch.setenv("TRIGGER_DAEMON_ENABLED", "false")
