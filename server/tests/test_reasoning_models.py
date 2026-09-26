"""Models that reason before answering: the retry with room to reason, remembering
which models need it, the error when none comes, and hiding non-chat models.

The response shapes mirror what Lumen's models actually returned when probed with
the production prompt: qwen3.8-27b answers directly; GLM puts plain-text reasoning
in the answer and runs out of budget; muse-glimmer-30b puts reasoning in a separate
field and returns an empty answer."""

from types import SimpleNamespace

import pytest

from vex_agent.llm import client as ls
from vex_agent.llm.sanitizer import strip_thinking


def _reply(content, finish_reason="stop"):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def _fake_client(monkeypatch, replies):
    calls = []

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls.append(kwargs)
                    return replies[len(calls) - 1]

    monkeypatch.setattr(ls, "create_openai_client", lambda: _Client())
    return calls


def test_a_direct_answer_is_one_call_in_the_production_shape(monkeypatch):
    calls = _fake_client(monkeypatch, [_reply("Check the distance.")])
    assert (
        ls.execute_prompt(model="qwen3.8-27b", prompt="p", max_tokens=160) == "Check the distance."
    )
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 160
    assert calls[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert "reasoning_effort" not in calls[0]


def test_plain_text_reasoning_cut_off_retries_with_room_to_reason(monkeypatch):
    calls = _fake_client(
        monkeypatch,
        [
            _reply("Let me analyze the situation:\n\nTask: ...", finish_reason="length"),
            _reply("Look at the distance in your `drive forward` block."),
        ],
    )
    answer = ls.execute_prompt(model="glm-5.3", prompt="p", max_tokens=160)
    assert answer == "Look at the distance in your `drive forward` block."
    retry = calls[1]
    assert retry["reasoning_effort"] == "low"
    assert "extra_body" not in retry
    assert retry["max_tokens"] == 160 + ls.REASONING_BUDGET_TOKENS


def test_a_model_that_needed_reasoning_is_asked_that_way_next_time(monkeypatch):
    calls = _fake_client(
        monkeypatch,
        [_reply("", finish_reason="length"), _reply("First."), _reply("Second.")],
    )
    assert ls.execute_prompt(model="muse-glimmer-30b", prompt="p", max_tokens=160) == "First."
    assert ls.execute_prompt(model="muse-glimmer-30b", prompt="p", max_tokens=160) == "Second."
    assert len(calls) == 3
    assert calls[2]["reasoning_effort"] == "low"


def test_an_answer_left_only_in_a_thinking_block_retries(monkeypatch):
    calls = _fake_client(
        monkeypatch, [_reply("<think>still working it out"), _reply("Try a shorter turn.")]
    )
    assert ls.execute_prompt(model="m", prompt="p") == "Try a shorter turn."
    assert len(calls) == 2


def test_no_answer_even_with_room_to_reason_is_a_clear_error(monkeypatch):
    _fake_client(monkeypatch, [_reply("", "length"), _reply("", "length")])
    with pytest.raises(ls.EmptyAnswerError, match="may need more max tokens"):
        ls.execute_prompt(model="m", prompt="p", max_tokens=160)


def test_strip_thinking_handles_a_template_opened_block():
    # The chat template opened <think>, so only the closing tag reaches us.
    assert strip_thinking("reasoning here</think>\n\nThe answer.").strip() == "The answer."
    assert strip_thinking("<think>a</think>The answer.") == "The answer."
    assert strip_thinking("No reasoning at all.") == "No reasoning at all."


def test_model_list_leaves_out_models_that_cannot_chat(monkeypatch):
    def model(model_id, **extra):
        return SimpleNamespace(id=model_id, model_extra=extra)

    listing = SimpleNamespace(
        data=[
            model("qwen3.8-27b", input_modalities=["text"], output_modalities=["text"]),
            model("granite-speech-4.1-2b-plus", input_modalities=["audio"]),
            model("ollama-model"),
        ]
    )
    fake = SimpleNamespace(models=SimpleNamespace(list=lambda: listing))
    monkeypatch.setattr(ls, "get_openai_client", lambda: fake)
    assert ls.list_available_models() == ["ollama-model", "qwen3.8-27b"]
