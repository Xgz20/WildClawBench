---
id: 02_Code_Intelligence_task_007_async_cache_singleflight
name: Coalesce concurrent cache misses
category: 02_Code_Intelligence
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: automated
grading_weights:
  automated: 1.0
  llm_judge: 0.0
tags:
  - custom
---

# Coalesce concurrent cache misses

## Prompt

Concurrent misses for the same key are calling the upstream provider multiple times in `/tmp_workspace/project/cache.py`. Keep the existing async `get(key)` API and TTL behavior, but coalesce identical in-flight requests so one provider call serves all waiters.

Different keys must remain independent. Provider errors and cancellations must not be cached or leave a stuck in-flight entry, and cancelling one waiter must not cancel work still needed by another waiter. Use only the standard library, modify only `/tmp_workspace/project/cache.py`, and run the tests without network access or creating result files:

```bash
cd /tmp_workspace/project
python3 -m unittest -v
```

## Expected Behavior

The cache should keep one in-flight task per key, share its successful result, and remove the in-flight entry after completion or failure. TTL begins when a successful value is stored. A failed or cancelled provider call can be retried, a cancelled waiter does not disrupt other waiters, and different keys can load concurrently. Existing constructor, async method, tests, and source scope remain intact.

## Grading Criteria

- [ ] `same_key_coalesced`: concurrent misses for one key share exactly one provider call
- [ ] `ttl_cache_hits_correct`: cached hits and boundary expiry preserve existing TTL behavior
- [ ] `errors_cancellation_recover`: provider failures, provider cancellation, and waiter cancellation recover without stale state
- [ ] `different_keys_independent`: different keys can load concurrently without global serialization
- [ ] `deterministic_tests_passed`: supplied deterministic async tests pass unchanged
- [ ] `scope_api_preserved`: source scope, standard-library constraint, class, and async API remain valid

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import ast
    import hashlib
    import json
    from pathlib import Path
    import subprocess
    import sys

    keys = [
        "same_key_coalesced",
        "ttl_cache_hits_correct",
        "errors_cancellation_recover",
        "different_keys_independent",
        "deterministic_tests_passed",
        "scope_api_preserved",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    project = root / "project"
    source = project / "cache.py"

    def regular(path):
        try:
            return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        except OSError:
            return False

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        protected_ok = all(
            regular(root / relative)
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in expected["protected_file_sha256"].items()
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores
    if not regular(source):
        return scores

    driver = r'''
import asyncio, importlib.util, inspect, json, pathlib, sys
project = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("candidate_cache", project / "cache.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Clock:
    def __init__(self): self.value = 10.0
    def __call__(self): return self.value

async def checks():
    result = {}
    calls = []
    release = asyncio.Event()
    async def same_provider(key):
        calls.append(key)
        await release.wait()
        return "value:" + key
    cache = module.AsyncTTLCache(same_provider, 20)
    waiters = [asyncio.create_task(cache.get("same")) for _ in range(5)]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    release.set()
    values = await asyncio.gather(*waiters)
    result["same_key"] = values == ["value:same"] * 5 and calls == ["same"]

    clock = Clock()
    ttl_calls = []
    async def ttl_provider(key):
        ttl_calls.append(key)
        return len(ttl_calls)
    ttl_cache = module.AsyncTTLCache(ttl_provider, 5, clock=clock)
    first = await ttl_cache.get("k")
    clock.value = 14.999
    hit = await ttl_cache.get("k")
    clock.value = 15.0
    expired = await ttl_cache.get("k")
    result["ttl"] = [first, hit, expired] == [1, 1, 2] and ttl_calls == ["k", "k"]

    failures = 0
    async def failing_provider(key):
        nonlocal failures
        failures += 1
        if failures == 1:
            raise RuntimeError("temporary")
        return "recovered"
    failure_cache = module.AsyncTTLCache(failing_provider, 30)
    try:
        await failure_cache.get("f")
    except RuntimeError:
        pass
    else:
        result["error_retry"] = False
    if "error_retry" not in result:
        result["error_retry"] = await failure_cache.get("f") == "recovered" and failures == 2

    cancellations = 0
    async def cancelled_provider(key):
        nonlocal cancellations
        cancellations += 1
        if cancellations == 1:
            raise asyncio.CancelledError()
        return "retry-ok"
    cancelled_cache = module.AsyncTTLCache(cancelled_provider, 30)
    try:
        await cancelled_cache.get("c")
    except asyncio.CancelledError:
        pass
    else:
        result["provider_cancel"] = False
    if "provider_cancel" not in result:
        result["provider_cancel"] = await cancelled_cache.get("c") == "retry-ok" and cancellations == 2

    waiter_calls = []
    waiter_release = asyncio.Event()
    async def waiter_provider(key):
        waiter_calls.append(key)
        await waiter_release.wait()
        return "shared"
    waiter_cache = module.AsyncTTLCache(waiter_provider, 30)
    cancelled_waiter = asyncio.create_task(waiter_cache.get("w"))
    surviving_waiter = asyncio.create_task(waiter_cache.get("w"))
    await asyncio.sleep(0)
    cancelled_waiter.cancel()
    try:
        await cancelled_waiter
    except asyncio.CancelledError:
        pass
    waiter_release.set()
    result["waiter_cancel"] = await surviving_waiter == "shared" and waiter_calls == ["w"]

    started = set()
    different_release = asyncio.Event()
    async def different_provider(key):
        started.add(key)
        await different_release.wait()
        return key.upper()
    different_cache = module.AsyncTTLCache(different_provider, 30)
    left = asyncio.create_task(different_cache.get("left"))
    right = asyncio.create_task(different_cache.get("right"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    concurrent = started == {"left", "right"}
    different_release.set()
    result["different"] = concurrent and await left == "LEFT" and await right == "RIGHT"
    result["signature"] = list(inspect.signature(module.AsyncTTLCache.get).parameters) == ["self", "key"]
    return result

print("__RESULT__" + json.dumps(asyncio.run(checks()), sort_keys=True))
'''
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", driver, str(project)],
            text=True,
            capture_output=True,
            timeout=15,
        )
        marker = next(
            line[len("__RESULT__") :]
            for line in reversed(completed.stdout.splitlines())
            if line.startswith("__RESULT__")
        )
        hidden = json.loads(marker) if completed.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, StopIteration, json.JSONDecodeError):
        hidden = {}

    scores["same_key_coalesced"] = float(bool(hidden.get("same_key")))
    scores["ttl_cache_hits_correct"] = float(bool(hidden.get("ttl")))
    scores["errors_cancellation_recover"] = sum(
        bool(hidden.get(name))
        for name in ("error_retry", "provider_cancel", "waiter_cancel")
    ) / 3.0
    scores["different_keys_independent"] = float(bool(hidden.get("different")))

    try:
        public = subprocess.run(
            [sys.executable, "-m", "unittest", "-v"],
            cwd=project,
            text=True,
            capture_output=True,
            timeout=20,
        )
        scores["deterministic_tests_passed"] = float(public.returncode == 0)
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        files = sorted(
            path.relative_to(project).as_posix()
            for path in project.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
        source_text = source.read_text(encoding="utf-8")
        tree = ast.parse(source_text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"asyncio", "time"}
        scope_flags = [
            protected_ok,
            files == sorted(expected["allowed_project_files"]),
            bool(hidden.get("signature")),
            imported <= stdlib,
        ]
        scores["scope_api_preserved"] = sum(scope_flags) / len(scope_flags)
    except (OSError, UnicodeError, SyntaxError):
        pass
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_007_async_cache_singleflight
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
```

## Additional Notes

- The tests use deterministic events and a mutable clock rather than wall-clock sleeps.
- No result artifact is requested; the source modification is the delivery.
