"""Episode segmentation engine, vendored from lm-dashboard/app/episode_engine/.

Pure stdlib. Carves a session into CODE / RUN / RESET episodes with INACTIVE_PAUSE
and POST_RUN_PAUSE detection. No DB, no framework."""
from src.triggers.episode_engine.segmenter import (
    segment_session,
    segment_episodes,
    boundary_kind,
)

__all__ = ["segment_session", "segment_episodes", "boundary_kind"]
