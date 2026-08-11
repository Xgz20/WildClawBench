# AstronCode 桌面端端到端评测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `eval_e2e/` 三阶段脚本（prepare / collect / grade），用 WildClawBench 现有用例在 AstronCode 桌面端做端到端评测，评分与 CLI 侧同源同码。

**Architecture:** 三个独立脚本通过磁盘上的 `manifest.json` 串联，人工执行插在 prepare 与 collect 之间。prepare 只拷 `exec/` 保证 GT 隔离；collect 按 `cwd` + 时间窗匹配桌面端轨迹并落成与 CLI 同构的结果目录；grade 把项目目录挂为容器 `/tmp_workspace` 后调用现有 `run_grading()`。全程 import 复用 `src/utils/`，不修改任何现有文件。

**Tech Stack:** Python 3（标准库 + `pyyaml` + `python-dotenv`，均已在 `requirements.txt`）、Docker（评分载体，镜像 `wildclawbench-astroncode-ubuntu:v0.4`）、`unittest`（跟随现有 `tests/` 约定，用 `python3 -m pytest` 运行）。

设计文档：`docs/superpowers/specs/2026-08-10-astroncode-desktop-e2e-eval-design.md`

## Global Constraints

- **不修改任何现有文件。** 只新增 `eval_e2e/` 与 `tests/test_e2e_*.py`。若发现必须改现有文件才能复用，先停下来问用户。
- **容器内工作区路径固定为 `/tmp_workspace`。** 184 个用例中 164 个的 `grade()` 硬编码了该字面量，用例一律不改。
- **仓库侧路径全部相对化。** `manifest.json` 内仓库路径存相对路径；`project_dir` 存相对路径，运行时由 `--e2e-root` 解析为绝对路径。
- **GT 绝不进入项目目录。** prepare 只拷 `workspace/<...>/<task>/exec/` 的内容，`gt/` 留在仓库，仅在 grade 阶段 `docker cp` 进容器。
- **harness 名固定为 `astroncode-desktop`**，与 CLI 侧 `astroncode` 并列。
- **单用例失败不中断批次。** 失败原因落盘 `execution_status.json`，批次继续。
- **测试风格**：`unittest.TestCase` 类 + `from __future__ import annotations`，`REPO_ROOT = Path(__file__).resolve().parents[1]`，跟随 `tests/test_task_warmups.py`。
- **复用的现有接口签名（只读，不得改动）**：
  - `parse_task_md(task_file: Path) -> dict`，返回含 `task_id`/`prompt`/`workspace_path`/`automated_checks`/`env`/`llm_judge_rubric`/`rubric_criteria`/`grading_weights`/`category`/`timeout_seconds`
  - `run_grading(task_id, automated_checks, output_dir, extra_env="", lobster_env=None, transcript_container_path="", write_error_score=False, *, llm_judge_rubric="", rubric_criteria=None, grading_weights=None) -> dict`
  - `write_error_score(output_dir: Path, task_id: str, message: str) -> dict`
  - `start_container(task_id, workspace_path, extra_env="", tmp_path="", lobster_env=None, docker_image=None) -> None`
  - `remove_container(name: str) -> None`

---

## File Structure

| 文件 | 职责 |
|---|---|
| `eval_e2e/e2e_manifest.py` | manifest 的数据结构、读写、相对↔绝对路径解析。三脚本共享，不含业务流程 |
| `eval_e2e/prompt_rewrite.py` | Prompt 路径改写（`/tmp_workspace` 前缀 → 项目目录绝对路径），纯函数 |
| `eval_e2e/trace_match.py` | 桌面端轨迹定位（扫 `*.jsonl`、读 `session_meta`、按 cwd + 时间窗匹配）与 usage 解析 |
| `eval_e2e/prepare_workspaces.py` | 阶段①CLI：读 task-list → 拷 `exec/` → 生成双份 Prompt → 写 manifest + 人工清单 |
| `eval_e2e/collect_runs.py` | 阶段②CLI：匹配轨迹 → 落同构结果目录（`chat.jsonl`/`usage.json`/`task_output/`） |
| `eval_e2e/grade_runs.py` | 阶段③CLI：挂载项目目录 → `docker cp` gt → 调 `run_grading()` → 写 `score.json` |
| `eval_e2e/README.md` | 三阶段用法、人工执行步骤、参数说明 |
| `tests/test_e2e_manifest.py` | manifest 路径解析与往返读写 |
| `tests/test_e2e_prompt_rewrite.py` | Prompt 改写正确性 |
| `tests/test_e2e_trace_match.py` | 轨迹匹配的命中/零命中/多命中分支、usage 解析 |
| `tests/test_e2e_prepare.py` | GT 隔离回归断言、缺失工作区跳过 |

纯逻辑（manifest / 改写 / 匹配）与副作用（文件拷贝 / Docker / CLI 参数）分离，
使前三个模块可完全离线单测，无需 Docker 与桌面端。

---

### Task 1: manifest 数据结构与相对路径解析

**Files:**
- Create: `eval_e2e/__init__.py`
- Create: `eval_e2e/e2e_manifest.py`
- Test: `tests/test_e2e_manifest.py`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces:
  - `HARNESS_NAME: str = "astroncode-desktop"`
  - `@dataclass RunEntry`，字段：`task_id: str`, `category: str`, `task_file: str`, `workspace_src: str`, `project_dir: str`, `model: str`, `reasoning_effort: str`, `prompt_rewritten: bool`, `prompt_rewrite_map: dict[str, str]`, `status: str`, `started_at: str = ""`, `finished_at: str = ""`
  - `@dataclass Manifest`，字段：`e2e_root: str`, `created_at: str`, `runs: list[RunEntry]`
  - `RunEntry.to_dict() -> dict` / `RunEntry.from_dict(d: dict) -> RunEntry`
  - `Manifest.to_dict() -> dict` / `Manifest.from_dict(d: dict) -> Manifest`
  - `save_manifest(manifest: Manifest, path: Path) -> None`
  - `load_manifest(path: Path) -> Manifest`
  - `resolve_project_dir(entry: RunEntry, e2e_root: Path) -> Path`（把相对 `project_dir` 解析为绝对路径）
  - `resolve_repo_path(rel: str, repo_root: Path) -> Path`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_e2e_manifest.py`：

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eval_e2e.e2e_manifest import (
    HARNESS_NAME,
    Manifest,
    RunEntry,
    load_manifest,
    resolve_project_dir,
    resolve_repo_path,
    save_manifest,
)


def _entry(**over) -> RunEntry:
    base = dict(
        task_id="02_Code_Intelligence_task_001_temperature_cli_fix",
        category="02_Code_Intelligence",
        task_file="tasks/extension/02_Code_Intelligence/t.md",
        workspace_src="workspace/extension/02_Code_Intelligence/task_001",
        project_dir="xopglm52/02_Code_Intelligence_task_001_temperature_cli_fix/tmp_workspace",
        model="xopglm52",
        reasoning_effort="medium",
        prompt_rewritten=True,
        prompt_rewrite_map={"/tmp_workspace": "/abs/x/tmp_workspace"},
        status="pending",
    )
    base.update(over)
    return RunEntry(**base)


class ManifestTest(unittest.TestCase):
    def test_harness_name_is_astroncode_desktop(self) -> None:
        self.assertEqual(HARNESS_NAME, "astroncode-desktop")

    def test_roundtrip_preserves_all_fields(self) -> None:
        manifest = Manifest(
            e2e_root="eval_out_e2e", created_at="2026-08-10T12:00:00+08:00",
            runs=[_entry()],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            save_manifest(manifest, path)
            loaded = load_manifest(path)
        self.assertEqual(loaded.to_dict(), manifest.to_dict())
        self.assertEqual(loaded.runs[0].prompt_rewrite_map["/tmp_workspace"],
                         "/abs/x/tmp_workspace")

    def test_manifest_stores_relative_project_dir(self) -> None:
        """project_dir 必须是相对路径，保证可移植性。"""
        manifest = Manifest(e2e_root="eval_out_e2e", created_at="x", runs=[_entry()])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            save_manifest(manifest, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(Path(raw["runs"][0]["project_dir"]).is_absolute())

    def test_resolve_project_dir_rebases_on_new_root(self) -> None:
        """换一台机器（换 e2e_root）后路径应重新解析到新根下。"""
        entry = _entry()
        got = resolve_project_dir(entry, Path("/data1/out"))
        self.assertEqual(
            got,
            Path("/data1/out/xopglm52/"
                 "02_Code_Intelligence_task_001_temperature_cli_fix/tmp_workspace"),
        )
        self.assertTrue(got.is_absolute())

    def test_resolve_repo_path_joins_repo_root(self) -> None:
        got = resolve_repo_path("workspace/extension/x", Path("/repo"))
        self.assertEqual(got, Path("/repo/workspace/extension/x"))

    def test_resolve_repo_path_keeps_absolute_input(self) -> None:
        got = resolve_repo_path("/already/abs", Path("/repo"))
        self.assertEqual(got, Path("/already/abs"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_manifest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_e2e'`

- [ ] **Step 3: 写最小实现**

创建 `eval_e2e/__init__.py`（空文件）：

```python
```

创建 `eval_e2e/e2e_manifest.py`：

