import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import openai

from vex_agent.config import get_navigator_model
from vex_agent.domain.context_builder import PROMPT_TEMPLATE, build_feedback_prompt_from_classes
from vex_agent.domain.feedback_policy import FeedbackClass
from vex_agent.llm.sanitizer import sanitize_llm_output, strip_thinking

logger = logging.getLogger(__name__)

DEFAULT_LLM_TIMEOUT_S = 30.0
# Replies are bite-sized. Models asked for one sentence often write two short ones
# ("You're off to a good start! Try running it and watch where it stops."), and the
# hint is in the second, so a second sentence stays when both fit the word cap.
MAX_STUDENT_RESPONSE_SENTENCES = 2
MAX_STUDENT_RESPONSE_WORDS = 22
# A single sentence a little over the cap is kept whole: a complete sentence reads
# better than one cut off mid-phrase. Past this it is shortened.
MAX_SINGLE_SENTENCE_WORDS = 30
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
# Places a long sentence can end early and still read as a sentence.
CLAUSE_BREAK_PATTERN = re.compile(r"(?:,|;|:|\s[\u2014\u2013-])\s")
# Don't cut a sentence down to a fragment shorter than this.
MIN_CLAUSE_WORDS = 6
# Buffer above MAX_STUDENT_RESPONSE_WORDS (~1.3 tokens/word). Generous on purpose:
# a long `block name` in backticks can eat 20+ tokens on its own, and a cap that's
# too tight truncates the model mid-word instead of mid-generation-savings.
MAIN_RESPONSE_MAX_TOKENS = 160
# Room a reasoning model gets to think before it answers, on top of the answer budget.
# Some models (muse-glimmer-30b) can't turn reasoning off and spend ~1-2k tokens on it.
REASONING_BUDGET_TOKENS = 4096

_client: openai.OpenAI | None = None
# Models that answered only once given room to reason, so later calls ask that way first.
_reasoning_models: set[str] = set()


@dataclass(frozen=True)
class GenerationSettings:
    """Knobs a researcher can turn from the research preview. Every field left at its
    default reproduces exactly what students get: the configured model, PROMPT_TEMPLATE,
    the provider's default temperature, MAIN_RESPONSE_MAX_TOKENS, and the
    bite-size trim."""

    model: str | None = None
    prompt_template: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    trim_reply: bool = True


DEFAULT_GENERATION_SETTINGS = GenerationSettings()


def prepare_main_llm_request(
    task: str,
    student_message: str,
    available_blocks: list[str] | None,
    current_program: str,
    situation: str,
    recent_messages: list[dict[str, str]],
    feedback_classes: set[FeedbackClass],
    settings: GenerationSettings = DEFAULT_GENERATION_SETTINGS,
) -> dict[str, str]:
    prompt = build_feedback_prompt_from_classes(
        task=task,
        student_message=student_message,
        available_blocks=available_blocks,
        current_program=current_program,
        situation=situation,
        recent_messages=recent_messages,
        feedback_classes=feedback_classes,
        template=settings.prompt_template or PROMPT_TEMPLATE,
    )
    return {
        "model": settings.model or get_navigator_model(),
        "prompt": prompt,
    }


def load_navigator_credentials() -> tuple[str, str]:
    env_api_key = os.getenv("OPENAI_API_KEY")
    env_base_url = os.getenv("OPENAI_BASE_URL")
    if env_api_key and env_base_url:
        return env_api_key, env_base_url

    key_file_path = Path(__file__).resolve().parents[1] / "navigator_api_keys.json"
    if not key_file_path.exists():
        raise FileNotFoundError(
            "Missing LLM credentials. Set OPENAI_API_KEY and OPENAI_BASE_URL, "
            f"or create {key_file_path} for local development."
        )

    with key_file_path.open("r", encoding="utf-8") as file:
        credentials = json.load(file)

    return credentials["OPENAI_API_KEY"], credentials["base_url"]


