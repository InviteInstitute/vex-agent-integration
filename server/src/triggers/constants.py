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
EXPLORER_EDIT_DISTANCE = 13      # a single run with edit_distance >= this -> explorer
ITERATIVE_EDIT_MIN = 1           # runs with edit_distance > this count toward iterative
ITERATIVE_DEFAULT_THRESHOLD = 6  # count of such runs that fires iterative
# Per-playground Step-by-Step thresholds; unlisted playgrounds use the default.
ITERATIVE_THRESHOLDS = {"CastleCrasherPlus": 6, "CoralReefRescue": 5, "RoverRescue": 3}

TRIGGER_LABELS = {
    "wheel_spin": "Wheel-spinning", "resilience": "Resilience", "inactive": "Inactive",
    "explorer": "Explorer", "iterative": "Step-by-Step",
}