```python
"""端到端评测 manifest 的读写与路径解析。

manifest 内仓库路径与 project_dir 一律存相对路径，运行时按 --e2e-root /
仓库根重新解析，换机器只需换入口参数。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

HARNESS_NAME = "astroncode-desktop"

STATUS_PENDING = "pending"
STATUS_COLLECTED = "collected"
STATUS_GRADED = "graded"
STATUS_TRACE_MISSING = "trace_missing"


@dataclass
class RunEntry:
    task_id: str
    category: str
    task_file: str
    workspace_src: str
    project_dir: str
    model: str
    reasoning_effort: str
    prompt_rewritten: bool
    prompt_rewrite_map: dict[str, str] = field(default_factory=dict)
    status: str = STATUS_PENDING
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunEntry":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Manifest:
    e2e_root: str
    created_at: str
    runs: list[RunEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "e2e_root": self.e2e_root,
            "created_at": self.created_at,
            "runs": [r.to_dict() for r in self.runs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        return cls(
            e2e_root=data.get("e2e_root", ""),
            created_at=data.get("created_at", ""),
            runs=[RunEntry.from_dict(r) for r in data.get("runs", [])],
        )


def save_manifest(manifest: Manifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> Manifest:
    return Manifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def resolve_project_dir(entry: RunEntry, e2e_root: Path) -> Path:
    p = Path(entry.project_dir)
    return p if p.is_absolute() else (Path(e2e_root) / p)


def resolve_repo_path(rel: str, repo_root: Path) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (Path(repo_root) / p)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_e2e_manifest.py -q`
Expected: PASS — `6 passed`

- [ ] **Step 5: 提交**

```bash
git add eval_e2e/__init__.py eval_e2e/e2e_manifest.py tests/test_e2e_manifest.py
git commit -m "feat(e2e): 新增 manifest 数据结构与相对路径解析"
```

---

### Task 2: Prompt 路径改写

**Files:**
- Create: `eval_e2e/prompt_rewrite.py`
- Test: `tests/test_e2e_prompt_rewrite.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `CONTAINER_WORKSPACE: str = "/tmp_workspace"`
  - `rewrite_prompt(prompt: str, project_dir: Path) -> tuple[str, dict[str, str]]`
    返回 `(改写后的 Prompt, {"/tmp_workspace": "<abs project_dir>"})`；
    未出现该前缀时返回 `(原文, {})`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_e2e_prompt_rewrite.py`：

```python
from __future__ import annotations

import unittest
from pathlib import Path

from eval_e2e.prompt_rewrite import CONTAINER_WORKSPACE, rewrite_prompt

PROJECT = Path("/Users/x/eval_out_e2e/m/task_001/tmp_workspace")


class PromptRewriteTest(unittest.TestCase):
    def test_container_workspace_constant(self) -> None:
        self.assertEqual(CONTAINER_WORKSPACE, "/tmp_workspace")

    def test_rewrites_prefix_and_keeps_tail_structure(self) -> None:
        out, mapping = rewrite_prompt(
            "修复 /tmp_workspace/project/converter.py 中的缺陷", PROJECT
        )
        self.assertEqual(
            out,
            f"修复 {PROJECT}/project/converter.py 中的缺陷",
        )
        self.assertEqual(mapping, {"/tmp_workspace": str(PROJECT)})

    def test_rewrites_every_occurrence(self) -> None:
        out, _ = rewrite_prompt(
            "读 /tmp_workspace/input/a.png 写 /tmp_workspace/results/r.md", PROJECT
        )
        # PROJECT 尾部本身命名 tmp_workspace，改写后 out 必然仍含子串
        # "/tmp_workspace/"，故不能用 assertNotIn；改判前缀出现次数。
        self.assertEqual(out.count(f"{PROJECT}/"), 2)
        self.assertIn(f"{PROJECT}/input/a.png", out)
        self.assertIn(f"{PROJECT}/results/r.md", out)

    def test_rewrites_bare_path_without_trailing_slash(self) -> None:
        out, _ = rewrite_prompt("产物放到 /tmp_workspace 下", PROJECT)
        self.assertEqual(out, f"产物放到 {PROJECT} 下")

    def test_does_not_touch_similar_but_different_prefix(self) -> None:
        """/tmp_workspace_backup 不是工作区路径，不应被改写。"""
        out, _ = rewrite_prompt("备份在 /tmp_workspace_backup/x", PROJECT)
        self.assertEqual(out, "备份在 /tmp_workspace_backup/x")

    def test_returns_empty_map_when_no_match(self) -> None:
        out, mapping = rewrite_prompt("没有任何工作区路径", PROJECT)
        self.assertEqual(out, "没有任何工作区路径")
        self.assertEqual(mapping, {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_e2e_prompt_rewrite.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_e2e.prompt_rewrite'`

- [ ] **Step 3: 写最小实现**

创建 `eval_e2e/prompt_rewrite.py`：

```python
"""把用例 Prompt 里的容器内工作区路径改写为桌面端可见的本机路径。

这是端到端与 CLI 侧唯一的输入差异（路径必须真实存在才能执行）。
改写只替换前缀，尾部结构保持不变；映射关系一并返回供结果披露。
"""
from __future__ import annotations

import re
from pathlib import Path

CONTAINER_WORKSPACE = "/tmp_workspace"


def rewrite_prompt(prompt: str, project_dir: Path) -> tuple[str, dict[str, str]]:
    """返回 (改写后的 Prompt, 改写映射)。无匹配时映射为空 dict。

    用 (?![\\w-]) 断言避免误伤 /tmp_workspace_backup 之类的相似前缀。
    """
    target = str(project_dir)
    pattern = re.compile(re.escape(CONTAINER_WORKSPACE) + r"(?![\w-])")
    rewritten, count = pattern.subn(target, prompt)
    if count == 0:
        return prompt, {}
    return rewritten, {CONTAINER_WORKSPACE: target}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_e2e_prompt_rewrite.py -q`
Expected: PASS — `6 passed`

- [ ] **Step 5: 提交**

```bash
git add eval_e2e/prompt_rewrite.py tests/test_e2e_prompt_rewrite.py
git commit -m "feat(e2e): 新增 Prompt 工作区路径改写"
```

---

### Task 3: 轨迹定位与 usage 解析

**Files:**
- Create: `eval_e2e/trace_match.py`
- Test: `tests/test_e2e_trace_match.py`

**Interfaces:**
- Consumes: 无（纯函数模块，不依赖 Task 1/2）
- Produces:
  - `DEFAULT_TRACE_ROOT: str = "~/.acode/sessions"`
  - `@dataclass TraceCandidate`：`path: Path`, `cwd: str`, `timestamp: str`
  - `read_session_meta(path: Path) -> TraceCandidate | None`（读首行 `session_meta`，非法返回 `None`）
  - `find_trace(trace_root: Path, project_dir: Path, started_at: str, finished_at: str) -> tuple[Path | None, str]`
    返回 `(命中路径或 None, 状态说明)`；多命中取 `timestamp` 最新
  - `parse_usage(trace_path: Path) -> dict`，返回键 `input_tokens`/`output_tokens`/`cache_read_tokens`/`total_tokens`/`tool_calls`/`request_count`/`cost_usd`

轨迹匹配以 `session_meta.payload.cwd` 等于项目目录（或为其后代）且 `timestamp`
落在 `[started_at, finished_at]` 为准。时间窗任一端为空时该端不设限。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_e2e_trace_match.py`：

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eval_e2e.trace_match import (
    find_trace,
    parse_usage,
    read_session_meta,
)


def _write_trace(root: Path, name: str, cwd: str, ts: str, extra=()) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    rows = [{"timestamp": ts, "type": "session_meta",
             "payload": {"cwd": cwd, "timestamp": ts}}]
    rows.extend(extra)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return path


class ReadSessionMetaTest(unittest.TestCase):
    def test_reads_cwd_and_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_trace(Path(tmp), "a.jsonl", "/x/tmp_workspace",
                             "2026-08-10T12:00:00.000Z")
            got = read_session_meta(p)
        self.assertIsNotNone(got)
        self.assertEqual(got.cwd, "/x/tmp_workspace")
        self.assertEqual(got.timestamp, "2026-08-10T12:00:00.000Z")

    def test_returns_none_for_malformed_first_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.jsonl"
            p.write_text("not json\n", encoding="utf-8")
            self.assertIsNone(read_session_meta(p))

    def test_returns_none_when_first_line_is_not_session_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.jsonl"
            p.write_text(json.dumps({"type": "message"}) + "\n", encoding="utf-8")
            self.assertIsNone(read_session_meta(p))


class FindTraceTest(unittest.TestCase):
    def test_matches_by_cwd_and_time_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            want = _write_trace(root, "hit.jsonl", str(proj),
                                "2026-08-10T12:05:00.000Z")
            _write_trace(root, "other_cwd.jsonl", "/y/tmp_workspace",
                         "2026-08-10T12:05:00.000Z")
            _write_trace(root, "out_of_window.jsonl", str(proj),
                         "2026-08-09T12:05:00.000Z")
            got, note = find_trace(root, proj,
                                   "2026-08-10T12:00:00.000Z",
                                   "2026-08-10T12:10:00.000Z")
        self.assertEqual(got, want)
        self.assertEqual(note, "matched")

    def test_returns_none_when_no_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            root.mkdir(parents=True)
            got, note = find_trace(root, Path("/x/tmp_workspace"), "", "")
        self.assertIsNone(got)
        self.assertEqual(note, "trace_missing")

    def test_picks_latest_when_multiple_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            _write_trace(root, "early.jsonl", str(proj),
                         "2026-08-10T12:01:00.000Z")
            latest = _write_trace(root, "late.jsonl", str(proj),
                                  "2026-08-10T12:09:00.000Z")
            got, note = find_trace(root, proj, "", "")
        self.assertEqual(got, latest)
        self.assertEqual(note, "matched_multiple")

    def test_missing_trace_root_reports_explicitly(self) -> None:
        got, note = find_trace(Path("/definitely/not/here"),
                               Path("/x/tmp_workspace"), "", "")
        self.assertIsNone(got)
        self.assertEqual(note, "trace_root_missing")

    def test_empty_window_bounds_do_not_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            proj = Path("/x/tmp_workspace")
            want = _write_trace(root, "a.jsonl", str(proj),
                                "1999-01-01T00:00:00.000Z")
            got, _ = find_trace(root, proj, "", "")
        self.assertEqual(got, want)


class ParseUsageTest(unittest.TestCase):
    def test_counts_tool_calls_and_tokens(self) -> None:
        extra = [
            {"type": "function_call", "payload": {"name": "shell"}},
            {"type": "function_call", "payload": {"name": "shell"}},
            {"type": "token_count", "payload": {"total_token_usage": {
                "input_tokens": 100, "output_tokens": 20,
                "cached_input_tokens": 5, "total_tokens": 120}}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_trace(Path(tmp), "a.jsonl", "/x", "2026-08-10T12:00:00Z", extra)
            got = parse_usage(p)
        self.assertEqual(got["tool_calls"], 2)
        self.assertEqual(got["input_tokens"], 100)
        self.assertEqual(got["output_tokens"], 20)
        self.assertEqual(got["cache_read_tokens"], 5)
        self.assertEqual(got["total_tokens"], 120)

    def test_returns_zeros_for_missing_file(self) -> None:
        got = parse_usage(Path("/nope/x.jsonl"))
        self.assertEqual(got["tool_calls"], 0)
        self.assertEqual(got["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_trace_match.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_e2e.trace_match'`

