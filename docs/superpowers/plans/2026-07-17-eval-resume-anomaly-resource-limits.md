# 跑批可靠性闭环实施计划（resume + 异常检测 + 资源限额）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 WildClawBench 补齐选型报告 §6 的第一迭代三能力：断点续跑/选择性重跑（`--resume`/`--rerun-error`/`--rerun-anomalous`）、13 类异常检测（每 run 落 `anomalies.json` + 批级 `anomaly_report.json` + 历史回溯扫描）、容器资源限额（`--memory`/`--cpus`，**不加参数则行为与现状完全一致**）。

**Architecture:** 异常检测为独立纯函数模块 `src/utils/anomalies.py`（输入 = run 目录产物，无副作用，可单测可回溯）；resume 在 `run_batch.py` 任务分发前按「最新同模型 run 的 score.json + anomalies」过滤；资源限额经 `docker_utils.container_resource_args()`（读环境变量）注入全部 5 处 `docker run` 构造点，CLI 参数只负责写环境变量（CLI 优先、env 兜底，与 timeout 系参数同款模式）。

**Tech Stack:** Python 3.10+（现有框架，零新依赖）；借鉴 QwenClawBench `scripts/benchmark.py:_load_existing_results` 与 `scripts/lib_anomalies.py`（路径见选型报告 §6）。

## Global Constraints

- **默认行为零变化**：不传 `--resume`/`--memory`/`--cpus` 时，现有评测命令（速查文档全部命令块）行为与产物完全不变；异常检测只**追加**文件（`anomalies.json`），不改动任何现有产物的内容与命名
- 输出目录结构不变：`output_root/<category>/<task_id>/<short_model>_<ts>_<runid>/`
- 环境变量命名沿用 `WILDCLAW_` 前缀：`WILDCLAW_DOCKER_MEMORY` / `WILDCLAW_DOCKER_CPUS`
- 仓库无 pytest 体系，验证用 `python3 -` 内联断言 + 真实冒烟；每 Task 独立提交
- 严重级只有两档：`error`（分数不可信）/ `warning`（瞬态，分数仍有效）

---

### Task 1: 容器资源限额（最小独立改动，先行）

**Files:**
- Modify: `src/utils/docker_utils.py`（新增 `container_resource_args()`；`start_container` 的 cmd 注入，约 :68）
- Modify: `src/agents/codex/runner.py:361-374`（`_start_container` cmd 注入）
- Modify: `src/agents/astroncode/runner.py`（同上，`"run",` 在 :373 附近）
- Modify: `src/agents/claudecode/runner.py:384-392`（cmd 注入）
- Modify: `src/agents/hermesagent/runner.py:266-272`（cmd 注入）
- Modify: `src/utils/cli_args.py`（`--memory`/`--cpus`）
- Modify: `eval/run_batch.py`（main() 里 CLI → env）

**Interfaces:**
- Produces: `container_resource_args() -> list[str]`（`from src.utils.docker_utils import container_resource_args`），环境变量未设置时返回 `[]`

- [ ] **Step 1: docker_utils 增加 helper**

在 `src/utils/docker_utils.py` 顶部常量区之后加：

```python
def container_resource_args() -> list[str]:
    """任务容器资源限额参数（--memory/--cpus）。

    读环境变量 WILDCLAW_DOCKER_MEMORY / WILDCLAW_DOCKER_CPUS（由 run_batch
    的 CLI 参数写入，或用户直接 export）。都未设置时返回空列表——
    即默认无限额，现有评测命令行为不变。
    """
    args: list[str] = []
    memory = os.environ.get("WILDCLAW_DOCKER_MEMORY", "").strip()
    cpus = os.environ.get("WILDCLAW_DOCKER_CPUS", "").strip()
    if memory:
        args += ["--memory", memory]
    if cpus:
        args += ["--cpus", cpus]
    return args
```

- [ ] **Step 2: 注入 5 处 docker run**

每处都在 `"--name", task_id,` 的下一行插入 `*container_resource_args(),`：

1. `src/utils/docker_utils.py` `start_container`（openclaw 用）：
```python
    cmd = [
        "docker", "run", "-d",
        "--name", task_id,
        *container_resource_args(),
        *env_args,
        ...
```
2. `src/agents/codex/runner.py` `_start_container`（文件顶部补 `container_resource_args` 到已有的 `from src.utils.docker_utils import ...`）
3. `src/agents/astroncode/runner.py` 同上
4. `src/agents/claudecode/runner.py` 同上
5. `src/agents/hermesagent/runner.py` 同上

