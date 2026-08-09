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
    # Drop the run-distance cache between tests so a cached sequence from one test
    # can't satisfy another (the cache is keyed on (student, session) + event signature,
    # but clearing keeps the isolation story simple and explicit).
    from vex_agent.services.proactive import clear_run_cache

    clear_run_cache()
    # Drop the cached LLM client between tests so a fake client monkeypatched into
    # create_openai_client() by one test can't leak into another.
    from vex_agent.llm.client import clear_client_cache

    clear_client_cache()
    # Same for the cached Invite Hub auth token.
    from vex_agent.ingest.fetch_invite_hub_logs import clear_cached_token

    clear_cached_token()
