import logging
import os
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vex_agent.api.admin import router as admin_router
from vex_agent.api.stream import router as stream_router
from vex_agent.api.students import router as students_router
from vex_agent.api.system import router as system_router
from vex_agent.api.turnstile import TurnstileGateMiddleware
from vex_agent.llm.client import get_openai_client
from vex_agent.services.daemon import start_daemon, stop_daemon
from vex_agent.services.logsync import sync_invite_hub_logs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()


def warm_up() -> None:
    """Prime the process-global singletons that would otherwise be built inside the
    FIRST student request -- the LLM HTTP client and the Invite Hub auth token (~1s
    token POST). Moves that cold-start off the request path onto boot. Best-effort:
    a dependency that's cold at boot must not block startup."""
    try:
        get_openai_client()
    except Exception:
        logger.warning("LLM client warm-up skipped", exc_info=True)
    try:
        sync_invite_hub_logs()  # primes + caches the Invite Hub auth token
    except Exception:
        logger.warning("Invite Hub warm-up sync skipped", exc_info=True)


def get_allowed_origins() -> list[str]:
    configured_origins = os.getenv("BACKEND_CORS_ORIGINS", "")
    if configured_origins.strip():
        return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Prime lazy singletons (LLM client + Invite Hub token) so the first student
    # request doesn't pay ~1.3s of cold-start. In a background thread so the backlog
    # drain inside the warm-up sync can't block startup/readiness.
    threading.Thread(target=warm_up, name="warm-up", daemon=True).start()
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
