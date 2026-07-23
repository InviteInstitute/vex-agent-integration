"""
Feedback Policy
"""

from enum import Enum

try:
    from src.current_state_metrics import CurrentStateSnapshot
except ModuleNotFoundError:
    from server.src.current_state_metrics import CurrentStateSnapshot

class FeedbackClass(Enum):
    # Acknowledge / Notify
    POSITIVE_FEEDBACK = "Positive Feedback"
    PARTIAL_CORRECTNESS = "Partial Correctness"
    CORRECTIVE_GUIDANCE = "Corrective Guidance"

    # Motivate
    EVIDENCE_BASED_PRAISE = "Evidence-based Praise"
    REASSURE = "Reassure"
    NEUTRAL = "Neutral"

    # Evaluate / Stimulate
    ERROR_FLAGGING = "Error Flagging"
    HOW_TO = "How To"
    INFORM = "Inform"
    NUDGE = "Nudge"
    DIAGNOSE = "Diagnose"
    QUESTION = "Question"
    ELABORATE = "Elaborate"
    REPEAT = "Repeat"
    NEXT_STEP = "Next Step"

def determine_feedback_class(snapshot: CurrentStateSnapshot) -> set[FeedbackClass]:
    feedback_classes = set()
    cognition = snapshot.cognition.value
    persistence = snapshot.persistence.value

    # Long-term stalled progress -> Help out -> c.i
    if cognition == "LONG_TERM_STALLED_PROGRESS":
        feedback_classes.add(FeedbackClass.ERROR_FLAGGING)

    # Development increases progress -> Reflection/Rehearsal -> c.viii
    if cognition == "DEVELOPMENT_INCREASES_PROGRESS":
        feedback_classes.add(FeedbackClass.ELABORATE)

    # Development for static progress -> Motivate to keep persisting -> b.ii
    if cognition == "DEVELOPMENT_STATIC_PROGRESS":
        feedback_classes.add(FeedbackClass.REASSURE)

    # Development decreases progress -> Corrective explanation -> c.iii
    if cognition == "DEVELOPMENT_DECREASES_PROGRESS":
        feedback_classes.add(FeedbackClass.INFORM)

    # Trial & Error -> a.ii
    if cognition == "TRIAL_AND_ERROR":
        feedback_classes.add(FeedbackClass.PARTIAL_CORRECTNESS)
        
        # -> b.i
        if persistence == "EXPECTED_COMPLETION":
            feedback_classes.add(FeedbackClass.EVIDENCE_BASED_PRAISE)

        # -> b.ii
        if persistence == "HIGH_PERSISTER":
            feedback_classes.add(FeedbackClass.REASSURE)

        # -> c.ii
        if persistence == "EARLY_QUITTER":
            feedback_classes.add(FeedbackClass.HOW_TO)

    # Code abandonment
    if cognition == "CODE_ABANDONMENT":

        # -> c.v
        if persistence in {"EXPECTED_COMPLETION", "EARLY_QUITTER"}:
            feedback_classes.add(FeedbackClass.DIAGNOSE)

        # -> b.ii, c.vii, c.viii
        if persistence == "HIGH_PERSISTER":
            feedback_classes.update({
                FeedbackClass.REASSURE,
                FeedbackClass.ELABORATE,
            })

    # Step-by-step elimination -> c.iv
    if cognition == "STEP_BY_STEP_ELIMINATION":
        feedback_classes.add(FeedbackClass.NUDGE)

    # Snap'n test -> c.ii
    if cognition == "SNAP_N_TEST":
        feedback_classes.add(FeedbackClass.INFORM)

    return feedback_classes
