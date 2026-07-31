"""Trigger thresholds + APTED edit costs, vendored from lm-dashboard/app/constants.py.
Keep these values in sync with the dashboard so the agent's triggers stay comparable
to the researcher board's numbers."""

# --- APTED edit costs (Hyeongjo's colab cost model) ---
# Edge nodes (synthetic connectors) cost 0 to add/remove, so adding one real block
# scores 1, not 2.
BLOCK_DELETE_COST = 1.0
BLOCK_INSERT_COST = 1.0
EDGE_DELETE_COST = 0.0
EDGE_INSERT_COST = 0.0
FIELD_CHANGE_COST = 1.0
TYPE_CHANGE_COST = 1.0
EDGE_CHANGE_COST = 1.0

# --- Trigger thresholds (all defined on each run's integer edit_distance) ---
WHEEL_SPIN_ZERO_RUNS = 6         # >= this many consecutive zero-edit runs -> wheel_spin
RESILIENCE_ZERO_RUNS = 4         # an edit after >= this many zeros -> resilience
INACTIVE_TRIGGER_SECONDS = 240   # idle > this many seconds -> inactive
RE_ALERT_SECONDS = 600           # re-alert a still-idle student after this many seconds
                                  # (ported from lm-dashboard). Without it, inactive fires
                                  # once per session and a persistently-idle student never
                                  # hears from the agent again.
EXPLORER_EDIT_DISTANCE = 13      # a single run with edit_distance >= this -> explorer
ITERATIVE_EDIT_MIN = 0           # runs with edit_distance > this count toward iterative (so any real edit, >= 1, counts)
ITERATIVE_DEFAULT_THRESHOLD = 6  # count of such runs that fires iterative
# Per-playground Step-by-Step thresholds; unlisted playgrounds use the default.
ITERATIVE_THRESHOLDS = {"CastleCrasherPlus": 6, "CoralReefRescue": 5, "RoverRescue": 3}

TRIGGER_LABELS = {
    "wheel_spin": "Wheel-spinning", "resilience": "Resilience", "inactive": "Inactive",
    "explorer": "Explorer", "iterative": "Step-by-Step",
}

# ==========================================================================
# Episode segmentation (vendored from lm-dashboard/app/constants.py)
# Mirrors learner-model-pipeline/src/episodes.py. Hard-boundary episode types
# stop surrounding episodes from merging regardless of the time gap; soft events
# never form an episode of their own and fold into whatever episode surrounds them.
# ==========================================================================
PAUSE_THRESHOLD_S = 300.0             # gap >= this becomes INACTIVE_PAUSE
SHORT_PAUSE_MIN_S = 5.0               # smallest gap that counts as a contextual pause
PAUSE_MAX_S = 86400.0                 # ignore gaps > 24h (likely a session boundary)

# Event types that open an episode, by kind.
CODE_EVENTS = frozenset({"blockMoved", "blockChanged", "blockCreated", "blockDeleted"})
RUN_START_EVENTS = frozenset({"runProject"})
RUN_END_EVENTS = frozenset({"projectEnd"})
RESET_EVENTS = frozenset({"loadProject", "newProject"})

# Episode types that act as merge barriers regardless of the merge gaps.
HARD_BOUNDARY_EPISODE_TYPES = frozenset({"RUN", "CODE", "RESET", "INACTIVE_PAUSE", "POST_RUN_PAUSE"})
# Pause categories tagged as "hard" boundaries downstream.
HARD_PAUSE_TYPES = frozenset({"INACTIVE_PAUSE", "POST_RUN_PAUSE"})

# Event types absorbed into surrounding episodes (no episode of their own).
SOFT_EVENT_TYPES = frozenset({
    "menuOpen", "menuSelect", "menuClose",                                    # nav_ui
    "playgroundOpen", "playgroundClosed", "playgroundHidden",                 # playground_ui
    "playgroundShow", "playgroundReset",
    "playgroundData",                                                         # performance_data
})

# Subset of SOFT_EVENT_TYPES skipped when scanning for the "next actionful event
# after a RUN" during POST_RUN_PAUSE detection. Caitlin's rule (episodes.py:
# 763-766) excludes nav_ui -- menu events count as actionful there.
POST_RUN_PAUSE_TRANSPARENT_TYPES = frozenset({
    "playgroundOpen", "playgroundClosed", "playgroundHidden",                 # playground_ui
    "playgroundShow", "playgroundReset",
    "playgroundData",                                                         # performance_data
})


def boundary_kind(episode_type):
    """Classify an episode_type as a 'hard' or 'soft' boundary (only the pause
    types count as hard here)."""
    return "hard" if episode_type.upper() in HARD_PAUSE_TYPES else "soft"
