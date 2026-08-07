---
id: 02_Code_Intelligence_task_010_idempotent_event_pipeline
name: Recoverable ordered event pipeline
category: 02_Code_Intelligence
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.7
  llm_judge: 0.3
tags:
  - custom
---

# Recoverable ordered event pipeline

## Prompt

This worker duplicates side effects after restart and sometimes applies older events after newer ones. The small project under `/tmp_workspace/project/` uses JSONL events with `event_id`, `aggregate_id`, `sequence`, and `payload`.

Fix the pipeline so duplicate events are harmless, each aggregate is applied in sequence, gaps are deferred rather than skipped, and a crash between state update and side-effect delivery can recover without emitting twice. Keep different aggregates independent. Preserve the existing CLI, event schema, `EventPipeline` methods, and delivery test hook.

Only modify `/tmp_workspace/project/pipeline.py`; do not change `events.jsonl` or the tests. Run:

```bash
cd /tmp_workspace/project
python3 -m unittest -v
```

Also write `/tmp_workspace/results/migration.md` and `/tmp_workspace/results/rollback.md` for the production rollout. Do not use the network or create other result files.

## Expected Behavior

The implementation should durably deduplicate event IDs, reject conflicting reuse, store out-of-order events until each aggregate’s next sequence arrives, and apply ready events in order. State update and outbox creation should be transactional. Effect recording and delivery acknowledgement should also share a transaction so the supplied crash hook rolls both back and recovery emits once. The CLI should retain its three arguments and export the original event objects as JSONL. The two operational documents should match the implemented storage and compatibility behavior.

## Grading Criteria

### Automated group

- [ ] `duplicate_idempotency`: duplicate events remain harmless before and after restart, while conflicting reuse is rejected
- [ ] `per_aggregate_ordering`: gaps are deferred and each aggregate advances only in sequence without blocking other aggregates
- [ ] `crash_recovery_exactly_once_effect`: durable outbox recovery and transactional effect delivery produce one committed effect
- [ ] `cli_schema_compatibility`: existing CLI arguments and event object schema remain compatible
- [ ] `tests_scope_valid`: public tests, protected files, source scope, APIs, and requested result-file scope remain valid

### Judge group

- [ ] `migration_plan_quality`: rollout, data preparation, compatibility, validation, and pause controls are actionable and match the implementation
- [ ] `rollback_plan_quality`: rollback triggers, durable-state handling, compatibility limits, and verification prevent duplicate effects or data loss

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    from pathlib import Path
    import subprocess
    import sys

    keys = [
        "duplicate_idempotency",
        "per_aggregate_ordering",
        "crash_recovery_exactly_once_effect",
        "cli_schema_compatibility",
        "tests_scope_valid",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    project = root / "project"
    source = project / "pipeline.py"

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
import importlib.util, inspect, json, pathlib, subprocess, sys, tempfile
project = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("candidate_pipeline", project / "pipeline.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def event(event_id, aggregate_id, sequence, delta):
    return {"event_id": event_id, "aggregate_id": aggregate_id, "sequence": sequence, "payload": {"delta": delta}}

result = {}
with tempfile.TemporaryDirectory() as temporary:
    database = pathlib.Path(temporary) / "state.db"
    first = module.EventPipeline(database)
    e1 = event("dup-1", "account", 1, 4)
    first.process_events([e1, e1])
    first.deliver()
    first.close()
    second = module.EventPipeline(database)
    second.process_events([e1])
    second.deliver()
    try:
        second.process_events([event("dup-1", "account", 1, 99)])
    except Exception:
        conflict = True
    else:
        conflict = False
    count = second.connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
    second.close()
    result["duplicate"] = count == 1
    result["conflict"] = conflict

with tempfile.TemporaryDirectory() as temporary:
    database = pathlib.Path(temporary) / "state.db"
    pipeline = module.EventPipeline(database)
    pipeline.ingest(event("a2", "a", 2, 2))
    pipeline.ingest(event("b1", "b", 1, 3))
    pipeline.deliver()
    before = [tuple(row) for row in pipeline.connection.execute("SELECT aggregate_id, sequence FROM effects ORDER BY effect_id")]
    pipeline.ingest(event("a1", "a", 1, 1))
    pipeline.deliver()
    after = [tuple(row) for row in pipeline.connection.execute("SELECT aggregate_id, sequence FROM effects ORDER BY effect_id")]
    states = dict(pipeline.connection.execute("SELECT aggregate_id, last_sequence FROM aggregate_state"))
    pipeline.close()
    result["gap"] = before == [("b", 1)] and after == [("b", 1), ("a", 1), ("a", 2)]
    result["states"] = states == {"a": 2, "b": 1}

class Crash(module.EventPipeline):
    def __init__(self, path):
        super().__init__(path)
        self.once = True
    def _before_delivery_commit(self, event):
        if self.once:
            self.once = False
            raise RuntimeError("simulated crash")

with tempfile.TemporaryDirectory() as temporary:
    database = pathlib.Path(temporary) / "state.db"
    crashing = Crash(database)
    crashing.ingest(event("crash-1", "c", 1, 1))
    try:
        crashing.deliver()
    except RuntimeError:
        raised = True
    else:
        raised = False
    rolled_back = crashing.connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0] == 0
    crashing.close()
    recovered = module.EventPipeline(database)
    recovered.deliver()
    recovered.deliver()
    effect_count = recovered.connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
    recovered.close()
    result["crash"] = raised and rolled_back and effect_count == 1

with tempfile.TemporaryDirectory() as temporary:
    directory = pathlib.Path(temporary)
    events = directory / "events.jsonl"
    database = directory / "state.db"
    effects = directory / "effects.jsonl"
    rows = [event("x2", "x", 2, 2), event("x1", "x", 1, 1), event("x2", "x", 2, 2)]
    events.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(project / "pipeline.py"), "--db", str(database), "--events", str(events), "--effects", str(effects)],
        text=True, capture_output=True, timeout=10,
    )
    try:
        delivered = [json.loads(line) for line in effects.read_text(encoding="utf-8").splitlines()]
    except Exception:
        delivered = []
    result["cli"] = (
        completed.returncode == 0
        and [(row.get("event_id"), row.get("sequence")) for row in delivered] == [("x1", 1), ("x2", 2)]
        and all(set(row) == {"event_id", "aggregate_id", "sequence", "payload"} for row in delivered)
    )

