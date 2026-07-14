"""Admin endpoints for the proactive push lane. /admin/tick runs ONE full trigger
pass for a session by hand -- the Slice-1 way to validate intervention quality on
real sessions before the always-on daemon (#11) exists."""
from fastapi import APIRouter
from pydantic import BaseModel

from src.trigger_service import run_proactive_tick

router = APIRouter(prefix="/admin", tags=["admin"])


class TickRequest(BaseModel):
    student_id: str
    session_id: str
    playground: str | None = None


@router.post("/tick")
def tick(payload: TickRequest) -> dict:
    """Detect + persist triggers for the session, then generate/deliver a proactive
    message for each new acted-on trigger. Returns {detected: [...], acted: [...]}."""
    return run_proactive_tick(
        student_id=payload.student_id,
        session_id=payload.session_id,
        playground=payload.playground,
    )
