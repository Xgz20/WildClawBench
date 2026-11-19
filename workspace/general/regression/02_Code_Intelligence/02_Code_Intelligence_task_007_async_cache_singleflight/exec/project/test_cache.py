import asyncio
import unittest

from cache import AsyncTTLCache


class MutableClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class CacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_same_key_uses_one_provider_call(self):
        calls = []
        release = asyncio.Event()

        async def provider(key):
            calls.append(key)
            await release.wait()
            return f"value:{key}"

        cache = AsyncTTLCache(provider, 30)
        first = asyncio.create_task(cache.get("alpha"))
        second = asyncio.create_task(cache.get("alpha"))
        await asyncio.sleep(0)
        release.set()
        self.assertEqual(await asyncio.gather(first, second), ["value:alpha"] * 2)
        self.assertEqual(calls, ["alpha"])

    async def test_ttl_hit_and_expiry(self):
        clock = MutableClock()
        calls = []

        async def provider(key):
            calls.append(key)
            return len(calls)

        cache = AsyncTTLCache(provider, 10, clock=clock)
        self.assertEqual(await cache.get("k"), 1)
        clock.value = 109.9
        self.assertEqual(await cache.get("k"), 1)
        clock.value = 110.0
        self.assertEqual(await cache.get("k"), 2)

    async def test_provider_error_can_retry(self):
        calls = 0

        async def provider(key):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary")
            return "ok"

        cache = AsyncTTLCache(provider, 10)
        with self.assertRaises(RuntimeError):
            await cache.get("k")
        self.assertEqual(await cache.get("k"), "ok")


if __name__ == "__main__":
    unittest.main()
