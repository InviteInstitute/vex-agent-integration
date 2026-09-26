"""Token budgets for LLM calls made on behalf of a browser.

The chat and the research preview's Agent tab (any model on the gateway, any prompt)
are open to anyone who passes Turnstile. What keeps that from turning the Lumen
account into a free LLM is a token budget per browser session, plus a site-wide daily
ceiling. A session is one Turnstile cookie: it lasts COOKIE_MAX_AGE (12h), and getting
a new one means solving the challenge again, so the per-session cap can't be reset by
a script. The daily ceiling bounds the worst case either way.

Proactive check-ins are server-initiated and don't count against any browser.
"""

import hashlib
import os

from vex_agent.data.db import (
    get_llm_tokens_for_budget_key,
    get_llm_tokens_last_day,
    record_llm_usage,
)

DEFAULT_SESSION_TOKEN_LIMIT = 150_000
DEFAULT_DAILY_TOKEN_LIMIT = 3_000_000
NO_SESSION_KEY = "no-session"


class TokenBudgetExceeded(Exception):
    """This browser session, or the whole site today, is out of LLM tokens."""


def session_token_limit() -> int:
    return int(os.getenv("LLM_SESSION_TOKEN_LIMIT", DEFAULT_SESSION_TOKEN_LIMIT))


def daily_token_limit() -> int:
    return int(os.getenv("LLM_DAILY_TOKEN_LIMIT", DEFAULT_DAILY_TOKEN_LIMIT))


def budget_key(session_cookie: str | None) -> str:
    """Stable id for one browser session. A hash, so the cookie itself is never stored."""
    if not session_cookie:
        return NO_SESSION_KEY
    return hashlib.sha256(session_cookie.encode()).hexdigest()[:32]


def session_usage(key: str) -> dict[str, int]:
    return {"used": get_llm_tokens_for_budget_key(key), "limit": session_token_limit()}


def check_budget(key: str) -> None:
    """Raise TokenBudgetExceeded when this session or the site is out of tokens. A call
    already under way may run a little past the limit; the next one is refused."""
    limit = session_token_limit()
    if get_llm_tokens_for_budget_key(key) >= limit:
        raise TokenBudgetExceeded(
            f"This session has used its {limit:,} LLM tokens. "
            "Start a new session later to keep going."
        )
    if get_llm_tokens_last_day() >= daily_token_limit():
        raise TokenBudgetExceeded("The agent has reached today's usage limit. Try again tomorrow.")


def record_usage(*, key: str, student_id: str | None, model: str, origin: str, tokens: int):
    if tokens > 0:
        record_llm_usage(
            budget_key=key, student_id=student_id, model=model, origin=origin, tokens=tokens
        )