- [ ] **Step 3: CLI 参数**

`src/utils/cli_args.py` 在 `--timeout-override` 之后加：

```python
    parser.add_argument(
        "--memory",
        default=None,
        metavar="SIZE",
        help="Per-task container memory limit, e.g. 4g / 512m (docker --memory). "
             "CLI first; falls back to env WILDCLAW_DOCKER_MEMORY. Default: no limit",
    )
    parser.add_argument(
        "--cpus",
        default=None,
        metavar="N",
        help="Per-task container CPU limit, e.g. 2 / 1.5 (docker --cpus). "
             "CLI first; falls back to env WILDCLAW_DOCKER_CPUS. Default: no limit",
    )
```

`eval/run_batch.py` `main()` 里 TIMEOUT_OVERRIDE 解析块之后加：

```python
    if args.memory:
        os.environ["WILDCLAW_DOCKER_MEMORY"] = args.memory
    if args.cpus:
        os.environ["WILDCLAW_DOCKER_CPUS"] = str(args.cpus)
    _mem = os.environ.get("WILDCLAW_DOCKER_MEMORY", "").strip()
    _cpu = os.environ.get("WILDCLAW_DOCKER_CPUS", "").strip()
    if _mem or _cpu:
        logger.info("Container resource limits: memory=%s cpus=%s",
                    _mem or "unlimited", _cpu or "unlimited")
```

- [ ] **Step 4: 验证**

```bash
# 默认零变化：不设参数时 helper 返回空
python3 -c "
import sys, os; sys.path.insert(0,'.')
os.environ.pop('WILDCLAW_DOCKER_MEMORY', None); os.environ.pop('WILDCLAW_DOCKER_CPUS', None)
from src.utils.docker_utils import container_resource_args
assert container_resource_args() == [], container_resource_args()
os.environ['WILDCLAW_DOCKER_MEMORY']='512m'; os.environ['WILDCLAW_DOCKER_CPUS']='1.5'
assert container_resource_args() == ['--memory','512m','--cpus','1.5']
print('helper ok')"
# 真容器验证限额生效
source docs/local/deploy/export.astroncode.sh
docker run -d --name wcb_res_test --memory 512m --cpus 1 "$DOCKER_IMAGE_ASTRONCODE" tail -f /dev/null
docker inspect wcb_res_test --format 'mem={{.HostConfig.Memory}} cpus={{.HostConfig.NanoCpus}}'
docker rm -f wcb_res_test
```
Expected: `helper ok`；inspect 输出 `mem=536870912 cpus=1000000000`。

- [ ] **Step 5: Commit**

```bash
git add src/utils/docker_utils.py src/utils/cli_args.py eval/run_batch.py \
  src/agents/codex/runner.py src/agents/astroncode/runner.py \
  src/agents/claudecode/runner.py src/agents/hermesagent/runner.py
git commit -m "feat: 容器资源限额 --memory/--cpus（默认不限，零行为变化）"
```

---

### Task 2: 异常检测模块（纯函数，13 条规则）

**Files:**
- Create: `src/utils/anomalies.py`

**Interfaces:**
- Produces:
  - `scan_run_dir(run_dir: Path) -> dict`：单 run 检测，返回 `{"is_anomalous", "has_error", "items": [{"id","severity","description"}]}`
  - `scan_batch(output_root: Path) -> dict`：整批扫描（含跨 run 规则），返回聚合报告 dict
  - 常量 `ERROR = "error"` / `WARNING = "warning"`

**规则表**（改编自 QwenClawBench `lib_anomalies.py`，按 WildClawBench 产物重写输入源）：

