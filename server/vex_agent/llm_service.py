import json
import os
import re
from pathlib import Path

import openai

from vex_agent.context_builder import (
    build_feedback_prompt_from_classes,
    build_robot_behavior_prompt,
)
from vex_agent.feedback_policy import FeedbackClass
from vex_agent.output_sanitizer import sanitize_llm_output
from vex_agent.settings import get_navigator_model

DEFAULT_LLM_TIMEOUT_S = 30.0
MAX_STUDENT_RESPONSE_SENTENCES = 1
MAX_STUDENT_RESPONSE_WORDS = 22
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
# Buffer above MAX_STUDENT_RESPONSE_WORDS (~1.3 tokens/word). Generous on purpose:
# a long `block name` in backticks can eat 20+ tokens on its own, and a cap that's
# too tight truncates the model mid-word instead of mid-generation-savings.
MAIN_RESPONSE_MAX_TOKENS = 160

_client: openai.OpenAI | None = None


def prepare_main_llm_request(
    task: str,
    student_message: str,
    available_blocks: list[str] | None,
    current_program: str,
    robot_behavior_summary: str,
    recent_messages: list[dict[str, str]],
    feedback_classes: set[FeedbackClass],
) -> dict[str, str]:
    prompt = build_feedback_prompt_from_classes(
        task=task,
        student_message=student_message,
        available_blocks=available_blocks,
        current_program=current_program,
        robot_behavior_summary=robot_behavior_summary,
        recent_messages=recent_messages,
        feedback_classes=feedback_classes,
    )
    return {
        "model": get_navigator_model(),
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
    """Lazily-created, process-wide client so back-to-back calls (robot-behavior
    summary, then main response) reuse one warm connection instead of each paying
    a fresh TCP+TLS handshake to the LLM endpoint."""
    global _client
    if _client is None:
        _client = create_openai_client()
    return _client


def clear_client_cache() -> None:
    """Drop the cached client. Test hook (conftest calls it between tests)."""
    global _client
    _client = None


def execute_prompt(*, model: str, prompt: str, max_tokens: int | None = None) -> str:
    client = get_openai_client()
    kwargs = {"max_tokens": max_tokens} if max_tokens is not None else {}
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        **kwargs,
    )
    return response.choices[0].message.content


def enforce_student_response_length(response_text: str) -> str:
    normalized_text = " ".join((response_text or "").split())
    if not normalized_text:
        return ""

    sentences = []
    for sentence in SENTENCE_SPLIT_PATTERN.split(normalized_text):
        cleaned_sentence = sentence.strip()
        if not cleaned_sentence:
            continue
        sentences.append(cleaned_sentence)
        if len(sentences) == MAX_STUDENT_RESPONSE_SENTENCES:
            break

    trimmed_text = " ".join(sentences) if sentences else normalized_text
    words = trimmed_text.split()
    if len(words) > MAX_STUDENT_RESPONSE_WORDS:
        trimmed_text = " ".join(words[:MAX_STUDENT_RESPONSE_WORDS]).rstrip(" ,;:")
        if trimmed_text and trimmed_text[-1] not in ".!?":
            trimmed_text = f"{trimmed_text}."

    return trimmed_text


def generate_robot_behavior_summary(task: str, raw_logs: str) -> dict[str, str]:
    model = get_navigator_model()
    prompt = build_robot_behavior_prompt(
        task=task,
        raw_logs=raw_logs,
    )
    response_text = execute_prompt(model=model, prompt=prompt)
    return {
        "model": model,
        "prompt": prompt,
        "response_text": response_text,
    }


def generate_main_llm_response(
    task: str,
    student_message: str,
    available_blocks: list[str] | None,
    current_program: str,
    robot_behavior_summary: str,
    recent_messages: list[dict[str, str]],
    feedback_classes: set[FeedbackClass],
) -> dict[str, str]:
    llm_request = prepare_main_llm_request(
        task=task,
        student_message=student_message,
        available_blocks=available_blocks,
        current_program=current_program,
        robot_behavior_summary=robot_behavior_summary,
        recent_messages=recent_messages,
        feedback_classes=feedback_classes,
    )
    response_text = execute_prompt(
        model=llm_request["model"],
        prompt=llm_request["prompt"],
        max_tokens=MAIN_RESPONSE_MAX_TOKENS,
    )
    response_text = enforce_student_response_length(sanitize_llm_output(response_text))
    return {
        "model": llm_request["model"],
        "prompt": llm_request["prompt"],
        "response_text": response_text,
    }