def create_openai_client() -> openai.OpenAI:
    api_key, base_url = load_navigator_credentials()
    return openai.OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=float(os.getenv("LLM_TIMEOUT_S", DEFAULT_LLM_TIMEOUT_S)),
    )


def get_openai_client() -> openai.OpenAI:
    """Lazily-created, process-wide client so calls across requests reuse one warm
    connection instead of each paying a fresh TCP+TLS handshake to the LLM endpoint."""
    global _client
    if _client is None:
        _client = create_openai_client()
    return _client


def clear_client_cache() -> None:
    """Drop the cached client and learned model behavior. Test hook (conftest calls
    it between tests)."""
    global _client
    _client = None
    _reasoning_models.clear()


def _thinking_enabled() -> bool:
    """Thinking models (e.g. qwen3) emit a `<think>...</think>` reasoning block
    before the answer. The navigator produces short student-facing feedback, so
    thinking is off by default -- it would otherwise burn the token budget on
    hidden reasoning and leave the visible reply blank. Opt in via
    LLM_ENABLE_THINKING=true if a future use case wants it."""
    return os.getenv("LLM_ENABLE_THINKING", "false").lower() in ("1", "true", "yes", "on")


def _is_chat_model(model) -> bool:
    """Text in, text out. Gateways that publish modalities (Lumen does) also serve
    speech and other models the agent can't use; ones that don't publish them list
    only chat models, so a missing field counts as chat."""
    extra = model.model_extra or {}
    inputs = extra.get("input_modalities")
    outputs = extra.get("output_modalities")
    return (inputs is None or "text" in inputs) and (outputs is None or "text" in outputs)


def list_available_models() -> list[str]:
    """Chat model ids the configured OpenAI-compatible endpoint (Lumen in prod) serves."""
    return sorted(
        model.id for model in get_openai_client().models.list().data if _is_chat_model(model)
    )


class EmptyAnswerError(RuntimeError):
    """The model spent its whole budget without producing a usable answer. Carries the
    tokens it spent, which still count against the caller's budget."""

    def __init__(self, message: str, tokens: int = 0):
        super().__init__(message)
        self.tokens = tokens


def _request_answer(
    *,
    model: str,
    prompt: str,
    max_tokens: int | None,
    temperature: float | None,
    allow_reasoning: bool,
) -> tuple[str, str, int]:
    """One chat completion. Returns (answer, finish_reason, tokens), where the answer
    has any reasoning block stripped and tokens is what the call spent, prompt plus
    completion (estimated at ~4 characters a token if the gateway reports no usage).

    The default shape is what production has always sent: the answer budget, and
    Qwen's enable_thinking=false. With allow_reasoning the model may think first:
    reasoning_effort=low keeps it short, the Qwen flag is dropped (on GLM it turns
    off the reasoning parser but not the reasoning, which then lands in the answer
    as plain text), and REASONING_BUDGET_TOKENS is added on top of the answer budget.
    """
    kwargs = {}
    budget = max_tokens
    if allow_reasoning:
        kwargs["reasoning_effort"] = "low"
        budget = (max_tokens or MAIN_RESPONSE_MAX_TOKENS) + REASONING_BUDGET_TOKENS
    elif not _thinking_enabled():
        # Only pass the thinking flag when disabling it; opt-in leaves the request
        # untouched so a non-Qwen server never sees an unknown field.
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    if budget is not None:
        kwargs["max_tokens"] = budget
    if temperature is not None:
        kwargs["temperature"] = temperature
    response = get_openai_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    choice = response.choices[0]
    content = choice.message.content or ""
    usage = getattr(response, "usage", None)
    tokens = getattr(usage, "total_tokens", None) or (len(prompt) + len(content)) // 4
    answer = strip_thinking(content).strip()
    return answer, getattr(choice, "finish_reason", None) or "stop", tokens


