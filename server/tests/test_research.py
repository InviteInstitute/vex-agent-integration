"""Research preview: the key gate, the config endpoint, and generation overrides.

No database or LLM is touched: the model list and the OpenAI client are faked, and the
overrides are exercised through generate_main_llm_response directly."""

import pytest
from fastapi.testclient import TestClient

from vex_agent.api import research as research_api
from vex_agent.api.turnstile import COOKIE_NAME, sign_cookie
from vex_agent.domain.context_builder import (
    PROMPT_PLACEHOLDERS,
    PROMPT_TEMPLATE,
    render_prompt_template,
)
from vex_agent.domain.feedback_policy import FeedbackClass
from vex_agent.llm import client as ls

KEY = "test-research-key"


@pytest.fixture
def api(monkeypatch):
    from vex_agent.app import app

    monkeypatch.setattr("vex_agent.app.warm_up", lambda: None)
    with TestClient(app) as client:
        client.cookies.set(COOKIE_NAME, sign_cookie())
        yield client


def _values():
    return {name: f"<{name}>" for name in PROMPT_PLACEHOLDERS}


def test_render_matches_str_format_on_the_production_template():
    values = _values()
    assert render_prompt_template(PROMPT_TEMPLATE, values) == PROMPT_TEMPLATE.format(**values)


def test_render_leaves_unknown_placeholders_and_stray_braces():
    rendered = render_prompt_template('{task} then {"json": 1} and {nope}', {"task": "T"})
    assert rendered == 'T then {"json": 1} and {nope}'


def test_config_reports_tools_off_without_a_key(api, monkeypatch):
    monkeypatch.delenv("RESEARCH_KEY", raising=False)
    monkeypatch.setattr(research_api, "get_research_key", lambda: None)
    assert api.get("/v1/research/config").status_code == 404


def test_config_rejects_a_wrong_key(api, monkeypatch):
    monkeypatch.setattr(research_api, "get_research_key", lambda: KEY)
    response = api.get("/v1/research/config", headers={"X-Research-Key": "nope"})
    assert response.status_code == 403


def test_config_lists_models_and_the_live_template(api, monkeypatch):
    monkeypatch.setattr(research_api, "get_research_key", lambda: KEY)
    monkeypatch.setattr(research_api, "get_navigator_model", lambda: "default-model")
    monkeypatch.setattr(research_api, "list_available_models", lambda: ["a", "b"])
    body = api.get("/v1/research/config", headers={"X-Research-Key": KEY}).json()
    assert body["models"] == ["default-model", "a", "b"]
    assert body["defaults"] == {
        "model": "default-model",
        "max_tokens": ls.MAIN_RESPONSE_MAX_TOKENS,
        "trim_reply": True,
    }
    assert body["prompt_template"] == PROMPT_TEMPLATE
    assert set(body["placeholders"]) == set(PROMPT_PLACEHOLDERS)


def test_config_still_answers_when_listing_models_fails(api, monkeypatch):
    def boom():
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(research_api, "get_research_key", lambda: KEY)
    monkeypatch.setattr(research_api, "get_navigator_model", lambda: "default-model")
    monkeypatch.setattr(research_api, "list_available_models", boom)
    body = api.get("/v1/research/config", headers={"X-Research-Key": KEY}).json()
    assert body["models"] == ["default-model"]
    assert "endpoint down" in body["models_error"]


def test_overrides_on_a_response_need_the_research_key(api, monkeypatch):
    monkeypatch.setattr(research_api, "get_research_key", lambda: KEY)
    response = api.post(
        "/v1/students/s1/responses",
        json={"student_message": "Help", "overrides": {"model": "other"}},
    )
    assert response.status_code == 403


def _capture_llm(monkeypatch, reply):
    calls = {}

    def fake_execute(**kwargs):
        calls.update(kwargs)
        return reply

    monkeypatch.setattr(ls, "execute_prompt", fake_execute)
    monkeypatch.setattr(ls, "get_navigator_model", lambda: "default-model")
    return calls


def _generate(settings=ls.DEFAULT_GENERATION_SETTINGS):
    return ls.generate_main_llm_response(
        task="Rescue the rover",
        student_message="Help",
        available_blocks=["drive forward"],
        current_program="",
        situation="None",
        recent_messages=[],
        feedback_classes={FeedbackClass.QUESTION},
        settings=settings,
    )


def test_default_settings_keep_the_student_path(monkeypatch):
    long_reply = "First sentence here. " + " ".join(["word"] * 40)
    calls = _capture_llm(monkeypatch, long_reply)
    result = _generate()
    assert calls["model"] == "default-model"
    assert calls["max_tokens"] == ls.MAIN_RESPONSE_MAX_TOKENS
    assert calls["temperature"] is None
    assert calls["prompt"].startswith("You are an educational feedback assistant")
    assert result["response_text"] == "First sentence here."


def test_overrides_change_model_prompt_sampling_and_trim(monkeypatch):
    long_reply = "First sentence here. Second sentence stays."
    calls = _capture_llm(monkeypatch, long_reply)
    settings = ls.GenerationSettings(
        model="glm-5.3",
        prompt_template="Be brief. Task: {task}. Said: {student_message}.",
        temperature=0.2,
        max_tokens=400,
        trim_reply=False,
    )
    result = _generate(settings)
    assert calls["model"] == "glm-5.3"
    assert calls["prompt"] == "Be brief. Task: Rescue the rover. Said: Help."
    assert calls["temperature"] == 0.2
    assert calls["max_tokens"] == 400
    assert result["model"] == "glm-5.3"
    assert result["response_text"] == long_reply


def test_execute_prompt_passes_temperature_only_when_set(monkeypatch):
    seen = []

    class _Resp:
        class _Choice:
            class message:
                content = "ok"

        choices = [_Choice()]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.append(kwargs)
                    return _Resp()

    monkeypatch.setattr(ls, "create_openai_client", lambda: _Client())
    ls.execute_prompt(model="m", prompt="p")
    ls.execute_prompt(model="m", prompt="p", temperature=0.7)
    assert "temperature" not in seen[0]
    assert seen[1]["temperature"] == 0.7
