"""App-level glue between the agent's EventRecord stream and the pure vendored
trigger engine (server/src/triggers/). The engine stays framework/DB-free; this
module does the adapting so the coupling points one way (app -> engine)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.current_state_metrics import (
    EventRecord, fetch_events_from_db, build_raw_logs_context,
)
from src.triggers.run_sequence import compute_run_edit_distances
from src.triggers.detectors import detect_run_triggers_by_playground
from src.triggers.constants import INACTIVE_TRIGGER_SECONDS, TRIGGER_LABELS
from src.db import insert_agent_trigger_if_new, insert_message, mark_agent_trigger_acted
from src.feedback_policy import FeedbackClass
from src.task_catalog import resolve_task_description
from src.block_catalog import resolve_available_blocks
from src.session_service import get_recent_session_messages, append_session_message
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
ACTED_TRIGGERS = {"wheel_spin", "resilience", "inactive"}

# inactive is sustained (time-based, not edit-distance), so it isn't produced by the
# per-run detector. It fires once per session (a fixed run_index sentinel deduplicates
# it) when the last event is older than the idle threshold.
INACTIVE_RUN_INDEX = -1

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
    """Detect all momentary (edit-distance) triggers for a session:
    (trigger_type, run_index, detail)."""
    runs = compute_run_distances_for_session(student_id, session_id)
    return detect_run_triggers_by_playground(runs)


def is_inactive(last_event_ts: datetime | None, now: datetime) -> bool:
    """True if the last event is older than the idle threshold."""
    if last_event_ts is None:
        return False
    return (now - last_event_ts).total_seconds() >= INACTIVE_TRIGGER_SECONDS


def detect_inactive_trigger(student_id: str, session_id: str, now: datetime | None = None):
    """The sustained inactive trigger: fires once per session (INACTIVE_RUN_INDEX
    sentinel dedupes it) when the session has gone idle. Returns a fire tuple or None."""
    events = fetch_events_from_db(student_id=student_id, session_id=session_id)
    if not events:
        return None
    now = now or datetime.now(timezone.utc)
    last_ts = events[-1].event_ts  # events are ascending by event_ts
    if not is_inactive(last_ts, now):
        return None
    idle_minutes = int((now - last_ts).total_seconds() // 60)
    return ("inactive", INACTIVE_RUN_INDEX,
            {"label": TRIGGER_LABELS["inactive"], "value": f"idle {idle_minutes}m"})


def persist_new_triggers(student_id: str, session_id: str) -> list[dict]:
    """Detect triggers for the session and persist the ones not seen before (deduped
    on student/session/type/run_index). Returns only the newly-inserted rows, so the
    caller can act on genuinely-new fires. Detection covers all trigger types; which
    ones get ACTED on is the caller's policy (ACTED_TRIGGERS)."""
    fires = list(detect_triggers_for_session(student_id, session_id))
    inactive_fire = detect_inactive_trigger(student_id, session_id)
    if inactive_fire is not None:
        fires.append(inactive_fire)

    new_rows = []
    for trigger_type, run_index, detail in fires:
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


def run_proactive_tick(student_id: str, session_id: str, playground: str | None = None) -> dict:
    """One full pass for a session: detect + dedupe-persist triggers, then for each
    NEW acted-on trigger, generate a proactive message, persist it to chat.messages
    (origin='proactive'), record it in the in-memory session, and mark the trigger
    acted. Returns what was detected and what was acted on. This is the Slice-1
    capstone the /admin/tick endpoint and (later) the daemon both call."""
    playground = playground or DEFAULT_PLAYGROUND
    new_triggers = persist_new_triggers(student_id, session_id)
    acted = []
    for fire in new_triggers:
        result = generate_proactive_response(
            student_id, session_id, fire["trigger_type"], fire["detail"], playground,
        )
        if result is None:  # trigger not acted on in v1
            continue
        response_id = uuid4()
        message_text = result["response_text"]
        feedback_class = ", ".join(
            sorted(c.value for c in feedback_classes_for_trigger(fire["trigger_type"]))
        )
        insert_message(
            session_id=UUID(session_id),
            student_id=student_id,
            role="assistant",
            message_text=message_text,
            feedback_class=feedback_class,
            response_id=response_id,
            origin="proactive",
        )
        append_session_message(
            student_id=student_id, playground=playground, session_id=session_id,
            role="assistant", content=message_text,
        )
        mark_agent_trigger_acted(trigger_id=fire["id"], response_id=response_id)
        acted.append({
            "trigger_id": fire["id"],
            "trigger_type": fire["trigger_type"],
            "run_index": fire["run_index"],
            "response_id": str(response_id),
            "message": message_text,
        })
    return {"detected": new_triggers, "acted": acted}
