import logging
from time import monotonic
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException

from src.block_catalog import resolve_available_blocks
from src.current_state_metrics import (
    build_raw_logs_context,
    compute_snapshot_for_student_session,
    fetch_events_from_db,
    has_active_project_run,
    select_current_playground_segment,
)
from src.db import (
    get_latest_session_id_for_student,
    get_message_id_for_response,
    insert_message,
    insert_message_feedback,
)
from src.feedback_policy import FeedbackClass, determine_feedback_class
from src.llm_service import generate_main_llm_response, generate_robot_behavior_summary
from src.log_sync import sync_invite_hub_logs
from src.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    MessageRequest,
    MessageResponse,
    SessionResolutionResponse,
    StudentResponseRequest,
    StudentResponseResponse,
)
from src.session_service import append_session_message, get_recent_session_messages
from src.task_catalog import resolve_task_description

router = APIRouter(prefix="/v1", tags=["students"])
logger = logging.getLogger(__name__)
DEFAULT_PLAYGROUND = "GO-Mars"
SESSION_CACHE_TTL_S = 60.0
SYNC_COOLDOWN_S = 15.0
ACTIVE_RUN_MESSAGE = (
    "Please stop your current run using the Stop button in the bottom-left of the playground, "
    "then ask for help again."
)
WRONG_PLAYGROUND_MESSAGE = (
    "You are on the wrong playground right now. Switch to GO-Mars, then ask for help again."
)
_latest_session_cache: dict[str, tuple[str, float]] = {}
_last_sync_at: dict[str, float] = {}


def log_stage(stage: str, **fields: object) -> None:
    lines = [f"[{stage}]"]
    lines.extend(f"  {key}: {value}" for key, value in fields.items())
    logger.info("\n".join(lines))


def remember_latest_session(student_id: str, session_id: str) -> None:
    _latest_session_cache[student_id] = (session_id, monotonic())


def get_cached_session_id(student_id: str) -> str | None:
    cached = _latest_session_cache.get(student_id)
    if not cached:
        return None
    session_id, cached_at = cached
    if monotonic() - cached_at > SESSION_CACHE_TTL_S:
        _latest_session_cache.pop(student_id, None)
        return None
    return session_id


def maybe_sync_invite_hub_logs(student_id: str) -> int:
    last_sync_at = _last_sync_at.get(student_id)
    now = monotonic()
    if last_sync_at is not None and now - last_sync_at < SYNC_COOLDOWN_S:
        return 0
    synced_count = sync_invite_hub_logs(student_id=student_id)
    _last_sync_at[student_id] = now
    return synced_count


def resolve_session_id_for_student(student_id: str) -> str:
    cached_session_id = get_cached_session_id(student_id)
    if cached_session_id is not None:
        return cached_session_id
    session_id = get_latest_session_id_for_student(student_id)
    if session_id is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No recent GO-Mars logs were found for this student. "
                "Run the project once in VEX VR, then try again."
            ),
        )
    remember_latest_session(student_id, session_id)
    return session_id


def resolve_session_id_with_sync(student_id: str) -> tuple[str, int]:
    try:
        return resolve_session_id_for_student(student_id), 0
    except HTTPException as error:
        if error.status_code != 404:
            raise
    synced_log_count = maybe_sync_invite_hub_logs(student_id)
    return resolve_session_id_for_student(student_id), synced_log_count


@router.get("/students/{student_id}/session", response_model=SessionResolutionResponse)
def resolve_session(student_id: str) -> SessionResolutionResponse:
    resolved_session_id, synced_log_count = resolve_session_id_with_sync(student_id)
    current_playground = DEFAULT_PLAYGROUND

    events = fetch_events_from_db(student_id=student_id, session_id=resolved_session_id)
    if events:
        current_playground, _ = select_current_playground_segment(events)

    log_stage(
        "Session Resolved",
        student_id=student_id,
        session_id=resolved_session_id,
        synced_log_count=synced_log_count,
        playground=current_playground,
    )

    return SessionResolutionResponse(
        session_id=resolved_session_id,
        student_id=student_id,
        playground=current_playground,
        status="resolved",
    )

