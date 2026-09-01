from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from statistics import mean
from typing import Any, Iterable


class ActionLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Direction(str, Enum):
    INCREASING = "INCREASING"
    STATIC = "STATIC"
    DECREASING = "DECREASING"


class CognitionCategory(str, Enum):
    LONG_TERM_STALLED_PROGRESS = "LONG_TERM_STALLED_PROGRESS"
    DEVELOPMENT_INCREASES_PROGRESS = "DEVELOPMENT_INCREASES_PROGRESS"
    DEVELOPMENT_STATIC_PROGRESS = "DEVELOPMENT_STATIC_PROGRESS"
    DEVELOPMENT_DECREASES_PROGRESS = "DEVELOPMENT_DECREASES_PROGRESS"
    TRIAL_AND_ERROR = "TRIAL_AND_ERROR"
    CODE_ABANDONMENT = "CODE_ABANDONMENT"
    STEP_BY_STEP_ELIMINATION = "STEP_BY_STEP_ELIMINATION"
    SNAP_N_TEST = "SNAP_N_TEST"
    UNCLASSIFIED = "UNCLASSIFIED"


class PersistenceCategory(str, Enum):
    EXPECTED_COMPLETION = "EXPECTED_COMPLETION"
    HIGH_PERSISTER = "HIGH_PERSISTER"
    EARLY_QUITTER = "EARLY_QUITTER"
    IN_PROGRESS = "IN_PROGRESS"


ALLOWED_PLAYGROUNDS = {
    "GOMARS": "GO-Mars",
}

GO_MARS_INITIAL_GOAL_SCORE = 5.0

GO_MARS_MILESTONE_RULES = {
    "move_sample_out_of_crater": lambda parameters: (
        isinstance(parameters.get("removed_samples_crater"), (int, float))
        and parameters.get("removed_samples_crater", 0) > 0
    ),
    "place_sample_on_lab": lambda parameters: (
        (
            isinstance(parameters.get("samples_moved_lab"), (int, float))
            and parameters.get("samples_moved_lab", 0) > 0
        )
        or (
            isinstance(parameters.get("samples_moved_lab_top"), (int, float))
            and parameters.get("samples_moved_lab_top", 0) > 0
        )
    ),
    "tilt_solar_panel": lambda parameters: parameters.get("tilted_solarPanel") is True,
    "move_hero_bot_out_of_crater": lambda parameters: parameters.get("rover_rescued") is True,
    "lift_rocket_ship_upright": lambda parameters: (
        parameters.get("lifted_rocketShip_upright") is True
    ),
    "remove_fuel_cells_from_cradles": lambda parameters: (
        isinstance(parameters.get("removed_fuel_cells_craters"), (int, float))
        and parameters.get("removed_fuel_cells_craters", 0) > 0
    ),
}

ACTION_LEVEL_THRESHOLDS = {
    ActionLevel.LOW: 1.5,
    ActionLevel.MEDIUM: 3.5,
}

PROGRESS_DELTA_THRESHOLD = 5.0

SWITCH_EVENTS = {"PlaygroundChange", "playgroundOpen", "menuSelect"}


@dataclass(frozen=True)
class EventRecord:
    id: int | None
    session_id: str
    student_id: str
    event_ts: datetime
    event_type: str
    playground: str | None
    project_json: dict[str, Any] | None
    block_event_data_json: dict[str, Any] | None
    playground_data_json: dict[str, Any] | None
    error_message: str | None


@dataclass(frozen=True)
class CurrentStateSnapshot:
    session_id: str
    student_id: str
    playground: str
    time_on_task_s: float
    action_level: ActionLevel
    progress_pct: float
    direction: Direction
    cognition: CognitionCategory
    persistence: PersistenceCategory
    computed_from_event_id_min: int | None
    computed_from_event_id_max: int | None
    created_at: str
    # Episode-segmentation signal (vendored from lm-dashboard's episode_engine). Not
    # persisted (migration 002 has no columns for these) -- computed on the fly so the
    # cognition classifier and the LLM prompt can use it. A POST_RUN_PAUSE is a "ran,
    # then sat watching the result" gap; INACTIVE_PAUSE is a long idle (>= 300s).
    post_run_pause_count: int = 0
    inactive_pause_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action_level"] = self.action_level.value
        payload["direction"] = self.direction.value
        payload["cognition"] = self.cognition.value
        payload["persistence"] = self.persistence.value
        return payload


def parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    raise TypeError(f"Unsupported datetime value: {value!r}")


