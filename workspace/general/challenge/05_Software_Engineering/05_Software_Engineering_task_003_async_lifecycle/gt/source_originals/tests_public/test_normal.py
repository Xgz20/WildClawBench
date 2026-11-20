import asyncio
import unittest
from project.worker import run_batch
from project.resources import ResourcePool, MemorySink

class NormalBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_is_ordered_and_balanced(self):
        pool, sink = ResourcePool(), MemorySink()
        async def work(item, lease):
            self.assertEqual(lease.item, item)
            await asyncio.sleep(0)
            return item.upper()
        self.assertEqual(await run_batch(["one", "two", "three"], pool, work, sink, concurrency=2), ["ONE", "TWO", "THREE"])
        self.assertFalse(pool.active)
        self.assertEqual(len(pool.acquired), len(pool.release_calls))
        self.assertLessEqual(pool.peak, 2)
        self.assertEqual({row[1] for row in sink.records}, {"succeeded"})
    async def test_empty_batch_does_not_touch_providers(self):
        pool, sink = ResourcePool(), MemorySink()
        async def work(item, lease):
            raise AssertionError("must not be called")
        self.assertEqual(await run_batch([], pool, work, sink), [])
        self.assertEqual((pool.acquired, pool.release_calls, sink.records), ([], [], []))

if __name__ == "__main__":
    unittest.main()
