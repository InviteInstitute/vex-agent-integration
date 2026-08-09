"""The single pedagogy pipeline, shared by both lanes.

Reactive (a student typed a message) and proactive (a trigger fired) used to be two
hand-copied sequences. They are the same steps: assemble grounded context (a
deterministic situation model over the session telemetry + the current program), then
one feedback LLM pass. The only differences are the inputs:

  - reactive  passes `student_message` (the real student turn), no `behavior_fact`.
  - proactive passes `behavior_fact` (the neutral trigger fact, NEVER the internal
    label -- design doc §9) and an empty `student_message` (there is no student turn).

`feedback_classes` is decided by each caller (reactive: from the snapshot; proactive:
from the trigger) and passed in.
"""

from vex_agent.data.db import fetch_events_from_db
from vex_agent.domain.catalogs import resolve_available_blocks, resolve_task_description
from vex_agent.domain.context_builder import build_current_program, build_situation_model
from vex_agent.llm.client import generate_main_llm_response
from vex_agent.services.sessions import get_recent_session_messages


def generate_feedback(
    *,
    student_id: str,
    session_id: str,
    playground: str,
    feedback_classes: set,
    student_message: str = "",
    behavior_fact: str | None = None,
    events=None,
) -> dict:
    """Run the shared context-assembly + single-pass LLM generation.

    Returns {llm_request, situation, feedback_classes}. `llm_request` is the feedback
    dict ({response_text, model, prompt}); `situation` is the deterministic grounding
    block fed to the model (returned so the route can log it). Pass `events` (reactive
    already has them) to skip a redundant DB fetch.

    Grounding is deterministic (build_situation_model over the session telemetry), not a
    second "what did the robot do" LLM call -- one LLM call, no raw logs, no paraphrase
    that can drift (design doc §9)."""
    task = resolve_task_description(playground)
    available_blocks = resolve_available_blocks(playground)

    if events is None:
        events = fetch_events_from_db(student_id=student_id, session_id=session_id)

    situation = build_situation_model(events)
    # Proactive appends the neutral trigger fact to the measured facts (never a fact-only
    # prompt -- that hallucinated, §9); reactive passes no behavior_fact.
    if behavior_fact:
        situation = f"{situation}\n\n{behavior_fact}"
    current_program = build_current_program(
        student_id=student_id, session_id=session_id, events=events
    )

    llm_request = generate_main_llm_response(
        task=task,
        student_message=student_message,
        available_blocks=available_blocks,
        current_program=current_program,
        situation=situation,
        recent_messages=get_recent_session_messages(student_id, playground, session_id),
        feedback_classes=feedback_classes,
    )
    return {
        "llm_request": llm_request,
        "situation": situation,
        "feedback_classes": feedback_classes,
    }
