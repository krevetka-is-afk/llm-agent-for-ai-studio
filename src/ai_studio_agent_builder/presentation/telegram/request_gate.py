"""Per-user serialization for mutable Telegram conversation work."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary


class PerUserRequestGate:
    def __init__(self, *, max_concurrent_requests: int = 8) -> None:
        if max_concurrent_requests <= 0:
            raise ValueError("Global request concurrency must be positive")
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self._global_slots = asyncio.Semaphore(max_concurrent_requests)

    @asynccontextmanager
    async def hold(self, user_id: str) -> AsyncIterator[None]:
        user_lock = self._locks.get(user_id)
        if user_lock is None:
            user_lock = asyncio.Lock()
            self._locks[user_id] = user_lock
        async with user_lock:
            async with self._global_slots:
                yield


__all__ = ["PerUserRequestGate"]
