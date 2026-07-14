"""Pure tests for proactive generation mapping + anti-leak (issue #6). The full
LLM generation is verified separately against Ollama (needs a model + DB)."""
from src.trigger_service import (
    feedback_classes_for_trigger, generate_proactive_response,
    _NEUTRAL_FACT, ACTED_TRIGGERS,
)
from src.feedback_policy import FeedbackClass


def test_wheel_spin_maps_to_reassure_diagnose():
    assert feedback_classes_for_trigger("wheel_spin") == {
        FeedbackClass.REASSURE, FeedbackClass.DIAGNOSE,
    }


def test_unknown_trigger_returns_none_without_side_effects():
    # an unrecognized trigger type is never acted on -> returns None before any DB/LLM call
    assert "totally_unknown" not in ACTED_TRIGGERS
    assert generate_proactive_response("stu", "sess", "totally_unknown") is None


def test_neutral_facts_never_leak_internal_labels():
    banned = ("wheel", "spin", "trigger", "resilience", "explorer", "iterative", "inactive")
    for fact in _NEUTRAL_FACT.values():
        low = fact.lower()
        assert not any(word in low for word in banned), fact
