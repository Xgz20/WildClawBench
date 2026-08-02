# AstronCode Trace Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 默认采集 AstronCode 0.0.13 的 Codex rollout trace，并在每个 WildClawBench run 中导出单个安全权限的 `astroncode_traces.tar.gz`。

**Architecture:** `AstronCodeAgent` 构造时快照默认开启的 `ASTRONCODE_TRACE_ENABLED`，开启时把固定容器路径映射到原生 `CODEX_ROLLOUT_TRACE_ROOT`。评测结束、容器清理前，独立私有方法在容器内压缩整个 trace 根目录、复制单个归档到 run 目录，并以结构化状态记录成功、关闭或非阻断失败。

**Tech Stack:** Python 3、`unittest`、Docker CLI、POSIX `tar`、JSON、Markdown

---

## File Structure

- Create: `tests/test_astroncode_trace.py` - 覆盖开关解析、容器环境注入、归档命令、状态记录和非阻断失败。
- Modify: `src/agents/astroncode/runner.py` - 增加 trace 配置、容器注入、目录准备、压缩复制和状态写入。
- Modify: `.env.example` - 记录默认开启和显式关闭方式。
- Modify: `docker/astroncode/v3/AstronCode-日志集成.md` - 记录 WildClawBench 归档行为、查看方式和敏感信息风险。
- Modify: `docs/local/guide/linux-评测命令速查.md` - 说明现有 AstronCode 命令默认采集 trace，不向命令重复加入开关。
- Modify: `docs/local/guide/macos-本地调试指南.md` - 说明本地 AstronCode 命令默认采集 trace 及关闭方式。

### Task 1: Trace 开关解析与容器注入

**Files:**
- Create: `tests/test_astroncode_trace.py`
- Modify: `src/agents/astroncode/runner.py`

- [ ] **Step 1: Write failing switch parsing tests**

创建 `tests/test_astroncode_trace.py`，先定义 Agent 工厂并覆盖默认、真值、假值和非法值：

```python
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.astroncode.runner import AstronCodeAgent


class AstronCodeTraceTests(unittest.TestCase):
    def make_agent(self) -> AstronCodeAgent:
        return AstronCodeAgent(
            openrouter_api_key="openrouter-key",
            openrouter_base_url="https://openrouter.example/api/v1",
        )

    def test_trace_is_enabled_by_default_and_for_true_values(self) -> None:
        for value in (None, "", "1", "true", "TRUE", "yes", "on"):
            environment = {}
            if value is not None:
                environment["ASTRONCODE_TRACE_ENABLED"] = value
            with self.subTest(value=value), patch.dict(
                os.environ,
                environment,
                clear=True,
            ):
                self.assertIs(
                    getattr(self.make_agent(), "trace_enabled", None),
                    True,
                )

    def test_trace_can_be_explicitly_disabled(self) -> None:
        for value in ("0", "false", "FALSE", "no", "off"):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {"ASTRONCODE_TRACE_ENABLED": value},
                clear=True,
            ):
                self.assertIs(
                    getattr(self.make_agent(), "trace_enabled", None),
                    False,
                )

    def test_invalid_trace_flag_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_TRACE_ENABLED": "sometimes"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "ASTRONCODE_TRACE_ENABLED.*1.*0",
            ):
                self.make_agent()
```

- [ ] **Step 2: Run switch tests to verify RED**

Run:

```bash
uv run python -m unittest tests.test_astroncode_trace -v
```

Expected: assertions FAIL because `trace_enabled` does not exist and invalid values are not rejected.

- [ ] **Step 3: Implement strict default-on parsing**

在 `src/agents/astroncode/runner.py` 常量区增加：

```python
ASTRONCODE_TRACE_ROOT = "/tmp/rollout-traces"
ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH = "/tmp/astroncode_traces.tar.gz"
ASTRONCODE_TRACE_ARCHIVE_NAME = "astroncode_traces.tar.gz"
ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS = 300
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}
```

增加模块级解析函数：

```python
def parse_env_flag(name: str, *, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_ENV_VALUES:
        return True
    if normalized in _FALSE_ENV_VALUES:
        return False
    raise ValueError(
        f"{name} must be one of: 1, true, yes, on, 0, false, no, off"
    )
```

