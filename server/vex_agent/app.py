import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel

from vex_agent.routes.students import router as students_router
from vex_agent.routes.admin import router as admin_router
from vex_agent.routes.stream import router as stream_router
from vex_agent.trigger_daemon import start_daemon, stop_daemon
from vex_agent.turnstile import (
    TurnstileGateMiddleware, COOKIE_NAME, COOKIE_MAX_AGE, sign_cookie, verify_turnstile,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

load_dotenv()


def get_allowed_origins() -> list[str]:
    configured_origins = os.getenv("BACKEND_CORS_ORIGINS", "")
    if configured_origins.strip():
        return [
            origin.strip()
            for origin in configured_origins.split(",")
            if origin.strip()
        ]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the proactive trigger daemon (no-op unless TRIGGER_DAEMON_ENABLED).
    start_daemon()
    yield
    stop_daemon()


app = FastAPI(title="Pedagogical AI Agent API", lifespan=lifespan)
# inner -> outer: TurnstileGate (bot gate over /v1/*) inside CORS (handles
# preflight). Result order: CORS -> TurnstileGate -> routes.
app.add_middleware(TurnstileGateMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(students_router)
app.include_router(admin_router)
app.include_router(stream_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


# Under /v1/, so it's Turnstile-gated: the client pings this once on mount to
# trip the gate at page load rather than waiting for the first real chat call.
@app.get("/v1/ping")
def ping() -> dict[str, bool]:
    return {"ok": True}


# bot gate: /v1/* is behind Cloudflare Turnstile (see src/turnstile.py). This is
# the one /v1/* route TurnstileGateMiddleware leaves open so a browser can solve
# the widget and get the cookie the middleware then checks on every other call.
class TurnstileVerifyRequest(BaseModel):
    token: str


@app.post("/v1/turnstile/verify/")
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
