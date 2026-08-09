from vex_agent.domain.feedback_policy import FeedbackClass, determine_feedback_class
from vex_agent.domain.metrics import (
    ActionLevel,
    CognitionCategory,
    CurrentStateSnapshot,
    Direction,
    PersistenceCategory,
)


def make_snapshot(
    *,
    cognition=CognitionCategory.UNCLASSIFIED,
    persistence=PersistenceCategory.IN_PROGRESS,
):
    return CurrentStateSnapshot(
        session_id="test-session",
        student_id="test-student",
        playground="GO-Mars",
        time_on_task_s=0.0,
        action_level=ActionLevel.LOW,
        progress_pct=0.0,
        direction=Direction.STATIC,
        cognition=cognition,
        persistence=persistence,
        computed_from_event_id_min=None,
        computed_from_event_id_max=None,
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_returns_empty_set_when_no_flags():
    result = determine_feedback_class(make_snapshot())
    assert result == set()


def test_long_term_stalled_progress():
    result = determine_feedback_class(
        make_snapshot(cognition=CognitionCategory.LONG_TERM_STALLED_PROGRESS)
    )
    assert result == {FeedbackClass.ERROR_FLAGGING}


def test_development_increases_progress():
    result = determine_feedback_class(
        make_snapshot(cognition=CognitionCategory.DEVELOPMENT_INCREASES_PROGRESS)
    )
    assert result == {FeedbackClass.ELABORATE}


def test_development_static_progress():
    result = determine_feedback_class(
        make_snapshot(cognition=CognitionCategory.DEVELOPMENT_STATIC_PROGRESS)
    )
    assert result == {FeedbackClass.REASSURE}


def test_development_decreases_progress():
    result = determine_feedback_class(
        make_snapshot(cognition=CognitionCategory.DEVELOPMENT_DECREASES_PROGRESS)
    )
    assert result == {FeedbackClass.INFORM}


def test_trial_and_error_baseline():
    result = determine_feedback_class(make_snapshot(cognition=CognitionCategory.TRIAL_AND_ERROR))
    assert result == {FeedbackClass.PARTIAL_CORRECTNESS}


def test_trial_and_error_with_expected_completion():
    result = determine_feedback_class(
        make_snapshot(
            cognition=CognitionCategory.TRIAL_AND_ERROR,
            persistence=PersistenceCategory.EXPECTED_COMPLETION,
        )
    )
    assert result == {FeedbackClass.PARTIAL_CORRECTNESS, FeedbackClass.EVIDENCE_BASED_PRAISE}


def test_trial_and_error_with_high_persister():
    result = determine_feedback_class(
        make_snapshot(
            cognition=CognitionCategory.TRIAL_AND_ERROR,
            persistence=PersistenceCategory.HIGH_PERSISTER,
        )
    )
    assert result == {FeedbackClass.PARTIAL_CORRECTNESS, FeedbackClass.REASSURE}


def test_trial_and_error_with_early_quitter():
    result = determine_feedback_class(
        make_snapshot(
            cognition=CognitionCategory.TRIAL_AND_ERROR,
            persistence=PersistenceCategory.EARLY_QUITTER,
        )
    )
    assert result == {FeedbackClass.PARTIAL_CORRECTNESS, FeedbackClass.HOW_TO}


def test_code_abandonment_with_expected_completion():
    result = determine_feedback_class(
        make_snapshot(
            cognition=CognitionCategory.CODE_ABANDONMENT,
            persistence=PersistenceCategory.EXPECTED_COMPLETION,
        )
    )
    assert result == {FeedbackClass.DIAGNOSE}


def test_code_abandonment_with_early_quitter():
    result = determine_feedback_class(
        make_snapshot(
            cognition=CognitionCategory.CODE_ABANDONMENT,
            persistence=PersistenceCategory.EARLY_QUITTER,
        )
    )
    assert result == {FeedbackClass.DIAGNOSE}


def test_code_abandonment_with_high_persister():
    result = determine_feedback_class(
        make_snapshot(
            cognition=CognitionCategory.CODE_ABANDONMENT,
            persistence=PersistenceCategory.HIGH_PERSISTER,
        )
    )
    assert result == {FeedbackClass.REASSURE, FeedbackClass.ELABORATE}


def test_step_by_step_elimination():
    result = determine_feedback_class(
        make_snapshot(cognition=CognitionCategory.STEP_BY_STEP_ELIMINATION)
    )
    assert result == {FeedbackClass.NUDGE}


def test_snap_n_test():
    result = determine_feedback_class(make_snapshot(cognition=CognitionCategory.SNAP_N_TEST))
    assert result == {FeedbackClass.INFORM}


def test_combined_inputs_are_union_without_duplicates():
    result = determine_feedback_class(
        make_snapshot(
            cognition=CognitionCategory.TRIAL_AND_ERROR,
            persistence=PersistenceCategory.EXPECTED_COMPLETION,
        )
    )
    assert result == {
        FeedbackClass.PARTIAL_CORRECTNESS,
        FeedbackClass.EVIDENCE_BASED_PRAISE,
    }
