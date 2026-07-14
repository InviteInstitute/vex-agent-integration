"""App-level glue between the agent's EventRecord stream and the pure vendored
trigger engine (server/src/triggers/). The engine stays framework/DB-free; this
module does the adapting so the coupling points one way (app -> engine)."""
from __future__ import annotations

from src.current_state_metrics import EventRecord, fetch_events_from_db
from src.triggers.run_sequence import compute_run_edit_distances


def _event_record_to_engine_dict(event: EventRecord) -> dict:
    """Shape one EventRecord the way run_sequence expects: event_type stays as-is
    (the agent already uses 'runProject'), and the run's workspace XML + playground
    ride under content['project'] / content['playground']. runProject rows carry the
    workspace XML directly in project_json."""
    return {
        "event_type": event.event_type,
        "content": {
            "project": event.project_json or {},
            "playground": event.playground,
        },
        "ts": event.event_ts.timestamp() if event.event_ts else None,
    }


def compute_run_distances(events: list[EventRecord]) -> list[dict]:
    """Per-run edit-distance sequence for a chronological EventRecord list.
    Returns run dicts {index, edit_distance, ts, playground}; edit_distance is None
    for the first run of each playground stretch, else the APTED distance vs the
    previous run."""
    engine_events = [_event_record_to_engine_dict(e) for e in events]
    return compute_run_edit_distances(engine_events)["runs"]


def compute_run_distances_for_session(student_id: str, session_id: str) -> list[dict]:
    """Fetch a session's events from the DB and compute the per-run distance sequence."""
    events = fetch_events_from_db(student_id=student_id, session_id=session_id)
    return compute_run_distances(events)
