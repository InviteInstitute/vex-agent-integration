"""Research preview endpoints: what a researcher needs to try other models and prompts.

Everything here sits behind a shared RESEARCH_KEY sent as the X-Research-Key header.
With no key configured the endpoints report the tools as off. The overrides themselves
ride on POST /v1/students/{id}/responses (see students.py), which checks the same key.
"""

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException

from vex_agent.api.schemas import ResearchConfigResponse, ResearchDefaults
from vex_agent.config import get_navigator_model, get_research_key
from vex_agent.domain.context_builder import PROMPT_PLACEHOLDERS, PROMPT_TEMPLATE
from vex_agent.llm.client import MAIN_RESPONSE_MAX_TOKENS, list_available_models

router = APIRouter(prefix="/v1/research", tags=["research"])
logger = logging.getLogger(__name__)


def require_research_key(provided: str | None) -> None:
    """Raise unless `provided` matches the configured RESEARCH_KEY."""
    expected = get_research_key()
    if expected is None:
        raise HTTPException(status_code=404, detail="Research tools are not enabled.")
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Research key is missing or wrong.")


@router.get("/config", response_model=ResearchConfigResponse)
def get_research_config(
    x_research_key: str | None = Header(default=None),
) -> ResearchConfigResponse:
    require_research_key(x_research_key)
    default_model = get_navigator_model()
    models_error = None
    try:
        models = list_available_models()
    except Exception as error:
        logger.warning("Listing models failed", exc_info=True)
        models, models_error = [], f"Could not list models: {error}"
    if default_model not in models:
        models = [default_model, *models]
    return ResearchConfigResponse(
        defaults=ResearchDefaults(
            model=default_model,
            max_tokens=MAIN_RESPONSE_MAX_TOKENS,
            trim_to_one_sentence=True,
        ),
        models=models,
        models_error=models_error,
        prompt_template=PROMPT_TEMPLATE,
        placeholders=PROMPT_PLACEHOLDERS,
    )
