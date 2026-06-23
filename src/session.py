from pathlib import Path

from agents.memory import SQLiteSession


def get_session(session_id: str, db_path: Path) -> SQLiteSession:
    """
    Return (or create) a persistent SQLite-backed thread
    for the given session_id.

    The SDK stores the full conversation history in
    openai_sessions / openai_session_items tables automatically.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteSession(
        session_id=session_id,
        db_path=db_path,
    )
