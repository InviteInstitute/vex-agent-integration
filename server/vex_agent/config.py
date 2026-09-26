"""Centralized configuration: env-backed settings + shared defaults (single source)."""

import os

from dotenv import load_dotenv

DEFAULT_NAVIGATOR_MODEL = "gpt-oss-20b"
DEFAULT_PLAYGROUND = "GO-Mars"


def get_navigator_model() -> str:
    load_dotenv()
    return os.getenv("NAVIGATOR_MODEL", DEFAULT_NAVIGATOR_MODEL)


def get_research_key() -> str | None:
    """Shared secret that unlocks the research preview's agent controls (model and
    prompt overrides). Unset means the research tools are off."""
    load_dotenv()
    return os.getenv("RESEARCH_KEY") or None
