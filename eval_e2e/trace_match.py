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
    """cwd 等于项目目录、或位于项目目录之内（后代）才算命中。

    只保留相等与后代方向：用户在项目目录里打开客户端后 cd 到子目录仍能匹配，
    但在工作区根打开的会话（cwd 为项目目录的祖先）不会被错算给任意用例。
    """
    try:
        candidate = Path(cwd)
    except (TypeError, ValueError):
        return False
    if candidate == project_dir:
        return True
    return project_dir in candidate.parents


def _parse_ts(timestamp: str) -> datetime | None:
    """把 ISO 时间戳解析为带时区的 datetime；无法解析返回 None。

    - 结尾 `Z` 先替换为 `+00:00`（Python 3.10 的 fromisoformat 不接受 `Z`）。
    - 无时区信息的时间戳按 UTC 处理，不报错。
    """
    if not timestamp:
        return None
    text = timestamp.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _in_window(timestamp: str, started_at: str, finished_at: str) -> bool:
    """空端不设限；时间戳解析为带时区 datetime 后比较。

    时间戳解析失败时该候选不匹配（返回 False），与"零命中返回 trace_missing"
    的容错风格一致，绝不抛异常。
    """
    started = _parse_ts(started_at)
    finished = _parse_ts(finished_at)
    if started is None and finished is None:
        return True
    event = _parse_ts(timestamp)
    if event is None:
        return False
    if started is not None and event < started:
        return False
    if finished is not None and event > finished:
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
    _EPOCH = datetime.min.replace(tzinfo=timezone.utc)

    def _sort_key(c: TraceCandidate) -> tuple[datetime, str]:
        # 按真实时刻（带时区 datetime）排序；无法解析的按最早处理，稳定回退到文件名。
        return (_parse_ts(c.timestamp) or _EPOCH, c.path.name)

    matched.sort(key=_sort_key)
    note = "matched" if len(matched) == 1 else "matched_multiple"
    return matched[-1].path, note


def _empty_usage() -> dict:
    """用量骨架。

    request_count 与 cost_usd 是**占位，parse_usage 永不填充，恒为 0**：桌面端
    轨迹拿不到与 CLI 侧可比的 request 计数（CLI 侧本身也已确认低估约 18x，见
    memory: astroncode-request-count-underestimate）。下游一律以 tool_calls
    为主口径，勿依赖这两个键做任何判断或换算。
    """
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,
        "tool_calls": 0,
        "request_count": 0,  # 占位，恒 0
        "cost_usd": 0.0,  # 占位，恒 0
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
