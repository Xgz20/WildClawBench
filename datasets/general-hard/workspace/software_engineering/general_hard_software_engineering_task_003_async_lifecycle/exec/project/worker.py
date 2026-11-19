"""Concurrent batch processor. Normal batches work; lifecycle paths need repair."""
import asyncio

class BatchTimeoutError(TimeoutError):
    pass

async def run_batch(items, pool, work, sink, *, concurrency=2, deadline=None):
    items = list(items)
    if type(concurrency) is not int or concurrency < 1:
        raise ValueError("concurrency must be a positive integer")
    if any(not isinstance(item, str) for item in items) or len(set(items)) != len(items):
        raise ValueError("items must be unique strings")
    if not items:
        return []
    semaphore = asyncio.Semaphore(concurrency)

    async def one(item):
        async with semaphore:
            lease = await pool.acquire(item)
            try:
                value = await work(item, lease)
            except asyncio.CancelledError:
                await sink.emit(item, "cancelled")
                return None
            except Exception as error:
                await pool.release(lease)
                await sink.emit(item, "failed", error=error)
                raise
            await sink.emit(item, "succeeded", value=value)
            await pool.release(lease)
            return value

    tasks = [asyncio.create_task(one(item)) for item in items]
    aggregate = asyncio.gather(*tasks)
    timer = None
    try:
        if deadline is not None:
            timer = asyncio.create_task(deadline.wait())
            done, _ = await asyncio.wait({aggregate, timer}, return_when=asyncio.FIRST_COMPLETED)
            if timer in done:
                aggregate.cancel()
                return []
        return await aggregate
    finally:
        if timer is not None:
            timer.cancel()
