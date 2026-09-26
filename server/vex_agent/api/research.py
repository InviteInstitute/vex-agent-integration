"""Research preview endpoint: what the Agent tab needs to try other models and prompts.

Open to anyone who passes Turnstile. What bounds it is the per-session and daily LLM
token budget (services/budget.py), which every reply made with these settings counts
against. The overrides themselves ride on POST /v1/students/{id}/responses.
"""

import logging

from fastapi import APIRouter, Request

from vex_agent.api.schemas import ResearchConfigResponse, ResearchDefaults, TokenUsage
from vex_agent.api.turnstile import COOKIE_NAME
from vex_agent.config import get_navigator_model
from vex_agent.domain.context_builder import PROMPT_PLACEHOLDERS, PROMPT_TEMPLATE
from vex_agent.llm.client import MAIN_RESPONSE_MAX_TOKENS, list_available_models
from vex_agent.services import budget

router = APIRouter(prefix="/v1/research", tags=["research"])
logger = logging.getLogger(__name__)


@router.get("/config", response_model=ResearchConfigResponse)
def get_research_config(request: Request) -> ResearchConfigResponse:
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
            trim_reply=True,
        ),
        models=models,
        models_error=models_error,
        prompt_template=PROMPT_TEMPLATE,
        placeholders=PROMPT_PLACEHOLDERS,
        session_tokens=TokenUsage(
            **budget.session_usage(budget.budget_key(request.cookies.get(COOKIE_NAME)))
        ),
    )
