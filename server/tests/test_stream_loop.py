"""Drives the SSE event generator (covers routes/stream.py _event_stream + endpoint)
without a live server or DB."""
import asyncio

from vex_agent.routes import stream as S


def test_event_stream_delivers_message_then_keepalive(monkeypatch):
    monkeypatch.setattr(S, "POLL_INTERVAL_S", 0)  # no real 2s wait
    monkeypatch.setattr(S, "latest_proactive_message_id", lambda student: 0)
    # the rev gate: initial read is 0, then bump to 1 so the first loop poll runs
    rev_state = {"calls": 0}

    def fake_rev():
        rev_state["calls"] += 1
        return 0 if rev_state["calls"] == 1 else 1  # first call seeds last_rev=0, then 1

    monkeypatch.setattr(S, "proactive_rev", fake_rev)
    pending = [[{"id": 1, "message_text": "hi", "response_id": None, "created_at": "t"}]]

    def fake_after(student, after_id):
        return pending.pop(0) if pending else []

    monkeypatch.setattr(S, "get_proactive_messages_after", fake_after)

    async def run():
        gen = S._event_stream("stu")
        frames = [await gen.__anext__() for _ in range(3)]
        await gen.aclose()
        return "".join(frames)

    joined = asyncio.run(run())
    assert "event: assistant_message" in joined
    assert '"message": "hi"' in joined
    assert ": keep-alive" in joined


def test_stream_endpoint_returns_event_stream():
    resp = asyncio.run(S.stream("stu"))
    assert resp.media_type == "text/event-stream"
    assert resp.headers.get("cache-control") == "no-cache"
