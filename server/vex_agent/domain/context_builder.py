"""
Context Builder
"""

import json
from dataclasses import dataclass, field

from vex_agent.data.db import fetch_events_from_db
from vex_agent.domain.feedback_policy import FeedbackClass
from vex_agent.domain.metrics import (
    GO_MARS_MILESTONE_RULES,
    EventRecord,
    analyze_current_state,
    extract_playground_parameters,
)


@dataclass
class FeedbackSpec:
    description: str
    examples: list[str]
    extra_notes: list[str] = field(default_factory=list)


FEEDBACK_SPECS = {
    "Positive Feedback": FeedbackSpec(
        description="Confirms that the action is fully correct. Clearly identifies what was done correctly and why it works. Focus on the task.",
        examples=[
            "You specified an appropriate distance for the robot to move forward, so it will not fall over the cliff.",
            "You used the [x] block, which allowed the robot to pick up the trash.",
        ],
        extra_notes=[
            "Keep the message concise and specific without excessive praise. Emphasize what makes the text correct and the student's apparent reasoning, rather than their abilities."
        ],
    ),
    "Partial Correctness": FeedbackSpec(
        description="Acknowledges what is correct, but also acknowledges what needs adjustment.",
        examples=[
            "You took the correct steps to avoid the debris, but you need to turn right earlier to avoid getting stuck. Make the turn right block appear earlier."
        ],
        extra_notes=[
            "Start with what works, then address what needs revision. Keep feedback manageable and focused on one or two issues, or keep the feedback more high level."
        ],
    ),
    "Corrective Guidance": FeedbackSpec(
        description="Indicates that the action is incorrect and provides clear guidance on how to fix it.",
        examples=[
            "The move forward command runs for too long, which is why your robot falls off the cliff. Replace the distance with something shorter.",
            "Your if block is always going to be true, so your robot will never turn left.",
        ],
        extra_notes=[],
    ),
    "Evidence-Based Praise": FeedbackSpec(
        description="Highlights a specific successful action and explains why it was effective. The goal is to encourage effort based on evidence.",
        examples=[
            "Your use of the conditional if statement allows your agent to move in the correct way without requiring a lot of code.",
            "You cleaned up the trash with very few lines of code.",
        ],
        extra_notes=[
            "Ensure that praise is tied to a specific accomplishment to avoid directing attention to the self.",
            "As long as the student is making progress, validate their work, which is not the same as praise.",
            "Focus on strategies and decisions, not the person.",
        ],
    ),
    "Reassure": FeedbackSpec(
        description="Encourages persistence by reducing student frustration. Validates prior effort and lets them know they are on the right track.",
        examples=[
            "Loops can be tricky. It is very common to have loops run forever until you find the right solution.",
            "You are definitely on the right track and taking the necessary steps. A lot of students struggle with this problem.",
        ],
        extra_notes=[],
    ),
    "Error Flagging": FeedbackSpec(
        description="Identifies a specific error clearly and objectively without immediately providing the full solution.",
        examples=[
            "The while statement is always true and will run forever.",
            "You did not connect the two blocks.",
            "The blocks are in the wrong order.",
        ],
        extra_notes=["Name the exact issue. Avoid framing it around the person."],
    ),
    "How To": FeedbackSpec(
        description="Provides step-by-step instructions to do a task or solve the problem.",
        examples=["To solve the problem of [problem], take steps a, b, c, and n."],
        extra_notes=[
            "Break the explanation into small steps. Do not overwhelm the student with technical terms."
        ],
    ),
    "Inform": FeedbackSpec(
        description="Provides relevant knowledge about VEX VR components or behavior.",
        examples=["Changing the speed affects how fast you go and how fast you turn."],
        extra_notes=[],
    ),
    "Hint": FeedbackSpec(
        description="Encourages the learner to examine a specific part of their code without giving an explicit solution.",
        examples=[
            "Check where the stop driving block is placed.",
            "Look at the order of each of your commands.",
        ],
        extra_notes=["Keep the solution subtle."],
    ),
    "Encourage Testing (Diagnose)": FeedbackSpec(
        description="Guides the learner to test the behavior of the robot to discover the issue independently.",
        examples=[
            "Does the condition in the while block ever become false?",
            "If you reduce the speed, does turning become more accurate?",
        ],
        extra_notes=[
            "Encourage experimentation in the VR environment and develop debugging skills."
        ],
    ),
    "Question": FeedbackSpec(
        description="Provides a focused question to stimulate reasoning about the problem.",
        examples=[
            "How many degrees should the robot turn to face the next obstacle?",
            "At what point does the condition in the block become false?",
        ],
        extra_notes=["Questions should be purposeful."],
    ),
    "Fill-in-the-Blank": FeedbackSpec(
        description="Makes the student recall a concept they are not thinking of or have forgotten.",
        examples=[
            "The _________ block stops all movement.",
            "To implement a condition, use the ___________ block.",
        ],
        extra_notes=["Reinforce VEX and programming jargon in the student's memory."],
    ),
    "Elaborate": FeedbackSpec(
        description="Provides a deeper explanation of why something happens.",
        examples=[
            "The robot misses the item because the drive distance is longer than it should be before turning.",
            "The robot continues turning because the turn block or loop is never false.",
        ],
        extra_notes=["Do this in small segments."],
    ),
    "Remind": FeedbackSpec(
        description="Restates the robotic goal.",
        examples=[
            "The goal is for the robot to pick up all objects.",
            "Right now, the robot keeps driving because the condition to stop is never met.",
        ],
        extra_notes=[
            "This is useful when the learner is possibly misunderstanding the task or outcome."
        ],
    ),
    "Next Step": FeedbackSpec(
        description="Gives a single immediate robotics action to try next.",
        examples=[
            "You could try changing the turn value to 90 degrees and try again.",
            "What if you lower the speed to 75% and test the path?",
        ],
        extra_notes=["Use this as a last resort."],
    ),
}

