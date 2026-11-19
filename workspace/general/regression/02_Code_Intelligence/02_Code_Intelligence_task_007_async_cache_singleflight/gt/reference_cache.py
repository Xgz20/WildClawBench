"""Reference singleflight TTL cache."""

import asyncio
import time


class AsyncTTLCache:
    def __init__(self, provider, ttl_seconds, clock=None):
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        self._provider = provider
        self._ttl_seconds = ttl_seconds
        self._clock = clock or time.monotonic
        self._cache = {}
        self._inflight = {}

    async def _load(self, key):
        value = await self._provider(key)
        self._cache[key] = (self._clock() + self._ttl_seconds, value)
        return value

    async def get(self, key):
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._load(key))
            self._inflight[key] = task
        try:
            return await asyncio.shield(task)
        finally:
            if task.done() and self._inflight.get(key) is task:
                self._inflight.pop(key, None)
