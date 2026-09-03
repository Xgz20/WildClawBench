#!/usr/bin/env python3
"""重解析 AstronCode/Codex 结果的 usage.json，并回填 AstronCode 首响。

背景：codex runner 旧逻辑把每个 token_count 事件的 total_token_usage(累积)
误判为唯一候选，导致 per_turn 为空、request_count 退化为 assistant_message_count，
严重低估真实模型往返次数（实测 ~18x）。runner._extract_usage_fields 已修复
（平局时优先 per-turn 增量）。本脚本用修复后的逻辑对已有产物重新解析，
就地更新 usage.json 的 request_count；AstronCode 结果还会从 chat.jsonl 的
task_complete 回填 time_to_first_token_ms。token/cost 不变。

用法：
    python3 tools/report/scripts/reparse_codex_usage.py <result_root> [--apply]

默认 dry-run 只打印将改动的任务；--apply 才写回（写前对 usage.json 存 .bak）。
只处理 `execution_status.json.harness` 明确为 codex/astroncode 的结果；token
重解析发生漂移时跳过该 run，不推断或写回请求数。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# 复用 runner 的解析逻辑（含已修复的 _extract_usage_fields）
# runner 内部用 `from src.agents...` 绝对导入，故把 repo 根(而非 src)加入 path
_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from src.agents.codex.runner import CodexAgent  # noqa: E402
from src.agents.astroncode.runner import AstronCodeAgent  # noqa: E402

SUPPORTED_HARNESSES = frozenset({"astroncode", "codex"})


def execution_harness(run_dir: Path) -> tuple[str, str]:
    """读取权威 Harness 标识；无法确定时返回错误原因。"""
    status_path = run_dir / "execution_status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return "", f"execution_status.json 无法读取：{exc}"
    except json.JSONDecodeError as exc:
        return "", f"execution_status.json 解析失败：{exc}"
    if not isinstance(status, dict):
        return "", "execution_status.json 顶层不是 JSON object"
    harness = str(status.get("harness") or "").strip().lower()
    if not harness:
        return "", "execution_status.json 缺少 harness"
    return harness, ""


def reparse_one(run_dir: Path, harness: str) -> tuple[dict, bool]:
    """复刻 runner 顺序：先 chat.jsonl，零 token 再回退 session_dir。"""
    harness = str(harness).strip().lower()
    if harness not in SUPPORTED_HARNESSES:
        raise ValueError(f"不支持重解析 Harness: {harness or '<empty>'}")
    is_astroncode = harness == "astroncode"
    agent_class = AstronCodeAgent if is_astroncode else CodexAgent
    agent = agent_class.__new__(agent_class)
    parsed = agent._extract_usage_from_jsonl(run_dir / "chat.jsonl")
    if parsed["total_tokens"] == 0 and parsed["input_tokens"] == 0:
        session_dir_name = "astroncode_sessions" if is_astroncode else "codex_sessions"
        sess = run_dir / session_dir_name
        if sess.is_dir():
            chat_ttft = parsed.get("time_to_first_token_ms")
            parsed = agent._extract_usage_from_session_dir(sess)
            if is_astroncode and parsed.get("time_to_first_token_ms") is None:
                parsed["time_to_first_token_ms"] = chat_ttft
    if is_astroncode and agent._run_has_explicit_execution_failure(run_dir):
        parsed["time_to_first_token_ms"] = None
    return parsed, is_astroncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("result_root", type=Path)
    ap.add_argument("--apply", action="store_true", help="写回 usage.json(默认dry-run)")
    args = ap.parse_args(argv)

    changed = 0
    ttft_changed_count = 0
    discovered = 0
    eligible = 0
    tok_drift = 0
    invalid_status = 0
    invalid_usage = 0
    missing_source = 0
    skipped_harnesses: Counter[str] = Counter()
    for usage_path in sorted(args.result_root.rglob("usage.json")):
        discovered += 1
        run_dir = usage_path.parent
        harness, status_error = execution_harness(run_dir)
        if status_error:
            invalid_status += 1
            print(f"  跳过 {run_dir.relative_to(args.result_root)}: {status_error}")
            continue
        if harness not in SUPPORTED_HARNESSES:
            skipped_harnesses[harness] += 1
            continue
        session_dir = run_dir / (
            "astroncode_sessions" if harness == "astroncode" else "codex_sessions"
        )
        if not (run_dir / "chat.jsonl").is_file() and not session_dir.is_dir():
            missing_source += 1
            print(
                f"  跳过 {run_dir.relative_to(args.result_root)}: "
                f"缺少 chat.jsonl 和 {session_dir.name}"
            )
            continue
        try:
            old = json.loads(usage_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            invalid_usage += 1
            continue
        if not isinstance(old, dict):
            invalid_usage += 1
            continue
        parsed, supports_ttft = reparse_one(run_dir, harness)
        eligible += 1
        old_rc = old.get("request_count", 0)
        new_rc = parsed["request_count"]
        new_ttft = parsed.get("time_to_first_token_ms")
        ttft_changed = supports_ttft and (
            "time_to_first_token_ms" not in old
            or old.get("time_to_first_token_ms") != new_ttft
        )
        # 本脚本只允许回填请求数和 AstronCode 首响。token 漂移说明当前轨迹
        # 不是该解析器支持的原生格式，不能继续推断 request_count。
        if old.get("total_tokens", 0) != parsed["total_tokens"]:
            tok_drift += 1
            print(
                f"  跳过 {run_dir.relative_to(args.result_root)}: token 漂移 "
                f"{old.get('total_tokens', 0)} -> {parsed['total_tokens']}"
            )
            continue
        request_count_changed = new_rc != old_rc
        if not request_count_changed and not ttft_changed:
            continue
        changed += 1
        ttft_changed_count += int(ttft_changed)
        rel = run_dir.relative_to(args.result_root)
        changes = []
        if request_count_changed:
            changes.append(f"request_count {old_rc} -> {new_rc}")
        if ttft_changed:
            changes.append(
                "time_to_first_token_ms "
                f"{old.get('time_to_first_token_ms', '<missing>')} -> {new_ttft}"
            )
        print(f"  {rel}: {'; '.join(changes)}")
        if args.apply:
            bak = usage_path.with_suffix(".json.bak")
            if not bak.exists():
                bak.write_text(
                    usage_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
            if request_count_changed:
                old["request_count"] = new_rc
            if ttft_changed:
                old["time_to_first_token_ms"] = new_ttft
            usage_path.write_text(
                json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    mode = "已写回" if args.apply else "dry-run(未写回)"
    print(
        f"\n[{mode}] 发现 {discovered} 个 usage.json，支持并扫描 {eligible} 个，"
        f"需更新 {changed} 个，其中首响字段 {ttft_changed_count} 个，"
        f"token 漂移 {tok_drift} 个(应为0)"
    )
    if skipped_harnesses:
        details = ", ".join(
            f"{harness}={count}"
            for harness, count in sorted(skipped_harnesses.items())
        )
        print(f"跳过不支持的 Harness {sum(skipped_harnesses.values())} 个：{details}")
    if invalid_status or invalid_usage or missing_source:
        print(
            f"跳过无效输入：execution_status={invalid_status}，"
            f"usage={invalid_usage}，source={missing_source}"
        )
    if args.apply and eligible == 0:
        print("错误：没有发现可安全重解析的 AstronCode/Codex 结果。", file=sys.stderr)
        return 2
    if args.apply and tok_drift:
        print(
            f"警告：{tok_drift} 个结果因 token 漂移未写回，请单独检查轨迹格式。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
