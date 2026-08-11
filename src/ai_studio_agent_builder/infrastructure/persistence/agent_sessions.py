from pathlib import Path

from agents.memory import SQLiteSession


def get_session(session_id: str, db_path: Path) -> SQLiteSession:
    """Return the Agents SDK SQLite-backed thread for a conversation."""
    return SQLiteSession(
        session_id=session_id,
        db_path=db_path,
    )


__all__ = ["get_session"]
