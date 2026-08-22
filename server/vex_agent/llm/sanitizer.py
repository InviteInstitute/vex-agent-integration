"""Strip the label/quote leaks small local models emit before we trim to one
sentence. The spike (server/poc_proactive_trigger.py) showed llama3.2 producing
things like `"Encouragement: Loops can be tricky."`, wrapping quotes, and a
`"Student,"` vocative -- all of which the OUTPUT RULES forbid but which survive
length trimming. Conservative on purpose: it only removes leak signatures, never
real sentence content."""

import re

# A leading "Label:" prefix -- a single capitalized word (or two) then a colon.
# One-sentence feedback almost never legitimately opens "Word:", so this is safe.
_LEADING_LABEL = re.compile(r"^\s*[A-Z][A-Za-z]+(?:\s+[A-Za-z]+)?:\s*")
# A leading vocative the model sometimes prepends.
_LEADING_VOCATIVE = re.compile(
    r"^\s*(?:hi\s+student|hey\s+student|student)\s*[,:]\s*", re.IGNORECASE
)
_WRAP_CHARS = "\"'`"
# Qwen3-style thinking blocks. A complete block is `...`; an
# unterminated `...` (max_tokens cut it mid-reasoning) is the case that
# blanks the reply. Both are anchored at the start so we never strip a genuine
# answer that happens to mention the tags mid-sentence. DOTALL so they span
# the newlines the model puts between reasoning steps.
_THINK_COMPLETE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
_THINK_UNTERMINATED = re.compile(r"^\s*<think>.*", re.DOTALL)


def _strip_thinking(text: str) -> str:
    # Complete block first, then any unterminated prefix left over. Each is
    # count=1 because thinking only appears at the very start of a reply.
    text = _THINK_COMPLETE.sub("", text, count=1)
    text = _THINK_UNTERMINATED.sub("", text, count=1)
    return text


def sanitize_llm_output(text: str) -> str:
    """Remove wrapping quotes/backticks, a leading 'Label:' prefix, and a leading
    'Student,' vocative, then re-capitalize. Idempotent and safe on clean input."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    # Drop Qwen3 thinking blocks before anything else: a truncated reasoning
    # block (max_tokens cut it mid-think) would otherwise survive as the whole
    # message and come out blank after length trimming.
    cleaned = _strip_thinking(cleaned).strip()
    if not cleaned:
        return ""

    # Balanced wrapping quote/backtick around the whole message.
    if len(cleaned) >= 2 and cleaned[0] in _WRAP_CHARS and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1].strip()
    # Unbalanced leaked quotes on either end.
    cleaned = cleaned.strip(_WRAP_CHARS).strip()

    cleaned = _LEADING_LABEL.sub("", cleaned, count=1)
    cleaned = _LEADING_VOCATIVE.sub("", cleaned, count=1)
    cleaned = cleaned.strip(_WRAP_CHARS).strip()

    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned
