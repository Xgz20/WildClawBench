"""Repository CLI for memory dataset, scoped handoff, scoring and reporting."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import HARNESS_PORTS
from .batch import load_batch, prepare
from .dataset import DATA, OPEN_DATA, load_dataset
from .io import MemoryEvaluationError, events, publish, read_json, require
from .probe import native_preflight, scan
from .report import write_report
from .runner import advance, import_receipt, next_action, register_intent
from .scoring import import_review, review_template
from .native_profiles import native_profiles
from .worker import run_worker
from .runtime_repair import repair_runtime
from .configuration import configuration_probe
from .activation import astudio_memory_config
from .recovery import recover_ui_lock, recover_qwen_step_lock
from .admission import channel_template, import_channel_review


def selftest(root):
    """Synthetic protocol round-trip. Never produces native evaluation scores."""
    prepare(root, batch_id="memory-protocol-selftest", seed="protocol-selftest-v1", mode="fixture",
            scenario_ids=["MEM-01", "MEM-10", "MEM-13", "MEM-19"])
    manifest = load_batch(root)
    ordered = [episode for name in manifest['harnesses'] for episode in manifest['episodes'] if episode['harness'] == name]
    for episode in ordered:
        while next_action(root, episode["id"])["status"] != "COMPLETED":
            advance(root, episode["id"])
        review = review_template(root, episode["id"])
        review["judge_context_id"] = "fixture-review-context"
        for check in review["checkpoints"]:
            check["value"] = 0
            check["reason"] = "协议模拟，不判断模型能力；固定测试值只用于验证证据入库与聚合。"
            artifact = check["available_evidence"]["final_response"]
            text = (Path(root) / artifact["path"]).read_text()
            check["evidence"] = [{"step_id": check["step_id"], "artifact": "final_response",
                                  "sha256": artifact["sha256"], "quote": text.strip()}]
        review_path = Path(root) / "private/reviews" / (episode["id"] + ".json")
        publish(review_path, review)
        import_review(root, review_path)
    report = write_report(root, Path(root) / "reports", include_fixture=True)
    return {"status": "FIXTURE_ONLY", "episode_count": len(manifest["episodes"]),
            "event_count": len(events(root)), **report}


def parser():
    result = argparse.ArgumentParser(prog="python -m eval_memory_e2e")
    commands = result.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-dataset", help="validate the separate memory task contract")
    validate.add_argument("--dataset", type=Path, default=OPEN_DATA)
    probe = commands.add_parser("scan", help="read-only client/transport inventory; never admits memory")
    probe.add_argument("--output", type=Path, required=True)
    native = commands.add_parser("native-preflight", help="reuse four read-only General probes; no Prompt or reset")
    native.add_argument("--output-dir", type=Path, required=True)
    native.add_argument("--harness", action="append", choices=list(HARNESS_PORTS))
    profiles = commands.add_parser("native-profiles", help="freeze real Driver commands and source hashes")
    profiles.add_argument("--output", type=Path, required=True)
    config = commands.add_parser("config-probe", help="four-client settings readback or reversible switch roundtrip; Codex excluded")
    config.add_argument("--output-dir", type=Path, required=True)
    config.add_argument("--harness", action="append", choices=list(HARNESS_PORTS))
    config.add_argument("--roundtrip", action="store_true")
    config.add_argument("--preflight-dir", type=Path)
    activation = commands.add_parser("astudio-memory-config", help="owned AStudio-only memory configuration lease; Codex excluded")
    activation.add_argument("--action", choices=['enable', 'restore'], required=True)
    activation.add_argument("--lease-dir", type=Path, required=True)
    worker = commands.add_parser("run", help="serial native stepping and observation; no task deadline")
    worker.add_argument("--root", type=Path, required=True)
    worker.add_argument("--harness", choices=list(HARNESS_PORTS))
    worker.add_argument("--poll-seconds", type=float, default=2)
    repair = commands.add_parser("repair-runtime", help="audit code-only source replacement without changing a sent operation")
    repair.add_argument("--root", type=Path, required=True)
    repair.add_argument("--reason", required=True)
    recover = commands.add_parser("recover-ui-lock", help="archive an exact dead memory-controller UI lock; never resend")
    recover.add_argument("--root", type=Path, required=True)
    recover.add_argument("--expected-owner-id", required=True)
    qrecover = commands.add_parser('recover-qwen-step-lock', help='archive one exact dead Memory Qwen step lock; never resend')
    qrecover.add_argument('--root', type=Path, required=True)
    qrecover.add_argument('--episode', required=True)
    qrecover.add_argument('--operation', required=True)
    qrecover.add_argument('--expected-owner-id', required=True)
    qrecover.add_argument('--probe', type=Path, required=True)
    init = commands.add_parser("prepare", help="freeze public/private tasks and a paired, cold-first plan")
    init.add_argument("--root", type=Path, required=True)
    init.add_argument("--batch-id", required=True)
    init.add_argument("--dataset", type=Path, default=OPEN_DATA)
    init.add_argument("--seed", required=True)
    init.add_argument("--repeats", type=int, default=1)
    init.add_argument("--harness", action="append", choices=list(HARNESS_PORTS))
    init.add_argument("--scenario", action="append")
    init.add_argument("--fixture", action="store_true")
    init.add_argument("--profiles", type=Path)
    init.add_argument("--judge-model")
    init.add_argument("--judge-reasoning")
    for command in ("next", "intent", "advance", "retry-pre-send", "import-receipt", "review-template"):
        sub = commands.add_parser(command)
        sub.add_argument("--root", type=Path, required=True)
        sub.add_argument("--episode", required=True)
        if command == "import-receipt":
            sub.add_argument("--receipt", type=Path, required=True)
        if command == "review-template":
            sub.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("import-review")
    score.add_argument("--root", type=Path, required=True)
    score.add_argument("--review", type=Path, required=True)
    channel = commands.add_parser('channel-template', help='private independent review of observed memory channel')
    channel.add_argument('--root', type=Path, required=True)
    channel.add_argument('--episode', required=True)
    channel.add_argument('--gate', required=True)
    channel.add_argument('--output', type=Path, required=True)
    channel_import = commands.add_parser('import-channel-review')
    channel_import.add_argument('--root', type=Path, required=True)
    channel_import.add_argument('--review', type=Path, required=True)
    report = commands.add_parser("report")
    report.add_argument("--root", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--include-fixture", action="store_true")
    test = commands.add_parser("selftest", help="32 fixture episodes; zero client/model calls")
    test.add_argument("--root", type=Path, required=True)
    return result


def run(args):
    if args.command == "validate-dataset":
        dataset = load_dataset(args.dataset)
        return {"status": "PASS", "dataset_id": dataset["dataset_id"], "scenarios": len(dataset["scenarios"]),
                "dimensions": dict(Counter(case["dimension"] for case in dataset["scenarios"])),
                "difficulties": dict(Counter(case["difficulty"] for case in dataset["scenarios"])),
                "checkpoints": sum(len(case["checkpoints"]) for case in dataset["scenarios"])}
    if args.command == "scan":
        report = scan()
        publish(args.output, report)
        return {"output": str(args.output), **report}
    if args.command == "native-preflight":
        return native_preflight(args.output_dir, args.harness)
    if args.command == "native-profiles":
        return native_profiles(args.output)
    if args.command == "config-probe":
        return configuration_probe(args.output_dir, args.harness, args.roundtrip, args.preflight_dir)
    if args.command == "astudio-memory-config":
        return astudio_memory_config(args.lease_dir, args.action)
    if args.command == "run":
        return run_worker(args.root, args.harness, args.poll_seconds)
    if args.command == "repair-runtime":
        return repair_runtime(args.root, args.reason)
    if args.command == "recover-ui-lock":
        return recover_ui_lock(args.root, args.expected_owner_id)
    if args.command == 'recover-qwen-step-lock':
        return recover_qwen_step_lock(args.root, args.episode, args.operation, args.expected_owner_id, args.probe)
    if args.command == "prepare":
        return prepare(args.root, batch_id=args.batch_id, seed=args.seed, repeats=args.repeats,
                       harnesses=args.harness, scenario_ids=args.scenario, mode="fixture" if args.fixture else "native",
                       profiles=read_json(args.profiles) if args.profiles else None,
                       dataset_path=args.dataset,
                       judge={"protocol": "memory-checkpoint-review/v1", "model": args.judge_model, "reasoning": args.judge_reasoning})
    if args.command == "next":
        return next_action(args.root, args.episode)
    if args.command == "intent":
        return register_intent(args.root, args.episode)
    if args.command in {"advance", "retry-pre-send"}:
        return advance(args.root, args.episode, retry_pre_send=args.command == 'retry-pre-send')
    if args.command == "import-receipt":
        return import_receipt(args.root, args.episode, args.receipt)
    if args.command == "review-template":
        output = args.output.absolute()
        require(not any(output.is_relative_to(args.root.absolute() / directory) for directory in ("public", "candidate")),
                "PRIVATE_MATERIAL_LEAK", "Review templates must remain outside candidate/public directories")
        publish(output, review_template(args.root, args.episode))
        return {"review_template": str(output)}
    if args.command == "import-review":
        return import_review(args.root, args.review)
    if args.command == 'channel-template':
        output = args.output.absolute()
        require(not any(output.is_relative_to(args.root.absolute() / d) for d in ('public', 'candidate')),
                'PRIVATE_MATERIAL_LEAK', 'Channel review stays outside candidate/public directories')
        publish(output, channel_template(args.root, args.episode, args.gate))
        return {'channel_template': str(output)}
    if args.command == 'import-channel-review':
        return import_channel_review(args.root, args.review)
    if args.command == "report":
        return write_report(args.root, args.output, include_fixture=args.include_fixture)
    if args.command == "selftest":
        return selftest(args.root)
    raise AssertionError(args.command)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        payload = run(args)
        print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if isinstance(payload, dict) and payload.get('status') in {'NEEDS_ATTENTION', 'PARTIAL', 'PREREQUISITE_FAILED', 'AWAITING_CHANNEL_REVIEW'} else 0
    except (MemoryEvaluationError, OSError, KeyError, TypeError, UnicodeDecodeError) as exc:
        print(json.dumps({"status": "NEEDS_ATTENTION", "code": getattr(exc, "code", type(exc).__name__),
                          "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
