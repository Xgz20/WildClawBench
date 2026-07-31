# OpenCode Thinking Variant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 WildClawBench 的 `--thinking high` 在 OpenCode Harness 中转换为原生 `opencode run --variant high`。

**Architecture:** 保持通用 `AgentTaskSpec.thinking` 契约不变，在 `OpenCodeAgent` 内沿 `run_task -> _run_prompt -> _run_opencode_exec -> _build_exec_command` 传递可空字符串。只有命令构造函数负责将非空值安全转义为 `--variant` 参数，未指定时继续使用模型默认值。

**Tech Stack:** Python 3、`unittest`、`unittest.mock`、OpenCode CLI、Docker runner

---

### Task 1: 构造 OpenCode variant 参数

**Files:**
- Create: `tests/test_opencode_runner.py`
- Modify: `src/agents/opencode/runner.py:537-547`

- [ ] **Step 1: 编写命令构造失败测试**

```python
from __future__ import annotations

import inspect
import unittest

from src.agents.opencode.runner import OpenCodeAgent


class OpenCodeRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = OpenCodeAgent(
            openrouter_api_key="test-key",
            openrouter_base_url="https://openrouter.example/api/v1",
        )

    def test_build_exec_command_maps_thinking_to_variant(self) -> None:
        parameters = inspect.signature(
            self.agent._build_exec_command
        ).parameters
        self.assertIn("thinking", parameters)

        command = self.agent._build_exec_command(
            model="openrouter/gpt-5.5",
            prompt_path="/tmp/prompt.txt",
            config_content="{}",
            thinking="high",
        )

        self.assertIn("--variant high", command)
        self.assertNotIn(" --thinking", command)

    def test_build_exec_command_omits_empty_variant(self) -> None:
        for thinking in (None, "", "   "):
            with self.subTest(thinking=thinking):
                command = self.agent._build_exec_command(
                    model="openrouter/gpt-5.5",
                    prompt_path="/tmp/prompt.txt",
                    config_content="{}",
                    thinking=thinking,
                )
                self.assertNotIn("--variant", command)

    def test_build_exec_command_shell_quotes_variant(self) -> None:
        command = self.agent._build_exec_command(
            model="openrouter/gpt-5.5",
            prompt_path="/tmp/prompt.txt",
            config_content="{}",
            thinking="high; echo injected",
        )

        self.assertIn("--variant 'high; echo injected'", command)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认正确失败**

Run:

```bash
uv run python -m unittest discover -s tests -p 'test_opencode_runner.py' -v
```

Expected: FAIL，`test_build_exec_command_maps_thinking_to_variant` 报告现有签名缺少 `thinking`。

- [ ] **Step 3: 实现最小命令映射**

将 `_build_exec_command()` 改为：

```python
def _build_exec_command(
    self,
    model: str,
    prompt_path: str,
    config_content: str,
    thinking: str | None = None,
) -> str:
    model_arg = self._model_arg(model)
    normalized_thinking = thinking.strip() if thinking else ""
    variant_arg = (
        f" --variant {shlex.quote(normalized_thinking)}"
        if normalized_thinking
        else ""
    )
    return (
        f"export OPENCODE_CONFIG_CONTENT={shlex.quote(config_content)} && "
        "cd /tmp_workspace && "
        f"opencode run \"$(cat {shlex.quote(prompt_path)})\" "
        f"--model {shlex.quote(model_arg)}{variant_arg} "
        "--format json --yolo --print-logs"
    )
```

- [ ] **Step 4: 运行测试并确认通过**

Run:

```bash
uv run python -m unittest discover -s tests -p 'test_opencode_runner.py' -v
```

Expected: 3 tests PASS。

- [ ] **Step 5: 提交命令构造变更**

```bash
git add tests/test_opencode_runner.py src/agents/opencode/runner.py
git commit -m "feat(opencode): 支持构造推理强度参数"
```

### Task 2: 贯通 AgentTaskSpec.thinking

**Files:**
- Modify: `tests/test_opencode_runner.py`
- Modify: `src/agents/opencode/runner.py:136-198,506-558`

- [ ] **Step 1: 编写调用链失败测试**

向 `tests/test_opencode_runner.py` 增加依赖：

```python
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.agents.base import AgentTaskSpec
```

向 `OpenCodeRunnerTests` 增加：

```python
def test_run_task_forwards_thinking_to_prompt_runner(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp) / "output"
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        spec = AgentTaskSpec(
            task_id="opencode-thinking-test",
            task={},
            workspace_path=str(workspace),
            prompt="test prompt",
            timeout_seconds=30,
            output_dir=output_dir,
            model="openrouter/gpt-5.5",
            thinking="high",
        )
        with (
            patch.object(self.agent, "_start_container"),
            patch.object(
                self.agent,
                "_probe_harness_version",
                return_value="test",
            ),
            patch.object(self.agent, "_prepare_workspace"),
            patch("src.agents.opencode.runner.setup_skills"),
            patch(
                "src.agents.opencode.runner.load_skill_documents",
                return_value=[],
            ),
            patch("src.agents.opencode.runner.run_warmup"),
            patch.object(
                self.agent,
                "_should_enable_image_helper",
                return_value=False,
            ),
            patch("src.agents.opencode.runner.snapshot_workspace_state"),
            patch.object(
                self.agent,
                "_build_task_prompt",
                return_value="prepared prompt",
            ),
            patch.object(self.agent, "_run_prompt") as run_prompt,
            patch.object(self.agent, "_install_openclaw_transcript_shim"),
        ):
            execution = self.agent.run_task(spec)

    self.assertIsNone(execution.error)
    run_prompt.assert_called_once_with(
        task_id="opencode-thinking-test",
        model="openrouter/gpt-5.5",
        prompt="prepared prompt",
        timeout_seconds=30,
        output_dir=output_dir,
        thinking="high",
    )
```

- [ ] **Step 2: 运行测试并确认正确失败**

Run:

```bash
uv run python -m unittest discover -s tests -p 'test_opencode_runner.py' -v
```

Expected: 现有 3 个测试 PASS，新增调用链测试 FAIL，mock 调用参数中缺少 `thinking="high"`。

- [ ] **Step 3: 实现整条参数传递**

在 `run_task()` 调用 `_run_prompt()` 时增加：

```python
thinking=spec.thinking,
```

给 `_run_prompt()` 增加末尾可选参数：

```python
thinking: str | None = None,
```

调用 `_run_opencode_exec()` 时增加关键字参数：

```python
thinking=thinking,
```

给 `_run_opencode_exec()` 增加末尾可选参数：

```python
thinking: str | None = None,
```

构造命令时改为：

```python
cmd = self._build_exec_command(
    model,
    prompt_path,
    config_content,
    thinking=thinking,
)
```

- [ ] **Step 4: 运行 OpenCode 测试并确认通过**

Run:

```bash
uv run python -m unittest discover -s tests -p 'test_opencode_runner.py' -v
```

Expected: 4 tests PASS。

- [ ] **Step 5: 运行完整单测和静态检查**

Run:

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
python -m compileall -q src/agents/opencode tests/test_opencode_runner.py
git diff --check
```

Expected: 全部命令退出码为 0，无测试失败、语法错误或空白错误。

- [ ] **Step 6: 提交调用链变更**

```bash
git add tests/test_opencode_runner.py src/agents/opencode/runner.py
git commit -m "feat(opencode): 传递评测推理强度"
```
