"""The single pedagogy pipeline, shared by both lanes.

Reactive (a student typed a message) and proactive (a trigger fired) used to be two
hand-copied sequences. They are the same steps: assemble grounded context (raw logs +
episode timeline + current program), run the robot-behavior LLM pass, then the main
feedback pass. The only differences are the inputs:

  - reactive  passes `student_message` (the real student turn), no `behavior_fact`.
  - proactive passes `behavior_fact` (the neutral trigger fact, NEVER the internal
    label -- design doc §9) and an empty `student_message` (there is no student turn).

`feedback_classes` is decided by each caller (reactive: from the snapshot; proactive:
from the trigger) and passed in.
"""
from vex_agent.domain.catalogs import resolve_available_blocks, resolve_task_description
from vex_agent.domain.context_builder import (
    build_current_program,
    build_episode_summary,
    build_raw_logs_context,
)
from vex_agent.llm.client import generate_main_llm_response, generate_robot_behavior_summary
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
    """Run the shared context-assembly + two-pass LLM generation.

    Returns {llm_request, robot_behavior_request, robot_behavior_summary,
    feedback_classes}. `llm_request` is the main feedback dict
    ({response_text, model, prompt}); the robot-behavior artifacts are returned so the
    reactive route can log the prompts it sends. Pass `events` (reactive already has
    them) to skip redundant DB fetches in the episode/program builders."""
    task = resolve_task_description(playground)
    available_blocks = resolve_available_blocks(playground)

    raw_logs = build_raw_logs_context(student_id=student_id, session_id=session_id)
    episode_summary = build_episode_summary(
        student_id=student_id, session_id=session_id, events=events
    )
    if episode_summary:
        raw_logs = f"{episode_summary}\n{raw_logs}"
    current_program = build_current_program(
        student_id=student_id, session_id=session_id, events=events
    )

    robot_behavior_request = generate_robot_behavior_summary(task=task, raw_logs=raw_logs)
    robot_behavior_summary = robot_behavior_request["response_text"]
    # Proactive grounds the same real robot-behavior summary the reactive lane uses, then
    # appends the neutral trigger fact (not a fact-only prompt -- that hallucinated, §9).
    if behavior_fact:
        robot_behavior_summary = f"{robot_behavior_summary}\n\n{behavior_fact}"

    llm_request = generate_main_llm_response(
        task=task,
        student_message=student_message,
        available_blocks=available_blocks,
        current_program=current_program,
        robot_behavior_summary=robot_behavior_summary,
        recent_messages=get_recent_session_messages(student_id, playground, session_id),
        feedback_classes=feedback_classes,
    )
    return {
        "llm_request": llm_request,
        "robot_behavior_request": robot_behavior_request,
        "robot_behavior_summary": robot_behavior_summary,
        "feedback_classes": feedback_classes,
    }