def execute_prompt(
    *,
    model: str,
    prompt: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
    usage: list[int] | None = None,
) -> str:
    """Ask `model` for a reply, adapting to models that reason before answering.
    Pass a list as `usage` to have the tokens each request spent appended to it.

    A short feedback reply never legitimately runs out of budget, so an empty answer
    or finish_reason="length" means the model spent the budget reasoning (as a
    separate field, inside <think>, or as plain text). Then retry once with room to
    reason, and remember the model so later calls ask that way first. Models that
    answer directly (production's qwen3.8-27b among them) never see the retry."""
    spent = usage if usage is not None else []
    allow_reasoning = model in _reasoning_models
    answer, finish_reason, tokens = _request_answer(
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        allow_reasoning=allow_reasoning,
    )
    spent.append(tokens)
    if (not answer or finish_reason == "length") and not allow_reasoning:
        logger.info(
            "%s gave no usable answer (finish_reason=%s); retrying with room to reason",
            model,
            finish_reason,
        )
        answer, finish_reason, tokens = _request_answer(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            allow_reasoning=True,
        )
        spent.append(tokens)
        if answer:
            _reasoning_models.add(model)
    if not answer:
        raise EmptyAnswerError(
            f"{model} returned no answer (finish_reason={finish_reason}). "
            "It may need more max tokens or a different prompt.",
            tokens=sum(spent),
        )
    return answer


def _end_sentence(text: str) -> str:
    text = text.rstrip(" ,;:\u2014\u2013-")
    return text if not text or text[-1] in ".!?" else f"{text}."


def _shorten_sentence(sentence: str) -> str:
    """Cut an over-long sentence at its last clause break within the word cap, or at
    the cap itself when there is no break late enough to leave a real sentence."""
    words = sentence.split()
    head = " ".join(words[:MAX_STUDENT_RESPONSE_WORDS])
    breaks = [
        match.start()
        for match in CLAUSE_BREAK_PATTERN.finditer(head)
        if len(head[: match.start()].split()) >= MIN_CLAUSE_WORDS
    ]
    return _end_sentence(head[: breaks[-1]] if breaks else head)


def enforce_student_response_length(response_text: str) -> str:
    """Keep a reply bite-sized without leaving it cut off mid-thought: the first
    sentence, plus the next when both fit MAX_STUDENT_RESPONSE_WORDS. A first sentence
    up to MAX_SINGLE_SENTENCE_WORDS is kept whole; a longer one is shortened at a
    clause break."""
    normalized_text = " ".join((response_text or "").split())
    if not normalized_text:
        return ""

    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT_PATTERN.split(normalized_text)
        if sentence.strip()
    ]
    first = sentences[0]
    if len(first.split()) > MAX_SINGLE_SENTENCE_WORDS:
        return _shorten_sentence(first)

    kept = [first]
    word_count = len(first.split())
    for sentence in sentences[1:MAX_STUDENT_RESPONSE_SENTENCES]:
        word_count += len(sentence.split())
        if word_count > MAX_STUDENT_RESPONSE_WORDS:
            break
        kept.append(sentence)
    return _end_sentence(" ".join(kept))


def generate_main_llm_response(
    task: str,
    student_message: str,
    available_blocks: list[str] | None,
    current_program: str,
    situation: str,
    recent_messages: list[dict[str, str]],
    feedback_classes: set[FeedbackClass],
    settings: GenerationSettings = DEFAULT_GENERATION_SETTINGS,
) -> dict[str, str]:
    llm_request = prepare_main_llm_request(
        task=task,
        student_message=student_message,
        available_blocks=available_blocks,
        current_program=current_program,
        situation=situation,
        recent_messages=recent_messages,
        feedback_classes=feedback_classes,
        settings=settings,
    )
    usage: list[int] = []
    response_text = execute_prompt(
        model=llm_request["model"],
        prompt=llm_request["prompt"],
        max_tokens=settings.max_tokens or MAIN_RESPONSE_MAX_TOKENS,
        temperature=settings.temperature,
        usage=usage,
    )
    response_text = sanitize_llm_output(response_text)
    if settings.trim_reply:
        response_text = enforce_student_response_length(response_text)
    return {
        "model": llm_request["model"],
        "prompt": llm_request["prompt"],
        "response_text": response_text,
        "tokens": sum(usage),
    }