result["api"] = all(
    hasattr(module.EventPipeline, name)
    for name in ("ingest", "process_events", "deliver", "export_effects", "close", "_before_delivery_commit")
)
print("__RESULT__" + json.dumps(result, sort_keys=True))
'''
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", driver, str(project)],
            text=True,
            capture_output=True,
            timeout=25,
        )
        marker = next(
            line[len("__RESULT__") :]
            for line in reversed(completed.stdout.splitlines())
            if line.startswith("__RESULT__")
        )
        hidden = json.loads(marker) if completed.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, StopIteration, json.JSONDecodeError):
        hidden = {}

    scores["duplicate_idempotency"] = sum(
        bool(hidden.get(name)) for name in ("duplicate", "conflict")
    ) / 2.0
    scores["per_aggregate_ordering"] = sum(
        bool(hidden.get(name)) for name in ("gap", "states")
    ) / 2.0
    scores["crash_recovery_exactly_once_effect"] = float(bool(hidden.get("crash")))
    scores["cli_schema_compatibility"] = float(bool(hidden.get("cli")))

    try:
        public = subprocess.run(
            [sys.executable, "-m", "unittest", "-v"],
            cwd=project,
            text=True,
            capture_output=True,
            timeout=30,
        )
        project_files = sorted(
            path.relative_to(project).as_posix()
            for path in project.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
        results = root / "results"
        result_files = sorted(
            path.name for path in results.iterdir() if path.is_file() or path.is_symlink()
        )
        delivery_flags = [
            public.returncode == 0,
            protected_ok,
            project_files == sorted(expected["allowed_project_files"]),
            result_files == expected["result_files"],
            all(regular(results / name) for name in expected["result_files"]),
            bool(hidden.get("api")),
        ]
        scores["tests_scope_valid"] = sum(delivery_flags) / len(delivery_flags)
    except (OSError, subprocess.SubprocessError, KeyError):
        pass
    scores["overall_score"] = round(
        0.25 * scores["duplicate_idempotency"]
        + 0.25 * scores["per_aggregate_ordering"]
        + 0.25 * scores["crash_recovery_exactly_once_effect"]
        + 0.10 * scores["cli_schema_compatibility"]
        + 0.15 * scores["tests_scope_valid"],
        6,
    )
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

Judge only the two requested operational documents against the supplied project and implemented `pipeline.py`. Do not add an overall-impression criterion. Each criterion must use one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Migration plan quality (key: migration_plan_quality, weight: 0.5)

Evaluate `/tmp_workspace/results/migration.md` for a safe production rollout that is consistent with the submitted storage and delivery model.

**Score 1.0**: Specifies ordered deployment steps, creation or backfill of deduplication/state/outbox data, a defined old/new worker compatibility window, concrete duplicate/order/outbox-lag validation metrics, and explicit pause conditions; all steps match the implementation.

**Score 0.75**: The rollout, data preparation, compatibility, and validation approach are technically correct, but one secondary metric or pause detail is incomplete.

**Score 0.5**: Provides a usable basic rollout and migration sequence, but compatibility handling or post-deployment validation is materially weak.

**Score 0.25**: Gives only generic instructions such as deploy gradually and observe, without a data transition, compatibility boundary, or measurable control.

**Score 0.0**: The plan would discard pending events, bypass ordering or deduplication state, or otherwise contradict the implementation.

### Criterion 2: Rollback plan quality (key: rollback_plan_quality, weight: 0.5)

Evaluate `/tmp_workspace/results/rollback.md` for recovery without duplicate committed effects or event loss.

**Score 1.0**: Defines measurable rollback triggers, which durable tables and pending rows must be retained, the old-version compatibility boundary, treatment of in-flight and gap events, and verification of state/effect counts before resuming.

**Score 0.75**: The rollback is safe and implementation-aligned, but one recovery check or compatibility detail is incomplete.

**Score 0.5**: Includes a workable version rollback and preserves core state, but does not fully address pending outbox/gap data or final verification.

**Score 0.25**: Says only to redeploy the previous version or restore a backup, without explaining new-state handling and duplicate prevention.

**Score 0.0**: The proposed rollback deletes unprocessed events, resets deduplication markers, repeats committed effects, or provides no usable recovery path.

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_010_idempotent_event_pipeline
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

- Auto checkpoints are equally weighted within the 70% automated group.
- The two Judge criteria are equally weighted within the 30% Judge group.