@router.post("/students/{student_id}/messages", response_model=MessageResponse)
def create_message(student_id: str, payload: MessageRequest) -> MessageResponse:
    message_id = uuid4()
    source = "help_button" if payload.message == "" else "chat"
    student_message_text = payload.message if payload.message else "Help"
    resolved_playground = payload.playground or DEFAULT_PLAYGROUND
    if payload.session_id:
        resolved_session_id = payload.session_id
        remember_latest_session(student_id, resolved_session_id)
    else:
        resolved_session_id, _ = resolve_session_id_with_sync(student_id)
    session_uuid = UUID(resolved_session_id)
    append_session_message(
        student_id=student_id,
        playground=resolved_playground,
        session_id=resolved_session_id,
        role="student",
        content=student_message_text,
    )
    insert_message(
        session_id=session_uuid,
        student_id=student_id,
        role="student",
        message_text=student_message_text,
    )
    log_stage(
        "Student Message Received",
        student_id=student_id,
        session_id=resolved_session_id,
        playground=resolved_playground,
        source=source,
        message=student_message_text,
    )
    return MessageResponse(
        message_id=str(message_id),
        session_id=resolved_session_id,
        student_id=student_id,
        playground=resolved_playground,
        message=payload.message,
        source=source,
        status="received",
    )


