"""App-level glue between the agent's EventRecord stream and the pure vendored
trigger engine (server/src/triggers/). The engine stays framework/DB-free; this
module does the adapting so the coupling points one way (app -> engine)."""
from __future__ import annotations

from src.current_state_metrics import (
    EventRecord, fetch_events_from_db, build_raw_logs_context,
)
from src.triggers.run_sequence import compute_run_edit_distances
from src.triggers.detectors import detect_run_triggers_by_playground
from src.db import insert_agent_trigger_if_new
from src.feedback_policy import FeedbackClass
from src.task_catalog import resolve_task_description
from src.block_catalog import resolve_available_blocks
from src.session_service import get_recent_session_messages
from src.llm_service import generate_robot_behavior_summary, generate_main_llm_response

DEFAULT_PLAYGROUND = "GO-Mars"

# Seed table (from the spike). Only wheel_spin is ACTED on in v1; the rest are
# seeded so graduating them later (issues #13/#14) is a one-line change.
TRIGGER_TO_FEEDBACK_CLASS = {
    "wheel_spin": {FeedbackClass.REASSURE, FeedbackClass.DIAGNOSE},
    "resilience": {FeedbackClass.EVIDENCE_BASED_PRAISE},
    "iterative": {FeedbackClass.EVIDENCE_BASED_PRAISE},
    "explorer": {FeedbackClass.DIAGNOSE},
    "inactive": {FeedbackClass.REASSURE, FeedbackClass.QUESTION},
}
ACTED_TRIGGERS = {"wheel_spin"}

# The trigger fed to the LLM as a NEUTRAL behavioral fact -- never the internal
# label ("Wheel-spinning"), which the spike showed leaking into student-facing text.
_NEUTRAL_FACT = {
    "wheel_spin": "The student keeps running the same program without changing any blocks.",
    "resilience": "The student just changed their program after several unchanged runs.",
    "explorer": "The student made a large change to their program in a single step.",
    "iterative": "The student has been making steady, small changes to their program.",
    "inactive": "The student has not done anything for a while.",
}


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


def feedback_classes_for_trigger(trigger_type: str) -> set:
    """The pedagogical feedback class(es) the agent reaches out with for a trigger."""
    return TRIGGER_TO_FEEDBACK_CLASS.get(trigger_type, set())


def generate_proactive_response(
    student_id: str,
    session_id: str,
    trigger_type: str,
    detail: dict | None = None,
    playground: str | None = None,
) -> dict | None:
    """Produce a proactive intervention for a fired trigger, reusing the reactive
    pipeline (so proactive and reactive share the same pedagogy + sanitizer + trim).
    Returns None for triggers v1 doesn't act on.

    Two spike learnings baked in: (1) the message is grounded in the REAL robot-behavior
    summary over the session's logs, not the trigger fact alone; (2) the trigger enters
    as a NEUTRAL behavioral fact, never its internal label, and student_message is empty
    (there is no student turn)."""
    if trigger_type not in ACTED_TRIGGERS:
        return None
    feedback_classes = feedback_classes_for_trigger(trigger_type)
    if not feedback_classes:
        return None

    playground = playground or DEFAULT_PLAYGROUND
    task = resolve_task_description(playground)
    available_blocks = resolve_available_blocks(playground)
    raw_logs = build_raw_logs_context(student_id=student_id, session_id=session_id)
    robot_behavior = generate_robot_behavior_summary(task=task, raw_logs=raw_logs)["response_text"]
    neutral_fact = _NEUTRAL_FACT.get(trigger_type, "The student may need a check-in.")
    grounded_summary = f"{robot_behavior}\n\n{neutral_fact}"

    return generate_main_llm_response(
        task=task,
        student_message="",
        available_blocks=available_blocks,
        robot_behavior_summary=grounded_summary,
        recent_messages=get_recent_session_messages(student_id, playground, session_id),
        feedback_classes=feedback_classes,
    )
