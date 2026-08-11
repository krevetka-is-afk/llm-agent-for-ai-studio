import asyncio
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_studio_agent_builder.infrastructure.persistence.agent_sessions import (
    SQLiteConversationSessionStore,
)


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode unavailable")
def test_conversation_session_store_restricts_database_permissions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "conversation.db"
    cleared: list[str] = []

    async def clear_session() -> None:
        cleared.append("done")

    store = SQLiteConversationSessionStore(
        {database},
        session_factory=lambda _user_id, _path: SimpleNamespace(
            clear_session=clear_session
        ),
    )

    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    asyncio.run(store.clear("user-1"))
    assert cleared == ["done"]