在 `AstronCodeAgent.__init__()` 中快照开关：

```python
self.trace_enabled = parse_env_flag(
    "ASTRONCODE_TRACE_ENABLED",
    default=True,
)
```

- [ ] **Step 4: Run switch tests to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_astroncode_trace -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Write failing container injection tests**

先将测试文件的 runner 导入改为：

```python
from src.agents.astroncode.runner import (
    ASTRONCODE_TRACE_ROOT,
    AstronCodeAgent,
)
```

再在同一测试类增加辅助方法和三个测试：

```python
    def start_container_command(self, trace_value: str | None) -> list[str]:
        environment = {}
        if trace_value is not None:
            environment["ASTRONCODE_TRACE_ENABLED"] = trace_value
        with patch.dict(os.environ, environment, clear=True), patch(
            "src.agents.astroncode.runner.subprocess.run"
        ) as run_mock, tempfile.TemporaryDirectory() as temp_dir:
            run_mock.return_value = subprocess.CompletedProcess(
                [], 0, "container-id", ""
            )
            (Path(temp_dir) / "exec").mkdir()
            self.make_agent()._start_container(
                "trace-env-test",
                temp_dir,
                {},
                None,
            )
            return run_mock.call_args.args[0]

    def test_default_trace_injects_codex_rollout_root(self) -> None:
        command = self.start_container_command(None)
        trace_env_index = command.index("CODEX_ROLLOUT_TRACE_ROOT")
        self.assertEqual(command[trace_env_index - 1], "-e")

    def test_disabled_trace_does_not_inject_codex_rollout_root(self) -> None:
        command = self.start_container_command("0")
        self.assertNotIn("CODEX_ROLLOUT_TRACE_ROOT", command)

    def test_workspace_prepares_trace_root_only_when_enabled(self) -> None:
        for value, expected in ((None, True), ("0", False)):
            environment = {}
            if value is not None:
                environment["ASTRONCODE_TRACE_ENABLED"] = value
            with self.subTest(value=value), patch.dict(
                os.environ,
                environment,
                clear=True,
            ), patch(
                "src.agents.astroncode.runner.subprocess.run"
            ) as run_mock, tempfile.TemporaryDirectory() as temp_dir:
                run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
                self.make_agent()._prepare_workspace("trace-root-test", temp_dir)
                prepare_command = run_mock.call_args.args[0][-1]
                self.assertEqual(
                    ASTRONCODE_TRACE_ROOT in prepare_command,
                    expected,
                )
```

- [ ] **Step 6: Run injection tests to verify RED**

Run:

```bash
uv run python -m unittest \
  tests.test_astroncode_trace.AstronCodeTraceTests.test_default_trace_injects_codex_rollout_root \
  tests.test_astroncode_trace.AstronCodeTraceTests.test_disabled_trace_does_not_inject_codex_rollout_root \
  tests.test_astroncode_trace.AstronCodeTraceTests.test_workspace_prepares_trace_root_only_when_enabled -v
```

Expected: default-on test FAIL because the Docker command lacks `CODEX_ROLLOUT_TRACE_ROOT`.

- [ ] **Step 7: Inject the native trace root and prepare its directory**

在 `_start_container()` 的 `env_map` 增加：

```python
"CODEX_ROLLOUT_TRACE_ROOT": (
    ASTRONCODE_TRACE_ROOT if self.trace_enabled else ""
),
```

在 `_prepare_workspace()` 构建命令前计算：

```python
trace_directory_command = (
    f"&& mkdir -p {shlex.quote(ASTRONCODE_TRACE_ROOT)} "
    if self.trace_enabled
    else ""
)
```

并将其加入现有 `mkdir/cp/chmod` shell 命令，确保 trace 开启时固定目录存在，关闭时不创建。

