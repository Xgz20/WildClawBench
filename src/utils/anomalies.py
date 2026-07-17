"""基于规则的 run 级异常检测（改编自 QwenClawBench lib_anomalies.py）。

输入是 WildClawBench 单个 run 目录的落盘产物（execution_status.json /
usage.json / chat.jsonl / agent.log / score.json），全部只读，无副作用。
异常 = 使分数不可信的基础设施/执行类问题；分 error（分数不可信）与
warning（瞬态干扰，分数仍有效）两档。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ERROR = "error"
WARNING = "warning"

# 文本型关键词足够特定，全文子串匹配即可；
# 纯数字状态码（429/5xx）太易误命中任务内容（如 "scroll down 500"、"120,500"），
# 须词边界匹配且同一行伴随 HTTP/错误上下文词才算。
_RATE_LIMIT_TEXT = ("rate limit", "rate_limit", "too many requests", "ratelimit")
_SERVER_ERROR_TEXT = (
    "bad gateway", "service unavailable",
    "internal server error", "internal error has occurred",
)
_RATE_LIMIT_CODES = ("429",)
_SERVER_ERROR_CODES = ("500", "502", "503")
_HTTP_CONTEXT = ("error", "http", "status", "code", "exception", "failed", "request")


def _log_hits(agent_log: str, text_keywords: tuple[str, ...], codes: tuple[str, ...]) -> bool:
    for line in agent_log.splitlines():
        if any(k in line for k in text_keywords):
            return True
        if any(re.search(rf"\b{c}\b", line) for c in codes) and any(
            ctx in line for ctx in _HTTP_CONTEXT
        ):
            return True
    return False
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
    # ≥80% 被拒即视为系统性工具协议故障（如 X2-300B 曾 exec×27 被拒但 write_stdin×2
    # 成功，93% 拒绝率、0 分——要求 100% 会漏掉这类混合场景）
    if len(tool_results) >= 3 and len(rejected) / len(tool_results) >= 0.8:
        hit("TOOL_CALLS_ALL_REJECTED", ERROR,
            f"{len(rejected)}/{len(tool_results)} tool calls rejected "
            "(unsupported/unknown tool) — tool-name protocol failure")
    if _log_hits(agent_log, _RATE_LIMIT_TEXT, _RATE_LIMIT_CODES):
        hit("API_RATE_LIMIT", WARNING, "rate-limit markers found in agent.log")
    if _log_hits(agent_log, _SERVER_ERROR_TEXT, _SERVER_ERROR_CODES):
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
