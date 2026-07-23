"""Server-Sent Events stream for proactively-pushed assistant messages.

Delivery is a DB poll behind an SSE facade (spec §5.4): the endpoint watches
chat.messages for new origin='proactive' rows for the student and emits them as
`assistant_message` events. No in-process pub/sub, no cross-thread bridge -- the
blocking DB reads run in a thread so the event loop stays free. Swap to pub/sub
only past ~50 concurrent students.
"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.db import latest_proactive_message_id, get_proactive_messages_after

router = APIRouter(prefix="/v1", tags=["stream"])

POLL_INTERVAL_S = 2.0


def format_sse_event(message: dict) -> str:
    """One proactive message as an SSE `assistant_message` event frame."""
    payload = {
        "message_id": message["id"],
        "response_id": message.get("response_id"),
        "message": message["message_text"],
        "created_at": message.get("created_at"),
        "origin": "proactive",
        "trigger_type": message.get("trigger_type"),
        "trigger_why": message.get("trigger_why"),
    }
    return f"event: assistant_message\ndata: {json.dumps(payload)}\n\n"


async def _event_stream(student_id: str):
    # Start at "now" so a fresh connection doesn't replay old proactive messages.
    last_id = await asyncio.to_thread(latest_proactive_message_id, student_id)
    while True:
        rows = await asyncio.to_thread(get_proactive_messages_after, student_id, last_id)
        for row in rows:
            last_id = row["id"]
            yield format_sse_event(row)
        # A comment line doubles as a keep-alive so proxies don't drop an idle stream.
        yield ": keep-alive\n\n"
        await asyncio.sleep(POLL_INTERVAL_S)


@router.get("/students/{student_id}/stream")
async def stream(student_id: str) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(student_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
