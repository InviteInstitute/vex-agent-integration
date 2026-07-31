"""Pure tests for proactive generation mapping + anti-leak (issue #6). The full
LLM generation is verified separately against Ollama (needs a model + DB)."""
from vex_agent.services.proactive import (
    feedback_classes_for_trigger, generate_proactive_response,
    _NEUTRAL_FACT, ACTED_TRIGGERS, disabled_trigger_types,
)
from vex_agent.domain.feedback_policy import FeedbackClass


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


def test_disabled_trigger_returns_none_without_side_effects(monkeypatch):
    # a trigger that IS in ACTED_TRIGGERS but disabled via env -> None before any DB/LLM call
    assert "wheel_spin" in ACTED_TRIGGERS
    monkeypatch.setenv("TRIGGER_DISABLED", "wheel_spin")
    assert "wheel_spin" in disabled_trigger_types()
    assert generate_proactive_response("stu", "sess", "wheel_spin") is None


def test_disabled_trigger_types_parses_comma_separated(monkeypatch):
    monkeypatch.setenv("TRIGGER_DISABLED", " inactive , explorer , ")
    assert disabled_trigger_types() == {"inactive", "explorer"}


def test_disabled_trigger_types_empty_by_default(monkeypatch):
    monkeypatch.delenv("TRIGGER_DISABLED", raising=False)
    assert disabled_trigger_types() == set()
