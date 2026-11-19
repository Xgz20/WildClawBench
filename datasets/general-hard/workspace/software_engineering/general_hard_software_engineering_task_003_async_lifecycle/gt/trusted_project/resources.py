"""Observable in-memory providers. This fixture is protected input, not the fix."""
import asyncio
from dataclasses import dataclass

@dataclass(frozen=True)
class Lease:
    item: str
    serial: int

class ResourcePool:
    def __init__(self):
        self.active = set()
        self.acquired = []
        self.release_calls = []
        self.peak = 0
    async def acquire(self, item):
        await asyncio.sleep(0)
        lease = Lease(item, len(self.acquired) + 1)
        self.active.add(lease)
        self.acquired.append(lease)
        self.peak = max(self.peak, len(self.active))
        return lease
    async def release(self, lease):
        self.release_calls.append(lease)
        await asyncio.sleep(0)
        if lease not in self.active:
            raise RuntimeError("lease was released twice or not owned")
        self.active.remove(lease)

class MemorySink:
    def __init__(self):
        self.attempts = []
        self.records = []
    async def emit(self, item, status, *, value=None, error=None):
        self.attempts.append((item, status))
        if any(row[0] == item for row in self.records):
            raise RuntimeError("duplicate terminal publication")
        self.records.append((item, status, value, error))
        await asyncio.sleep(0)