| # | 规则 ID | 级别 | 判据（数据源） |
|---|---|---|---|
| 1 | EXECUTION_ERROR | error | `execution_status.json` `status=="error"` |
| 2 | TASK_TIMED_OUT | error | `execution_status.json` `timed_out==true` |
| 3 | EXIT_CODE_OOM | error | `execution_status.json` `exit_code==137` |
| 4 | EMPTY_TRANSCRIPT | error | `chat.jsonl` 缺失或 0 行（且非 timed_out） |
| 5 | SHORT_TRANSCRIPT | error | `chat.jsonl` 1-4 行 |
| 6 | QUICK_EXIT_SUSPICIOUS | error | `elapsed_time < 10s` 且 status=="finished" |
| 7 | ZERO_TOKEN_RUN | error | `usage.json` `request_count==0 or total_tokens==0`（且 transcript 非空） |
| 8 | SCORE_MISSING | error | `score.json` 不存在或 JSON 解析失败 |
| 9 | GRADING_SCRIPT_ERROR | error | `score.json` 顶层 `error` 含 "Grading failed" / "Traceback" |
| 10 | TOOL_CALLS_ALL_REJECTED | error | transcript 中 tool 调用 ≥3 次且 100% 的 tool_result 含 "unsupported call"/"unknown tool"（X2-300B 工具名故障签名） |
| 11 | API_RATE_LIMIT | warning* | `agent.log` 含 429/rate limit/too many requests |
| 12 | API_SERVER_ERROR | warning* | `agent.log` 含 5xx/bad gateway/service unavailable/internal server error |
| 13 | DUPLICATE_TRANSCRIPT | error | **跨 run 规则**（scan_batch）：同批内两个不同 task 的 `chat_openclaw.jsonl`（或 chat.jsonl）内容 md5 相同（曾发生的 L4 采集 bug） |

\* 11/12 与致命规则（1/3/4/7）同时命中时升级为 error（沿用 QwenClawBench 的升级逻辑）。

- [ ] **Step 1: 写模块**

