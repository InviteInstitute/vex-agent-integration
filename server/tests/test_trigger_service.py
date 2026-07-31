"""Tests for the EventRecord -> trigger-engine adapter (issue #4).

Run from server/:  PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_trigger_service.py
"""
from datetime import datetime, timezone

from src.current_state_metrics import EventRecord
from src.trigger_service import compute_run_distances

XMLNS = 'xmlns="https://developers.google.com/blockly/xml"'
WS_A = f'<xml {XMLNS}><block type="pg_events_when_started" id="s"></block></xml>'
WS_B = (f'<xml {XMLNS}><block type="pg_events_when_started" id="s">'
        f'<next><block type="pg_drivetrain_drive_for" id="d"></block></next></block></xml>')


def _run(ws, i, playground="GO-Mars"):
    return EventRecord(
        id=i, session_id="s", student_id="stu",
        event_ts=datetime(2026, 7, 14, 12, 0, i, tzinfo=timezone.utc),
        event_type="runProject", playground=playground,
        project_json={"workspace": ws, "playground": playground},
        block_event_data_json=None, playground_data_json=None, error_message=None,
    )


def _noise(i):
    return EventRecord(
        id=i, session_id="s", student_id="stu",
        event_ts=datetime(2026, 7, 14, 12, 0, i, tzinfo=timezone.utc),
        event_type="blockChanged", playground="GO-Mars",
        project_json={"workspace": WS_A}, block_event_data_json=None,
        playground_data_json=None, error_message=None,
    )


def test_first_run_distance_is_none():
    runs = compute_run_distances([_run(WS_A, 0)])
    assert len(runs) == 1 and runs[0]["edit_distance"] is None


def test_identical_rerun_is_zero_changed_is_positive():
    events = [_run(WS_A, 0), _noise(1), _run(WS_A, 2), _run(WS_B, 3)]
    runs = compute_run_distances(events)
    # only the 3 runProject events count; blockChanged is ignored
    assert [r["index"] for r in runs] == [0, 1, 2]
    assert runs[0]["edit_distance"] is None
    assert runs[1]["edit_distance"] == 0     # identical rerun
    assert runs[2]["edit_distance"] > 0      # added a block


def test_playground_switch_resets_distance_to_none():
    events = [_run(WS_A, 0, "GO-Mars"), _run(WS_B, 1, "CoralReefRescue")]
    runs = compute_run_distances(events)
    assert runs[1]["edit_distance"] is None  # first run of a new playground stretch


def test_run_cache_skips_recompute_on_signature_match(monkeypatch):
    # the cached path must return the same sequence without re-running APTED
    from src import trigger_service as ts

    events = [_run(WS_A, 0), _run(WS_B, 1)]
    calls = {"compute": 0}
    real = ts.compute_run_distances

    def counting(events):
        calls["compute"] += 1
        return real(events)

    monkeypatch.setattr(ts, "compute_run_distances", counting)
    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: events)
    ts.clear_run_cache()

    first = ts.compute_run_distances_for_session("stu", "sess")
    second = ts.compute_run_distances_for_session("stu", "sess")
    assert first == second
    assert calls["compute"] == 1  # APTED ran once; the second call hit the cache


def test_run_cache_invalidates_when_events_grow(monkeypatch):
    from src import trigger_service as ts

    ev1 = [_run(WS_A, 0)]
    ev2 = [_run(WS_A, 0), _run(WS_B, 1)]
    state = {"events": ev1}
    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: state["events"])
    ts.clear_run_cache()

    first = ts.compute_run_distances_for_session("stu", "sess")
    state["events"] = ev2  # a new run landed
    second = ts.compute_run_distances_for_session("stu", "sess")
    assert len(first) == 1 and len(second) == 2  # cache invalidated, recomputed
