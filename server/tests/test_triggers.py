"""Acceptance tests for the vendored trigger engine (issue #2).

Run from server/:  PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_triggers.py
"""
from src.triggers.detectors import detect_run_triggers, detect_run_triggers_by_playground
from src.triggers.distance import cached_edit_distance, compute_edit_distance
from src.triggers.ast_builder import xml_to_block_ast, extract_workspace_xml

XMLNS = 'xmlns="https://developers.google.com/blockly/xml"'
WS_ONE = f'<xml {XMLNS}><block type="pg_events_when_started" id="s"></block></xml>'
WS_TWO = (f'<xml {XMLNS}><block type="pg_events_when_started" id="s">'
          f'<next><block type="pg_drivetrain_drive_for" id="d"></block></next></block></xml>')


def _fire_types(seq):
    return [t[0] for t in detect_run_triggers(seq)]


def test_wheel_spin_fires_at_sixth_zero():
    fired = detect_run_triggers([None, 0, 0, 0, 0, 0, 0])
    wheel = [t for t in fired if t[0] == "wheel_spin"]
    assert len(wheel) == 1
    assert wheel[0][1] == 6  # run index of the 6th zero


def test_wheel_spin_silent_before_threshold():
    assert "wheel_spin" not in _fire_types([None, 0, 0, 0, 0, 0])  # only 5 zeros


def test_resilience_fires_after_recovery():
    fired = detect_run_triggers([None, 0, 0, 0, 0, 5])
    assert any(t[0] == "resilience" and t[1] == 5 for t in fired)


def test_wheel_spin_rearms_after_edit():
    # 6 zeros (fire), an edit (re-arm), then 6 more zeros (fire again)
    seq = [None] + [0] * 6 + [3] + [0] * 6
    wheel = [t for t in detect_run_triggers(seq) if t[0] == "wheel_spin"]
    assert len(wheel) == 2


def test_explorer_fires_on_big_change():
    assert "explorer" in _fire_types([None, 13])


def test_identical_xml_distance_zero():
    ast = xml_to_block_ast(WS_ONE)
    assert cached_edit_distance(WS_ONE, WS_ONE, ast, ast) == 0


def test_added_block_distance_positive():
    a1, a2 = xml_to_block_ast(WS_ONE), xml_to_block_ast(WS_TWO)
    assert compute_edit_distance(a1, a2) > 0


def test_extract_workspace_xml_from_project_json_string():
    # matches the agent's event shape: project is a JSON string carrying workspace
    content = {"project": '{"mode":"Blocks","workspace":"<xml></xml>"}'}
    assert extract_workspace_xml(content) == "<xml></xml>"


def test_by_playground_resets_counters_on_switch():
    # 3 zeros on pg A, then pg B: the streak must not carry across the switch
    runs = ([{"index": i, "edit_distance": 0, "ts": None, "playground": "A"} for i in range(3)]
            + [{"index": i + 3, "edit_distance": 0, "ts": None, "playground": "B"} for i in range(3)])
    assert "wheel_spin" not in [t[0] for t in detect_run_triggers_by_playground(runs)]


def test_iterative_counts_distance_one():
    # A single-block edit (edit_distance == 1) counts toward Step-by-Step
    # (ITERATIVE_EDIT_MIN = 0, synced with lm-dashboard), so six of them reach
    # the default threshold. Regression guard: the vendored copy was stale at 1.
    seq = [None, 1, 1, 1, 1, 1, 1, 1]
    fired = detect_run_triggers(seq)
    assert any(t == "iterative" and i == 6 for t, i, _ in fired)


def test_iterative_fires_at_threshold_then_cooldown_until_zero():
    # six runs of edit_distance > 0 -> fires at the 6th; then needs a 0 to re-arm
    seq = [None, 2, 2, 2, 2, 2, 2, 2, 0, 3, 3, 3, 3, 3, 3]
    fired = [i for t, i, _ in detect_run_triggers(seq) if t == "iterative"]
    assert fired == [6, 14]


def test_wheel_spin_and_resilience_both_fire_on_long_then_edit():
    seq = [None, 0, 0, 0, 0, 0, 0, 0, 1]  # 7 zeros then an edit
    fired = [(t, i) for t, i, _ in detect_run_triggers(seq)]
    assert ("wheel_spin", 6) in fired and ("resilience", 8) in fired


def test_by_playground_uses_per_playground_iterative_threshold():
    # RoverRescue needs only 3 steady edits (vs the default 6); CastleCrasherPlus 6.
    base = {"index": 0, "edit_distance": 1, "ts": None}
    rover = [{**base, "index": i, "playground": "RoverRescue"} for i in range(3)]
    assert any(t == "iterative" for t, _, _ in detect_run_triggers_by_playground(rover))
    castle = [{**base, "index": i, "playground": "CastleCrasherPlus"} for i in range(3)]
    assert not any(t == "iterative" for t, _, _ in detect_run_triggers_by_playground(castle))
