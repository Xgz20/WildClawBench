#!/usr/bin/env python3
"""重解析 AstronCode/Codex 结果的 usage.json，修正被低估的 request_count。

背景：codex runner 旧逻辑把每个 token_count 事件的 total_token_usage(累积)
误判为唯一候选，导致 per_turn 为空、request_count 退化为 assistant_message_count，
严重低估真实模型往返次数（实测 ~18x）。runner._extract_usage_fields 已修复
（平局时优先 per-turn 增量）。本脚本用修复后的逻辑对已有产物重新解析，
就地更新 usage.json 的 request_count（token/cost 不变，仅在偏差时改动）。

用法：
    python3 tools/report/scripts/reparse_codex_usage.py <result_root> [--apply]

默认 dry-run 只打印将改动的任务；--apply 才写回（写前对 usage.json 存 .bak）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 复用 runner 的解析逻辑（含已修复的 _extract_usage_fields）
# runner 内部用 `from src.agents...` 绝对导入，故把 repo 根(而非 src)加入 path
_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from src.agents.codex.runner import CodexAgent  # noqa: E402


def reparse_one(run_dir: Path) -> dict | None:
    """复刻 runner 顺序：先 chat.jsonl，零 token 再回退 session_dir。"""
    agent = CodexAgent.__new__(CodexAgent)
    parsed = agent._extract_usage_from_jsonl(run_dir / "chat.jsonl")
    if parsed["total_tokens"] == 0 and parsed["input_tokens"] == 0:
        sess = run_dir / "astroncode_sessions"
        if sess.is_dir():
            parsed = agent._extract_usage_from_session_dir(sess)
    return parsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("result_root", type=Path)
    ap.add_argument("--apply", action="store_true", help="写回 usage.json(默认dry-run)")
    args = ap.parse_args()

    changed = 0
    total = 0
    tok_drift = 0
    for usage_path in sorted(args.result_root.rglob("usage.json")):
        run_dir = usage_path.parent
        # 仅处理 codex/astroncode 产物(有 astroncode_sessions 或 chat.jsonl 为事件流)
        if not (run_dir / "chat.jsonl").is_file():
            continue
        try:
            old = json.loads(usage_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        parsed = reparse_one(run_dir)
        if parsed is None:
            continue
        total += 1
        old_rc = old.get("request_count", 0)
        new_rc = parsed["request_count"]
        # token 漂移监测(应为 0，仅诊断)
        if old.get("total_tokens", 0) != parsed["total_tokens"]:
            tok_drift += 1
        if new_rc == old_rc:
            continue
        changed += 1
        rel = run_dir.relative_to(args.result_root)
        print(f"  {rel}: request_count {old_rc} -> {new_rc}")
        if args.apply:
            bak = usage_path.with_suffix(".json.bak")
            if not bak.exists():
                bak.write_text(usage_path.read_text())
            old["request_count"] = new_rc
            usage_path.write_text(json.dumps(old, ensure_ascii=False, indent=2))

    mode = "已写回" if args.apply else "dry-run(未写回)"
    print(f"\n[{mode}] 扫描 {total} 个任务，request_count 需修正 {changed} 个"
          f"，token 漂移 {tok_drift} 个(应为0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
