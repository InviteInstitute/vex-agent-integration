"""build_situation_model: deterministic grounding rendering -- measured facts only,
no LLM call, no raw-log dump. Snapshot is faked so this tests the rendering/phrasing."""

from types import SimpleNamespace

from vex_agent.domain import context_builder as cb


def _snapshot(**over):
    base = dict(
        progress_pct=45.0,
        direction=SimpleNamespace(value="INCREASING"),
        cognition=SimpleNamespace(value="TRIAL_AND_ERROR"),
        persistence=SimpleNamespace(value="HIGH_PERSISTER"),
        time_on_task_s=360.0,
        post_run_pause_count=2,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_empty_events_returns_none():
    assert cb.build_situation_model([]) == "None"
    assert cb.build_situation_model(None) == "None"


def test_non_go_mars_playground_degrades_to_none(monkeypatch):
    def boom(events):
        raise ValueError("progress metric only configured for GO-Mars")

    monkeypatch.setattr(cb, "analyze_current_state", boom)
    assert cb.build_situation_model([object()]) == "None"


def test_renders_measured_facts_not_raw_logs(monkeypatch):
    monkeypatch.setattr(cb, "analyze_current_state", lambda events: _snapshot())
    events = [
        SimpleNamespace(event_type="runProject", error_message=None, playground_data_json=None),
        SimpleNamespace(
            event_type="runProject", error_message="Robot hit a wall", playground_data_json=None
        ),
    ]
    out = cb.build_situation_model(events)
    assert "Goal progress: 45% (going up)." in out
    assert "2 run(s)" in out
    assert "6 min" in out
    assert "trying many quick changes" in out  # cognition phrase
    assert "persistently" in out  # persistence phrase
    assert "paused to watch the result 2 time(s)" in out
    assert "Robot hit a wall" in out  # last error, verbatim
    assert "runProject" not in out  # never a raw event dump


def test_milestones_rendered_from_playground_parameters(monkeypatch):
    monkeypatch.setattr(cb, "analyze_current_state", lambda events: _snapshot())
    # A real playgroundData payload: rover rescued + a sample removed from the crater,
    # everything else still to do.
    params = {
        "rover_rescued": True,
        "removed_samples_crater": 1,
        "tilted_solarPanel": False,
        "lifted_rocketShip_upright": False,
        "removed_fuel_cells_craters": 0,
        "samples_moved_lab": 0,
    }
    events = [
        SimpleNamespace(event_type="runProject", error_message=None, playground_data_json=None),
        SimpleNamespace(
            event_type="playgroundData",
            error_message=None,
            playground_data_json={"parameters": params},
        ),
    ]
    out = cb.build_situation_model(events)
    assert "Milestones done:" in out
    assert "rescue the rover" in out
    assert "move a sample out of the crater" in out
    assert "Still to do:" in out
    assert "tilt the solar panel" in out
    # a done milestone must not also appear in the to-do list
    todo_line = next(line for line in out.splitlines() if line.startswith("Still to do:"))
    assert "rescue the rover" not in todo_line


def test_unclassified_signals_are_omitted(monkeypatch):
    snap = _snapshot(
        cognition=SimpleNamespace(value="UNCLASSIFIED"),
        persistence=SimpleNamespace(value="IN_PROGRESS"),
        post_run_pause_count=0,
    )
    monkeypatch.setattr(cb, "analyze_current_state", lambda events: snap)
    out = cb.build_situation_model(
        [SimpleNamespace(event_type="runProject", error_message=None, playground_data_json=None)]
    )
    assert "Work pattern" not in out
    assert "Persistence" not in out
    assert "paused" not in out
    assert "Goal progress:" in out  # the always-present line survives
