"""App-level glue between the agent's EventRecord stream and the pure vendored
trigger engine (server/src/triggers/). The engine stays framework/DB-free; this
module does the adapting so the coupling points one way (app -> engine)."""
from __future__ import annotations

from src.current_state_metrics import EventRecord, fetch_events_from_db
from src.triggers.run_sequence import compute_run_edit_distances
from src.triggers.detectors import detect_run_triggers_by_playground
from src.db import insert_agent_trigger_if_new


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


def detect_triggers_for_session(student_id: str, session_id: str) -> list[tuple]:
    """Detect all momentary triggers for a session: (trigger_type, run_index, detail)."""
    runs = compute_run_distances_for_session(student_id, session_id)
    return detect_run_triggers_by_playground(runs)


def persist_new_triggers(student_id: str, session_id: str) -> list[dict]:
    """Detect triggers for the session and persist the ones not seen before (deduped
    on student/session/type/run_index). Returns only the newly-inserted rows, so the
    caller can act on genuinely-new fires. Detection covers all five trigger types;
    which ones get ACTED on is the caller's policy (v1: wheel_spin only)."""
    new_rows = []
    for trigger_type, run_index, detail in detect_triggers_for_session(student_id, session_id):
        trigger_id = insert_agent_trigger_if_new(
            student_id=student_id,
            session_id=session_id,
            trigger_type=trigger_type,
            run_index=run_index,
            detail=detail,
        )
        if trigger_id is not None:
            new_rows.append({
                "id": trigger_id,
                "trigger_type": trigger_type,
                "run_index": run_index,
                "detail": detail,
            })
    return new_rows
