"""Token budgets per browser session and per day (services/budget.py), with the DB
lookups faked. The SQL helpers themselves are covered in test_db_helpers.py."""

import pytest

from vex_agent.llm import client as ls
from vex_agent.services import budget


def _usage(monkeypatch, *, session=0, day=0):
    monkeypatch.setattr(budget, "get_llm_tokens_for_budget_key", lambda key: session)
    monkeypatch.setattr(budget, "get_llm_tokens_last_day", lambda: day)


def test_budget_key_hashes_the_cookie_and_handles_none():
    key = budget.budget_key("cookie-value")
    assert key == budget.budget_key("cookie-value")
    assert key != budget.budget_key("other-cookie") and "cookie-value" not in key
    assert budget.budget_key(None) == budget.NO_SESSION_KEY


def test_under_both_limits_passes(monkeypatch):
    _usage(monkeypatch, session=149_999, day=2_999_999)
    budget.check_budget("k")


def test_a_spent_session_is_refused(monkeypatch):
    _usage(monkeypatch, session=150_000)
    with pytest.raises(budget.TokenBudgetExceeded, match="150,000 LLM tokens"):
        budget.check_budget("k")


def test_the_daily_ceiling_refuses_everyone(monkeypatch):
    _usage(monkeypatch, session=0, day=3_000_000)
    with pytest.raises(budget.TokenBudgetExceeded, match="today's usage limit"):
        budget.check_budget("k")


def test_limits_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("LLM_SESSION_TOKEN_LIMIT", "500")
    _usage(monkeypatch, session=500)
    assert budget.session_usage("k") == {"used": 500, "limit": 500}
    with pytest.raises(budget.TokenBudgetExceeded, match="500 LLM tokens"):
        budget.check_budget("k")


def test_zero_tokens_are_not_recorded(monkeypatch):
    rows = []
    monkeypatch.setattr(budget, "record_llm_usage", lambda **row: rows.append(row))
    budget.record_usage(key="k", student_id="s", model="m", origin="reactive", tokens=0)
    budget.record_usage(key="k", student_id="s", model="m", origin="research", tokens=42)
    assert rows == [
        {"budget_key": "k", "student_id": "s", "model": "m", "origin": "research", "tokens": 42}
    ]


def test_every_request_the_call_makes_is_counted(monkeypatch):
    from types import SimpleNamespace

    def reply(content, finish, total):
        message = SimpleNamespace(content=content)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=finish)],
            usage=SimpleNamespace(total_tokens=total),
        )

    replies = iter([reply("", "length", 1800), reply("Try it.", "stop", 2400)])

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return next(replies)

    monkeypatch.setattr(ls, "create_openai_client", lambda: _Client())
    spent = []
    assert ls.execute_prompt(model="m", prompt="p", usage=spent) == "Try it."
    assert spent == [1800, 2400]


def test_a_failed_call_still_reports_what_it_spent(monkeypatch):
    from types import SimpleNamespace

    empty = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=""), finish_reason="length")],
        usage=SimpleNamespace(total_tokens=900),
    )

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return empty

    monkeypatch.setattr(ls, "create_openai_client", lambda: _Client())
    with pytest.raises(ls.EmptyAnswerError) as error:
        ls.execute_prompt(model="m", prompt="p")
    assert error.value.tokens == 1800