- [ ] **Step 3: 写最小实现**

创建 `eval_e2e/trace_match.py`：

```python
"""桌面端轨迹定位与用量解析。

轨迹以首行 session_meta 的 payload.cwd 与项目目录匹配、timestamp 落在执行
时间窗内为准。用量以工具调用数为主口径——CLI 侧已确认 request_count 存在
低估（见 memory: astroncode-request-count-underestimate）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TRACE_ROOT = "~/.acode/sessions"


@dataclass
class TraceCandidate:
    path: Path
    cwd: str
    timestamp: str


def read_session_meta(path: Path) -> TraceCandidate | None:
    """读首行 session_meta；格式不符或不可读时返回 None。"""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            first = fh.readline().strip()
    except OSError:
        return None
    if not first:
        return None
    try:
        row = json.loads(first)
    except ValueError:
        return None
    if not isinstance(row, dict) or row.get("type") != "session_meta":
        return None
    payload = row.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    cwd = str(payload.get("cwd") or "")
    timestamp = str(payload.get("timestamp") or row.get("timestamp") or "")
    if not cwd:
        return None
    return TraceCandidate(path=path, cwd=cwd, timestamp=timestamp)


def _cwd_matches(cwd: str, project_dir: Path) -> bool:
    try:
        candidate = Path(cwd)
    except (TypeError, ValueError):
        return False
    if candidate == project_dir:
        return True
    # 只认相等与后代：祖先方向会把用户在工作区根打开的一次会话
    # 同时算给该根下所有用例，且不报错。
    return project_dir in candidate.parents


def _parse_ts(value: str) -> datetime | None:
    """ISO 时间戳 -> 带时区 datetime；Z 后缀在 3.10 需转 +00:00，无时区按 UTC。"""
    if not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _in_window(timestamp: str, started_at: str, finished_at: str) -> bool:
    """空端不设限。必须解析为 datetime 比较：字符串字典序在时区偏移
    与毫秒精度不一致时与真实时序不符（+08:00 会被误判早于同刻 UTC）。"""
    ts = _parse_ts(timestamp)
    if ts is None:
        return False
    start, finish = _parse_ts(started_at), _parse_ts(finished_at)
    if start is not None and ts < start:
        return False
    if finish is not None and ts > finish:
        return False
    return True


def find_trace(
    trace_root: Path,
    project_dir: Path,
    started_at: str,
    finished_at: str,
) -> tuple[Path | None, str]:
    """返回 (命中轨迹路径或 None, 状态说明)。多命中取 timestamp 最新。"""
    root = Path(trace_root).expanduser()
    if not root.is_dir():
        return None, "trace_root_missing"

    matched: list[TraceCandidate] = []
    for path in sorted(root.rglob("*.jsonl")):
        if not path.is_file():
            continue
        meta = read_session_meta(path)
        if meta is None:
            continue
        if not _cwd_matches(meta.cwd, project_dir):
            continue
        if not _in_window(meta.timestamp, started_at, finished_at):
            continue
        matched.append(meta)

    if not matched:
        return None, "trace_missing"
    # 按解析后的真实时刻排序：字符串序会把 +08:00 的较早时刻排到 Z 的较晚时刻之后。
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    matched.sort(key=lambda c: (_parse_ts(c.timestamp) or epoch, c.path.name))
    note = "matched" if len(matched) == 1 else "matched_multiple"
    return matched[-1].path, note


def _empty_usage() -> dict:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,
        "tool_calls": 0,
        "request_count": 0,
        "cost_usd": 0.0,
    }


def parse_usage(trace_path: Path) -> dict:
    """解析轨迹的用量。工具调用数为主口径，token 取最后一次累计值。"""
    usage = _empty_usage()
    try:
        raw = Path(trace_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return usage

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        row_type = str(row.get("type") or "")
        payload = row.get("payload")
        payload = payload if isinstance(payload, dict) else {}

        if row_type in ("function_call", "tool_call", "local_shell_call"):
            usage["tool_calls"] += 1
            continue

        if row_type == "token_count":
            totals = payload.get("total_token_usage")
            if isinstance(totals, dict):
                usage["input_tokens"] = int(totals.get("input_tokens") or 0)
                usage["output_tokens"] = int(totals.get("output_tokens") or 0)
                usage["cache_read_tokens"] = int(
                    totals.get("cached_input_tokens")
                    or totals.get("cache_read_tokens")
                    or 0
                )
                usage["total_tokens"] = int(totals.get("total_tokens") or 0)

    if usage["total_tokens"] == 0:
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return usage
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_trace_match.py -q`
Expected: PASS — `11 passed`

- [ ] **Step 5: 提交**

```bash
git add eval_e2e/trace_match.py tests/test_e2e_trace_match.py
git commit -m "feat(e2e): 新增桌面端轨迹定位与用量解析"
```

---

### Task 4: prepare 阶段核心逻辑（拷贝 exec/、GT 隔离）

**Files:**
- Create: `eval_e2e/prepare_workspaces.py`
- Test: `tests/test_e2e_prepare.py`

**Interfaces:**
- Consumes:
  - Task 1：`Manifest`, `RunEntry`, `save_manifest`, `HARNESS_NAME`, `STATUS_PENDING`
  - Task 2：`rewrite_prompt`
  - 现有：`parse_task_md(task_file: Path) -> dict`
