"""Tests for the output sanitizer (issue #7). Cases are the exact leaks the spike
produced on llama3.2, plus clean inputs that must pass through untouched."""
from src.output_sanitizer import sanitize_llm_output


def test_strips_leading_label():
    assert sanitize_llm_output("Encouragement: Loops can be tricky.") == "Loops can be tricky."


def test_strips_wrapping_quotes():
    assert sanitize_llm_output('"Try reducing your speed and see what happens."') \
        == "Try reducing your speed and see what happens."


def test_strips_student_vocative():
    out = sanitize_llm_output("Student, remember that it's normal to get stuck.")
    assert out == "Remember that it's normal to get stuck."


def test_strips_unbalanced_leading_quote():
    assert sanitize_llm_output('`Enable the drive blocks by connecting them.') \
        == "Enable the drive blocks by connecting them."


def test_clean_sentence_unchanged():
    assert sanitize_llm_output("You're close!") == "You're close!"


def test_apostrophes_preserved():
    # a mid-word apostrophe must survive
    assert sanitize_llm_output("Your robot's arm won't lift yet.") == "Your robot's arm won't lift yet."


def test_empty_and_none_safe():
    assert sanitize_llm_output("") == ""
    assert sanitize_llm_output(None) == ""


def test_idempotent():
    once = sanitize_llm_output('"Encouragement: keep going."')
    assert sanitize_llm_output(once) == once == "Keep going."
