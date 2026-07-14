"""Trigger-graduation tests (#13 resilience+inactive, #14 explorer+iterative)."""
from datetime import datetime, timedelta, timezone

from src.trigger_service import ACTED_TRIGGERS, feedback_classes_for_trigger, is_inactive
from src.feedback_policy import FeedbackClass
from src.triggers.constants import INACTIVE_TRIGGER_SECONDS


def test_resilience_and_inactive_are_acted():
    assert {"resilience", "inactive"} <= ACTED_TRIGGERS
    assert feedback_classes_for_trigger("resilience") == {FeedbackClass.EVIDENCE_BASED_PRAISE}
    assert feedback_classes_for_trigger("inactive") == {
        FeedbackClass.REASSURE, FeedbackClass.QUESTION,
    }


def test_explorer_and_iterative_are_acted():
    assert {"explorer", "iterative"} <= ACTED_TRIGGERS
    assert feedback_classes_for_trigger("explorer") == {FeedbackClass.DIAGNOSE}
    assert feedback_classes_for_trigger("iterative") == {FeedbackClass.EVIDENCE_BASED_PRAISE}


def test_all_five_triggers_are_acted():
    assert ACTED_TRIGGERS == {"wheel_spin", "resilience", "inactive", "explorer", "iterative"}


def test_is_inactive_threshold():
    now = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
    assert is_inactive(None, now) is False
    assert is_inactive(now - timedelta(seconds=INACTIVE_TRIGGER_SECONDS - 10), now) is False
    assert is_inactive(now - timedelta(seconds=INACTIVE_TRIGGER_SECONDS + 10), now) is True