- Produces:
  - `read_task_list(path: Path) -> list[str]`（读 task-list，忽略空行与 `#` 注释）
  - `copy_exec_dir(workspace_src: Path, project_dir: Path) -> None`
    只拷 `workspace_src/exec/` 的内容，**绝不拷 `gt/`**；`exec/` 不存在时建空目录
  - `build_run_entry(task_file: Path, repo_root: Path, e2e_root_rel: str, model: str, reasoning_effort: str) -> RunEntry`
  - `prepare_one(entry: RunEntry, repo_root: Path, e2e_root: Path, prompt: str) -> None`
    建项目目录、拷 exec、写 `prompt_original.txt` 与 `prompt_desktop.txt`
  - `render_checklist(manifest: Manifest, e2e_root: Path) -> str`（人工执行清单 Markdown）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_e2e_prepare.py`：

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eval_e2e.e2e_manifest import Manifest, RunEntry
from eval_e2e.prepare_workspaces import (
    copy_exec_dir,
    prepare_one,
    read_task_list,
    render_checklist,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_src(root: Path) -> Path:
    """造一个含 exec/ 与 gt/ 的源工作区。"""
    src = root / "workspace" / "02_Code" / "task_001"
    (src / "exec" / "project").mkdir(parents=True)
    (src / "exec" / "project" / "converter.py").write_text("x = 1\n", encoding="utf-8")
    (src / "gt").mkdir(parents=True)
    (src / "gt" / "expected.json").write_text('{"a": 1}\n', encoding="utf-8")
    return src


def _entry(project_dir: str) -> RunEntry:
    return RunEntry(
        task_id="02_Code_task_001", category="02_Code",
        task_file="tasks/x.md", workspace_src="workspace/02_Code/task_001",
        project_dir=project_dir, model="xopglm52", reasoning_effort="medium",
        prompt_rewritten=True, prompt_rewrite_map={}, status="pending",
    )


class CopyExecDirTest(unittest.TestCase):
    def test_copies_exec_contents_to_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = _make_src(root)
            proj = root / "out" / "task_001" / "tmp_workspace"
            copy_exec_dir(src, proj)
        self.assertTrue((proj / "project" / "converter.py").is_file())

    def test_never_copies_gt_directory(self) -> None:
        """GT 隔离回归断言：项目目录内不得出现 gt/ 或其内容。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = _make_src(root)
            proj = root / "out" / "task_001" / "tmp_workspace"
            copy_exec_dir(src, proj)
            leaked = [str(p.relative_to(proj)) for p in proj.rglob("*")
                      if "gt" in p.parts or p.name == "expected.json"]
        self.assertEqual(leaked, [])

    def test_creates_empty_dir_when_exec_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "empty_src"
            src.mkdir()
            proj = root / "out" / "tmp_workspace"
            copy_exec_dir(src, proj)
        self.assertTrue(proj.is_dir())


class PrepareOneTest(unittest.TestCase):
    def test_writes_both_prompt_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_src(root)
            e2e_root = root / "out"
            entry = _entry("xopglm52/02_Code_task_001/tmp_workspace")
            prepare_one(entry, root, e2e_root,
                        "改 /tmp_workspace/project/converter.py")
            case_dir = e2e_root / "xopglm52" / "02_Code_task_001"
            original = (case_dir / "prompt_original.txt").read_text(encoding="utf-8")
            desktop = (case_dir / "prompt_desktop.txt").read_text(encoding="utf-8")
        self.assertIn("/tmp_workspace/project/converter.py", original)
        self.assertNotIn("改 /tmp_workspace/project", desktop)
        self.assertIn(str(case_dir / "tmp_workspace" / "project" / "converter.py"),
                      desktop)

    def test_records_rewrite_map_on_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_src(root)
            e2e_root = root / "out"
            entry = _entry("xopglm52/02_Code_task_001/tmp_workspace")
            prepare_one(entry, root, e2e_root, "见 /tmp_workspace/a.txt")
        self.assertTrue(entry.prompt_rewritten)
        self.assertEqual(
            entry.prompt_rewrite_map["/tmp_workspace"],
            str(e2e_root / "xopglm52" / "02_Code_task_001" / "tmp_workspace"),
        )

    def test_project_dir_tail_is_tmp_workspace(self) -> None:
        """尾部命名对齐 CLI 侧，Prompt 只需替换前缀。"""
        entry = _entry("xopglm52/02_Code_task_001/tmp_workspace")
        self.assertEqual(Path(entry.project_dir).name, "tmp_workspace")


class ReadTaskListTest(unittest.TestCase):
    def test_skips_blank_lines_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "list.txt"
            p.write_text(
                "# 注释\n\ntasks/a.md\n  tasks/b.md  \n# 又一个注释\n",
                encoding="utf-8",
            )
            got = read_task_list(p)
        self.assertEqual(got, ["tasks/a.md", "tasks/b.md"])


class RenderChecklistTest(unittest.TestCase):
    def test_checklist_contains_abs_path_model_and_prompt_ref(self) -> None:
        manifest = Manifest(
            e2e_root="out", created_at="2026-08-10T12:00:00+08:00",
            runs=[_entry("xopglm52/02_Code_task_001/tmp_workspace")],
        )
        got = render_checklist(manifest, Path("/data1/out"))
        self.assertIn("/data1/out/xopglm52/02_Code_task_001/tmp_workspace", got)
        self.assertIn("xopglm52", got)
        self.assertIn("medium", got)
        self.assertIn("prompt_desktop.txt", got)
        self.assertIn("- [ ]", got)


class RealWorkspaceContractTest(unittest.TestCase):
    def test_repo_workspaces_use_exec_gt_layout(self) -> None:
        """回归：仓库工作区应维持 exec/ + gt/ 分离约定。"""
        gt_dirs = list(REPO_ROOT.glob("workspace/*/*/gt"))
        self.assertTrue(gt_dirs, "未找到任何 gt 目录，exec/gt 约定可能已变更")
        for gt in gt_dirs[:5]:
            self.assertTrue((gt.parent / "exec").is_dir(),
                            f"{gt.parent} 有 gt/ 但缺 exec/")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_prepare.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_e2e.prepare_workspaces'`

- [ ] **Step 3: 写最小实现（模块函数部分）**

创建 `eval_e2e/prepare_workspaces.py`，先写导入与核心函数：

```python
"""阶段①：准备端到端评测的项目目录、双份 Prompt 与人工执行清单。

只拷源工作区的 exec/ 内容，gt/ 留在仓库（评分阶段才送进容器），
确保交付给桌面端的项目目录不含 Ground Truth。
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval_e2e.e2e_manifest import (  # noqa: E402
    HARNESS_NAME,
    STATUS_PENDING,
    Manifest,
    RunEntry,
    resolve_project_dir,
    save_manifest,
)
from eval_e2e.prompt_rewrite import rewrite_prompt  # noqa: E402
from src.utils.task_parser import parse_task_md  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_E2E_ROOT = "eval_out_e2e"
PROJECT_DIR_TAIL = "tmp_workspace"


def read_task_list(path: Path) -> list[str]:
    """读 task-list，忽略空行与 # 注释行。"""
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        items.append(stripped)
    return items


def copy_exec_dir(workspace_src: Path, project_dir: Path) -> None:
    """把 workspace_src/exec/ 的内容拷到 project_dir。

    gt/ 一律不拷。exec/ 不存在时（用例无输入文件）建空目录。
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    exec_dir = workspace_src / "exec"
    if not exec_dir.is_dir():
        logger.warning("源工作区无 exec/，建空项目目录: %s", workspace_src)
        return
    for item in exec_dir.iterdir():
        dest = project_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
```

- [ ] **Step 4: 追加 entry 构建、prepare_one 与清单渲染**

在 `eval_e2e/prepare_workspaces.py` 末尾追加：

```python
def build_run_entry(
    task_file: Path,
    repo_root: Path,
    e2e_root_rel: str,
    model: str,
    reasoning_effort: str,
) -> RunEntry:
    """从 task.md 解析出一个 RunEntry，路径一律存相对仓库根的相对路径。"""
    task = parse_task_md(task_file)
    task_id = task["task_id"]
    workspace_src = Path(task["workspace_path"])
    try:
        workspace_rel = str(workspace_src.relative_to(repo_root))
    except ValueError:
        workspace_rel = str(workspace_src)
    return RunEntry(
        task_id=task_id,
        category=task.get("category", ""),
        task_file=str(task_file.relative_to(repo_root)),
        workspace_src=workspace_rel,
        project_dir=str(Path(model) / task_id / PROJECT_DIR_TAIL),
        model=model,
        reasoning_effort=reasoning_effort,
        prompt_rewritten=False,
        prompt_rewrite_map={},
        status=STATUS_PENDING,
    )


def prepare_one(
    entry: RunEntry,
    repo_root: Path,
    e2e_root: Path,
    prompt: str,
) -> None:
    """建项目目录、拷 exec/、写双份 Prompt，并把改写记录写回 entry。"""
    project_dir = resolve_project_dir(entry, e2e_root)
    workspace_src = repo_root / entry.workspace_src
    copy_exec_dir(workspace_src, project_dir)

    case_dir = project_dir.parent
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "prompt_original.txt").write_text(prompt, encoding="utf-8")

    desktop_prompt, mapping = rewrite_prompt(prompt, project_dir)
    (case_dir / "prompt_desktop.txt").write_text(desktop_prompt, encoding="utf-8")
    entry.prompt_rewritten = bool(mapping)
    entry.prompt_rewrite_map = mapping


def render_checklist(manifest: Manifest, e2e_root: Path) -> str:
    """渲染人工执行清单：每个用例一段，含项目路径、模型、Prompt 位置与打勾位。"""
    lines = [
        "# AstronCode 桌面端人工执行清单",
        "",
        f"生成时间：{manifest.created_at}",
        f"用例数：{len(manifest.runs)}",
        "",
        "每个用例：在桌面端新建项目并选择下方「项目目录」，选好模型与推理强度，",
        "把 `prompt_desktop.txt` 全文粘贴进对话框触发执行；执行完在本行打勾。",
        "",
    ]
    for idx, entry in enumerate(manifest.runs, start=1):
        project_dir = resolve_project_dir(entry, e2e_root)
        lines += [
            f"## {idx}. {entry.task_id}",
            "",
            f"- [ ] 已执行完毕",
            f"- 项目目录：`{project_dir}`",
            f"- 模型：`{entry.model}`　推理强度：`{entry.reasoning_effort}`",
            f"- Prompt：`{project_dir.parent / 'prompt_desktop.txt'}`",
            f"- Harness：`{HARNESS_NAME}`",
            "",
        ]
    return "\n".join(lines)
```

- [ ] **Step 5: 追加 CLI 入口**

在 `eval_e2e/prepare_workspaces.py` 末尾追加：

```python
def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 AstronCode 桌面端端到端评测的项目目录与人工执行清单",
    )
    parser.add_argument("--task-list", required=True,
                        help="用例清单文件（每行一个 task.md 路径，# 为注释）")
    parser.add_argument("--model", required=True, help="要评测的模型名")
    parser.add_argument("--reasoning-effort", default="medium",
                        help="推理强度（仅记录进清单，供人工在界面选择）")
    parser.add_argument("--e2e-root", default=DEFAULT_E2E_ROOT,
                        help=f"端到端输出根目录（默认 {DEFAULT_E2E_ROOT}）")
    parser.add_argument("--repo-root", default="",
                        help="仓库根（默认按脚本位置推断）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    repo_root = (Path(args.repo_root).expanduser().resolve()
                 if args.repo_root else Path(__file__).resolve().parents[1])
    e2e_root = Path(args.e2e_root).expanduser()
    if not e2e_root.is_absolute():
        e2e_root = (repo_root / e2e_root).resolve()

    task_list_path = Path(args.task_list).expanduser()
    if not task_list_path.is_absolute():
        task_list_path = repo_root / task_list_path

    entries: list[RunEntry] = []
    skipped: list[str] = []
    for rel in read_task_list(task_list_path):
        task_file = Path(rel).expanduser()
        if not task_file.is_absolute():
            task_file = repo_root / task_file
        if not task_file.is_file():
            logger.error("用例文件不存在，跳过: %s", task_file)
            skipped.append(rel)
            continue
        try:
            entry = build_run_entry(task_file, repo_root, args.e2e_root,
                                    args.model, args.reasoning_effort)
            prompt = parse_task_md(task_file)["prompt"]
            prepare_one(entry, repo_root, e2e_root, prompt)
        except (OSError, ValueError) as exc:
            logger.error("准备失败，跳过 %s: %s", rel, exc)
            skipped.append(rel)
            continue
        entries.append(entry)
        logger.info("已准备 %s -> %s", entry.task_id,
                    resolve_project_dir(entry, e2e_root))

    manifest = Manifest(
        e2e_root=args.e2e_root,
        created_at=datetime.now(timezone.utc).astimezone().isoformat(),
        runs=entries,
    )
    e2e_root.mkdir(parents=True, exist_ok=True)
    manifest_path = e2e_root / "manifest.json"
    save_manifest(manifest, manifest_path)
    checklist_path = e2e_root / "执行清单.md"
    checklist_path.write_text(render_checklist(manifest, e2e_root),
                              encoding="utf-8")

    logger.info("已准备 %d 个用例，跳过 %d 个", len(entries), len(skipped))
    logger.info("manifest: %s", manifest_path)
    logger.info("人工执行清单: %s", checklist_path)
    if skipped:
        logger.warning("跳过的用例: %s", ", ".join(skipped))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_prepare.py -q`