- [ ] **Step 8: Run all trace tests to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_astroncode_trace -v
```

Expected: 6 tests PASS.

- [ ] **Step 9: Commit trace activation**

```bash
git add src/agents/astroncode/runner.py tests/test_astroncode_trace.py
git commit -m "feat(astroncode): 默认启用 rollout trace"
```

### Task 2: 单文件归档与非阻断状态记录

**Files:**
- Modify: `tests/test_astroncode_trace.py`
- Modify: `src/agents/astroncode/runner.py`

- [ ] **Step 1: Write failing successful-export test**

在测试文件中增加 JSON 导入、Docker mock 和成功断言：

```python
import json

    def test_trace_export_copies_one_archive_and_records_count(self) -> None:
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            agent = self.make_agent()

            def fake_run(command, **kwargs):
                if command[:2] == ["docker", "exec"]:
                    self.assertIn("tar -C /tmp", command[-1])
                    self.assertIn("rollout-traces", command[-1])
                    return subprocess.CompletedProcess(command, 0, "3", "")
                if command[:2] == ["docker", "cp"]:
                    Path(command[-1]).write_bytes(b"tar-gzip-content")
                    return subprocess.CompletedProcess(command, 0, "", "")
                self.fail(f"unexpected command: {command}")

            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=fake_run,
            ):
                agent._collect_rollout_trace_archive("trace-task", output_dir)

            archive = output_dir / "astroncode_traces.tar.gz"
            self.assertTrue(archive.is_file())
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                status["trace_export"],
                {
                    "enabled": True,
                    "status": "exported",
                    "archive": "astroncode_traces.tar.gz",
                    "trace_count": 3,
                    "error": None,
                },
            )
            event = json.loads(
                (output_dir / "agent.log").read_text(encoding="utf-8").splitlines()[-1]
            )
            self.assertEqual(event["type"], "runner.trace_export")
            self.assertEqual(event["status"], "exported")
```

- [ ] **Step 2: Run successful-export test to verify RED**

Run:

```bash
uv run python -m unittest \
  tests.test_astroncode_trace.AstronCodeTraceTests.test_trace_export_copies_one_archive_and_records_count -v
```

Expected: FAIL because `_collect_rollout_trace_archive` does not exist.

- [ ] **Step 3: Implement archive command and structured recording**

在 runner 中增加结果记录方法：

```python
    @staticmethod
    def _record_trace_export(output_dir: Path, result: dict[str, Any]) -> None:
        write_execution_status(output_dir, trace_export=result)
        append_agent_log_event(
            output_dir,
            {"type": "runner.trace_export", **result},
        )

    @staticmethod
    def _remove_partial_trace_archive(archive_path: Path) -> None:
        try:
            archive_path.unlink(missing_ok=True)
        except OSError:
            pass
```

增加非抛出归档方法：

```python
    def _collect_rollout_trace_archive(
        self,
        task_id: str,
        output_dir: Path,
    ) -> None:
        archive_path = output_dir / ASTRONCODE_TRACE_ARCHIVE_NAME
        if not self.trace_enabled:
            self._record_trace_export(
                output_dir,
                {
                    "enabled": False,
                    "status": "disabled",
                    "archive": None,
                    "trace_count": 0,
                    "error": None,
                },
            )
            return

        self._remove_partial_trace_archive(archive_path)
        trace_root_name = Path(ASTRONCODE_TRACE_ROOT).name
        trace_root_parent = str(Path(ASTRONCODE_TRACE_ROOT).parent)
        archive_command = (
            "umask 077; "
            f"mkdir -p {shlex.quote(ASTRONCODE_TRACE_ROOT)}; "
            "trace_count=$(find "
            f"{shlex.quote(ASTRONCODE_TRACE_ROOT)} "
            "-mindepth 1 -maxdepth 1 -type d -name 'trace-*' "
            "2>/dev/null | wc -l); "
            f"rm -f {shlex.quote(ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH)}; "
            f"tar -C {shlex.quote(trace_root_parent)} -czf "
            f"{shlex.quote(ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH)} "
            f"{shlex.quote(trace_root_name)}; "
            'printf "%s" "$trace_count"'
        )

        try:
            archived = subprocess.run(
                ["docker", "exec", task_id, "/bin/sh", "-c", archive_command],
                capture_output=True,
                text=True,
                timeout=ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS,
            )
            if archived.returncode != 0:
                raise RuntimeError(
                    "archive command failed: " + (archived.stderr or "").strip()[:1000]
                )
            copied = subprocess.run(
                [
                    "docker",
                    "cp",
                    f"{task_id}:{ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH}",
                    str(archive_path),
                ],
                capture_output=True,
                text=True,
                timeout=ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS,
            )
            if copied.returncode != 0:
                raise RuntimeError(
                    "archive copy failed: " + (copied.stderr or "").strip()[:1000]
                )
            archive_path.chmod(0o600)
            result = {
                "enabled": True,
                "status": "exported",
                "archive": ASTRONCODE_TRACE_ARCHIVE_NAME,
                "trace_count": int((archived.stdout or "0").strip() or "0"),
                "error": None,
            }
            self._record_trace_export(output_dir, result)
            logger.info(
                "[%s] AstronCode trace archive exported (%d traces): %s",
                task_id,
                result["trace_count"],
                archive_path,
            )
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            self._remove_partial_trace_archive(archive_path)
            error = str(exc)[:1000]
            self._record_trace_export(
                output_dir,
                {
                    "enabled": True,
                    "status": "failed",
                    "archive": None,
                    "trace_count": 0,
                    "error": error,
                },
            )
            logger.warning("[%s] AstronCode trace export failed: %s", task_id, error)
