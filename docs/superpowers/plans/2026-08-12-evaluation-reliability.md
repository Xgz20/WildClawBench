# Evaluation Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make shared Rubric Judge output capacity configurable, classify Judge output failures reliably, and validate only the task scope planned by each evaluation batch.

**Architecture:** Keep Judge configuration in the shared grading layer, keep run anomaly attribution in `src/utils/anomalies.py`, and persist selection metadata beside each unit's `run.log`. The validator consumes structured scope first and falls back to historical log parsing.

**Tech Stack:** Python 3, unittest, JSON result artifacts, existing WildClawBench report validators.

---

### Task 1: Shared Judge response capacity

**Files:**
- Modify: `src/utils/grading.py`
- Test: `tests/test_website_semantic_grading.py`

- [ ] Add failing tests for default 1000, configured positive integer, and invalid/non-positive fallback.
- [ ] Run the focused tests and confirm failures are caused by the hard-coded 800 value.
- [ ] Add `DEFAULT_JUDGE_MAX_TOKENS` and `_judge_max_tokens()`; embed its result in the v2 Rubric Judge request.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Judge output anomaly classification

**Files:**
- Modify: `src/utils/anomalies.py`
- Test: `tests/test_anomalies.py`

- [ ] Add failing tests for `_grading.llm_notes` values `judge failed:` and `judge_call_failed:`.
- [ ] Add a control test proving normal Judge notes do not create an anomaly.
- [ ] Extract explicit grading failure evidence from top-level fields and nested Judge notes.
- [ ] Run anomaly tests and confirm the failure is classified as `GRADING_SCRIPT_ERROR`.

### Task 3: Persist and consume the planned evaluation scope

**Files:**
- Modify: `eval/run_batch.py`
- Modify: `tools/report/skills/validate-eval-results/scripts/validate_eval_results.py`
- Test: `tests/test_run_batch_task_counts.py`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [ ] Add failing tests for the `evaluation_scope.json` schema and planned task set.
- [ ] Add failing validator tests for structured scope priority and historical `Category:` plus tag fallback.
- [ ] Write scope metadata after filtering and before execution, preserving pre-resume planned tasks.
- [ ] Make validator expected-task selection consume structured scope first, then scoped log filters.
- [ ] Run focused runner and report validation tests.

### Task 4: Regression and real-result verification

**Files:**
- No production files beyond Tasks 1-3.

- [ ] Run `git diff --check`.
- [ ] Run grading, anomaly, batch-selection, task-parser, and report pipeline tests.
- [ ] Run `validate_eval_results.py` against `eval_out_debug/website-e2e/round1` and verify only task 005 Judge failure remains.
- [ ] Generate a new Excel report from round1 and verify the overview reports one evaluation anomaly.
- [ ] Run report audit and record that publication remains blocked until task 005 is re-judged.