```python
"""基于规则的 run 级异常检测（改编自 QwenClawBench lib_anomalies.py）。

输入是 WildClawBench 单个 run 目录的落盘产物（execution_status.json /
usage.json / chat.jsonl / agent.log / score.json），全部只读，无副作用。
异常 = 使分数不可信的基础设施/执行类问题；分 error（分数不可信）与
warning（瞬态干扰，分数仍有效）两档。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ERROR = "error"
WARNING = "warning"

_RATE_LIMIT_KEYWORDS = ("429", "rate limit", "rate_limit", "too many requests", "ratelimit")
_SERVER_ERROR_KEYWORDS = (
    "502", "503", "500", "bad gateway", "service unavailable",
    "internal server error", "internal error has occurred",
)
_TOOL_REJECT_KEYWORDS = ("unsupported call", "unknown tool")
_FATAL_IDS = {"EXECUTION_ERROR", "EXIT_CODE_OOM", "EMPTY_TRANSCRIPT", "ZERO_TOKEN_RUN"}
_API_WARNING_IDS = {"API_RATE_LIMIT", "API_SERVER_ERROR"}


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    try:
        with path.open("rb") as f:
            return f.read(max_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _transcript_lines(run_dir: Path) -> list[dict]:
    for name in ("chat.jsonl", "chat_openclaw.jsonl"):
        path = run_dir / name
        if not path.exists():
            continue
        events = []
        for line in _read_text(path).splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events
    return []


def _tool_result_texts(events: list[dict]) -> list[str]:
    texts = []
    for e in events:
        payload = e.get("payload") or e.get("message") or e
        if not isinstance(payload, dict):
            continue
        ptype = str(payload.get("type") or "").lower()
        if ptype in ("function_call_output", "tool_result"):
            texts.append(str(payload.get("output") or payload.get("content") or ""))
        content = payload.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    texts.append(str(block.get("content") or ""))
    return texts


def scan_run_dir(run_dir: Path) -> dict[str, Any]:
    """检测单个 run 目录，返回 anomalies dict（不落盘）。"""
    run_dir = Path(run_dir)
    status = _load_json(run_dir / "execution_status.json") or {}
    usage = _load_json(run_dir / "usage.json") or {}
    score = _load_json(run_dir / "score.json")
    events = _transcript_lines(run_dir)
    agent_log = _read_text(run_dir / "agent.log").lower()

    items: list[dict[str, str]] = []

    def hit(rule_id: str, severity: str, desc: str) -> None:
        items.append({"id": rule_id, "severity": severity, "description": desc})

    timed_out = bool(status.get("timed_out"))
    st = str(status.get("status") or "")
    if st == "error":
        hit("EXECUTION_ERROR", ERROR, f"execution_status=error: {str(status.get('error'))[:150]}")
    if timed_out:
        hit("TASK_TIMED_OUT", ERROR, f"timed out after {status.get('timeout_seconds')}s")
    if status.get("exit_code") == 137:
        hit("EXIT_CODE_OOM", ERROR, "exit_code=137 (SIGKILL, likely OOM)")
    if not events and not timed_out:
        hit("EMPTY_TRANSCRIPT", ERROR, "chat.jsonl missing/empty — agent may never have run")
    elif 0 < len(events) < 5:
        hit("SHORT_TRANSCRIPT", ERROR, f"transcript only {len(events)} events")
    elapsed = status.get("elapsed_time")
    if isinstance(elapsed, (int, float)) and elapsed < 10 and st == "finished":
        hit("QUICK_EXIT_SUSPICIOUS", ERROR, f"finished in {elapsed:.1f}s — suspiciously fast")
    if events and (usage.get("request_count", 0) == 0 or usage.get("total_tokens", 0) == 0):
        hit("ZERO_TOKEN_RUN", ERROR, "usage shows zero requests/tokens despite transcript")
    if score is None:
        hit("SCORE_MISSING", ERROR, "score.json missing or unparsable")
    else:
        err = str(score.get("error") or "")
        if "Grading failed" in err or "Traceback" in err:
            hit("GRADING_SCRIPT_ERROR", ERROR, f"grading error: {err[:150]}")
    tool_results = _tool_result_texts(events)
    rejected = [t for t in tool_results if any(k in t.lower() for k in _TOOL_REJECT_KEYWORDS)]
    if len(tool_results) >= 3 and len(rejected) == len(tool_results):
        hit("TOOL_CALLS_ALL_REJECTED", ERROR,
            f"all {len(tool_results)} tool calls rejected (unsupported/unknown tool) — "
            "tool-name protocol failure")
    if any(k in agent_log for k in _RATE_LIMIT_KEYWORDS):
        hit("API_RATE_LIMIT", WARNING, "rate-limit markers found in agent.log")
    if any(k in agent_log for k in _SERVER_ERROR_KEYWORDS):
        hit("API_SERVER_ERROR", WARNING, "server-error markers found in agent.log")

    triggered = {i["id"] for i in items}
    if triggered & _FATAL_IDS:
        for item in items:
            if item["id"] in _API_WARNING_IDS:
                item["severity"] = ERROR
                item["description"] += " [upgraded: co-occurs with fatal failure]"

    return {
        "is_anomalous": bool(items),
        "has_error": any(i["severity"] == ERROR for i in items),
        "items": items,
    }


def iter_run_dirs(output_root: Path):
    """遍历 output_root 下所有 run 目录（含 execution_status.json 的叶子目录）。"""
    for status_file in Path(output_root).glob("*/*/*/execution_status.json"):
        yield status_file.parent


def scan_batch(output_root: Path) -> dict[str, Any]:
    """整批扫描：逐 run 规则 + 跨 run 规则（DUPLICATE_TRANSCRIPT）。"""
    output_root = Path(output_root)
    runs: dict[str, dict] = {}
    digests: dict[str, list[str]] = {}
    for run_dir in iter_run_dirs(output_root):
        rel = str(run_dir.relative_to(output_root))
        runs[rel] = scan_run_dir(run_dir)
        for name in ("chat_openclaw.jsonl", "chat.jsonl"):
            path = run_dir / name
            if path.exists() and path.stat().st_size > 0:
                digest = hashlib.md5(path.read_bytes()).hexdigest()
                digests.setdefault(digest, []).append(rel)
                break
    for digest, rels in digests.items():
        tasks = {r.split("/")[1] for r in rels}
        if len(tasks) > 1:
            for rel in rels:
                runs[rel]["items"].append({
                    "id": "DUPLICATE_TRANSCRIPT", "severity": ERROR,
                    "description": f"transcript md5 {digest[:8]} shared across tasks: {sorted(tasks)}",
                })
                runs[rel]["is_anomalous"] = True
                runs[rel]["has_error"] = True
    total = len(runs)
    anomalous = {k: v for k, v in runs.items() if v["is_anomalous"]}
    return {
        "output_root": str(output_root),
        "total_runs": total,
        "anomalous_runs": len(anomalous),
        "error_runs": sum(1 for v in runs.values() if v["has_error"]),
        "runs": anomalous,
    }
```