Expected: PASS — `9 passed`

- [ ] **Step 7: 冒烟验证 CLI 与 GT 隔离**

```bash
cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench
printf '%s\n' \
  'tasks/extension/02_Code_Intelligence/02_Code_Intelligence_task_001_temperature_cli_fix.md' \
  > /tmp/e2e_smoke_list.txt
python3 eval_e2e/prepare_workspaces.py \
  --task-list /tmp/e2e_smoke_list.txt --model xopglm52 --e2e-root /tmp/e2e_smoke_out
echo "--- 项目目录内容 ---"
find /tmp/e2e_smoke_out -type f | sort
echo "--- GT 泄漏检查（必须无输出）---"
find /tmp/e2e_smoke_out -name 'expected.json' -o -type d -name gt
```

Expected: 项目目录含 `tmp_workspace/project/converter.py`、`prompt_original.txt`、
`prompt_desktop.txt`，以及 `manifest.json` 与 `执行清单.md`；GT 泄漏检查**无任何输出**。

- [ ] **Step 8: 提交**

```bash
git add eval_e2e/prepare_workspaces.py tests/test_e2e_prepare.py
git commit -m "feat(e2e): 新增 prepare 阶段（拷 exec/、双份 Prompt、人工清单）"
```

---

### Task 5: collect 阶段（匹配轨迹、落同构结果目录）

**Files:**
- Create: `eval_e2e/collect_runs.py`
- Test: `tests/test_e2e_collect.py`

**Interfaces:**
- Consumes:
  - Task 1：`Manifest`, `RunEntry`, `load_manifest`, `save_manifest`, `resolve_project_dir`, `HARNESS_NAME`, `STATUS_COLLECTED`, `STATUS_TRACE_MISSING`
  - Task 3：`find_trace`, `parse_usage`, `DEFAULT_TRACE_ROOT`
- Produces:
  - `run_dir_for(out_root: Path, entry: RunEntry, run_slug: str) -> Path`
    → `<out_root>/round-1/<model>/astroncode-desktop/<category>/<task_id>/<run_slug>/`
  - `make_run_slug(entry: RunEntry, now: datetime) -> str` → `<model>_<YYYYmmdd>_<HHMM>_<6位hash>`
  - `collect_one(entry: RunEntry, e2e_root: Path, out_root: Path, trace_root: Path, now: datetime) -> dict`
    返回 `{"status": ..., "run_dir": ..., "note": ...}`，单例失败不抛异常
  - `snapshot_project(project_dir: Path, run_dir: Path) -> None`（拷项目目录到 `task_output/`）

结果目录内文件：`chat.jsonl`、`usage.json`、`task_output/`、`manifest_entry.json`、`execution_status.json`。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_e2e_collect.py`：

```python
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from eval_e2e.collect_runs import (
    collect_one,
    make_run_slug,
    run_dir_for,
    snapshot_project,
)
from eval_e2e.e2e_manifest import RunEntry

NOW = datetime(2026, 8, 10, 16, 34)


def _entry() -> RunEntry:
    return RunEntry(
        task_id="02_Code_task_001", category="02_Code",
        task_file="tasks/x.md", workspace_src="workspace/02_Code/task_001",
        project_dir="xopglm52/02_Code_task_001/tmp_workspace",
        model="xopglm52", reasoning_effort="medium",
        prompt_rewritten=True, prompt_rewrite_map={}, status="pending",
    )


