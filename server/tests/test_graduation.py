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


def test_is_inactive_threshold():
    now = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
    assert is_inactive(None, now) is False
    assert is_inactive(now - timedelta(seconds=INACTIVE_TRIGGER_SECONDS - 10), now) is False
    assert is_inactive(now - timedelta(seconds=INACTIVE_TRIGGER_SECONDS + 10), now) is True
