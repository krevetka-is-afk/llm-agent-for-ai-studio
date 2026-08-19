import os
import stat
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from agents.memory import SQLiteSession


def get_session(session_id: str, db_path: Path) -> SQLiteSession:
    """Return the Agents SDK SQLite-backed thread for a conversation."""
    return SQLiteSession(
        session_id=session_id,
        db_path=db_path,
    )


SessionFactory = Callable[[str, Path], Any]


class SQLiteConversationSessionStore:
    def __init__(
        self,
        db_paths: Iterable[Path],
        *,
        session_factory: SessionFactory = get_session,
    ) -> None:
        self._db_paths = frozenset(db_paths)
        self._session_factory = session_factory
        for db_path in self._db_paths:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.touch(mode=0o600, exist_ok=True)
            if os.name == "posix":
                db_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    async def clear(self, user_id: str) -> None:
        for db_path in self._db_paths:
            await self._session_factory(user_id, db_path).clear_session()


__all__ = ["SQLiteConversationSessionStore", "get_session"]