```

- [ ] **Step 4: Write a failing collect-usage integration test**

增加测试，证明现有清理前采集入口会调用 trace 导出：

```python
    def test_collect_usage_triggers_trace_export(self) -> None:
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            agent = self.make_agent()
            usage = {
                "input_tokens": 1,
                "output_tokens": 1,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_tokens": 2,
                "cost_usd": 1.0,
                "request_count": 1,
            }
            with patch.object(
                agent,
                "_collect_rollout_trace_archive",
            ) as export_mock, patch.object(
                agent,
                "_copy_dir_from_container",
            ), patch.object(
                agent,
                "_find_latest_session",
                return_value=None,
            ), patch.object(
                agent,
                "_extract_usage_from_jsonl",
                return_value=usage,
            ):
                agent.collect_usage("trace-usage", Path(temp_dir), 1.0)
            export_mock.assert_called_once_with("trace-usage", Path(temp_dir))
```

Run:

```bash
uv run python -m unittest \
  tests.test_astroncode_trace.AstronCodeTraceTests.test_collect_usage_triggers_trace_export -v
```

Expected: FAIL because `collect_usage()` does not call the trace exporter.

- [ ] **Step 5: Call trace export before usage parsing**

在 `collect_usage()` 创建 `output_dir` 后立即加入：

```python
self._collect_rollout_trace_archive(task_id, output_dir)
```

该调用保持在 `eval/run_batch.py` 删除容器之前，并适用于成功、执行错误和超时路径。

- [ ] **Step 6: Run successful-export and integration tests to verify GREEN**

Run:

```bash
uv run python -m unittest \
  tests.test_astroncode_trace.AstronCodeTraceTests.test_trace_export_copies_one_archive_and_records_count \
  tests.test_astroncode_trace.AstronCodeTraceTests.test_collect_usage_triggers_trace_export -v
