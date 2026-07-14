"""The pure trigger-detection pass over a per-run edit_distance sequence. Vendored
from lm-dashboard/app/pipeline/triggers.py (the momentary edit-distance detectors
only; the DB-coupled sustained `inactive` sweep lives in a later slice).

  wheel_spin : >= WHEEL_SPIN_ZERO_RUNS consecutive zero-edit runs (re-running the
               same code); silent until a real edit re-arms it.
  resilience : a real edit right after >= RESILIENCE_ZERO_RUNS zeros (recovered).
  explorer   : a single run with edit_distance >= EXPLORER_EDIT_DISTANCE.
  iterative  : ITERATIVE_DEFAULT_THRESHOLD runs with edit_distance > 1 (steady edits).
"""
from src.triggers.constants import (
    WHEEL_SPIN_ZERO_RUNS, RESILIENCE_ZERO_RUNS, EXPLORER_EDIT_DISTANCE,
    ITERATIVE_EDIT_MIN, ITERATIVE_DEFAULT_THRESHOLD, ITERATIVE_THRESHOLDS,
    TRIGGER_LABELS as LABELS,
)


def detect_run_triggers(edit_distances, iterative_threshold=ITERATIVE_DEFAULT_THRESHOLD):
    """One pure pass over a per-run edit_distance sequence (first element None).
    Emits (trigger_type, run_index, detail) for each momentary fire. Deterministic,
    so the worker can re-run it and dedupe by run_index without double-firing.

      wheel_spin : a trailing run of edit_distance == 0 reaches WHEEL_SPIN_ZERO_RUNS;
                   silent (cooldown) until a non-zero edit re-arms it.
      resilience : a non-zero edit lands right after >= RESILIENCE_ZERO_RUNS zeros.
      explorer   : a single run with edit_distance >= EXPLORER_EDIT_DISTANCE.
      iterative  : the count of runs with edit_distance > ITERATIVE_EDIT_MIN reaches
                   the threshold; silent until an edit_distance == 0 run resets it.
    """
    out = []
    zero_streak = 0
    wheel_armed = True
    iter_count = 0
    iter_armed = True
    for i, ed in enumerate(edit_distances):
        if ed is None:
            continue
        if ed > 0 and zero_streak >= RESILIENCE_ZERO_RUNS:
            out.append(("resilience", i, {"label": LABELS["resilience"],
                                          "value": f"recovered after {zero_streak} reruns"}))
        if ed == 0:
            zero_streak += 1
            if zero_streak >= WHEEL_SPIN_ZERO_RUNS and wheel_armed:
                out.append(("wheel_spin", i, {"label": LABELS["wheel_spin"],
                                              "value": f"{zero_streak} identical reruns"}))
                wheel_armed = False
        else:
            zero_streak = 0
            wheel_armed = True
        if ed >= EXPLORER_EDIT_DISTANCE:
            out.append(("explorer", i, {"label": LABELS["explorer"], "value": f"changed {ed}"}))
        if ed > ITERATIVE_EDIT_MIN:
            iter_count += 1
            if iter_count >= iterative_threshold and iter_armed:
                out.append(("iterative", i, {"label": LABELS["iterative"],
                                             "value": f"{iter_count} steady edits"}))
                iter_armed = False
        if ed == 0:
            iter_count = 0
            iter_armed = True
    return out


def detect_run_triggers_by_playground(runs):
    """Split `runs` into contiguous same-playground stretches and run
    detect_run_triggers on each, using that playground's Step-by-Step threshold
    (ITERATIVE_THRESHOLDS.get(playground, ITERATIVE_DEFAULT_THRESHOLD)). `runs` is
    the list from compute_run_edit_distances ({index, edit_distance, ts, playground}).
    Returns [(trigger_type, global_run_index, detail)].

    Each stretch is its own detect_run_triggers call, so every counter resets at a
    playground switch. Run indices stay global via the stretch offset."""
    out = []
    i, n = 0, len(runs)
    while i < n:
        pg = runs[i].get("playground")
        j = i
        while j < n and runs[j].get("playground") == pg:
            j += 1
        edit_distances = [r["edit_distance"] for r in runs[i:j]]
        threshold = ITERATIVE_THRESHOLDS.get(pg, ITERATIVE_DEFAULT_THRESHOLD)
        for ttype, local_idx, detail in detect_run_triggers(
            edit_distances, iterative_threshold=threshold
        ):
            out.append((ttype, i + local_idx, detail))
        i = j
    return out