FEEDBACK_CLASS_TO_SPEC_KEY = {
    FeedbackClass.POSITIVE_FEEDBACK: "Positive Feedback",
    FeedbackClass.PARTIAL_CORRECTNESS: "Partial Correctness",
    FeedbackClass.CORRECTIVE_GUIDANCE: "Corrective Guidance",
    FeedbackClass.EVIDENCE_BASED_PRAISE: "Evidence-Based Praise",
    FeedbackClass.REASSURE: "Reassure",
    FeedbackClass.ERROR_FLAGGING: "Error Flagging",
    FeedbackClass.HOW_TO: "How To",
    FeedbackClass.INFORM: "Inform",
    FeedbackClass.NUDGE: "Hint",
    FeedbackClass.DIAGNOSE: "Encourage Testing (Diagnose)",
    FeedbackClass.QUESTION: "Question",
    FeedbackClass.ELABORATE: "Elaborate",
    FeedbackClass.REPEAT: "Remind",
    FeedbackClass.NEXT_STEP: "Next Step",
}


PROMPT_TEMPLATE = """You are an educational feedback assistant for VEXcode VR, a block-based programming tool for middle school students.

Your job is to write one short feedback message for the student.

INPUTS

Task:
{task}

Available blocks:
{available_blocks}

Student's current program (parsed from their workspace):
{current_program}

Student message:
{student_message}

What's happening now (measured from the session's telemetry):
{situation}

Recent chat in this session:
{recent_chat}

Feedback types to use:
{feedback_types}

Feedback type descriptions:
{descriptions}

Examples of each feedback type:
{examples}

Extra notes:
{extra_notes}

INSTRUCTIONS

Use these sources in this priority order:
1. Student message
2. The student's current program (what blocks are actually on the workspace)
3. What's happening now (the measured telemetry facts)
4. Recent chat
5. Task
6. Feedback type descriptions/examples/notes

Before writing feedback:
- Use the student's current program as the source of truth for which blocks are on the workspace and how they are connected.
- Use the measured telemetry facts to understand the student's progress, trajectory, and any error the robot reported. These facts are measured, not guessed -- trust them, but do not restate a number the student can already see.
- Only mention a block that appears in the current program. If the current program is empty or unavailable, do not guess or mention a specific block.
- Do not invent actions, errors, goals, or progress that are not supported by the inputs.

How to write the feedback:
- Write for a middle school student.
- Use simple, direct, natural language.
- Be specific and clear.
- Keep feedback as simple as possible, but no simpler.
- Give unbiased, objective feedback.
- Combine ALL listed feedback types into one cohesive message.
- If the feedback types pull in different directions, blend them naturally into one message instead of forcing separate ideas.
- Prefer the most immediately useful next step for the student.

Behavior rules:
- Do not give an overall evaluation or grade.
- Do not discourage the student or threaten self-esteem.
- Use praise sparingly and only if supported by the student's recent work.
- Do not interrupt active productive work with unnecessary advice.
- If the student's input is unclear or vague, ask them to restate their question clearly.
- In extreme cases of long-term struggle or no progress, tell the student to ask their teacher for help.

Block reference rule:
- When referring to a specific block, wrap only the exact block name in backticks.
- Preserve the exact capitalization and wording from the Available blocks list.

OUTPUT RULES
- Output only the feedback message.
- Do not include labels, explanations, bullet points, or quotation marks.
- Prefer one bite-sized hint or explanation over a full paragraph.
- Keep it to exactly 1 short sentence.
- Aim for about 10-18 words when possible.
- Never exceed 22 words.
"""