def _write_trace(root: Path, name: str, cwd: str, ts: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    rows = [
        {"timestamp": ts, "type": "session_meta", "payload": {"cwd": cwd}},
        {"type": "function_call", "payload": {"name": "shell"}},
        {"type": "token_count", "payload": {"total_token_usage": {
            "input_tokens": 10, "output_tokens": 2,
            "cached_input_tokens": 1, "total_tokens": 12}}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


class RunDirTest(unittest.TestCase):
    def test_layout_matches_cli_side_structure(self) -> None:
        got = run_dir_for(Path("/out"), _entry(), "slug1")
        self.assertEqual(
            got,
            Path("/out/round-1/xopglm52/astroncode-desktop/02_Code/"
                 "02_Code_task_001/slug1"),
        )

    def test_slug_contains_model_and_timestamp(self) -> None:
        slug = make_run_slug(_entry(), NOW)
        self.assertTrue(slug.startswith("xopglm52_20260810_1634_"))
        self.assertEqual(len(slug.rsplit("_", 1)[-1]), 6)


class SnapshotTest(unittest.TestCase):
    def test_copies_project_files_into_task_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "tmp_workspace" / "project"
            proj.mkdir(parents=True)
            (proj / "converter.py").write_text("y = 2\n", encoding="utf-8")
            run_dir = root / "run"
            run_dir.mkdir()
            snapshot_project(root / "tmp_workspace", run_dir)
        self.assertTrue((run_dir / "task_output" / "project" / "converter.py").is_file())


class CollectOneTest(unittest.TestCase):
    def _setup(self, tmp: str):
        root = Path(tmp)
        e2e_root = root / "e2e"
        entry = _entry()
        proj = e2e_root / entry.project_dir
        (proj / "project").mkdir(parents=True)
        (proj / "project" / "converter.py").write_text("z = 3\n", encoding="utf-8")
        return root, e2e_root, entry, proj

    def test_writes_chat_usage_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, entry, proj = self._setup(tmp)
            trace_root = root / "sessions"
            _write_trace(trace_root, "hit.jsonl", str(proj), "2026-08-10T12:05:00Z")
            got = collect_one(entry, e2e_root, root / "out", trace_root, NOW)
            run_dir = Path(got["run_dir"])
            usage = json.loads((run_dir / "usage.json").read_text(encoding="utf-8"))
        self.assertEqual(got["status"], "collected")
        self.assertTrue((run_dir / "chat.jsonl").is_file())
        self.assertTrue((run_dir / "task_output" / "project" / "converter.py").is_file())
        self.assertEqual(usage["tool_calls"], 1)
        self.assertEqual(usage["total_tokens"], 12)

    def test_records_trace_missing_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, entry, _ = self._setup(tmp)
            trace_root = root / "sessions"
            trace_root.mkdir()
            got = collect_one(entry, e2e_root, root / "out", trace_root, NOW)
            run_dir = Path(got["run_dir"])
            status = json.loads(
                (run_dir / "execution_status.json").read_text(encoding="utf-8"))
        self.assertEqual(got["status"], "trace_missing")
        self.assertEqual(status["status"], "trace_missing")
        self.assertFalse((run_dir / "chat.jsonl").exists())

    def test_persists_prompt_rewrite_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, entry, proj = self._setup(tmp)
            entry.prompt_rewrite_map = {"/tmp_workspace": str(proj)}
            trace_root = root / "sessions"
            _write_trace(trace_root, "h.jsonl", str(proj), "2026-08-10T12:05:00Z")
            got = collect_one(entry, e2e_root, root / "out", trace_root, NOW)
            saved = json.loads((Path(got["run_dir"]) / "manifest_entry.json")
                               .read_text(encoding="utf-8"))
        self.assertTrue(saved["prompt_rewritten"])
        self.assertEqual(saved["prompt_rewrite_map"]["/tmp_workspace"], str(proj))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_collect.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_e2e.collect_runs'`

- [ ] **Step 3: 写最小实现（模块函数部分）**

创建 `eval_e2e/collect_runs.py`：

```python
"""阶段②：匹配桌面端轨迹，落成与 CLI 同构的结果目录。

结果目录布局与 CLI 侧一致：
    <out>/round-1/<model>/astroncode-desktop/<category>/<task_id>/<run_slug>/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval_e2e.e2e_manifest import (  # noqa: E402
    HARNESS_NAME,
    STATUS_COLLECTED,
    STATUS_TRACE_MISSING,
    Manifest,
    RunEntry,
    load_manifest,
    resolve_project_dir,
    save_manifest,
)
from eval_e2e.trace_match import (  # noqa: E402
    DEFAULT_TRACE_ROOT,
    find_trace,
    parse_usage,
)

logger = logging.getLogger("e2e.collect")


def make_run_slug(entry: RunEntry, now: datetime) -> str:
    digest = hashlib.sha1(
        f"{entry.task_id}|{entry.model}|{now.isoformat()}".encode("utf-8")
    ).hexdigest()[:6]
    return f"{entry.model}_{now:%Y%m%d_%H%M}_{digest}"


def run_dir_for(out_root: Path, entry: RunEntry, run_slug: str) -> Path:
    return (
        out_root / "round-1" / entry.model / HARNESS_NAME
        / entry.category / entry.task_id / run_slug
    )


def snapshot_project(project_dir: Path, run_dir: Path) -> None:
    dest = run_dir / "task_output"
    if dest.exists():
        shutil.rmtree(dest)
    if project_dir.is_dir():
        shutil.copytree(project_dir, dest)
    else:
        dest.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: 追加 collect_one**

在 `eval_e2e/collect_runs.py` 末尾追加：

```python
def collect_one(
    entry: RunEntry,
    e2e_root: Path,
    out_root: Path,
    trace_root: Path,
    now: datetime,
) -> dict:
    """采集单个 run。任何失败都记录状态并返回，不向上抛异常。"""
    project_dir = resolve_project_dir(entry, e2e_root)
    run_slug = make_run_slug(entry, now)
    run_dir = run_dir_for(out_root, entry, run_slug)
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "manifest_entry.json").write_text(
        json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    trace_path, note = find_trace(
        trace_root, project_dir, entry.started_at, entry.finished_at
    )

    if trace_path is None:
        status = STATUS_TRACE_MISSING
        logger.warning("[%s] 轨迹未命中：%s", entry.task_id, note)
    else:
        status = STATUS_COLLECTED
        shutil.copyfile(trace_path, run_dir / "chat.jsonl")
        usage = parse_usage(trace_path)
        (run_dir / "usage.json").write_text(
            json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("[%s] 轨迹命中（%s）：%s", entry.task_id, note, trace_path)

    snapshot_project(project_dir, run_dir)

    payload = {
        "task_id": entry.task_id,
        "status": status,
        "note": note,
        "harness": HARNESS_NAME,
        "model": entry.model,
        "reasoning_effort": entry.reasoning_effort,
        "trace_path": str(trace_path) if trace_path else "",
        "collected_at": now.isoformat(),
    }
    (run_dir / "execution_status.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    entry.status = status
    return {"status": status, "run_dir": str(run_dir), "note": note}
```

- [ ] **Step 5: 追加 CLI 入口**

在 `eval_e2e/collect_runs.py` 末尾追加：

```python
def main() -> None:
    parser = argparse.ArgumentParser(
        description="阶段②：采集桌面端轨迹与产物，落成同构结果目录"
    )
    parser.add_argument("--manifest", required=True,
                        help="prepare 阶段产出的 manifest.json 路径")
    parser.add_argument("--e2e-root", default="",
                        help="项目目录根（默认取 manifest 内 e2e_root，相对仓库根解析）")
    parser.add_argument("--out-root", required=True, help="评测结果输出根目录")
    parser.add_argument("--trace-root", default=DEFAULT_TRACE_ROOT,
                        help=f"桌面端轨迹根目录（默认 {DEFAULT_TRACE_ROOT}）")
    parser.add_argument("--only", default="", help="仅采集指定 task_id")
    parser.add_argument("--resume", action="store_true",
                        help="跳过 status 已为 collected/graded 的用例")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_path)

    e2e_root = Path(args.e2e_root).expanduser() if args.e2e_root \
        else (REPO_ROOT / manifest.e2e_root)
    e2e_root = e2e_root.resolve()
    out_root = Path(args.out_root).expanduser().resolve()
    trace_root = Path(args.trace_root).expanduser()

    if not trace_root.is_dir():
        logger.error(
            "轨迹根目录不存在：%s（用 --trace-root 指定桌面端实际轨迹目录）",
            trace_root,
        )

    now = datetime.now()
    collected = missing = skipped = 0
    for entry in manifest.runs:
        if args.only and entry.task_id != args.only:
            continue
        if args.resume and entry.status in (STATUS_COLLECTED, "graded"):
            skipped += 1
            continue
        result = collect_one(entry, e2e_root, out_root, trace_root, now)
        if result["status"] == STATUS_COLLECTED:
            collected += 1
        else:
            missing += 1

    save_manifest(manifest, manifest_path)
    logger.info("采集完成：命中 %d，轨迹缺失 %d，跳过 %d",
                collected, missing, skipped)
    logger.info("结果根目录：%s", out_root)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_collect.py -q`
Expected: PASS — `7 passed`

- [ ] **Step 7: 提交**

```bash
git add eval_e2e/collect_runs.py tests/test_e2e_collect.py
git commit -m "feat(e2e): 新增 collect 阶段，匹配轨迹并落同构结果目录"
```

---

### Task 6: grade 阶段（挂载项目目录，复用 run_grading）

**Files:**
- Create: `eval_e2e/grade_runs.py`
- Test: `tests/test_e2e_grade.py`

**Interfaces:**
- Consumes:
  - Task 1：`RunEntry`, `load_manifest`, `resolve_project_dir`, `resolve_repo_path`, `HARNESS_NAME`, `STATUS_GRADED`
  - Task 5：`run_dir_for`
  - 现有（只读复用）：`parse_task_md`, `run_grading`, `write_error_score`, `start_container`, `remove_container`
- Produces:
  - `DEFAULT_DOCKER_IMAGE: str = "wildclawbench-astroncode-ubuntu:v0.4"`
  - `copy_gt_into_container(task_id: str, workspace_src: Path) -> bool`
    存在 `gt/` 时 `docker cp` 到 `<task_id>:/tmp_workspace/gt`，复刻 `eval/run_batch.py:130` 手法
  - `grade_one(entry, repo_root, e2e_root, out_root, docker_image, run_dir=None) -> dict`
    返回 `{"status": ..., "scores": ...}`；异常时经 `write_error_score()` 落盘，不抛出
  - `find_existing_run_dir(out_root: Path, entry: RunEntry) -> Path | None`（取最新 run_slug 目录）

容器名沿用 `task_id`，与 CLI 侧一致，使 `run_grading()` 内的 `docker exec` 直接命中。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_e2e_grade.py`。Docker 与 `run_grading` 用 `unittest.mock.patch` 替身，
使测试无需 Docker 即可跑：

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eval_e2e.e2e_manifest import RunEntry
from eval_e2e.grade_runs import (
    DEFAULT_DOCKER_IMAGE,
    copy_gt_into_container,
    find_existing_run_dir,
    grade_one,
)


def _entry() -> RunEntry:
    return RunEntry(
        task_id="02_Code_task_001", category="02_Code",
        task_file="tasks/x.md", workspace_src="workspace/02_Code/task_001",
        project_dir="xopglm52/02_Code_task_001/tmp_workspace",
        model="xopglm52", reasoning_effort="medium",
        prompt_rewritten=True, prompt_rewrite_map={}, status="collected",
    )


TASK_MD = """---
id: 02_Code_task_001
category: 02_Code
timeout_seconds: 300
grading_type: automated
---
## Prompt

改 /tmp_workspace/project/converter.py

## Automated Checks

```python
def grade(**kwargs) -> dict:
    return {"overall_score": 1.0}
```

## Workspace Path

```
workspace/02_Code/task_001
```

## Env

```
```
"""


def _setup(tmp: str):
    root = Path(tmp)
    (root / "tasks").mkdir(parents=True)
    (root / "tasks" / "x.md").write_text(TASK_MD, encoding="utf-8")
    src = root / "workspace" / "02_Code" / "task_001"
    (src / "exec").mkdir(parents=True)
    (src / "gt").mkdir(parents=True)
    (src / "gt" / "expected.json").write_text("{}", encoding="utf-8")
    e2e_root = root / "e2e"
    proj = e2e_root / "xopglm52" / "02_Code_task_001" / "tmp_workspace"
    proj.mkdir(parents=True)
    return root, e2e_root, proj


class DefaultsTest(unittest.TestCase):
    def test_default_image_is_astroncode_v04(self) -> None:
        self.assertEqual(DEFAULT_DOCKER_IMAGE,
                         "wildclawbench-astroncode-ubuntu:v0.4")


class CopyGtTest(unittest.TestCase):
    def test_copies_gt_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ws"
            (src / "gt").mkdir(parents=True)
            with mock.patch("eval_e2e.grade_runs.subprocess.run") as run:
                run.return_value = mock.Mock(returncode=0, stderr="")
                got = copy_gt_into_container("t1", src)
            args = run.call_args[0][0]
        self.assertTrue(got)
        self.assertIn("cp", args)
        self.assertEqual(args[-1], "t1:/tmp_workspace/gt")

    def test_skips_when_gt_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ws"
            src.mkdir()
            with mock.patch("eval_e2e.grade_runs.subprocess.run") as run:
                got = copy_gt_into_container("t1", src)
        self.assertFalse(got)
        run.assert_not_called()


class GradeOneTest(unittest.TestCase):
    def test_mounts_project_dir_and_writes_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, proj = _setup(tmp)
            out_root = root / "out"
            run_dir = out_root / "round-1" / "xopglm52" / "astroncode-desktop" \
                / "02_Code" / "02_Code_task_001" / "slug1"
            run_dir.mkdir(parents=True)
            with mock.patch("eval_e2e.grade_runs.start_container") as start, \
                 mock.patch("eval_e2e.grade_runs.remove_container") as remove, \
                 mock.patch("eval_e2e.grade_runs.copy_gt_into_container",
                            return_value=True), \
                 mock.patch("eval_e2e.grade_runs.run_grading",
                            return_value={"overall_score": 0.75}) as grading:
                got = grade_one(_entry(), root, e2e_root, out_root,
                                DEFAULT_DOCKER_IMAGE, run_dir=run_dir)
            score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
        self.assertEqual(got["status"], "graded")
        self.assertEqual(score["overall_score"], 0.75)
        # 项目目录被挂为容器工作区
        self.assertEqual(start.call_args.args[1], str(proj))
        self.assertEqual(start.call_args.kwargs["docker_image"], DEFAULT_DOCKER_IMAGE)
        remove.assert_called()
        # grade 参数由 parse_task_md 原样透传
        self.assertIn("def grade", grading.call_args.kwargs["automated_checks"])

    def test_writes_error_score_when_grading_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, _ = _setup(tmp)
            out_root = root / "out"
            run_dir = out_root / "r"
            run_dir.mkdir(parents=True)
            with mock.patch("eval_e2e.grade_runs.start_container"), \
                 mock.patch("eval_e2e.grade_runs.remove_container") as remove, \
                 mock.patch("eval_e2e.grade_runs.copy_gt_into_container",
                            return_value=True), \
                 mock.patch("eval_e2e.grade_runs.run_grading",
                            side_effect=RuntimeError("boom")):
                got = grade_one(_entry(), root, e2e_root, out_root,
                                DEFAULT_DOCKER_IMAGE, run_dir=run_dir)
        self.assertEqual(got["status"], "error")
        self.assertTrue((run_dir / "score.json").is_file())
        remove.assert_called()  # 异常路径也要清理容器

    def test_removes_container_even_when_start_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, _ = _setup(tmp)
            run_dir = root / "out" / "r"
            run_dir.mkdir(parents=True)
            with mock.patch("eval_e2e.grade_runs.start_container",
                            side_effect=RuntimeError("no docker")), \
                 mock.patch("eval_e2e.grade_runs.remove_container") as remove:
                got = grade_one(_entry(), root, e2e_root, root / "out",
                                DEFAULT_DOCKER_IMAGE, run_dir=run_dir)
        self.assertEqual(got["status"], "error")
        remove.assert_called()


class FindRunDirTest(unittest.TestCase):
    def test_picks_latest_slug_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "round-1" / "xopglm52" / "astroncode-desktop" \
                / "02_Code" / "02_Code_task_001"
            (base / "xopglm52_20260810_1200_aaaaaa").mkdir(parents=True)
            latest = base / "xopglm52_20260810_1634_bbbbbb"
            latest.mkdir(parents=True)
            got = find_existing_run_dir(Path(tmp), _entry())
        self.assertEqual(got, latest)

    def test_returns_none_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_existing_run_dir(Path(tmp), _entry()))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_grade.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval_e2e.grade_runs'`

- [ ] **Step 3: 写模块函数**

创建 `eval_e2e/grade_runs.py`：

```python
"""阶段③：把项目目录挂为容器 /tmp_workspace 并复用现有 run_grading 评分。

评分口径与 CLI 侧同源同码：容器内路径固定 /tmp_workspace，gt/ 在评分前单独
docker cp 进容器（复刻 eval/run_batch.py:130），grade() 参数由 parse_task_md
原样透传。
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval_e2e.collect_runs import run_dir_for  # noqa: E402
from eval_e2e.e2e_manifest import (  # noqa: E402
    HARNESS_NAME,
    STATUS_GRADED,
    RunEntry,
    load_manifest,
    resolve_project_dir,
    resolve_repo_path,
    save_manifest,
)
from src.utils.docker_utils import remove_container, start_container  # noqa: E402
from src.utils.grading import run_grading, write_error_score  # noqa: E402
from src.utils.task_parser import parse_task_md  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_DOCKER_IMAGE = "wildclawbench-astroncode-ubuntu:v0.4"
TMP_WORKSPACE = "/tmp_workspace"


def copy_gt_into_container(task_id: str, workspace_src: Path) -> bool:
    """把源工作区的 gt/ 送进容器；无 gt/ 时跳过。"""
    gt_host = workspace_src / "gt"
    if not gt_host.is_dir():
        return False
    proc = subprocess.run(
        ["docker", "cp", str(gt_host), f"{task_id}:{TMP_WORKSPACE}/gt"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        logger.warning("[%s] gt 拷入失败: %s", task_id, proc.stderr)
        return False
    return True


def find_existing_run_dir(out_root: Path, entry: RunEntry) -> Path | None:
    base = (out_root / "round-1" / entry.model / HARNESS_NAME
            / entry.category / entry.task_id)
    if not base.is_dir():
        return None
    slugs = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    return slugs[-1] if slugs else None
```

- [ ] **Step 4: 追加 grade_one**

在 `eval_e2e/grade_runs.py` 末尾追加：

```python
def grade_one(
    entry: RunEntry,
    repo_root: Path,
    e2e_root: Path,
    out_root: Path,
    docker_image: str,
    run_dir: Path | None = None,
) -> dict:
    """单例评分：起容器 → 送 gt → run_grading → 写 score.json。异常不外抛。"""
    if run_dir is None:
        run_dir = find_existing_run_dir(out_root, entry)
    if run_dir is None:
        return {"status": "error", "note": "结果目录不存在，请先运行 collect_runs.py"}
    run_dir.mkdir(parents=True, exist_ok=True)

    task_file = resolve_repo_path(entry.task_file, repo_root)
    workspace_src = resolve_repo_path(entry.workspace_src, repo_root)
    project_dir = resolve_project_dir(entry, e2e_root)
    task_id = entry.task_id

    try:
        task = parse_task_md(task_file)
    except (OSError, ValueError) as exc:
        write_error_score(run_dir, task_id, f"用例解析失败: {exc}")
        return {"status": "error", "note": str(exc)}

    try:
        remove_container(task_id)
        start_container(
            task_id, str(project_dir),
            extra_env=task.get("env", ""),
            docker_image=docker_image,
        )
        copy_gt_into_container(task_id, workspace_src)
        scores = run_grading(
            task_id=task_id,
            automated_checks=task.get("automated_checks", ""),
            output_dir=run_dir,
            extra_env=task.get("env", ""),
            transcript_container_path="",
            write_error_score=True,
            llm_judge_rubric=task.get("llm_judge_rubric", ""),
            rubric_criteria=task.get("rubric_criteria") or [],
            grading_weights=task.get("grading_weights") or {},
        )
    except Exception as exc:  # 容器/评分任何失败都落盘并继续
        logger.error("[%s] 评分失败: %s", task_id, exc)
        write_error_score(run_dir, task_id, str(exc))
        return {"status": "error", "note": str(exc)}
    finally:
        remove_container(task_id)

    entry.status = STATUS_GRADED
    return {"status": STATUS_GRADED, "scores": scores, "run_dir": str(run_dir)}
```

`run_grading()` 自身会把 `score.json` 写入 `output_dir`，故无需重复写盘。
`transcript_container_path` 传空字符串：桌面端轨迹不在容器内，需要 transcript
的用例由 `load_transcript()` 的回退路径处理，返回空列表而非报错。

- [ ] **Step 5: 追加 CLI 入口**

在 `eval_e2e/grade_runs.py` 末尾追加：

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="端到端评测阶段③：评分")
    parser.add_argument("--manifest", required=True, help="manifest.json 路径")
    parser.add_argument("--e2e-root", default="", help="项目目录根，默认取 manifest 内相对值")
    parser.add_argument("--out-root", required=True, help="结果根目录（同 collect 阶段）")
    parser.add_argument("--docker-image", default=DEFAULT_DOCKER_IMAGE)
    parser.add_argument("--only", default="", help="只处理指定 task_id")
    parser.add_argument("--resume", action="store_true", help="跳过已评分项")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_path)
    e2e_root = (Path(args.e2e_root).expanduser().resolve() if args.e2e_root
                else resolve_repo_path(manifest.e2e_root, repo_root))
    out_root = Path(args.out_root).expanduser().resolve()

    graded = failed = skipped = 0
    for entry in manifest.runs:
        if args.only and entry.task_id != args.only:
            continue
        if args.resume and entry.status == STATUS_GRADED:
            skipped += 1
            continue
        result = grade_one(entry, repo_root, e2e_root, out_root, args.docker_image)
        if result["status"] == STATUS_GRADED:
            graded += 1
            logger.info("[%s] 评分完成", entry.task_id)
        else:
            failed += 1
            logger.warning("[%s] 评分失败: %s", entry.task_id, result.get("note", ""))

    save_manifest(manifest, manifest_path)
    logger.info("评分完成：成功 %d，失败 %d，跳过 %d", graded, failed, skipped)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_grade.py -q`
Expected: PASS — `8 passed`

- [ ] **Step 7: 确认未修改任何现有文件**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && git status --porcelain`
Expected: 输出中只有 `eval_e2e/` 与 `tests/test_e2e_*.py` 的新增项（`??` 或 `A`），
`src/`、`eval/`、`tasks/`、`workspace/`、`tools/` 下**无任何 `M` 修改标记**。
若出现 `M`，说明违反了全局约束，须回退该改动。

- [ ] **Step 8: 提交**

```bash
git add eval_e2e/grade_runs.py tests/test_e2e_grade.py
git commit -m "feat(e2e): 新增评分阶段，复用 run_grading 保证与 CLI 同源"
```

---

### Task 7: README 与全链路冒烟验证

**Files:**
- Create: `eval_e2e/README.md`
- Test: 手动冒烟（本任务无新单测，验证前 6 个任务的集成）

**Interfaces:**
- Consumes: Task 1-6 全部产出
- Produces: 无新代码接口；产出可交付的使用文档与一次全链路验证记录

- [ ] **Step 1: 写 README**

创建 `eval_e2e/README.md`：

````markdown
# AstronCode 桌面端端到端评测（eval_e2e）

用 WildClawBench 现有用例在 **AstronCode 桌面客户端**上做端到端评测，
与 CLI 侧结果对比，验证两种产品形态的多模型评测结论是否一致。

评分复用 `src/utils/grading.py`（import，不复制），与 CLI 侧**同源同码**，
故分差可归因为产品形态差异而非评分器差异。

## 三阶段流程

```
① prepare  →  [人工在桌面端执行]  →  ② collect  →  ③ grade  →  tools/report
```

三个脚本通过 `manifest.json` 串联，人工执行插在中间。

## ① 准备工作空间

```bash
python3 eval_e2e/prepare_workspaces.py \
  --task-list my_e2e_tasks.txt \
  --model xopglm52 \
  --reasoning-effort medium \
  --e2e-root eval_out_e2e
```

`--task-list` 是纯文本文件，每行一个用例 md 的仓库相对路径，`#` 开头为注释：

```
tasks/extension/02_Code_Intelligence/02_Code_Intelligence_task_001_temperature_cli_fix.md
tasks/extension/02_Code_Intelligence/02_Code_Intelligence_task_002_inventory_aggregator.md
```

产出：

- `eval_out_e2e/<model>/<task_id>/tmp_workspace/` — 项目目录，**不含 GT**
- `eval_out_e2e/<model>/<task_id>/prompt_desktop.txt` — 改写过路径，供粘贴
- `eval_out_e2e/<model>/<task_id>/prompt_original.txt` — 原文，供审计
- `eval_out_e2e/manifest.json`
- `eval_out_e2e/执行清单.md` — 人工执行清单

## ② 人工在桌面端执行

按 `执行清单.md` 逐个用例操作：

1. 桌面端新建项目，路径选清单里的项目目录（尾部为 `tmp_workspace`）
2. 选清单指定的模型与推理强度
3. 粘贴 `prompt_desktop.txt` 全文，触发执行
4. 执行结束后在清单上打勾，进入下一个用例

## ③ 采集轨迹与产物

```bash
python3 eval_e2e/collect_runs.py \
  --e2e-root eval_out_e2e \
  --out-root eval_out_e2e/results \
  --trace-root ~/.acode/sessions
```

`--trace-root` 默认 `~/.acode/sessions`。**若桌面端轨迹目录不同，用该参数覆盖**；
目录不存在时显式报错，不静默漏采。

轨迹按 `session_meta.payload.cwd` 匹配项目目录 + `timestamp` 落在执行时间窗定位。
多命中取最新并告警，零命中记 `trace_missing` 并继续处理其余用例。

## ④ 评分

```bash
python3 eval_e2e/grade_runs.py \
  --e2e-root eval_out_e2e \
  --out-root eval_out_e2e/results \
  --docker-image wildclawbench-astroncode-ubuntu:v0.4
```

把项目目录挂为容器 `/tmp_workspace`，单独 `docker cp` 送入 `gt/`，再调 `run_grading()`。
需要本机 Docker 与该镜像。

## ⑤ 出报告

结果目录与 CLI 侧同构，harness 名为 `astroncode-desktop`：

```
eval_out_e2e/results/round-1/<model>/astroncode-desktop/<category>/<task_id>/<run-slug>/
    score.json  usage.json  chat.jsonl  task_output/  manifest_entry.json  execution_status.json
```

可直接交给 `tools/report`，与 CLI 侧 `astroncode` 并列对比：

```bash
python3 tools/report/scripts/generate_eval_report.py \
  --result-root eval_out_e2e/results/round-1 \
  --models xopglm52 \
  --harnesses astroncode astroncode-desktop \
  --target-model xopglm52
```

## 通用参数

| 参数 | 说明 |
|---|---|
| `--only <task_id>` | 只处理单个用例，用于重跑 |
| `--resume` | 跳过已完成项 |

## 设计要点

- **GT 隔离**：prepare 只拷源工作区的 `exec/`，`gt/` 留在仓库，仅评分时进容器。
- **路径对齐**：容器内固定 `/tmp_workspace`（184 个用例中 164 个的 `grade()` 硬编码该字面量，
  用例一律不改）；项目目录尾部也命名 `tmp_workspace`，故 Prompt 只需替换前缀。
- **可移植**：`manifest.json` 内路径全为相对路径，换机器只需换 `--e2e-root`。
- **唯一输入差异**：桌面端 Prompt 的路径前缀。已保留双份 Prompt 与
  `prompt_rewrite_map` 供报告披露。

## 已知报告侧适配点

`tools/report/scripts/generate_eval_report.py:350` 按 harness 名选 request 抽取器，
`astroncode-desktop` 未在白名单内，else 分支会 `raise ValueError`。该分支**仅对分档定价模型触发**
（单档定价在 342 行提前返回）。本链路在 collect 阶段已把 `usage.json` 写全，报告无需回退解析。
若后续要对分档定价模型出成本对比，在报告侧把 `astroncode-desktop` 并入 Codex 系分支即可。

## 未纳入

- Codex Computer Use 自动化驱动桌面端（执行环节已可替换，补自动化不需改采集与评分）
- 多轮 round-N 统计（当前固定 `round-1`）
- 异常检测（`src/utils/anomalies.py` 面向容器内 `agent.log`，桌面端无对应日志源）
````

- [ ] **Step 2: 跑全量单测**

Run: `cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench && python3 -m pytest tests/test_e2e_*.py -q`
Expected: PASS，全部 e2e 测试通过，无 F/E

- [ ] **Step 3: 确认未改动任何现有文件**

Run:
```bash
cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench
git status --porcelain
```
Expected: 输出只含 `eval_e2e/`、`tests/test_e2e_*.py`、`docs/superpowers/` 下的新增项（`??` 或 `A`）。
**若出现任何现有文件的 `M`（modified），停下来向用户报告**——全局约束要求不改现有文件。

- [ ] **Step 4: 冒烟①—— prepare 真实用例**

Run:
```bash
cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench
printf '%s\n' \
  'tasks/extension/02_Code_Intelligence/02_Code_Intelligence_task_001_temperature_cli_fix.md' \
  > /tmp/e2e_smoke_list.txt
python3 eval_e2e/prepare_workspaces.py \
  --task-list /tmp/e2e_smoke_list.txt \
  --model xopglm52 --reasoning-effort medium \
  --e2e-root /tmp/e2e_smoke_out
```
Expected: 打印准备了 1 个用例；`/tmp/e2e_smoke_out/manifest.json` 与 `执行清单.md` 存在。

- [ ] **Step 5: 冒烟②—— GT 隔离与 Prompt 改写断言**

Run:
```bash
cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench
task=02_Code_Intelligence_task_001_temperature_cli_fix
case_dir=/tmp/e2e_smoke_out/xopglm52/$task
echo "--- GT 泄漏检查（应为空）---"
find "$case_dir/tmp_workspace" \( -name gt -o -name 'expected.json' \) -print
echo "--- 项目文件应存在 ---"
test -f "$case_dir/tmp_workspace/project/converter.py" && echo OK-converter
echo "--- manifest 内 project_dir 应为相对路径 ---"
python3 -c "
import json
d=json.load(open('/tmp/e2e_smoke_out/manifest.json'))
p=d['runs'][0]['project_dir']
print('project_dir =', p)
assert not p.startswith('/'), 'project_dir 必须是相对路径'
print('OK-relative')
"
echo "--- Prompt 改写应命中项目目录 ---"
grep -q "$case_dir/tmp_workspace/project/converter.py" "$case_dir/prompt_desktop.txt" \
  && echo OK-rewritten
grep -q '/tmp_workspace/project/converter.py' "$case_dir/prompt_original.txt" \
  && echo OK-original-kept
```
Expected: GT 检查无输出；`OK-converter`、`OK-relative`、`OK-rewritten`、`OK-original-kept` 全部打印。

- [ ] **Step 6: 冒烟③—— 轨迹缺失时 collect 不崩**

Run:
```bash
cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench
mkdir -p /tmp/e2e_smoke_sessions
python3 eval_e2e/collect_runs.py \
  --e2e-root /tmp/e2e_smoke_out \
  --out-root /tmp/e2e_smoke_out/results \
  --trace-root /tmp/e2e_smoke_sessions
echo "exit=$?"
find /tmp/e2e_smoke_out/results -name execution_status.json -exec cat {} \;
```
Expected: 退出码 0（单例失败不中断批次）；`execution_status.json` 内 `status` 为 `trace_missing`。

- [ ] **Step 7: 清理冒烟产物**

Run:
```bash
rm -rf /tmp/e2e_smoke_out /tmp/e2e_smoke_sessions /tmp/e2e_smoke_list.txt
echo cleaned
```
Expected: `cleaned`

- [ ] **Step 8: 提交**

```bash
cd /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench
git add eval_e2e/README.md
git commit -m "docs(e2e): 新增 eval_e2e 三阶段使用说明"
```

---

## 交付后待办

以下两项依赖实机与用户输入，不在本计划的可完成范围内，实现完成后需要用户配合：

1. **确认桌面端轨迹根目录**。计划默认 `~/.acode/sessions`（对齐 CLI 侧 `/root/.acode/sessions` 命名），
   本机未安装桌面端故无法验证。实机确认后若不符，用 `--trace-root` 覆盖；若默认值确定是错的，
   改 `eval_e2e/trace_match.py` 的 `DEFAULT_TRACE_ROOT` 一行。
2. **确认桌面端轨迹字段名**。计划按 Codex Desktop 实测格式解析
   （首行 `type: session_meta`、`payload.cwd`、`token_count` 事件的 `total_token_usage`）。
   AstronCode 桌面端若字段名不同，只需适配 `eval_e2e/trace_match.py` 的
   `read_session_meta()` 与 `parse_usage()`，其余阶段不受影响。

另需用户提供最终的用例 task-list 清单（用户已确认稍后提供）。

