"""Identity-switch detection + canon_id (vendored from lm-dashboard)."""
from src.triggers.switches import detect_switches
from src.db import canon_id


def test_casing_switch_detected():
    assert detect_switches("cobra3", None, "Cobra3", None) == [("casing", "cobra3", "Cobra3")]


def test_class_switch_detected():
    assert detect_switches("stu", "AAA", "stu", "BBB") == [("class", "AAA", "BBB")]


def test_both_switches_in_one_event():
    out = detect_switches("cobra3", "AAA", "Cobra3", "BBB")
    assert out == [("casing", "cobra3", "Cobra3"), ("class", "AAA", "BBB")]


def test_no_switch_when_unchanged():
    assert detect_switches("stu", "AAA", "stu", "AAA") == []


def test_no_switch_on_first_event():
    assert detect_switches(None, None, "stu", "AAA") == []


def test_no_casing_switch_when_truly_different_handles():
    assert detect_switches("stu1", None, "stu2", None) == []


def test_canon_id_folds_case_and_whitespace():
    assert canon_id("  Cobra3  ") == "cobra3"
    assert canon_id("Cobra3") == "cobra3"
    assert canon_id(None) == ""
    assert canon_id("") == ""