def build_feedback_prompt(
    task: str,
    student_message: str,
    available_blocks: str,
    current_program: str,
    situation: str,
    recent_chat: str,
    feedback_types: list[str],
    feedback_specs: dict,
) -> str:
    feedback_types_text = "\n".join(f"- {t}" for t in feedback_types)

    descriptions_text = "\n\n".join(
        f"{t}:\n{feedback_specs[t].description}" for t in feedback_types
    )

    examples_text = "\n\n".join(
        f"{t}:\n" + "\n".join(f"- {e}" for e in feedback_specs[t].examples) for t in feedback_types
    )

    extra_notes_text = "\n\n".join(
        f"{t}:\n"
        + (
            "\n".join(f"- {n}" for n in feedback_specs[t].extra_notes)
            if feedback_specs[t].extra_notes
            else "None"
        )
        for t in feedback_types
    )

    return PROMPT_TEMPLATE.format(
        task=task,
        student_message=student_message,
        available_blocks=available_blocks,
        current_program=current_program,
        situation=situation,
        recent_chat=recent_chat,
        feedback_types=feedback_types_text,
        descriptions=descriptions_text,
        examples=examples_text,
        extra_notes=extra_notes_text,
    )


def build_feedback_prompt_from_classes(
    task: str,
    student_message: str,
    available_blocks: list[str] | None,
    current_program: str,
    situation: str,
    recent_messages: list[dict[str, str]],
    feedback_classes: set[FeedbackClass],
) -> str:
    feedback_types = []
    for feedback_class in feedback_classes:
        feedback_type = FEEDBACK_CLASS_TO_SPEC_KEY.get(feedback_class)
        if feedback_type and feedback_type not in feedback_types:
            feedback_types.append(feedback_type)

    recent_chat = "\n".join(
        f"{message['role'].capitalize()}: {message['content']}" for message in recent_messages
    )
    if not recent_chat:
        recent_chat = "None"

    available_blocks_text = "\n".join(f"- {block}" for block in available_blocks or [])
    if not available_blocks_text:
        available_blocks_text = "None provided"

    if not current_program:
        current_program = "None available (no project snapshot yet)"

    return build_feedback_prompt(
        task=task,
        student_message=student_message,
        available_blocks=available_blocks_text,
        current_program=current_program,
        situation=situation,
        recent_chat=recent_chat,
        feedback_types=feedback_types,
        feedback_specs=FEEDBACK_SPECS,
    )


def build_current_program(
    student_id: str,
    session_id: str,
    *,
    events: list[EventRecord] | None = None,
) -> str:
    """Render the student's current workspace as compact pseudo-code for the LLM,
    via the vendored smart_delta engine ([Active]/[Orphaned] tree with fields).

    Grounds the feedback in the student's ACTUAL code (not just the block catalog
    or a raw-log dump) -- directly addresses the spike's "hallucination from thin
    grounding" learning (design doc §9). Falls back to humanize's readable listing
    (with parameter values) when smart_delta yields nothing. Returns "" when no
    project snapshot exists.

    Pass `events` to skip a redundant DB fetch (the reactive route already has them)."""
    from vex_agent.triggers.ast_builder import extract_workspace_xml
    from vex_agent.triggers.humanize import humanize_text
    from vex_agent.triggers.smart_delta import generate_llm_prompt_from_project

    if events is None:
        events = fetch_events_from_db(student_id=student_id, session_id=session_id)
    if not events:
        return ""

    # The latest runProject carries the most recent full workspace. Fall back to the
    # latest event with a project_json if no runProject is present.
    latest_project = None
    for event in reversed(events):
        if event.event_type == "runProject" and event.project_json:
            latest_project = event.project_json
            break
    if latest_project is None:
        for event in reversed(events):
            if event.project_json:
                latest_project = event.project_json
                break
    if not latest_project:
        return ""

    # smart_delta's bootstrap accepts a project dict (it json.loads strings, passes
    # dicts through). Prefer its [Active]/[Orphaned] render; fall back to humanize's
    # readable listing (which keeps <value> parameter numbers smart_delta drops).
    prompt = generate_llm_prompt_from_project(
        json.dumps(latest_project) if not isinstance(latest_project, str) else latest_project
    )
    if prompt:
        return prompt

    workspace_xml = extract_workspace_xml({"project": latest_project})
    return humanize_text(workspace_xml)


