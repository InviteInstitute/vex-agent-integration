"""System + bot-gate routes, kept out of the app wiring module: health, ping,
and the one open Turnstile-verify endpoint."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from vex_agent.api.turnstile import (
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    sign_cookie,
    verify_turnstile,
)

router = APIRouter(tags=["system"])


@router.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


# Under /v1/, so it's Turnstile-gated: the client pings this once on mount to
# trip the gate at page load rather than waiting for the first real chat call.
@router.get("/v1/ping")
def ping() -> dict[str, bool]:
    return {"ok": True}


# bot gate: /v1/* is behind Cloudflare Turnstile (see api/turnstile.py). This is
# the one /v1/* route TurnstileGateMiddleware leaves open so a browser can solve
# the widget and get the cookie the middleware then checks on every other call.
class TurnstileVerifyRequest(BaseModel):
    token: str


@router.post("/v1/turnstile/verify/")
async def turnstile_verify(body: TurnstileVerifyRequest, request: Request, response: Response):
    remote_ip = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip() \
        or (request.client.host if request.client else "")
    if not await verify_turnstile(body.token, remote_ip):
        raise HTTPException(status_code=403, detail="turnstile verification failed")
    response.set_cookie(
        COOKIE_NAME, sign_cookie(),
        max_age=COOKIE_MAX_AGE, httponly=True, secure=True, samesite="lax",
    )
    return {"ok": True}
