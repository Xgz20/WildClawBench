# Web 站点评测动态检查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `web-site-gen` 任务增加可重复的 Playwright 动态检查，并将内容/交互确定性证据与视觉 LLM Judge 证据按现有 Rubric key 合并评分。

**Architecture:** `eval/checks/website/runner.py` 在评分容器内负责构建、启动、浏览器隔离、审计和清理；每个任务脚本只实现该题的操作序列和断言，返回 canonical criterion key。`src/utils/grading.py` 仅对 `web-site-gen` 启用动态检查，内容/交互项使用脚本结果，视觉项保留截图给 Judge；非 Web v2 和 legacy 任务继续走原有路径。

**Tech Stack:** Python 3、Python Playwright、Chromium、Vite/npm、现有 `judge_shim`/OpenAI-compatible Judge、JSON 审计文件。

---

### Task 1: 固化 Web 动态检查协议

**Files:**
- Create: `src/utils/website_checks.py`
- Modify: `src/utils/grading.py`
- Test: `tests/test_website_dynamic_grading.py`

- [x] **Step 1: Write failing contract tests** for task routing, result shape, mixed evidence merge, and non-Web compatibility.
- [x] **Step 2: Run `uv run python -m pytest tests/test_website_dynamic_grading.py -q`** and confirm failure because no Web checker API exists.
- [x] **Step 3: Implement `run_website_checks(...)` and `merge_website_evidence(...)`** with strict canonical keys, `score` in `[0, 1]`, `evidence_mode`, and explicit infrastructure errors.
- [x] **Step 4: Add the Web branch to `_run_grading_v2`**. It runs dynamic checks before the visual Judge, passes screenshot manifest to the Judge, and computes all criterion scores with original weights.
- [x] **Step 5: Run focused tests and existing grading/parser tests.**

### Task 2: Implement container-side Playwright runner

**Files:**
- Create: `eval/checks/website/runner.py`
- Create: `eval/checks/website/common.py`
- Test: `tests/test_website_check_runner.py`

- [x] **Step 1: Write failing unit tests** for command construction, fixed viewport, clean context, localhost network policy, result/audit files, and process cleanup.
- [x] **Step 2: Run focused tests and observe expected missing-module failures.**
- [x] **Step 3: Implement build/start lifecycle:** `npm install` only when needed, `npm run build`, `npm run start -- --host 127.0.0.1 --port 4173`, readiness polling, timeout/error tags.
- [x] **Step 4: Implement browser lifecycle:** Python Playwright Chromium, 1440x900 context, storage reset, console/network/page errors, screenshot and trace capture, guaranteed `finally` cleanup.
- [x] **Step 5: Implement JSON output:** `{task_id, checks, screenshots, errors, status}` to `.grading/website/summary.json`, with one result per criterion key.

### Task 3: Add eleven task-specific check scripts

**Files:**
- Create: `eval/checks/website/tasks/task_001_daymark_product_website.py`
- Create: `eval/checks/website/tasks/task_002_focus_pomodoro_clock.py`
- Create: `eval/checks/website/tasks/task_003_chengnan_weekend_activity_discovery.py`
- Create: `eval/checks/website/tasks/task_004_orchard_memory_game.py`
- Create: `eval/checks/website/tasks/task_005_xiaoman_ledger_dashboard.py`
- Create: `eval/checks/website/tasks/task_006_xingji_travel_planner.py`
- Create: `eval/checks/website/tasks/task_007_neon_snake_game.py`
- Create: `eval/checks/website/tasks/task_008_shiguang_personal_blog.py`
- Create: `eval/checks/website/tasks/task_009_smart_teaching_dashboard.py`
- Create: `eval/checks/website/tasks/task_010_paperwork_pdf_tool.py`
- Create: `eval/checks/website/tasks/task_011_love_anniversary_site.py`
- Test: `tests/test_website_task_checks.py`

- [x] **Step 1: Write contract tests** that every script exports `run(page)`, covers every non-visual criterion key, and uses semantic locators before stable attributes.
- [x] **Step 2: Run the tests and confirm missing scripts/coverage.**
- [x] **Step 3: Implement task 001-004 checks** for content, navigation, forms, filtering, timers, and memory-game transitions; use deterministic assertions and avoid arbitrary sleeps where state assertions are possible.
- [x] **Step 4: Implement task 005 checks** with isolated local storage and explicit stateful phases for period switching, CRUD, filtering, analysis linkage, and refresh persistence.
- [x] **Step 5: Run parser, task-contract, and script-contract tests.**

### Task 4: Add visual evidence and report compatibility

**Files:**
- Modify: `src/utils/grading.py`
- Modify: `src/utils/judge_audit.py`
- Modify: `tests/test_website_dynamic_grading.py`
- Modify: `tests/test_judge_audit.py`

- [x] **Step 1: Write failing tests** for screenshot manifest in Judge request, `judge/attempt-*` audit persistence, and `_dimensions.evidence_mode`.
- [x] **Step 2: Implement screenshot selection** for visual criteria using stable key evidence and bounded PNG sizes; keep no visual criterion for `美观度` unless declared in the Rubric.
- [x] **Step 3: Extend Judge prompt** so the website path distinguishes runtime evidence from visual review and does not claim unsupported checks.
- [x] **Step 4: Verify report readers continue to consume `llm_judge.<key>`, `automated.<key>`, `overall_score`, and `_dimensions` without changes; add compatibility assertions.
- [x] **Step 5: Run the complete focused suite.**

### Task 5: Container smoke validation and documentation

**Files:**
- Create: `docs/superpowers/specs/2026-08-13-website-playwright-dynamic-evaluation.md`
- Modify: `docs/local/guide/macos-本地调试指南.md`
- Test: `tests/test_website_dynamic_grading.py`

- [x] **Step 1: Document the Web task contract:** semantic HTML/accessibility names, local-only data, deterministic states, and no evaluator code in `/tmp_workspace`.
- [x] **Step 2: Run a real smoke task in `wildclawbench-astroncode-ubuntu:v0.4-ppt`** with the Web profile and capture build/start/browser/Judge artifacts.
- [ ] **Step 3: Run the eleven-task Web batch if the smoke passes.**
- [x] **Step 4: Confirm non-Web regression tests pass and inspect generated `score.json`, `website/summary.json`, screenshots, traces, and Judge audit.
- [ ] **Step 5: Commit only related implementation and docs with a Chinese Conventional Commit title.**
