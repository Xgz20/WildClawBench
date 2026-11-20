"""In-memory concurrent batch processing with owned cleanup and one terminal attempt."""
import asyncio

class BatchTimeoutError(TimeoutError):
    pass

async def _finish_owned(awaitable):
    """Do not abandon an owned asynchronous cleanup on repeated cancellation."""
    future = asyncio.ensure_future(awaitable)
    interrupted = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            interrupted = True
    value = future.result()
    if interrupted:
        raise asyncio.CancelledError
    return value

async def _drain(tasks):
    if tasks:
        return await _finish_owned(asyncio.gather(*tasks, return_exceptions=True))
    return []

async def run_batch(items, pool, work, sink, *, concurrency=2, deadline=None):
    items = list(items)
    if type(concurrency) is not int or concurrency < 1:
        raise ValueError("concurrency must be a positive integer")
    if any(not isinstance(item, str) for item in items) or len(set(items)) != len(items):
        raise ValueError("items must be unique strings")
    if not items:
        return []
    if deadline is not None and deadline.is_set():
        raise BatchTimeoutError("batch deadline already expired")
    semaphore = asyncio.Semaphore(concurrency)

    async def one(item):
        async with semaphore:
            lease = await pool.acquire(item)
            try:
                try:
                    value = await work(item, lease)
                except asyncio.CancelledError:
                    await sink.emit(item, "cancelled")
                    raise
                except Exception as error:
                    await sink.emit(item, "failed", error=error)
                    raise
                else:
                    # This call is the sole attempt, even if acceptance is
                    # followed by a cancellation or an acknowledgement error.
                    await sink.emit(item, "succeeded", value=value)
                    return value
            finally:
                await _finish_owned(pool.release(lease))

    tasks = [asyncio.create_task(one(item)) for item in items]
    timer = asyncio.create_task(deadline.wait()) if deadline is not None else None
    pending = set(tasks)
    try:
        while pending:
            observed, _ = await asyncio.wait(pending | ({timer} if timer else set()), return_when=asyncio.FIRST_COMPLETED)
            if timer is not None and timer in observed:
                raise BatchTimeoutError("batch deadline signalled")
            pending.difference_update(observed)
            for completed in observed:
                error = completed.exception()
                if error is not None:
                    raise error
        return [task.result() for task in tasks]
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await _drain(tasks)
        raise
    finally:
        if timer is not None:
            timer.cancel()
            await _drain([timer])
