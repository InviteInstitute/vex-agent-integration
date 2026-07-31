import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from vex_agent.api.students import router as students_router
from vex_agent.api.admin import router as admin_router
from vex_agent.api.stream import router as stream_router
from vex_agent.api.system import router as system_router
from vex_agent.services.daemon import start_daemon, stop_daemon
from vex_agent.api.turnstile import TurnstileGateMiddleware

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
app.include_router(system_router)