```

Expected: PASS.

- [ ] **Step 7: Write disabled, empty and failure tests**

增加以下测试，验证关闭不调用 Docker、空目录仍导出，以及失败不抛异常：

```python
    def test_disabled_trace_records_status_without_archive(self) -> None:
        with patch.dict(
            os.environ,
            {"ASTRONCODE_TRACE_ENABLED": "0"},
            clear=True,
        ), patch(
            "src.agents.astroncode.runner.subprocess.run"
        ) as run_mock, tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            self.make_agent()._collect_rollout_trace_archive(
                "disabled-trace",
                output_dir,
            )
            run_mock.assert_not_called()
            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["trace_export"]["status"], "disabled")
            self.assertFalse((output_dir / "astroncode_traces.tar.gz").exists())

    def test_empty_trace_root_still_exports_archive(self) -> None:
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_run(command, **kwargs):
                if command[:2] == ["docker", "exec"]:
                    return subprocess.CompletedProcess(command, 0, "0", "")
                Path(command[-1]).write_bytes(b"empty-root-archive")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=fake_run,
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "empty-trace",
                    output_dir,
                )
            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["trace_export"]["status"], "exported")
            self.assertEqual(status["trace_export"]["trace_count"], 0)

    def test_trace_archive_failure_is_non_blocking_and_removes_partial_file(self) -> None:
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            archive = output_dir / "astroncode_traces.tar.gz"
            archive.write_bytes(b"partial")
            failed = subprocess.CompletedProcess([], 1, "", "disk full")
            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                return_value=failed,
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "failed-trace",
                    output_dir,
                )
            self.assertFalse(archive.exists())
            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["trace_export"]["status"], "failed")
            self.assertIn("archive command failed", status["trace_export"]["error"])

    def test_trace_copy_failure_is_non_blocking(self) -> None:
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            results = (
                subprocess.CompletedProcess([], 0, "1", ""),
                subprocess.CompletedProcess([], 1, "", "copy denied"),
            )
            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=results,
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "copy-failed-trace",
                    output_dir,
                )
            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["trace_export"]["status"], "failed")
            self.assertIn("archive copy failed", status["trace_export"]["error"])

    def test_trace_chmod_failure_is_non_blocking(self) -> None:
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_run(command, **kwargs):
                if command[:2] == ["docker", "exec"]:
                    return subprocess.CompletedProcess(command, 0, "1", "")
                Path(command[-1]).write_bytes(b"archive")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.astroncode.runner.subprocess.run",
                side_effect=fake_run,
            ), patch.object(
                Path,
                "chmod",
                side_effect=PermissionError("chmod denied"),
            ):
                self.make_agent()._collect_rollout_trace_archive(
                    "chmod-failed-trace",
                    output_dir,
                )
            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["trace_export"]["status"], "failed")
            self.assertIn("chmod denied", status["trace_export"]["error"])
```

- [ ] **Step 8: Run all trace tests to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_astroncode_trace -v
```

Expected: 13 tests PASS.

- [ ] **Step 9: Run existing AstronCode regression tests**

Run:

```bash
uv run python -m unittest \
  tests.test_astroncode_config \
  tests.test_astroncode_v3_image \
  tests.test_astroncode_trace -v
```

Expected: existing tests and 13 trace tests all PASS.

- [ ] **Step 10: Commit trace archive export**

```bash
git add src/agents/astroncode/runner.py tests/test_astroncode_trace.py
git commit -m "feat(astroncode): 归档导出 rollout trace"
```

### Task 3: Trace 使用与安全文档

**Files:**
- Modify: `.env.example`
- Modify: `docker/astroncode/v3/AstronCode-日志集成.md`
- Modify: `docs/local/guide/linux-评测命令速查.md`
- Modify: `docs/local/guide/macos-本地调试指南.md`

- [ ] **Step 1: Document the default-on environment contract**

在 `.env.example` 的 AstronCode 配置区增加：

```dotenv
# AstronCode rollout trace is enabled by default; set to 0 to disable export.
ASTRONCODE_TRACE_ENABLED=true
```

- [ ] **Step 2: Document archive layout and inspection commands**

在 `docker/astroncode/v3/AstronCode-日志集成.md` 增加 WildClawBench Harness 章节，明确：

````markdown
## WildClawBench Harness 采集行为

AstronCode Harness 默认开启 rollout trace。评测命令无需显式设置
`ASTRONCODE_TRACE_ENABLED`；如需关闭，设置：

```bash
ASTRONCODE_TRACE_ENABLED=0
```

每个评测 run 将全部 `trace-*` 压缩为结果目录中的单个文件：

```text
astroncode_traces.tar.gz
```

列出归档内容：

```bash
tar -tzf astroncode_traces.tar.gz
```

解压到独立目录：

```bash
mkdir -p astroncode_traces
tar -xzf astroncode_traces.tar.gz -C astroncode_traces
```

归档内保留 `rollout-traces/trace-*/manifest.json`、`trace.jsonl` 和
`payloads/`。Trace 包含完整模型请求、响应、工具参数和命令输出，应按敏感评测
数据管理，不应上传到公开仓库或发送给无权限人员。
````

- [ ] **Step 3: Update local command guide notes without changing commands**

