"""Cloudflare Turnstile gate for the API, ported from lm-dashboard/app/turnstile.py.

The agent has no login -- this isn't about authenticating a person, it's about
keeping bots off /v1/*. A browser solves the widget once, the response token is
verified server-side against Cloudflare's siteverify, and success is remembered
via a signed cookie for COOKIE_MAX_AGE seconds, so solving is a one-time cost per
browser rather than per request.
"""
import os

import httpx
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
COOKIE_NAME = "ts_verified"
COOKIE_MAX_AGE = 12 * 3600  # re-solve the widget every 12h
VERIFY_PATH = "/v1/turnstile/verify/"
GATED_PREFIX = "/v1/"

# Dev fallback keeps local runs/tests working but must never be used in prod
# (the cookie would be forgeable). Set a long random value in the real .env.
SESSION_SECRET = os.environ.get("SESSION_SECRET") or "dev-insecure-session-secret-change-me"
# Unset means the gate can't verify anyone -- every widget solve 403s.
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET")

_signer = TimestampSigner(SESSION_SECRET)


async def verify_turnstile(token, remote_ip):
    """True iff Cloudflare accepts this widget response token."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(SITEVERIFY_URL, data={
            "secret": TURNSTILE_SECRET,
            "response": token,
            "remoteip": remote_ip,
        })
    return resp.status_code == 200 and resp.json().get("success") is True


def sign_cookie():
    """A fresh signed cookie value for a browser that just solved the widget."""
    return _signer.sign(b"ok").decode()


def cookie_is_valid(value):
    """True iff `value` is a cookie this process signed, within COOKIE_MAX_AGE."""
    if not value:
        return False
    try:
        _signer.unsign(value, max_age=COOKIE_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


class TurnstileGateMiddleware(BaseHTTPMiddleware):
    """Gates /v1/* behind a solved Turnstile challenge. A missing/expired cookie
    gets a 403 the SPA recognizes and reacts to by showing the widget; the verify
    endpoint itself (and everything outside /v1/, i.e. the static SPA and
    /admin/* ops tooling) stays open."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if not path.startswith(GATED_PREFIX) or path == VERIFY_PATH:
            return await call_next(request)
        if not cookie_is_valid(request.cookies.get(COOKIE_NAME)):
            return JSONResponse({"error": "turnstile_required"}, status_code=403)
        return await call_next(request)
