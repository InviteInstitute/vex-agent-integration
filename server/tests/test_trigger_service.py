"""Tests for the EventRecord -> trigger-engine adapter (issue #4).

Run from server/:  PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_trigger_service.py
"""

from datetime import UTC, datetime

from vex_agent.domain.metrics import EventRecord
from vex_agent.services.proactive import compute_run_distances

XMLNS = 'xmlns="https://developers.google.com/blockly/xml"'
WS_A = f'<xml {XMLNS}><block type="pg_events_when_started" id="s"></block></xml>'
WS_B = (
    f'<xml {XMLNS}><block type="pg_events_when_started" id="s">'
    f'<next><block type="pg_drivetrain_drive_for" id="d"></block></next></block></xml>'
)


def _run(ws, i, playground="GO-Mars"):
    return EventRecord(
        id=i,
        session_id="s",
        student_id="stu",
        event_ts=datetime(2026, 7, 14, 12, 0, i, tzinfo=UTC),
        event_type="runProject",
        playground=playground,
        project_json={"workspace": ws, "playground": playground},
        block_event_data_json=None,
        playground_data_json=None,
        error_message=None,
    )


def _noise(i):
    return EventRecord(
        id=i,
        session_id="s",
        student_id="stu",
        event_ts=datetime(2026, 7, 14, 12, 0, i, tzinfo=UTC),
        event_type="blockChanged",
        playground="GO-Mars",
        project_json={"workspace": WS_A},
        block_event_data_json=None,
        playground_data_json=None,
        error_message=None,
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
    assert runs[1]["edit_distance"] == 0  # identical rerun
    assert runs[2]["edit_distance"] > 0  # added a block


def test_playground_switch_resets_distance_to_none():
    events = [_run(WS_A, 0, "GO-Mars"), _run(WS_B, 1, "CoralReefRescue")]
    runs = compute_run_distances(events)
    assert runs[1]["edit_distance"] is None  # first run of a new playground stretch


def _count_fed(monkeypatch, ts):
    fed = []
    real = ts._event_record_to_engine_dict

    def counting(event):
        fed.append(event.id)
        return real(event)

    monkeypatch.setattr(ts, "_event_record_to_engine_dict", counting)
    return fed


def test_run_stream_feeds_nothing_on_an_unchanged_tick(monkeypatch):
    from vex_agent.services import proactive as ts

    events = [_run(WS_A, 0), _run(WS_B, 1)]
    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: events)
    fed = _count_fed(monkeypatch, ts)
    ts.clear_run_cache()

    expected = compute_run_distances(events)
    fed.clear()
    first = ts.compute_run_distances_for_session("stu", "sess")
    second = ts.compute_run_distances_for_session("stu", "sess")
    assert fed == [0, 1]  # the second tick fed nothing
    assert first == second == expected


def test_run_stream_feeds_only_new_events(monkeypatch):
    from vex_agent.services import proactive as ts

    state = {"events": [_run(WS_A, 0), _noise(1)]}
    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: state["events"])
    fed = _count_fed(monkeypatch, ts)
    ts.clear_run_cache()

    first = ts.compute_run_distances_for_session("stu", "sess")
    state["events"] = state["events"] + [_run(WS_B, 2), _noise(3)]
    second = ts.compute_run_distances_for_session("stu", "sess")
    assert fed == [0, 1, 2, 3]  # each event fed once
    assert len(first) == 1 and len(second) == 2
    assert second == compute_run_distances(state["events"])


def test_run_stream_rebuilds_when_an_earlier_event_lands_late(monkeypatch):
    from vex_agent.services import proactive as ts

    state = {"events": [_run(WS_A, 0), _run(WS_A, 2)]}
    monkeypatch.setattr(ts, "fetch_events_from_db", lambda **k: state["events"])
    ts.clear_run_cache()

    ts.compute_run_distances_for_session("stu", "sess")
    # a run with an earlier event_ts arrives late and sorts into the middle
    state["events"] = [_run(WS_A, 0), _run(WS_B, 1), _run(WS_A, 2)]
    runs = ts.compute_run_distances_for_session("stu", "sess")
    assert runs == compute_run_distances(state["events"])
    assert [r["edit_distance"] for r in runs] == [None, 1, 1]


def test_run_streams_are_bounded(monkeypatch):
    from vex_agent.services import proactive as ts

    monkeypatch.setattr(ts, "_RUN_STREAMS_MAX", 2)
    ts.clear_run_cache()
    for k in range(4):
        ts._compute_run_distances_cached("stu", f"sess{k}", [_run(WS_A, 0)])
    assert list(ts._run_streams) == [("stu", "sess2"), ("stu", "sess3")]
