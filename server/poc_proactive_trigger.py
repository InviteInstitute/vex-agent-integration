"""
SPIKE / walking skeleton: does a wheel_spin trigger produce a good proactive
intervention? Riskiest-path-first, no daemon / no SSE / no migration.

Run from the server/ dir with env loaded:
    set -a; . ../.env; set +a
    PYTHONPATH=. ../.venv/bin/python poc_proactive_trigger.py

What's KEEPER vs THROWAWAY (name it up front so the spike doesn't rot into prod):
  - detect_run_triggers()  -> KEEPER. Pure, vendored verbatim from lm-dashboard.
  - the faked edit_distance sequence -> THROWAWAY. Real v1 computes this with the
    APTED port over each run's workspace XML. wheel_spin only needs 0-vs-nonzero,
    so a hand-written sequence is enough to prove the chain here.
  - the trigger -> feedback-class mapping -> the actual pedagogy. TODO(human) below.
"""
from src.feedback_policy import FeedbackClass
from src.context_builder import build_feedback_prompt_from_classes
from src.llm_service import execute_prompt, enforce_student_response_length
from src.settings import get_navigator_model
from src.task_catalog import resolve_task_description
from src.block_catalog import resolve_available_blocks

# --- vendored thresholds (lm-dashboard/app/constants.py) ---
WHEEL_SPIN_ZERO_RUNS = 6
RESILIENCE_ZERO_RUNS = 4
EXPLORER_EDIT_DISTANCE = 13
ITERATIVE_EDIT_MIN = 1
ITERATIVE_DEFAULT_THRESHOLD = 6
LABELS = {
    "wheel_spin": "Wheel-spinning", "resilience": "Resilience", "inactive": "Inactive",
    "explorer": "Explorer", "iterative": "Step-by-Step",
}


# --- KEEPER: the pure detector, vendored from lm-dashboard/app/pipeline/triggers.py ---
def detect_run_triggers(edit_distances, iterative_threshold=ITERATIVE_DEFAULT_THRESHOLD):
    """One pure pass over a per-run edit_distance sequence (first element None).
    Emits (trigger_type, run_index, detail) for each momentary fire."""
    out = []
    zero_streak = 0
    wheel_armed = True
    iter_count = 0
    iter_armed = True
    for i, ed in enumerate(edit_distances):
        if ed is None:
            continue
        if ed > 0 and zero_streak >= RESILIENCE_ZERO_RUNS:
            out.append(("resilience", i, {"label": LABELS["resilience"],
                                          "value": f"recovered after {zero_streak} reruns"}))
        if ed == 0:
            zero_streak += 1
            if zero_streak >= WHEEL_SPIN_ZERO_RUNS and wheel_armed:
                out.append(("wheel_spin", i, {"label": LABELS["wheel_spin"],
                                              "value": f"{zero_streak} identical reruns"}))
                wheel_armed = False
        else:
            zero_streak = 0
            wheel_armed = True
        if ed >= EXPLORER_EDIT_DISTANCE:
            out.append(("explorer", i, {"label": LABELS["explorer"], "value": f"changed {ed}"}))
        if ed > ITERATIVE_EDIT_MIN:
            iter_count += 1
            if iter_count >= iterative_threshold and iter_armed:
                out.append(("iterative", i, {"label": LABELS["iterative"],
                                             "value": f"{iter_count} steady edits"}))
                iter_armed = False
        if ed == 0:
            iter_count = 0
            iter_armed = True
    return out


# Seed for the real spec's TRIGGER_TO_FEEDBACK_CLASS table. Only wheel_spin is
# acted on in v1; the rest are seeds for when the other triggers graduate.
#   wheel_spin : stuck re-running identical code -> take the edge off (REASSURE),
#                then get them testing/noticing the code isn't changing (DIAGNOSE).
#   resilience : just broke a stuck streak with a real edit -> validate the recovery.
#   iterative  : steady productive edits -> validate progress, don't interrupt hard.
#   explorer   : one big change -> encourage them to test what it did.
#   inactive   : idle -> gentle, low-pressure re-engagement.
TRIGGER_TO_FEEDBACK_CLASS = {
    "wheel_spin": {FeedbackClass.REASSURE, FeedbackClass.DIAGNOSE},
    "resilience": {FeedbackClass.EVIDENCE_BASED_PRAISE},
    "iterative": {FeedbackClass.EVIDENCE_BASED_PRAISE},
    "explorer": {FeedbackClass.DIAGNOSE},
    "inactive": {FeedbackClass.REASSURE, FeedbackClass.QUESTION},
}


def feedback_classes_for_trigger(trigger_type: str) -> set[FeedbackClass]:
    """Map a fired trigger to the pedagogical feedback class(es) the agent should
    use when it reaches out unprompted."""
    return TRIGGER_TO_FEEDBACK_CLASS.get(trigger_type, set())


def build_proactive_prompt(trigger, playground: str) -> str:
    """Reuse the EXISTING feedback pipeline. Improvement #2 from review: do NOT fake
    a student message -- the trigger is telemetry, so it rides in the robot-behavior
    slot, and student_message stays empty."""
    classes = feedback_classes_for_trigger(trigger[0])
    telemetry = (f"Proactive trigger fired: {trigger[2]['label']} "
                 f"({trigger[2]['value']}). The student has not sent a message.")
    return build_feedback_prompt_from_classes(
        task=resolve_task_description(playground),
        student_message="",                       # no student turn -- this is a push
        available_blocks=resolve_available_blocks(playground),
        robot_behavior_summary=telemetry,         # trigger fact as telemetry, not a fake question
        recent_messages=[],
        feedback_classes=classes,
    )


def main():
    playground = "GO-Mars"
    # THROWAWAY: a student who re-ran identical code 6 times, then a real edit.
    edit_distances = [None, 0, 0, 0, 0, 0, 0, 5]

    fired = detect_run_triggers(edit_distances)
    print("=== detector output (KEEPER logic) ===")
    for t in fired:
        print(f"  {t[0]:12s} run#{t[1]}  {t[2]['value']}")

    wheel = next((t for t in fired if t[0] == "wheel_spin"), None)
    assert wheel is not None and wheel[1] == 6, "wheel_spin must fire at the 6th zero run"

    print("\n=== proactive intervention (real Ollama call) ===")
    prompt = build_proactive_prompt(wheel, playground)
    reply = enforce_student_response_length(execute_prompt(model=get_navigator_model(), prompt=prompt))
    print(f"  wheel_spin -> {sorted(c.value for c in feedback_classes_for_trigger('wheel_spin'))}")
    print(f"  agent says: {reply!r}")


if __name__ == "__main__":
    main()
