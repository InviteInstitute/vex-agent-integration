"""Covers llm_service without Ollama: credential loading, the OpenAI client call
(mocked), length enforcement, and the sanitized generate path."""
from src import llm_service as ls
from src.feedback_policy import FeedbackClass


def test_load_navigator_credentials_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://u")
    assert ls.load_navigator_credentials() == ("k", "http://u")


def test_enforce_student_response_length():
    assert ls.enforce_student_response_length("") == ""
    assert ls.enforce_student_response_length("One two three. Four five.").startswith("One two three")
    long = " ".join(str(i) for i in range(40))
    assert len(ls.enforce_student_response_length(long).split()) <= 22


def test_execute_prompt_calls_client(monkeypatch):
    class _Msg:
        content = "hello there"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _Resp()

    monkeypatch.setattr(ls, "create_openai_client", lambda: _Client())
    assert ls.execute_prompt(model="m", prompt="p") == "hello there"


def test_create_openai_client_uses_credentials(monkeypatch):
    made = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            made.update(kwargs)

    monkeypatch.setattr(ls.openai, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(ls, "load_navigator_credentials", lambda: ("k", "http://u"))
    ls.create_openai_client()
    assert made["api_key"] == "k" and made["base_url"] == "http://u"


def test_generate_robot_behavior_summary(monkeypatch):
    monkeypatch.setattr(ls, "execute_prompt", lambda **k: "the robot drives then stops")
    out = ls.generate_robot_behavior_summary(task="t", raw_logs="logs")
    assert out["response_text"] == "the robot drives then stops"


def test_credentials_missing_raises(monkeypatch):
    import pytest
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    # no env creds and no navigator_api_keys.json -> clear error
    with pytest.raises(FileNotFoundError):
        ls.load_navigator_credentials()


def test_generate_main_llm_response_sanitizes_and_trims(monkeypatch):
    # a leaked, multi-sentence model output -> cleaned + trimmed to one sentence
    monkeypatch.setattr(ls, "execute_prompt",
                        lambda **k: 'Encouragement: "You are close. Keep going and try more."')
    out = ls.generate_main_llm_response(
        task="t", student_message="m", available_blocks=["drive"],
        robot_behavior_summary="r", recent_messages=[],
        feedback_classes={FeedbackClass.REASSURE},
    )
    text = out["response_text"]
    assert "Encouragement" not in text and '"' not in text
    assert text.count(".") <= 1  # trimmed to one sentence
