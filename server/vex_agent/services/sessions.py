from collections import defaultdict


MAX_SESSION_TURNS = 6

_session_messages: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)


def get_recent_session_messages(
    student_id: str,
    playground: str,
    session_id: str,
) -> list[dict[str, str]]:
    return list(_session_messages[(student_id, playground, session_id)])


def append_session_message(
    student_id: str,
    playground: str,
    session_id: str,
    role: str,
    content: str,
) -> None:
    key = (student_id, playground, session_id)
    _session_messages[key].append({"role": role, "content": content})
    if len(_session_messages[key]) > MAX_SESSION_TURNS:
        _session_messages[key] = _session_messages[key][-MAX_SESSION_TURNS:]