# Neutral, plain-language readings of the deterministic snapshot signals. Never the
# internal enum label (design doc §9) -- these phrase what the telemetry measured so the
# single feedback call can ground on it without a second LLM "what did the robot do" pass.
_DIRECTION_PHRASE = {
    "INCREASING": "going up",
    "DECREASING": "going down",
    "STATIC": "holding steady",
}
_COGNITION_PHRASE = {
    "LONG_TERM_STALLED_PROGRESS": "has spent a long time with little change in progress",
    "DEVELOPMENT_INCREASES_PROGRESS": "has been improving their progress with recent changes",
    "DEVELOPMENT_STATIC_PROGRESS": "has been editing but progress has held steady",
    "DEVELOPMENT_DECREASES_PROGRESS": "made recent changes that lowered their progress",
    "TRIAL_AND_ERROR": "is trying many quick changes and re-running to see what happens",
    "CODE_ABANDONMENT": "removed code that had been improving their progress",
    "STEP_BY_STEP_ELIMINATION": "is removing pieces one at a time to isolate a problem",
    "SNAP_N_TEST": "is adding one block at a time and testing after each",
}
_PERSISTENCE_PHRASE = {
    "HIGH_PERSISTER": "has kept trying persistently despite low progress",
    "EARLY_QUITTER": "showed signs of stopping early",
    "EXPECTED_COMPLETION": "is at or near finishing the task",
}
# Readable names for the GO-Mars milestone rules -- turns the aggregate progress % into
# the concrete goal-gap (which milestones are done vs still to do) for the tutor.
_MILESTONE_LABEL = {
    "move_sample_out_of_crater": "move a sample out of the crater",
    "place_sample_on_lab": "place a sample on the lab",
    "tilt_solar_panel": "tilt the solar panel",
    "move_hero_bot_out_of_crater": "rescue the rover",
    "lift_rocket_ship_upright": "lift the rocket ship upright",
    "remove_fuel_cells_from_cradles": "remove fuel cells from the cradles",
}


def build_situation_model(events: list[EventRecord] | None) -> str:
    """Deterministic grounding facts for the feedback prompt, read straight from the
    session's structured telemetry. This REPLACES the old raw-log LLM summary pass: the
    same CurrentStateSnapshot the feedback-class policy already computes (progress toward
    the goal, its trajectory, the student's work pattern, persistence, reflective pauses),
    the concrete milestones done vs still to do, and the last error the robot reported --
    rendered as a compact labeled block.

    Every fact is measured, not paraphrased, so nothing here can hallucinate (design doc
    §9). Never emits raw logs. Returns "None" when there is nothing to ground on (no
    events, or a playground with no configured progress metric)."""
    if not events:
        return "None"
    # ponytail: progress metric is GO-Mars-only; analyze_current_state raises ValueError
    # for any other playground. Degrade to code-only grounding rather than break feedback.
    try:
        snapshot = analyze_current_state(events)
    except ValueError:
        return "None"

    lines = [
        f"Goal progress: {snapshot.progress_pct:.0f}% "
        f"({_DIRECTION_PHRASE.get(snapshot.direction.value, 'holding steady')})."
    ]

    # Concrete goal-gap: evaluate each milestone rule on the latest playgroundData
    # parameters (straight from the log payload) -- done vs still to do.
    parameters: dict = {}
    for event in reversed(events):
        params = extract_playground_parameters(event.playground_data_json)
        if params:
            parameters = params
            break
    if parameters:
        done = [
            label
            for name, label in _MILESTONE_LABEL.items()
            if GO_MARS_MILESTONE_RULES[name](parameters)
        ]
        todo = [
            label
            for name, label in _MILESTONE_LABEL.items()
            if not GO_MARS_MILESTONE_RULES[name](parameters)
        ]
        if done:
            lines.append("Milestones done: " + ", ".join(done) + ".")
        if todo:
            lines.append("Still to do: " + ", ".join(todo) + ".")

    run_count = sum(1 for event in events if event.event_type == "runProject")
    lines.append(
        f"Time on task: {snapshot.time_on_task_s / 60.0:.0f} min, {run_count} run(s) so far."
    )

    pattern = _COGNITION_PHRASE.get(snapshot.cognition.value)
    if pattern:
        lines.append(f"Work pattern: the student {pattern}.")
    persistence = _PERSISTENCE_PHRASE.get(snapshot.persistence.value)
    if persistence:
        lines.append(f"Persistence: the student {persistence}.")
    if snapshot.post_run_pause_count:
        lines.append(
            f"The student paused to watch the result {snapshot.post_run_pause_count} time(s)."
        )

    last_error = next(
        (event.error_message for event in reversed(events) if event.error_message), None
    )
    if last_error:
        lines.append(f"Most recent error the robot reported: {last_error}")

    return "\n".join(lines)
