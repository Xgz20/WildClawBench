"""Public CLI for the gated AgentCube integration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import uuid

from .common import E2EError, atomic_json, identifier, inside, read_json


def _workspace(parser):
    parser.add_argument("--workspace-root", required=True, type=Path)


def _batch(parser):
    _workspace(parser)
    parser.add_argument("--batch-id", required=True)


def _agentcube(parser):
    parser.add_argument("--agentcube-config", type=Path)


def _batch_root(args):
    return args.workspace_root.expanduser().resolve() / "batches" / identifier(args.batch_id, "batch_id")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WildClawBench 沙箱端到端执行入口")
    parser.add_argument("--api-version", type=int, choices=(1,))
    commands = parser.add_subparsers(dest="command", required=True)
    describe = commands.add_parser("describe", help="查询执行器协议与能力")
    describe.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    catalog = commands.add_parser("catalog", help="查询数据集与任务目录")
    catalog.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    catalog.add_argument("--scenario", choices=("general", "web", "all"), default="general")
    catalog.add_argument("--dataset")
    preflight = commands.add_parser("preflight", help="检查执行计划，返回实际任务范围")
    preflight.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    preflight.add_argument("--plan", type=Path, required=True)
    preflight.add_argument("--check-runtime", action="store_true", help="额外检查运行凭据、TTL 和沙箱平台域名解析，不创建沙箱")
    _agentcube(preflight)
    events = commands.add_parser("events", help="按游标只读查询执行事件")
    _batch(events)
    events.add_argument("--after-cursor", type=int, default=0)
    artifacts = commands.add_parser("artifacts", help="查询公开产物清单或读取文本")
    _batch(artifacts)
    artifacts.add_argument("--path", default="")
    artifacts.add_argument("--content", action="store_true")
    poc = commands.add_parser("poc", help="复现显式参考 BVT，记录严格 POC 证据")
    poc.add_argument("--workspace-root", required=True, type=Path)
    poc.add_argument("--reference-script", required=True, type=Path, help="受信任的 astudio-bvt.py 绝对路径")
    poc.add_argument("--agentcube-config", type=Path)
    poc.add_argument("--template")
    poc.add_argument("--batch-id")
    poc.add_argument("--keep-on-failure", action="store_true")
    poc.add_argument("--trust-env", action="store_true", help="显式继承系统代理；默认直连内网平台")
    status = commands.add_parser("status", help="只读查看批次或 POC 状态")
    status.add_argument("--workspace-root", required=True, type=Path)
    status.add_argument("--batch-id", required=True)
    run = commands.add_parser("run", help="准备并执行 General/Web 沙箱批次")
    _workspace(run)
    _agentcube(run)
    run.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    run.add_argument("--batch-id")
    run.add_argument("--plan", type=Path)
    run.add_argument("--scenario", choices=("general", "web", "all"))
    run.add_argument("--dataset")
    selection = run.add_mutually_exclusive_group()
    selection.add_argument("--task", type=Path)
    selection.add_argument("--task-id", action="append", default=[])
    selection.add_argument("--category", action="append", default=[])
    run.add_argument("--tag", action="append", default=[])
    run.add_argument("--exclude-tag", action="append", default=[])
    run.add_argument("--modality", choices=("pure-text", "multimodal"))
    run.add_argument("--harness")
    run.add_argument("--model")
    run.add_argument("--reasoning-effort", type=str.lower, choices=("none", "high", "max"))
    run.add_argument("--template")
    run.add_argument("--concurrency", "--parallel", type=int, help="批次沙箱并发，默认 3")
    run.add_argument("--runs", type=int, help="每题独立 run 数，默认 1")
    run.add_argument("--timeout-override", type=int, help="统一覆盖 wgui 运行预算（秒），默认 10800")
    run.add_argument("--scoring-mode", choices=("streaming", "batch"))
    run.add_argument("--scoring-concurrency", type=int, help="评分槽位，默认 3")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--expected-selection-sha256")
    run.add_argument("--jsonl", action="store_true", help="逐行输出持久化事件与最终回执")
    resume = commands.add_parser("resume", help="按冻结批次恢复原任务与远端 job")
    _batch(resume)
    _agentcube(resume)
    resume.add_argument("--unit-id", action="append", default=[])
    resume.add_argument("--jsonl", action="store_true")
    cleanup = commands.add_parser("cleanup", help="回收本批次登记的沙箱")
    _batch(cleanup)
    _agentcube(cleanup)
    cleanup.add_argument("--cancel", action="store_true", help="显式允许取消仍活动的本批次任务")
    restore = commands.add_parser("restore", help="从原始备份生成新的本地工作副本")
    _batch(restore)
    restore.add_argument("--execution-key", required=True)
    restore.add_argument("--destination", type=Path)
    export = commands.add_parser("export", help="导出可校验的原始执行结果压缩包")
    _batch(export)
    export.add_argument("--execution-key", action="append", default=[])
    export.add_argument("--unit-id", action="append", default=[])
    export.add_argument("--run-index", type=int)
    export.add_argument("--purpose", choices=("results", "scoring"), default="results")
    export.add_argument("--verification-skill-dir", type=Path,
                        help="显式补充 General 采集校验器，保留原批次与评分材料绑定")
    export.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("headless-score", help="使用独立 Harness CLI 沙箱评分，不重跑被测端")
    _batch(score)
    score.add_argument("--scorer-config", type=Path, required=True)
    score.add_argument("--output-root", type=Path, required=True)
    score.add_argument("--execution-key", action="append", default=[])
    report = commands.add_parser("general-report", help="从已验证的无头评分生成同源通用报告")
    report.add_argument("--source-manifest", type=Path, required=True)
    report.add_argument("--output-root", type=Path, required=True)
    imported = commands.add_parser("import", help="导入原始执行结果并核验完整性")
    _workspace(imported)
    imported.add_argument("--archive", type=Path, required=True)
    imported.add_argument("--receipt", type=Path)
    pipeline = commands.add_parser("pipeline", help="逐题或整批评分交接与现有编排器接续")
    _batch(pipeline)
    pipeline.add_argument("action", choices=("next-actions", "prepare-context", "init-orchestration", "poll", "record-submission", "compose", "takeover"))
    pipeline.add_argument("--owner", default="codex-control")
    pipeline.add_argument("--execution-key")
    pipeline.add_argument("--claim-id")
    pipeline.add_argument("--after-cursor", type=int, default=0)
    pipeline.add_argument("--wait-seconds", type=float, default=0)
    pipeline.add_argument("--previous-owner")
    pipeline.add_argument("--reason")
    pipeline.add_argument("--verification-skill-dir", type=Path,
                          help="显式冻结补充 General 收集校验器，保留批次原有 Skill 和评分材料")
    pipeline.add_argument("--score-python", type=Path,
                          help="首次初始化 General 评分编排使用的专用解释器；不改变已有编排")
    pipeline.add_argument("--orchestrator-reader-dir", type=Path,
                          help="显式绑定旧 General 编排的补充读取器，原脚本保持不变")
    return parser


def _run(args):
    from .agentcube import AgentCubeConfig
    from .engine import run_batch
    from .preparation import prepare_batch
    from .store import BatchStore
    if args.plan:
        raw = read_json(args.plan)
        if any((args.scenario, args.dataset, args.task, args.task_id, args.category, args.tag,
                args.exclude_tag, args.modality, args.harness, args.model, args.reasoning_effort, args.template)):
            raise E2EError("PLAN_AND_INLINE_UNIT_SELECTION_CONFLICT")
    else:
        unit = {"harness": args.harness or "astronstudio", "model": args.model,
                "reasoning_effort": args.reasoning_effort}
        if args.template:
            unit["template"] = args.template
        raw = {"selection": {"scenario": args.scenario, "dataset": args.dataset,
                             "task": str(args.task.resolve()) if args.task else None, "task_ids": args.task_id,
                             "categories": args.category, "tags": args.tag, "exclude_tags": args.exclude_tag,
                             "modality": args.modality}, "units": [unit]}
    for name in ("batch_id", "runs", "execution_concurrency", "scoring_mode", "scoring_concurrency", "timeout_override"):
        value = getattr(args, "concurrency" if name == "execution_concurrency" else name)
        if value is not None:
            raw[name] = value
    if args.timeout_override is not None:
        if not isinstance(raw.get("units"), list) or any(not isinstance(unit, dict) for unit in raw["units"]):
            raise E2EError("HARNESS_UNITS_MUST_BE_OBJECT_LIST")
        raw["units"] = [{**unit, "timeout_override": args.timeout_override} for unit in raw["units"]]
    config = None if args.dry_run else AgentCubeConfig.load(args.agentcube_config)
    if args.jsonl and not args.api_version:
        print(json.dumps({"type": "BATCH_PREPARING", "batch_id": raw.get("batch_id")}, ensure_ascii=False), flush=True)
    if args.expected_selection_sha256:
        batch = prepare_batch(args.repo_root, args.workspace_root, raw, expected_selection_sha256=args.expected_selection_sha256)
    else:
        batch = prepare_batch(args.repo_root, args.workspace_root, raw)
    if args.jsonl and not args.api_version:
        print(json.dumps({"type": "BATCH_PREPARED", "batch_id": batch.name, "batch_root": str(batch)}, ensure_ascii=False), flush=True)
    if args.dry_run:
        manifest = read_json(batch / "batch.json")
        return {"dry_run": True, "batch_root": str(batch), "plan": manifest["plan"],
                "unit_count": len(manifest["units"]), "selected_task_count": len(manifest["tasks"]),
                "planned_execution_count": len(BatchStore(batch).rows())}
    progress = (lambda event: _print_event(args, batch.name, event)) if args.jsonl else None
    return run_batch(batch, config, progress=progress)


def _status(args):
    from .engine import load_batch
    from .store import BatchStore
    root = _batch_root(args)
    if (root / "poc-state.json").exists():
        return read_json(root / "poc-state.json")
    load_batch(root)
    return BatchStore(root).summary()


def _resume(args):
    from .agentcube import AgentCubeConfig
    from .engine import run_batch
    progress = (lambda event: _print_event(args, args.batch_id, event)) if args.jsonl else None
    return run_batch(_batch_root(args), AgentCubeConfig.load(args.agentcube_config), unit_ids=args.unit_id, progress=progress)


def _cleanup(args):
    from .agentcube import AgentCubeConfig
    from .engine import cleanup_batch
    root = _batch_root(args)
    from .store import BatchStore
    local_only = args.cancel and all(not row.get("creation_intent_at") and not row.get("session_id") for row in BatchStore(root).rows())
    config = AgentCubeConfig() if local_only else AgentCubeConfig.load(args.agentcube_config)
    return cleanup_batch(root, config, cancel=args.cancel)


def _restore(args):
    from .artifacts import restore_execution
    from .engine import load_batch
    from .store import BatchStore, controller_lock
    from .common import digest
    root = _batch_root(args)
    load_batch(root)
    store = BatchStore(root)
    item = store.get(args.execution_key)
    # A sealed completed case is stable while unrelated cases are executing.
    # Active same-case grading still forbids changing its source pointer.
    lock_name = 'restore-' + digest(item['key'])[:16] if item['phase'] == 'COMPLETED' else 'execution'
    with controller_lock(root, lock_name), controller_lock(root, "scoring-queue"):
        if any(row["key"] == item["key"] and row["phase"] in {"CLAIMED", "RUNNING", "NEEDS_ATTENTION"}
               and (row.get('orchestration') or row['phase'] != 'CLAIMED')
               for row in store.scoring_rows()):
            raise E2EError("SCORING_ACTIVE_RESTORE_REQUIRES_QUIESCENT_ATTEMPT")
        parent = inside(root, item["execution_root"]).parent.parent / "restores"
        destination = args.destination.resolve() if args.destination else parent / ("generation-" + uuid.uuid4().hex)
        if not destination.is_relative_to(parent.resolve()):
            raise E2EError("RESTORE_DESTINATION_OUTSIDE_RESTORES")
        result = restore_execution(inside(root, item["execution_root"]), destination)
        atomic_json(parent / "current.json", result)
        return result


def _export(args):
    from .engine import load_batch
    from .packages import export_package
    from .store import BatchStore
    root = _batch_root(args)
    load_batch(root)
    keys = args.execution_key or None
    if args.unit_id or args.run_index is not None:
        rows = BatchStore(root).rows()
        if set(args.unit_id) - {row["unit_id"] for row in rows}:
            raise E2EError("EXPORT_UNIT_UNKNOWN")
        keys = [row["key"] for row in rows if (not keys or row["key"] in keys)
                and (not args.unit_id or row["unit_id"] in args.unit_id)
                and (args.run_index is None or row["run_index"] == args.run_index)]
        if not keys:
            raise E2EError("EXPORT_SELECTION_EMPTY")
    include_unsealed = False
    if args.api_version:
        from .protocol import snapshot
        include_unsealed = snapshot(root)["terminal"]
    return export_package(root, args.output.resolve(), keys=keys, purpose=args.purpose, include_unsealed=include_unsealed,
                          verification_skill=args.verification_skill_dir)


def _headless_score(args):
    from .headless import run_headless_score
    return run_headless_score(_batch_root(args), args.output_root.resolve(), read_json(args.scorer_config),
                              keys=args.execution_key or None)


def _general_report(args):
    from .general_reports import generate_report
    return generate_report(read_json(args.source_manifest), args.output_root.resolve())


def _import(args):
    from .artifacts import import_execution
    from .common import digest
    receipt = read_json(args.receipt) if args.receipt else {}
    from .packages import PACKAGE_SCHEMA, import_package
    if not receipt or receipt.get("schema") == PACKAGE_SCHEMA:
        return import_package(args.archive.resolve(), args.receipt.resolve() if args.receipt else None, args.workspace_root.expanduser().resolve())
    destination = args.workspace_root.expanduser().resolve() / "imports" / digest(receipt["identity"])
    return import_execution(args.archive.resolve(), args.receipt.resolve(), destination)


def _pipeline(args):
    from .handoff import prepare_scoring_context
    from .pipeline import init_orchestration, next_actions, poll_orchestration, record_submission
    root = _batch_root(args)
    if args.score_python is not None and args.action != 'init-orchestration':
        raise E2EError('SCORE_PYTHON_REQUIRES_INIT_ORCHESTRATION')
    if args.orchestrator_reader_dir is not None and args.action not in {'poll', 'record-submission'}:
        raise E2EError('ORCHESTRATOR_READER_REQUIRES_POLL_OR_SUBMISSION')
    if args.action == "takeover":
        from .engine import load_batch
        from .store import BatchStore
        load_batch(root)
        if not args.previous_owner or not args.reason:
            raise E2EError("PIPELINE_PREVIOUS_OWNER_AND_REASON_REQUIRED")
        BatchStore(root).transfer_pipeline_owner(args.previous_owner, args.owner, args.reason)
        return {"status": "owner_transferred", "owner": args.owner}
    if args.action == "next-actions":
        return next_actions(root, owner=args.owner, after=args.after_cursor, wait_seconds=args.wait_seconds)
    if args.action == "compose":
        from .selection import compose_results
        return compose_results(root)
    if not args.execution_key or not args.claim_id:
        raise E2EError("PIPELINE_EXECUTION_KEY_AND_CLAIM_REQUIRED")
    from .store import BatchStore
    store = BatchStore(root)
    store.check_claim_owner(args.execution_key, args.claim_id, args.owner)
    store.pipeline_owner(args.owner)
    if args.action == "prepare-context":
        return prepare_scoring_context(root, args.execution_key, args.claim_id,
                                       verification_skill=args.verification_skill_dir)
    if args.action == "init-orchestration":
        return init_orchestration(root, args.execution_key, args.claim_id, score_python=args.score_python)
    if args.action in {"poll", "record-submission"}:
        handler = poll_orchestration if args.action == "poll" else record_submission
        return handler(root, args.execution_key, args.claim_id,
                       reader_dir=args.orchestrator_reader_dir, reason=args.reason)
    handlers = {"prepare-context": prepare_scoring_context, "init-orchestration": init_orchestration,
                "poll": poll_orchestration, "record-submission": record_submission}
    return handlers[args.action](root, args.execution_key, args.claim_id)


def _print_event(args, batch_id, event):
    from .protocol import envelope, public_event
    value = envelope("event", public_event(event, batch_id)) if args.api_version else event
    print(json.dumps(value, ensure_ascii=False), flush=True)


def _public_command(args):
    from . import protocol
    if args.command == "describe":
        return protocol.describe(args.repo_root)
    if args.command == "catalog":
        return protocol.catalog(args.repo_root, args.scenario, args.dataset)
    if args.command == "preflight":
        return protocol.preflight(args.repo_root, read_json(args.plan), args.agentcube_config,
                                  check_runtime=args.check_runtime)
    if args.command == "events":
        return protocol.events(_batch_root(args), args.after_cursor)
    return protocol.artifacts(_batch_root(args), args.path, args.content)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "poc":
        from .poc import run_poc
        try:
            return run_poc(args)
        except (ValueError, FileExistsError, FileNotFoundError, ModuleNotFoundError) as error:
            print(json.dumps({"type": "POC_INPUT_ERROR", "error": str(error)}, ensure_ascii=False))
            return 2
    handlers = {"run": _run, "resume": _resume, "status": _status, "cleanup": _cleanup,
                "restore": _restore, "export": _export, "import": _import, "pipeline": _pipeline, "headless-score": _headless_score, "general-report": _general_report,
                **{name: _public_command for name in ("describe", "catalog", "preflight", "events", "artifacts")}}
    try:
        result = handlers[args.command](args)
        if args.api_version:
            from .protocol import envelope, snapshot
            if args.command in {"status", "resume", "cleanup"} or (args.command == "run" and not args.dry_run):
                result = snapshot(_batch_root(args) if args.command != "run" else args.workspace_root.expanduser().resolve() / "batches" / result["batch_id"])
            print(json.dumps(envelope("result", result), ensure_ascii=False), flush=True)
        elif getattr(args, "jsonl", False):
            print(json.dumps({"type": "BATCH_FINISHED", "result": result}, ensure_ascii=False), flush=True)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("interrupted"):
            return 130
        if result.get("status") == "NEEDS_ATTENTION" or result.get("state") == "needs_attention":
            return 3
        return 1 if result.get("status") == "FAILED" or result.get("state") in {"failed", "partial"} else 0
    except KeyboardInterrupt:
        return 130
    except (E2EError, OSError, KeyError, ValueError) as error:
        value = {"type": "E2E_ERROR", "error": str(error)}
        if args.api_version:
            from .protocol import envelope
            value = envelope("error", {"code": type(error).__name__, "message": str(error)})
        print(json.dumps(value, ensure_ascii=False))
        return 2