@router.post("/students/{student_id}/responses", response_model=StudentResponseResponse)
def create_response(
    student_id: str,
    payload: StudentResponseRequest,
) -> StudentResponseResponse:
    response_id = uuid4()
    resolved_session_id = payload.session_id
    resolved_playground = payload.playground or DEFAULT_PLAYGROUND
    llm_request = None
    response_text = payload.response_text
    feedback_classes = set()
    synced_log_count = 0
    task = resolve_task_description(resolved_playground)
    available_blocks = resolve_available_blocks(resolved_playground)
    raw_logs = "None"
    robot_behavior_summary = "None"
    recent_messages: list[dict[str, str]] = []

    # Refresh event logs — always pull so feedback reflects the student's newest run
    sync_invite_hub_logs(student_id=student_id)

    if task and payload.student_message:
        try:
            if resolved_session_id is None:
                resolved_session_id, synced_log_count = resolve_session_id_with_sync(student_id)
            else:
                remember_latest_session(student_id, resolved_session_id)
            events = fetch_events_from_db(
                student_id=student_id,
                session_id=resolved_session_id,
            )
            current_playground, _ = select_current_playground_segment(events)
            if current_playground != DEFAULT_PLAYGROUND:
                response_text = WRONG_PLAYGROUND_MESSAGE
                log_stage(
                    "Wrong Playground Detected",
                    student_id=student_id,
                    session_id=resolved_session_id,
                    synced_log_count=synced_log_count,
                    current_playground=current_playground,
                    expected_playground=DEFAULT_PLAYGROUND,
                    message=response_text,
                )
            elif has_active_project_run(events):
                response_text = ACTIVE_RUN_MESSAGE
                log_stage(
                    "Active Run Detected",
                    student_id=student_id,
                    session_id=resolved_session_id,
                    synced_log_count=synced_log_count,
                    message=response_text,
                )
            else:
                snapshot = compute_snapshot_for_student_session(
                    student_id=student_id,
                    session_id=resolved_session_id,
                    insert=True,
                )
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Current state analysis failed: {error}",
            ) from error
        if response_text is None:
            log_stage(
                "Current State Analyzer Output",
                student_id=student_id,
                session_id=resolved_session_id,
                synced_log_count=synced_log_count,
                snapshot=snapshot.to_dict(),
            )
            feedback_classes = determine_feedback_class(snapshot)
            if not feedback_classes:
                feedback_classes = {FeedbackClass.QUESTION}
            raw_logs = build_raw_logs_context(
                student_id=student_id,
                session_id=resolved_session_id,
            )
            recent_messages = get_recent_session_messages(
                student_id,
                resolved_playground,
                resolved_session_id,
            )
            log_stage(
                "Feedback Policy Output",
                student_id=student_id,
                session_id=resolved_session_id,
                synced_log_count=synced_log_count,
                feedback_classes=sorted(
                    feedback_class.value for feedback_class in feedback_classes
                ),
            )

    if task and payload.student_message and feedback_classes:
        try:
            robot_behavior_request = generate_robot_behavior_summary(
                task=task,
                raw_logs=raw_logs,
            )
            robot_behavior_summary = robot_behavior_request["response_text"]
            log_stage(
                "Robot Behavior Prompt Sent",
                student_id=student_id,
                session_id=resolved_session_id,
                model=robot_behavior_request["model"],
                prompt=robot_behavior_request["prompt"],
            )
            log_stage(
                "Robot Behavior Output",
                student_id=student_id,
                session_id=resolved_session_id,
                behavior_summary=robot_behavior_summary,
            )
            log_stage(
                "LLM Request Starting",
                student_id=student_id,
                session_id=resolved_session_id,
                model=robot_behavior_request["model"],
                feedback_classes=sorted(
                    feedback_class.value for feedback_class in feedback_classes
                ),
            )
            llm_request = generate_main_llm_response(
                task=task,
                student_message=payload.student_message,
                available_blocks=available_blocks,
                robot_behavior_summary=robot_behavior_summary,
                recent_messages=recent_messages,
                feedback_classes=feedback_classes,
            )
            log_stage(
                "LLM Prompt Sent",
                student_id=student_id,
                session_id=resolved_session_id,
                model=llm_request["model"],
                prompt=llm_request["prompt"],
            )
            response_text = llm_request["response_text"]
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
    elif not response_text:
        raise HTTPException(
            status_code=400,
            detail="Either response_text or playground/student_message must be provided.",
        )

    if resolved_session_id is None:
        resolved_session_id = resolve_session_id_for_student(student_id)

    session_uuid = UUID(resolved_session_id)

    append_session_message(
        student_id=student_id,
        playground=resolved_playground,
        session_id=resolved_session_id,
        role="assistant",
        content=response_text,
    )
    insert_message(
        session_id=session_uuid,
        student_id=student_id,
        role="assistant",
        message_text=response_text,
        feedback_class=", ".join(
            sorted(feedback_class.value for feedback_class in feedback_classes)
        )
        if feedback_classes
        else None,
        response_id=response_id,
    )
    log_stage(
        "Assistant Response Sent",
        student_id=student_id,
        session_id=resolved_session_id,
        response_id=str(response_id),
        message=response_text,
    )

    return StudentResponseResponse(
        response_id=str(response_id),
        session_id=resolved_session_id,
        student_id=student_id,
        playground=resolved_playground,
        message_id=payload.message_id,
        response_text=response_text,
        llm_model=llm_request["model"] if llm_request else None,
        llm_prompt=llm_request["prompt"] if llm_request else None,
        status="received",
    )


@router.post(
    "/students/{student_id}/responses/{response_id}/feedback",
    response_model=FeedbackResponse,
)
def create_feedback(
    student_id: str,
    response_id: str,
    payload: FeedbackRequest,
) -> FeedbackResponse:
    try:
        response_uuid = UUID(response_id)
        message_id = get_message_id_for_response(
            response_id=response_uuid,
            student_id=student_id,
        )
        if message_id is None:
            raise HTTPException(
                status_code=404,
                detail="Assistant response not found for this student.",
            )
        insert_message_feedback(
            message_id=message_id,
            student_id=student_id,
            thumb=payload.thumb,
            comment=payload.comment,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail="response_id must be a valid UUID.") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return FeedbackResponse(
        student_id=student_id,
        response_id=response_id,
        thumb=payload.thumb,
        comment=payload.comment,
        status="received",
    )
