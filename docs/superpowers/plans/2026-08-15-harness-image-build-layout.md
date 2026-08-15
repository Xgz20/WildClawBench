# Harness Image Build Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move AstronCode and Codex canonical image build entry points beside their Docker definitions and enforce a deterministic version-directory-to-image-tag mapping.

**Architecture:** Each Harness owns one `build.sh` and one `versions.json`. Each image generation gets one new `v1`/`v2` Docker context beside the Harness; legacy scripts remain thin wrappers so existing commands keep working while tests and current docs use the canonical paths.

**Tech Stack:** Bash, Docker CLI, JSON, Python `unittest`/`pytest` static contract tests.

---

### Task 1: Add failing build-layout contracts

**Files:**
- Modify: `tests/test_astroncode_v4_image.py`
- Modify: `tests/test_codex_upgrade_image.py`

- [ ] Change canonical script constants to `docker/astroncode/build.sh` and `docker/codex/build.sh`.
- [ ] Add assertions for executable canonical scripts, `versions.json`, version-directory Dockerfile paths, full image references and default versions.
- [ ] Add wrapper assertions that `script/build-*-image.sh` contains only repository resolution plus `exec` to the canonical script.
- [ ] Add CLI/Docker-stub cases for default version, explicit known version, unknown version, legacy AstronCode mapping and `SKIP_SAVE=1`.
- [ ] Run:

```bash
uv run --with pytest pytest -q tests/test_astroncode_v4_image.py tests/test_codex_upgrade_image.py
```

Expected: fail because the canonical scripts, manifests and required version paths do not exist yet.

### Task 2: Add AstronCode version mapping and canonical builder

**Files:**
- Create: `docker/astroncode/build.sh`
- Create: `docker/astroncode/versions.json`
- Reuse: `docker/astroncode/v1/Dockerfile`
- Reuse: `docker/astroncode/v2/Dockerfile`
- Reuse: `docker/astroncode/v3/Dockerfile`
- Reuse: `docker/astroncode/v4/Dockerfile` and `verify_search_agent.py`
- Modify: `script/build-astroncode-image.sh`

- [ ] Map each official image tag directly to the corresponding existing version context.
- [ ] Define full image refs and pinned/default build args in `versions.json`.
- [ ] Implement `build.sh --version <key>` with deterministic manifest lookup, path validation, proxy propagation, version checks and optional offline export.
- [ ] Translate legacy `ASTRONCODE_DOCKER_VARIANT`/`IMAGE_TAG` combinations in the old wrapper; reject mismatches instead of constructing arbitrary tags.
- [ ] Run the AstronCode focused tests and confirm all cases pass.

### Task 3: Add Codex version mapping and canonical builder

**Files:**
- Create: `docker/codex/build.sh`
- Create: `docker/codex/versions.json`
- Move: `docker/codex/Dockerfile` to `docker/codex/v1/Dockerfile`
- Modify: `script/build-codex-image.sh`

- [ ] Register `docker/codex/v1` as `wildclawbench-codex-ubuntu:v0.1` with `CODEX_VERSION=0.146.0`.
- [ ] Implement deterministic version selection, self-referential base-image rejection, installed-version reporting and `SKIP_SAVE=1`.
- [ ] Replace the old root script with an environment-compatible `exec` wrapper.
- [ ] Run the Codex focused tests and confirm all cases pass.

### Task 4: Synchronize current documentation and verify regressions

**Files:**
- Modify: `docker/astroncode/AstronCode镜像更新日志.md`
- Modify: `docker/codex/Codex镜像更新日志.md`
- Modify: `src/agents/codex/runner.py`
- Modify: current tests from Tasks 1-3

- [ ] Update current commands and related-implementation paths to the canonical builders.
- [ ] Retain legacy wrapper examples only in the compatibility section; do not rewrite historical specs/plans.
- [ ] Run syntax checks:

```bash
bash -n docker/astroncode/build.sh docker/codex/build.sh \
  script/build-astroncode-image.sh script/build-codex-image.sh
```

- [ ] Run focused tests:

```bash
uv run --with pytest pytest -q tests/test_astroncode_v4_image.py tests/test_codex_upgrade_image.py
```

- [ ] Run related image contract tests and whitespace validation:

```bash
uv run --with pytest pytest -q tests/test_astroncode_ppt_image.py tests/test_astroncode_v3_image.py \
  tests/test_astroncode_v4_image.py tests/test_codex_upgrade_image.py
git diff --check
```

- [ ] Review `git status --short`; leave all changes uncommitted until the user explicitly requests a commit.
