from collections import defaultdict

MAX_SESSION_TURNS = 6

# The chat panel keeps two separate conversations per session: what a student sees
# ("student") and a researcher's experiments ("research"). Each chat keeps its own
# recent turns, so an experiment never leaks into the context of a student reply.
STUDENT_CHAT = "student"
RESEARCH_CHAT = "research"
CHATS = (STUDENT_CHAT, RESEARCH_CHAT)

_session_messages: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)


def get_recent_session_messages(
    student_id: str,
    playground: str,
    session_id: str,
    chat: str = STUDENT_CHAT,
) -> list[dict[str, str]]:
    return list(_session_messages[(student_id, playground, session_id, chat)])


def append_session_message(
    student_id: str,
    playground: str,
    session_id: str,
    role: str,
    content: str,
    chat: str = STUDENT_CHAT,
) -> None:
    key = (student_id, playground, session_id, chat)
    _session_messages[key].append({"role": role, "content": content})
    if len(_session_messages[key]) > MAX_SESSION_TURNS:
        _session_messages[key] = _session_messages[key][-MAX_SESSION_TURNS:]