def normalize_playground(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    normalized = "".join(ch for ch in stripped.upper() if ch.isalnum())
    return ALLOWED_PLAYGROUNDS.get(normalized, stripped)


def canonical_playground_from_payload(
    playground: Any,
    project_json: dict[str, Any] | None,
    playground_data_json: dict[str, Any] | None,
) -> str | None:
    candidates: list[Any] = [playground]
    if isinstance(project_json, dict):
        candidates.append(project_json.get("playground"))
        playground_config = project_json.get("playgroundConfig")
        if isinstance(playground_config, dict):
            candidates.append(playground_config.get("playground_id"))
    if isinstance(playground_data_json, dict):
        candidates.append(playground_data_json.get("playground"))
    for candidate in candidates:
        canonical = normalize_playground(candidate)
        if canonical is not None:
            return canonical
    return None


def has_active_project_run(events: list[EventRecord]) -> bool:
    latest_run_ts: datetime | None = None
    latest_end_ts: datetime | None = None

    for event in events:
        if event.event_type == "runProject":
            latest_run_ts = event.event_ts
        elif event.event_type == "projectEnd":
            latest_end_ts = event.event_ts

    if latest_run_ts is None:
        return False
    if latest_end_ts is None:
        return True
    return latest_run_ts > latest_end_ts


def _events_to_segmenter_input(events: list[EventRecord]) -> list[dict]:
    """Adapt EventRecords to the episode segmenter's {event_type, ts} dict shape."""
    return [
        {
            "event_type": event.event_type,
            "ts": event.event_ts.timestamp() if event.event_ts else None,
        }
        for event in events
    ]


def segment_episodes_for_events(events: list[EventRecord]) -> tuple[list[dict], list[dict]]:
    """Segment an EventRecord list into CODE/RUN/RESET episodes + pauses, via the
    shared learner_models engine. Returns (episodes, pauses). Pure (no DB)."""
    from learner_models import segment_session

    if not events:
        return [], []
    return segment_session(_events_to_segmenter_input(events))


def select_current_playground_segment(events: list[EventRecord]) -> tuple[str, list[EventRecord]]:
    if not events:
        raise ValueError("No allowed playground events were found for this student/session.")

    current_playground = events[-1].playground
    if current_playground is None:
        raise ValueError("Could not determine the current playground.")

    start_index = 0
    for index in range(len(events) - 1, -1, -1):
        if events[index].playground != current_playground:
            start_index = index + 1
            break
        if events[index].event_type in SWITCH_EVENTS:
            start_index = index

    segment = [event for event in events[start_index:] if event.playground == current_playground]
    if not segment:
        raise ValueError("Could not isolate a current playground segment for analysis.")
    return current_playground, segment


def extract_playground_parameters(playground_data_json: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(playground_data_json, dict):
        return {}
    parameters = playground_data_json.get("parameters")
    return parameters if isinstance(parameters, dict) else {}


def compute_go_mars_milestone_progress_pct(parameters: dict[str, Any]) -> float:
    completed_milestones = sum(1 for rule in GO_MARS_MILESTONE_RULES.values() if rule(parameters))
    return round(
        min(completed_milestones, GO_MARS_INITIAL_GOAL_SCORE) / GO_MARS_INITIAL_GOAL_SCORE * 100.0,
        2,
    )


def compute_go_mars_progress_pct(playground_data_json: dict[str, Any] | None) -> float:
    parameters = extract_playground_parameters(playground_data_json)
    if not parameters:
        return 0.0

    total_score = parameters.get("total_score")
    if isinstance(total_score, (int, float)):
        return round(
            min(float(total_score), GO_MARS_INITIAL_GOAL_SCORE)
            / GO_MARS_INITIAL_GOAL_SCORE
            * 100.0,
            2,
        )

    return compute_go_mars_milestone_progress_pct(parameters)


def compute_progress_pct(playground_data_json: dict[str, Any] | None, playground: str) -> float:
    if playground != "GO-Mars":
        raise ValueError(
            f"Playground-data progress is only configured for GO-Mars, got {playground}."
        )
    return compute_go_mars_progress_pct(playground_data_json)


def compute_time_on_task_s(events: list[EventRecord]) -> float:
    if len(events) <= 1:
        return 0.0
    return max((events[-1].event_ts - events[0].event_ts).total_seconds(), 0.0)


def compute_action_level(total_events: int, time_on_task_s: float) -> ActionLevel:
    actions_per_min = total_events / max(time_on_task_s / 60.0, 1.0)
    if actions_per_min < ACTION_LEVEL_THRESHOLDS[ActionLevel.LOW]:
        return ActionLevel.LOW
    if actions_per_min <= ACTION_LEVEL_THRESHOLDS[ActionLevel.MEDIUM]:
        return ActionLevel.MEDIUM
    return ActionLevel.HIGH


def build_progress_series(
    events: list[EventRecord], playground: str
) -> list[tuple[datetime, float]]:
    series: list[tuple[datetime, float]] = []
    for event in events:
        if event.playground_data_json is None:
            continue
        series.append(
            (event.event_ts, compute_progress_pct(event.playground_data_json, playground))
        )
    return series


def compute_direction(
    progress_series: list[tuple[datetime, float]],
    segment_start: datetime,
    segment_end: datetime,
) -> Direction:
    if not progress_series:
        return Direction.STATIC

    midpoint = segment_start + ((segment_end - segment_start) / 2)
    first_half = [progress for ts, progress in progress_series if ts <= midpoint]
    second_half = [progress for ts, progress in progress_series if ts > midpoint]

    if not first_half:
        first_half = [progress_series[0][1]]
    if not second_half:
        second_half = [progress_series[-1][1]]

    delta = mean(second_half) - mean(first_half)
    if delta >= PROGRESS_DELTA_THRESHOLD:
        return Direction.INCREASING
    if delta <= -PROGRESS_DELTA_THRESHOLD:
        return Direction.DECREASING
    return Direction.STATIC


def compress_progress_values(progress_values: Iterable[float]) -> list[float]:
    compressed: list[float] = []
    for value in progress_values:
        if not compressed or value != compressed[-1]:
            compressed.append(value)
    return compressed


def significant_deltas(progress_values: list[float]) -> list[float]:
    deltas: list[float] = []
    for prev, current in zip(progress_values, progress_values[1:]):
        delta = round(current - prev, 2)
        if abs(delta) >= PROGRESS_DELTA_THRESHOLD:
            deltas.append(delta)
    return deltas


def classify_persistence(
    time_on_task_s: float,
    action_level: ActionLevel,
    progress_pct: float,
    direction: Direction,
) -> PersistenceCategory:
    if progress_pct >= 67.0 or (direction == Direction.INCREASING and progress_pct >= 50.0):
        return PersistenceCategory.EXPECTED_COMPLETION
    if time_on_task_s >= 600.0 and action_level == ActionLevel.HIGH and progress_pct < 33.0:
        return PersistenceCategory.HIGH_PERSISTER
    if time_on_task_s <= 120.0 and progress_pct < 10.0 and action_level == ActionLevel.LOW:
        return PersistenceCategory.EARLY_QUITTER
    return PersistenceCategory.IN_PROGRESS


def classify_cognition(
    events: list[EventRecord],
    progress_series: list[tuple[datetime, float]],
    time_on_task_s: float,
    action_level: ActionLevel,
    progress_pct: float,
    direction: Direction,
    *,
    post_run_pause_count: int = 0,
) -> CognitionCategory:
    if time_on_task_s >= 600.0 and progress_pct < 10.0 and action_level != ActionLevel.HIGH:
        return CognitionCategory.LONG_TERM_STALLED_PROGRESS
    if direction == Direction.INCREASING and progress_pct >= 10.0:
        return CognitionCategory.DEVELOPMENT_INCREASES_PROGRESS
    if direction == Direction.STATIC and time_on_task_s >= 300.0:
        return CognitionCategory.DEVELOPMENT_STATIC_PROGRESS
    if direction == Direction.DECREASING and progress_pct >= 10.0:
        return CognitionCategory.DEVELOPMENT_DECREASES_PROGRESS

    progress_values = compress_progress_values([progress for _, progress in progress_series])
    deltas = significant_deltas(progress_values)
    event_counts = Counter(event.event_type for event in events)
    run_count = event_counts["runProject"]
    delete_count = event_counts["blockDeleted"]
    snap_count = 0
    unsnap_count = 0
    last_edit_ts: datetime | None = None
    last_run_ts: datetime | None = None

    for event in events:
        if event.event_type == "runProject":
            last_run_ts = event.event_ts
        if event.event_type in {"blockCreated", "blockChanged", "blockDeleted", "blockMoved"}:
            last_edit_ts = event.event_ts
        if event.event_type != "blockMoved" or not isinstance(event.block_event_data_json, dict):
            continue
        old_info = event.block_event_data_json.get("oldInfo")
        new_info = event.block_event_data_json.get("newInfo")
        if isinstance(new_info, dict) and "parent" in new_info:
            snap_count += 1
        if (
            isinstance(old_info, dict)
            and "parent" in old_info
            and not (isinstance(new_info, dict) and "parent" in new_info)
        ):
            unsnap_count += 1

    progress_range = (max(progress_values) - min(progress_values)) if progress_values else 0.0
    sign_changes = 0
    for previous, current in zip(deltas, deltas[1:]):
        if previous * current < 0:
            sign_changes += 1

    if action_level == ActionLevel.HIGH and progress_range >= 10.0 and sign_changes >= 1:
        return CognitionCategory.TRIAL_AND_ERROR

    if len(progress_values) >= 3:
        peak_index = max(range(len(progress_values)), key=lambda index: progress_values[index])
        peak_progress = progress_values[peak_index]
        final_progress = progress_values[-1]
        after_peak = progress_values[peak_index:]
        after_peak_deltas = [curr - prev for prev, curr in zip(after_peak, after_peak[1:])]
        if (
            peak_progress - final_progress >= 15.0
            and after_peak_deltas
            and all(delta <= 0 for delta in after_peak_deltas)
            and action_level in {ActionLevel.MEDIUM, ActionLevel.HIGH}
        ):
            return CognitionCategory.CODE_ABANDONMENT

    if deltas:
        total_gain = progress_values[-1] - progress_values[0]
        negative_deltas = [delta for delta in deltas if delta < 0]
        if (
            total_gain >= 10.0
            and len(negative_deltas) <= 1
            and direction == Direction.INCREASING
            and action_level in {ActionLevel.MEDIUM, ActionLevel.HIGH}
        ):
            return CognitionCategory.STEP_BY_STEP_ELIMINATION

    if (
        run_count >= 1
        and snap_count >= 1
        and (delete_count + unsnap_count) >= 1
        and last_run_ts is not None
        and last_edit_ts is not None
        and (last_run_ts - last_edit_ts) <= timedelta(seconds=90)
    ):
        return CognitionCategory.SNAP_N_TEST

    # Episode signal: a POST_RUN_PAUSE is "ran, then sat watching the result" -- the
    # snap-and-test signature even when the 90s edit-to-run window above is missed.
    if (
        run_count >= 1
        and snap_count >= 1
        and post_run_pause_count >= 1
        and action_level in {ActionLevel.MEDIUM, ActionLevel.HIGH}
    ):
        return CognitionCategory.SNAP_N_TEST

    return CognitionCategory.UNCLASSIFIED


def analyze_current_state(events: list[EventRecord]) -> CurrentStateSnapshot:
    playground, segment = select_current_playground_segment(events)
    time_on_task_s = round(compute_time_on_task_s(segment), 2)
    action_level = compute_action_level(len(segment), time_on_task_s)
    progress_series = build_progress_series(segment, playground)
    progress_pct = round(progress_series[-1][1], 2) if progress_series else 0.0
    direction = compute_direction(progress_series, segment[0].event_ts, segment[-1].event_ts)
    # Episode-segmentation pauses over the current segment: a POST_RUN_PAUSE is the
    # "ran, then sat watching the result" signal SNAP_N_TEST looks for; INACTIVE_PAUSE
    # is a long idle that direction/time-on-task should ideally not average across.
    _, segment_pauses = segment_episodes_for_events(segment)
    post_run_pause_count = sum(1 for p in segment_pauses if p["episode_type"] == "POST_RUN_PAUSE")
    inactive_pause_count = sum(1 for p in segment_pauses if p["episode_type"] == "INACTIVE_PAUSE")
    cognition = classify_cognition(
        segment,
        progress_series,
        time_on_task_s,
        action_level,
        progress_pct,
        direction,
        post_run_pause_count=post_run_pause_count,
    )
    persistence = classify_persistence(time_on_task_s, action_level, progress_pct, direction)

    event_ids = [event.id for event in segment if event.id is not None]
    return CurrentStateSnapshot(
        session_id=segment[0].session_id,
        student_id=segment[0].student_id,
        playground=playground,
        time_on_task_s=time_on_task_s,
        action_level=action_level,
        progress_pct=progress_pct,
        direction=direction,
        cognition=cognition,
        persistence=persistence,
        computed_from_event_id_min=min(event_ids) if event_ids else None,
        computed_from_event_id_max=max(event_ids) if event_ids else None,
        created_at=datetime.now(UTC).isoformat(),
        post_run_pause_count=post_run_pause_count,
        inactive_pause_count=inactive_pause_count,
    )


def compute_snapshot_for_student_session(
    student_id: str,
    session_id: str,
    *,
    insert: bool = True,
) -> CurrentStateSnapshot:
    # Lazy import: this CLI/orchestration helper is the one DB-touching function left
    # in an otherwise-pure analytics module. Importing data.db at top level would cycle
    # (data.db imports this module for its domain types).
    from vex_agent.data.db import fetch_events_from_db, upsert_snapshot

    events = fetch_events_from_db(student_id=student_id, session_id=session_id)
    snapshot = analyze_current_state(events)
    if insert:
        upsert_snapshot(snapshot)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute a current-state snapshot for a student/session."
    )
    parser.add_argument("--student-id", required=True, help="Student ID to analyze")
    parser.add_argument("--session-id", required=True, help="Session ID to analyze")
    parser.add_argument(
        "--insert",
        action="store_true",
        help="Upsert the computed snapshot into current_state.state_snapshots",
    )
    args = parser.parse_args()

    snapshot = compute_snapshot_for_student_session(
        student_id=args.student_id,
        session_id=args.session_id,
        insert=args.insert,
    )
    print(json.dumps(snapshot.to_dict(), indent=2))


if __name__ == "__main__":
    main()
