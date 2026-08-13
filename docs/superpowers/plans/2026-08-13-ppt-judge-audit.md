# PPT Judge Reliability and Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make PPT evaluation use rendered slide evidence, make structured Judge failures retryable and diagnosable, and persist every Judge request/response in the run workspace without breaking existing tasks.

**Architecture:** Add an explicit `ppt` metric profile selected by the existing `ppt` tag. Keep automated checks and legacy text Judge paths unchanged, while the v2 grading runner builds a PPT-specific multimodal evidence payload after rendering discovered `.pptx` files. Wrap each Judge attempt with a redacted audit record under `<run>/judge/`, and use Anthropic `submit_grading` tool constraints plus bounded retries before reporting a validity failure.

**Tech Stack:** Python 3, unittest, pytest, Docker subprocesses, LibreOffice/soffice when available, OpenAI-compatible task grader API, Anthropic Messages API.

---

### Task 1: Metric profile routing and audit helpers

**Files:**
- Modify: `src/utils/task_parser.py`
- Create: `src/utils/judge_audit.py`
- Test: `tests/test_task_rubric_parser.py`, `tests/test_judge_audit.py`

- [ ] Add a failing test that a task with `tags: [ppt]` resolves to `metric_profile == "ppt"`, while a plain task remains empty.
- [ ] Add failing audit tests for attempt paths, secret redaction, and JSON serialization of messages without image base64.
- [ ] Implement the profile mapping and a small audit writer that stores `request.json`, `response.json`, `parsed.json`, and `summary.json` under the provided run directory.
- [ ] Run focused tests and confirm they pass.

### Task 2: Judge shim structured Anthropic responses

**Files:**
- Modify: `src/utils/judge_shim.py`
- Test: `tests/test_grading_timeouts.py`, `tests/test_judge_shim.py`

- [ ] Add failing tests asserting JSON requests include an Anthropic `submit_grading` tool and that returned stop reason, raw payload, and text are available to the caller.
- [ ] Implement the tool schema only for `response_format.type == "json_object"`, preserve the OpenAI-shaped response contract, and attach response metadata for audit.
- [ ] Run the focused shim tests.

### Task 3: Bounded retries and audit integration in grading

**Files:**
- Modify: `src/utils/grading.py`
- Test: `tests/test_website_semantic_grading.py`, `tests/test_judge_retries.py`

- [ ] Add failing tests for invalid JSON followed by valid JSON, exhausted retries, and audit output for each attempt.
- [ ] Implement two retries with a shorter repair prompt, configurable through `WILDCLAW_JUDGE_RETRIES` while defaulting to two, and retain validity-failure semantics after exhaustion.
- [ ] Pass the run output directory into the v2 Judge path and write redacted attempts and final summary.
- [ ] Verify non-PPT legacy and v2 text tasks keep their existing prompt and score behavior.

### Task 4: PPT rendering and multimodal evidence

**Files:**
- Create: `src/utils/ppt_evidence.py`
- Modify: `src/utils/grading.py`
- Test: `tests/test_ppt_evidence.py`, `tests/test_website_semantic_grading.py`

- [ ] Add failing tests for deterministic PPTX discovery, rendered slide ordering, image message blocks, and explicit render failure.
- [ ] Implement renderer discovery using `soffice`/`libreoffice`, render each deck to PDF/PNG, cap evidence size, and persist rendered images under the Judge audit directory.
- [ ] Build PPT Judge messages with rendered images plus bounded companion text; require rendered evidence for `metric_profile == "ppt"`.
- [ ] Run focused evidence and grading tests.

### Task 5: End-to-end compatibility and documentation

**Files:**
- Modify: `README.md`, `.env.example` (if present), relevant task/report docs
- Test: full Python test suite

- [ ] Document `WILDCLAW_JUDGE_RETRIES`, audit location, PPT rendering dependency, and failure semantics.
- [ ] Run `uv run pytest -q` and targeted static checks.
- [ ] Inspect the diff and commit only related files with a Chinese Conventional Commit message.

