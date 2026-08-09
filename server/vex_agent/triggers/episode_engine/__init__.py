"""Episode segmentation engine, vendored from lm-dashboard/app/episode_engine/.

Pure stdlib. Carves a session into CODE / RUN / RESET episodes with INACTIVE_PAUSE
and POST_RUN_PAUSE detection. No DB, no framework."""

from vex_agent.triggers.episode_engine.segmenter import (
    boundary_kind,
    segment_episodes,
    segment_session,
)

__all__ = ["segment_session", "segment_episodes", "boundary_kind"]