- [ ] **Step 2: 用真实历史产物验证**

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
from pathlib import Path
from src.utils.anomalies import scan_run_dir, scan_batch
# 正常满分 run（xopglm52 1.00）应无 error 异常
ok = sorted(Path('output/astroncode/04_Search_Retrieval/04_Search_Retrieval_task_11_fuzzy_repo_search').glob('xopglm52_*'))[-1]
r = scan_run_dir(ok)
print('正常run:', r['has_error'], [i['id'] for i in r['items']])
assert not r['has_error']
# X2-300B 全拒 run 应命中 TOOL_CALLS_ALL_REJECTED
bad = Path('output/astroncode/04_Search_Retrieval/04_Search_Retrieval_task_11_fuzzy_repo_search/xsparkx2agent_20260716_2017_997d42')
r = scan_run_dir(bad)
print('X2-300B坏run:', [i['id'] for i in r['items']])
assert any(i['id'] == 'TOOL_CALLS_ALL_REJECTED' for i in r['items'])
# 批扫描可运行
rep = scan_batch(Path('output/astroncode'))
print('batch:', rep['total_runs'], 'runs,', rep['anomalous_runs'], 'anomalous')
EOF
```
Expected: 正常 run `has_error=False`；X2-300B run 命中 `TOOL_CALLS_ALL_REJECTED`；批扫描输出计数。

- [ ] **Step 3: Commit**

```bash
git add src/utils/anomalies.py
git commit -m "feat: run 级异常检测模块（13 规则，纯函数，可回溯扫描）"
```

---

### Task 3: 逐 run 集成（跑批时自动落 anomalies.json）

**Files:**
- Modify: `eval/run_batch.py`（`run_single_task` 的 finally 尾部，`collect_task_output` 调用之后）

**Interfaces:**
- Consumes: `scan_run_dir`（Task 2）
- Produces: 每个 run 目录新增 `anomalies.json`；命中 error 级时打 WARNING 日志

- [ ] **Step 1: run_single_task 集成**

`eval/run_batch.py` import 区加 `from src.utils.anomalies import scan_run_dir`；在 `run_single_task` 的 finally 块中、容器清理之前（`collect_task_output` 之后）加：

```python
        try:
            anomalies = scan_run_dir(output_dir)
            (output_dir / "anomalies.json").write_text(
                json.dumps(anomalies, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            if anomalies["has_error"]:
                logger.warning(
                    "[%s] Anomalies detected (score unreliable): %s",
                    task_id,
                    ", ".join(i["id"] for i in anomalies["items"] if i["severity"] == "error"),
                )
            result["anomalies"] = anomalies
        except Exception as exc:
            logger.warning("[%s] Anomaly scan failed: %s", task_id, exc)
```

注意：此时 `chat.jsonl`/`usage.json` 已由 `collect_usage` 落盘（finally 中它在前），顺序依赖成立；若实际代码顺序不符，把本段移到 usage 落盘之后。

- [ ] **Step 2: 冒烟验证**

```bash
source docs/local/deploy/export.astroncode.sh && source .venv/bin/activate
OUTPUT_SUBDIR=/tmp/wcb_anom python3 eval/run_batch.py --agent-backend astroncode \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xopglm52
ls /tmp/wcb_anom/astroncode/03_Social_Interaction/*/*/anomalies.json
python3 -c "import json,glob; print(json.load(open(glob.glob('/tmp/wcb_anom/astroncode/*/*/*/anomalies.json')[0])))"
rm -rf /tmp/wcb_anom
```
Expected: `anomalies.json` 存在；正常 run `has_error=false`。

- [ ] **Step 3: Commit**

```bash
git add eval/run_batch.py
git commit -m "feat: 跑批逐 run 自动异常检测并落 anomalies.json"
```

---

### Task 4: 批级报告 + 历史回溯扫描脚本

**Files:**
- Create: `eval/scan_anomalies.py`
- Modify: `eval/run_batch.py`（批跑结束、打印全局 summary 之后，写 `anomaly_report.json` 并打印摘要）

**Interfaces:**
- Consumes: `scan_batch`（Task 2）
- Produces: `output_root/anomaly_report.json`；独立 CLI `python3 eval/scan_anomalies.py <output_root>`（可扫任意历史 round 目录）

- [ ] **Step 1: 独立扫描脚本**

```python
#!/usr/bin/env python3
"""对已有评测输出目录做异常回溯扫描。

用法：
    python3 eval/scan_anomalies.py output/astroncode
    python3 eval/scan_anomalies.py /data1/.../round1/xsparkx2agent/astroncode
输出 anomaly_report.json 到目标目录，并打印摘要表。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.anomalies import scan_batch


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).expanduser()
    if not root.is_dir():
        print(f"目录不存在: {root}")
        return 1
    report = scan_batch(root)
    out = root / "anomaly_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"扫描 {report['total_runs']} runs："
          f"异常 {report['anomalous_runs']}（error 级 {report['error_runs']}）")
    for rel, info in sorted(report["runs"].items()):
        flags = ",".join(i["id"] for i in info["items"])
        level = "❌" if info["has_error"] else "⚠️"
        print(f"  {level} {rel}: {flags}")
    print(f"报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: run_batch 批后汇总**

`main()` 打印全局 summary 之后（批处理分支收尾处）加：

```python
    try:
        from src.utils.anomalies import scan_batch
        report = scan_batch(output_root)
        (output_root / "anomaly_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if report["error_runs"]:
            logger.warning(
                "Anomaly summary: %d/%d runs have ERROR-level anomalies — "
                "consider --resume --rerun-error (report: %s)",
                report["error_runs"], report["total_runs"],
                output_root / "anomaly_report.json",
            )
        else:
            logger.info("Anomaly summary: %d runs scanned, no ERROR-level anomalies",
                        report["total_runs"])
    except Exception as exc:
        logger.warning("Batch anomaly scan failed: %s", exc)
```

- [ ] **Step 3: 用历史数据验证回溯扫描**

```bash
python3 eval/scan_anomalies.py output/astroncode
```
Expected: 列出既有异常 run（至少包含 X2-300B 旧 catalog 那两个 0 分 run 的 `TOOL_CALLS_ALL_REJECTED`），`output/astroncode/anomaly_report.json` 生成。

- [ ] **Step 4: Commit**

```bash
git add eval/scan_anomalies.py eval/run_batch.py
git commit -m "feat: 批级异常报告 + 历史输出回溯扫描脚本"
```

---

### Task 5: 断点续跑 / 选择性重跑

**Files:**
- Modify: `src/utils/cli_args.py`（`--resume`/`--rerun-error`/`--rerun-anomalous`）
- Modify: `eval/run_batch.py`（任务过滤 + 跳过 run 的 summary 合并）

**Interfaces:**
- Consumes: `scan_run_dir`（anomalies.json 缺失时现算，兼容旧产物）
- Produces: `--resume` 跳过已完成任务；`--rerun-error`/`--rerun-anomalous` 隐含 `--resume` 并按异常级别放行重跑；summary/全局统计包含被跳过 run 的历史结果

**语义定义（对齐 QwenClawBench）：**
- 「已完成」= 该 (task, model) 在 output_root 下**最新**的 run 目录（按目录名时间戳排序，匹配 `<short_model>_*` 前缀）存在可解析的 `score.json`
- `--resume`：已完成 → 跳过（无论分数高低，0 分也是有效结果）
- `--rerun-error`：已完成但 anomalies `has_error==true` → 不跳过（重跑）
- `--rerun-anomalous`：已完成但 `is_anomalous==true` → 不跳过（重跑）
- 跳过的 run 以其落盘 score.json/usage.json 重建 result dict，进入本批 summary，保证汇总完整

- [ ] **Step 1: CLI 参数**

```python
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip tasks whose latest run (same model) already has a valid score.json; "
             "only missing/failed-to-produce tasks are executed",
    )
    parser.add_argument(
        "--rerun-error",
        action="store_true",
        help="With --resume (implied): also rerun tasks whose latest run has "
             "ERROR-level anomalies (timeout/crash/empty transcript/...)",
    )
    parser.add_argument(
        "--rerun-anomalous",
        action="store_true",
        help="With --resume (implied): also rerun tasks whose latest run has ANY "
             "anomaly (including WARNING-level, e.g. transient rate limits)",
    )
```

- [ ] **Step 2: run_batch 过滤与合并**

`eval/run_batch.py` 加 helper（放在 `run_single_task` 之前）：

```python
def _short_model_slug(model: str) -> str:
    return re.sub(r'[^a-zA-Z0-9.\-_]', '_', model.rsplit('/', 1)[-1])


def _find_latest_run(output_root: Path, task: dict, model: str) -> Path | None:
    task_dir = output_root / task["category"] / task["task_id"]
    if not task_dir.is_dir():
        return None
    prefix = f"{_short_model_slug(model)}_"
    runs = sorted(p for p in task_dir.iterdir() if p.is_dir() and p.name.startswith(prefix))
    return runs[-1] if runs else None


def _load_resume_result(
    output_root: Path, task: dict, model: str,
    rerun_error: bool, rerun_anomalous: bool,
) -> dict | None:
    """已完成且无需重跑 → 返回重建的 result dict；否则返回 None（需执行）。"""
    latest = _find_latest_run(output_root, task, model)
    if latest is None:
        return None
    try:
        scores = json.loads((latest / "score.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    anomalies = None
    anomalies_file = latest / "anomalies.json"
    if anomalies_file.exists():
        try:
            anomalies = json.loads(anomalies_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            anomalies = None
    if anomalies is None:
        from src.utils.anomalies import scan_run_dir
        anomalies = scan_run_dir(latest)
    if rerun_anomalous and anomalies.get("is_anomalous"):
        logger.info("[resume] %s 最新 run 有异常，将重跑: %s",
                    task["task_id"], [i["id"] for i in anomalies["items"]])
        return None
    if rerun_error and anomalies.get("has_error"):
        logger.info("[resume] %s 最新 run 有 ERROR 级异常，将重跑: %s",
                    task["task_id"],
                    [i["id"] for i in anomalies["items"] if i["severity"] == "error"])
        return None
    usage = {}
    try:
        usage = json.loads((latest / "usage.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    status = {}
    try:
        status = json.loads((latest / "execution_status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    logger.info("[resume] 跳过已完成任务 %s（沿用 %s）", task["task_id"], latest.name)
    return {
        "task_id": latest.name,
        "scores": scores,
        "error": status.get("error"),
        "usage": usage,
        "anomalies": anomalies,
        "_resumed_from": str(latest),
    }
```

`main()` 的两个执行分支分别集成（以下行号为当前代码位置）：

**① 单任务分支**（`run_batch.py:414-432`）——`logger.info("Single task mode", ...)` 之后、`run_single_task` 调用之前插入：

```python
        resume_enabled = args.resume or args.rerun_error or args.rerun_anomalous
        if resume_enabled:
            prior = _load_resume_result(
                output_root, task, args.model, args.rerun_error, args.rerun_anomalous
            )
            if prior is not None:
                return  # _load_resume_result 已打印跳过日志；沿用旧结果，正常退出
```

**② category 分支**（`run_batch.py:441-510` 的 for 循环内）——`if not tasks: continue`（:468-469）与 `results: list[dict] = []`（:471）之间插入（`resume_enabled` 定义提到循环外）：

```python
        resumed_results: list[dict] = []
        if resume_enabled:
            pending = []
            for task in tasks:
                prior = _load_resume_result(
                    output_root, task, args.model, args.rerun_error, args.rerun_anomalous
                )
                if prior is None:
                    pending.append(task)
                else:
                    resumed_results.append(prior)
            logger.info("[resume] %s: 复用 %d 个已完成 run，待执行 %d 个任务",
                        category, len(resumed_results), len(pending))
            tasks = pending
```

并在 `print_summary(results, category, ...)`（:509）**之前**加一行合并，使被跳过 run 的分数计入类别与全局汇总：

```python
        results.extend(resumed_results)
```

（`all_results.extend(results)` 在 :510 原样保留，全局汇总自然包含复用结果；`tasks` 为空但 `resumed_results` 非空时不能 `continue` 跳过本类，需保证仍走到 print_summary——即把 :468 的 `if not tasks: continue` 改为在 resume 过滤**之前**判断原始任务列表。）

- [ ] **Step 3: 验证（三段式）**

```bash
source docs/local/deploy/export.astroncode.sh && source .venv/bin/activate
export OUTPUT_SUBDIR=/tmp/wcb_resume
T=tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md

# 1) 首跑：正常执行
python3 eval/run_batch.py --agent-backend astroncode --task $T --model openrouter/xopglm52
# 2) --resume 复跑：应跳过（日志出现 "[resume] 跳过已完成任务"，且不再新建 run 目录）
N1=$(ls /tmp/wcb_resume/astroncode/03_Social_Interaction/*/ | wc -l)
python3 eval/run_batch.py --agent-backend astroncode --task $T --model openrouter/xopglm52 --resume
N2=$(ls /tmp/wcb_resume/astroncode/03_Social_Interaction/*/ | wc -l)
[ "$N1" = "$N2" ] && echo "resume 跳过 OK"
# 3) 伪造 ERROR 异常后 --rerun-error：应重跑（新增 run 目录）
LATEST=$(ls -dt /tmp/wcb_resume/astroncode/03_Social_Interaction/*/xopglm52_* | head -1)
python3 -c "
import json, pathlib
p = pathlib.Path('$LATEST/execution_status.json')
d = json.loads(p.read_text()); d['status']='error'; d['error']='fake for test'
p.write_text(json.dumps(d))
(pathlib.Path('$LATEST/anomalies.json')).unlink(missing_ok=True)"
python3 eval/run_batch.py --agent-backend astroncode --task $T --model openrouter/xopglm52 --rerun-error
N3=$(ls /tmp/wcb_resume/astroncode/03_Social_Interaction/*/ | wc -l)
[ "$N3" -gt "$N2" ] && echo "rerun-error 重跑 OK"
rm -rf /tmp/wcb_resume
```
Expected: 三段分别输出 `resume 跳过 OK`、`rerun-error 重跑 OK`，且第 2 步 summary 里包含被复用 run 的分数。

- [ ] **Step 4: Commit**

```bash
git add src/utils/cli_args.py eval/run_batch.py
git commit -m "feat: 断点续跑 --resume 与选择性重跑 --rerun-error/--rerun-anomalous"
```

---

### Task 6: 回归验证 + 速查文档更新

**Files:**
- Modify: `docs/local/guide/wildclawbench-评测命令速查.md`（§8 备注加三条用法；不入库）

**Interfaces:**
- Consumes: Task 1-5 全部产物

- [ ] **Step 1: 默认行为零变化回归**

```bash
# 不带任何新参数跑一次单任务，对比产物集合与旧版一致（仅多出 anomalies.json）
source docs/local/deploy/export.astroncode.sh && source .venv/bin/activate
OUTPUT_SUBDIR=/tmp/wcb_reg python3 eval/run_batch.py --agent-backend astroncode \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xopglm52
ls /tmp/wcb_reg/astroncode/03_Social_Interaction/*/*/
# Expected: agent.log astroncode_sessions chat.jsonl chat_openclaw.jsonl config.toml
#           execution_status.json score.json task_output usage.json + anomalies.json
# 容器无资源限额（未设参数）：
docker inspect $(docker ps -lq) --format '{{.HostConfig.Memory}}' 2>/dev/null  # 跑批中执行，应为 0
rm -rf /tmp/wcb_reg
```

- [ ] **Step 2: 速查文档 §8 备注补三条**

在「超时统一覆盖」条目之后追加：

```markdown
- **断点续跑**：跑挂/中断后，同一条命令**加 `--resume`** 重发即可——已有有效 `score.json` 的任务直接复用旧结果（计入 summary），只补跑缺失任务。`--rerun-error` 额外重跑有 ERROR 级异常（超时/崩溃/空轨迹/工具全拒等）的任务；`--rerun-anomalous` 连 WARNING 级（如瞬态限流）一并重跑。三者均不改变"重跑不覆盖旧结果"的目录规则（新跑落新 run 目录）。
- **异常检测**：每个 run 自动落 `anomalies.json`（13 条规则，error=分数不可信 / warning=瞬态），批跑结束在输出根目录生成 `anomaly_report.json` 并打印摘要；历史轮次回溯扫描：`python3 eval/scan_anomalies.py <round 目录>`。对外报告出数前先看 error 级异常数。
- **容器资源限额**：`--memory 4g --cpus 2`（或 env `WILDCLAW_DOCKER_MEMORY`/`WILDCLAW_DOCKER_CPUS`，CLI 优先）。**不加参数 = 不限额，现有命令完全不受影响**。
```

- [ ] **Step 3: 最终提交**

```bash
git log --oneline -6   # 确认 Task 1-5 各自的提交都在
git status             # 应只剩 docs/local（不入库）改动
```
