"""Tests for the output sanitizer (issue #7). Cases are the exact leaks the spike
produced on llama3.2, plus clean inputs that must pass through untouched."""

from vex_agent.llm.sanitizer import sanitize_llm_output


def test_strips_leading_label():
    assert sanitize_llm_output("Encouragement: Loops can be tricky.") == "Loops can be tricky."


def test_strips_wrapping_quotes():
    assert (
        sanitize_llm_output('"Try reducing your speed and see what happens."')
        == "Try reducing your speed and see what happens."
    )


def test_strips_student_vocative():
    out = sanitize_llm_output("Student, remember that it's normal to get stuck.")
    assert out == "Remember that it's normal to get stuck."


def test_strips_unbalanced_leading_quote():
    assert (
        sanitize_llm_output("`Enable the drive blocks by connecting them.")
        == "Enable the drive blocks by connecting them."
    )


def test_clean_sentence_unchanged():
    assert sanitize_llm_output("You're close!") == "You're close!"


def test_apostrophes_preserved():
    # a mid-word apostrophe must survive
    assert (
        sanitize_llm_output("Your robot's arm won't lift yet.")
        == "Your robot's arm won't lift yet."
    )


def test_empty_and_none_safe():
    assert sanitize_llm_output("") == ""
    assert sanitize_llm_output(None) == ""


def test_idempotent():
    once = sanitize_llm_output('"Encouragement: keep going."')
    assert sanitize_llm_output(once) == once == "Keep going."


def test_strips_complete_thinking_block():
    # Qwen3 with thinking on emits a complete block then the answer; the
    # answer must survive intact, including its capitalization.
    out = sanitize_llm_output(
        "<think>Let me reason about this.\n"
        "The student forgot the loop.\n</think>\n"
        "Your loop needs a condition block."
    )
    assert out == "Your loop needs a condition block."


def test_strips_unterminated_thinking_block():
    # max_tokens cut the model mid-reasoning -- the whole reply is an open
    # think block with no answer. This is the blank-output failure mode.
    assert sanitize_llm_output("<think>Let me reason carefully\nabout the student's") == ""


def test_thinking_tags_mid_sentence_not_stripped():
    # anchored at the start only: a genuine sentence mentioning a tag survives
    out = sanitize_llm_output("Add a think block to your code.")
    assert out == "Add a think block to your code."
