"""Covers llm_service without Ollama: credential loading, the OpenAI client call
(mocked), length enforcement, and the sanitized generate path."""

from vex_agent.domain.feedback_policy import FeedbackClass
from vex_agent.llm import client as ls


def test_load_navigator_credentials_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://u")
    assert ls.load_navigator_credentials() == ("k", "http://u")


def test_enforce_student_response_length():
    assert ls.enforce_student_response_length("") == ""
    assert ls.enforce_student_response_length("One two three. Four five.").startswith(
        "One two three"
    )
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


def test_credentials_missing_raises(monkeypatch):
    import pytest

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    # no env creds and no navigator_api_keys.json -> clear error
    with pytest.raises(FileNotFoundError):
        ls.load_navigator_credentials()


def test_generate_main_llm_response_sanitizes_and_trims(monkeypatch):
    # a leaked, multi-sentence model output -> cleaned; two short sentences fit the cap
    monkeypatch.setattr(
        ls, "execute_prompt", lambda **k: 'Encouragement: "You are close. Keep going and try more."'
    )
    out = ls.generate_main_llm_response(
        task="t",
        student_message="m",
        available_blocks=["drive"],
        current_program="when started\ndrive for forward, amount 200",
        situation="r",
        recent_messages=[],
        feedback_classes={FeedbackClass.REASSURE},
    )
    assert out["response_text"] == "You are close. Keep going and try more."


# Replies below are real ones Lumen's models gave for the Help scenario.


def test_trim_keeps_the_hint_after_a_short_praise_sentence():
    reply = "Your first steps are a good start. Try running the code to see where the rover stops."
    assert ls.enforce_student_response_length(reply) == reply


def test_trim_drops_a_second_sentence_that_would_pass_the_word_cap():
    reply = (
        "Hang in there, starting with a drive and turn is a good first step! "
        "After turning right, run it and watch: where does the rover end up?"
    )
    assert ls.enforce_student_response_length(reply) == (
        "Hang in there, starting with a drive and turn is a good first step!"
    )


def test_trim_keeps_one_slightly_long_sentence_whole():
    reply = (
        "You're close to getting the rover moving, so try running just the "
        "`drive forward 200 mm` block to see how far it actually goes."
    )
    assert ls.enforce_student_response_length(reply) == reply


def test_trim_shortens_a_runaway_sentence_at_a_clause_break():
    reply = (
        "Your robot drives forward and turns right, which is a fine start for this task, "
        "but you will need many more blocks after that to reach the crater and rescue "
        "the rover and bring the samples back to the lab before time runs out."
    )
    assert ls.enforce_student_response_length(reply) == (
        "Your robot drives forward and turns right, which is a fine start for this task."
    )