在 Linux 和 macOS 指南的 AstronCode 章节开头分别加入同一条说明：

```markdown
> AstronCode rollout trace 默认开启。现有命令无需增加开关，每个 run 会生成
> `astroncode_traces.tar.gz`；临时关闭可在命令环境变量中加入
> `ASTRONCODE_TRACE_ENABLED=0`。
```

不要把 `ASTRONCODE_TRACE_ENABLED=true` 重复加入每个模型命令。

- [ ] **Step 4: Check documentation diffs**

Run:

```bash
git diff --check -- \
  .env.example \
  docker/astroncode/v3/AstronCode-日志集成.md \
  docs/local/guide/linux-评测命令速查.md \
  docs/local/guide/macos-本地调试指南.md
rg -n "ASTRONCODE_TRACE_ENABLED|astroncode_traces.tar.gz" \
  .env.example \
  docker/astroncode/v3/AstronCode-日志集成.md \
  docs/local/guide/linux-评测命令速查.md \
  docs/local/guide/macos-本地调试指南.md
```

Expected: no whitespace errors; all four documents state the same default-on behavior, and existing commands remain free of repeated enable flags.

- [ ] **Step 5: Commit tracked documentation**

```bash
git add .env.example docker/astroncode/v3/AstronCode-日志集成.md
git commit -m "docs(astroncode): 补充 trace 归档使用说明"
```

`docs/local/` is intentionally ignored in this repository. Keep those two local guide updates in place without forcing them into Git.

### Task 4: Regression and real smoke verification

**Files:**
- Test: `tests/test_astroncode_trace.py`
- Test: `tests/test_astroncode_config.py`
- Test: `tests/test_astroncode_v3_image.py`
- Verify: one new run under the configured `OUTPUT_SUBDIR`

- [ ] **Step 1: Run syntax and complete focused regression checks**

Run:

```bash
git diff --check
uv run python -m compileall -q \
  src/agents/astroncode \
  tests/test_astroncode_trace.py
uv run python -m unittest \
  tests.test_astroncode_trace \
  tests.test_astroncode_config \
  tests.test_astroncode_v3_image -v
```

Expected: all commands return 0 and all focused tests PASS.

- [ ] **Step 2: Run one default-on AstronCode 0.0.13 smoke case**

Use the existing foreground command from `docs/local/guide/macos-本地调试指南.md` for:

```text
tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md
```

Keep `DOCKER_IMAGE_ASTRONCODE=wildclawbench-astroncode-ubuntu:v0.3`. Do not add `ASTRONCODE_TRACE_ENABLED`; this verifies the default-on contract.

Expected: run finishes or reaches its normal grading path, and its result directory contains `astroncode_traces.tar.gz`.

- [ ] **Step 3: Validate the real archive and trace status**

From the new run directory execute:

```bash
test -f astroncode_traces.tar.gz
test "$(find . -maxdepth 1 -type f -name '*trace*' | wc -l | tr -d ' ')" = "1"
tar -tzf astroncode_traces.tar.gz | rg \
  '^rollout-traces/trace-[^/]+/(manifest\.json|trace\.jsonl)$'
uv run python -c '
import json
from pathlib import Path
status = json.loads(Path("execution_status.json").read_text())
trace = status["trace_export"]
assert trace["enabled"] is True
assert trace["status"] == "exported"
assert trace["archive"] == "astroncode_traces.tar.gz"
assert trace["trace_count"] >= 1
'
```

Expected: all commands return 0; one archive contains at least one trace manifest and JSONL; status reports `exported`.

- [ ] **Step 4: Verify explicit disable without a model call**

Run the unit-level disabled test again rather than spending another model request:

```bash
uv run python -m unittest \
  tests.test_astroncode_trace.AstronCodeTraceTests.test_disabled_trace_records_status_without_archive -v
```

Expected: PASS, no Docker archive command is issued, and status is `disabled`.

- [ ] **Step 5: Inspect final repository state**

Run:

```bash
git log -5 --oneline
git status --short
git diff --check
```

Expected: trace code and tracked documentation are committed; ignored local guides contain the documented note; pre-existing unrelated untracked files remain untouched.
