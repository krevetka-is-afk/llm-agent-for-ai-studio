"""Per-user serialization for mutable Telegram conversation work."""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class PerUserRequestGate:
    def __init__(self) -> None:
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def hold(self, user_id: str) -> AsyncIterator[None]:
        async with self._locks[user_id]:
            yield


__all__ = ["PerUserRequestGate"]
