"""Scenario-first aggregation with fixed scope and explicit paired coverage."""

from __future__ import annotations

import math
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from . import CONTRACT, METRICS
from .batch import load_batch, operation_id
from .io import digest, events, publish, read_json, require, verify_artifact
from .scoring import validate_review


def _mean(values):
    return sum(values) / len(values) if values else None


def _interval(values, seed):
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    samples = sorted(_mean(rng.choices(values, k=len(values))) for _ in range(2000))
    def percentile(p):
        position = (len(samples) - 1) * p
        lo = math.floor(position)
        return samples[lo] + (samples[min(lo + 1, len(samples) - 1)] - samples[lo]) * (position - lo)
    return [percentile(.025), percentile(.975)]


def aggregate(root, *, include_fixture=False):
    manifest = load_batch(root)
    require(manifest["mode"] != "fixture" or include_fixture, "FIXTURE_NOT_FORMAL", "Use --include-fixture for pipeline QA only")
    history = events(root)
    observation_counts = Counter()
    observation_stages = Counter()
    for event in history:
        if event['kind'] == 'MEMORY_OBSERVATION':
            payload = event['payload']
            snapshot = json.loads(verify_artifact(root, payload['snapshot']))
            for file in snapshot['files']:
                verify_artifact(root, file['artifact'])
            observation_counts[snapshot['status']] += 1
            observation_stages[snapshot['stage']] += 1
    scores, failures, receipts, scoring_errors = {}, {}, [], []
    control_errors, receipt_sequences = {}, {}
    for event in history:
        payload = event["payload"]
        if event["kind"] == "RECEIPT":
            receipt_sequences[payload['operation_id']] = event['sequence']
            for artifact in payload["artifacts"].values():
                verify_artifact(root, artifact)
            for entry in payload.get("candidate_snapshot", []):
                verify_artifact(root, entry["artifact"])
            receipts.append(payload)
        if event['kind'] == 'UNCERTAIN':
            control_errors[payload['operation_id']] = {'operation_id': payload['operation_id'],
                'error_code': payload['error_code'], 'event_sequence': event['sequence']}
        if event["kind"] == "EXECUTION_ERROR":
            failures[event["episode_id"]] = payload
        if event["kind"] == "SCORING_ERROR":
            verify_artifact(root, payload["review_artifact"])
            scoring_errors.append({"episode_id": event["episode_id"], **payload})
        if event["kind"] == "SCORE":
            require(event["episode_id"] not in scores, "DUPLICATE_SCORE", event["episode_id"])
            review = read_json(Path(root) / payload["review_artifact"]["path"])
            verify_artifact(root, payload["review_artifact"])
            rebuilt = validate_review(root, review)
            require({key: value for key, value in payload.items() if key not in {"review_artifact", "scoring_attempt_id"}} == rebuilt,
                    "SCORE_DRIFT", event["episode_id"])
            scores[event["episode_id"]] = payload
    scenarios = read_json(Path(root) / "private/scenarios.json")
    latest_receipts = {receipt['operation_id']: receipt for receipt in receipts}
    from .admission import gate_results
    from .cleanup import cleanup_layers
    groups = defaultdict(list)
    rows, units, paired = [], {}, {}
    for item in manifest["episodes"]:
        score = scores.get(item["id"])
        failure = failures.get(item["id"])
        row = {key: item[key] for key in ("id", "harness", "scenario_id", "dimension", "arm", "run")}
        row.update(status="valid" if score else "evaluation_error" if any(error["episode_id"] == item["id"] for error in scoring_errors)
                   or (failure and failure["status"] == "infrastructure_error")
                   else "unsupported_product" if failure else "unscored", score=score["score"] if score else None,
                   success=score["success"] if score else None)
        steps = read_json(Path(root) / item['plan_path'])['steps']
        planned = [operation_id(manifest, item['id'], 'prepare'),
                   *[operation_id(manifest, item['id'], step['id']) for step in steps]]
        operations = [latest_receipts.get(key) for key in planned]
        completed_operations = sum(bool(receipt and receipt['status'] == 'completed') for receipt in operations)
        unresolved = [control_errors[key] for key in planned if key in control_errors
                      and control_errors[key]['event_sequence'] > receipt_sequences.get(key, -1)]
        row['unresolved_control_errors'] = unresolved
        case = scenarios[item['private_key']]
        gate_steps = list(dict.fromkeys(g['before_step'] for g in case.get('gates', []) if item['arm'] in g['arms']))
        reached = [step for step in gate_steps if all(
            latest_receipts.get(operation_id(manifest, item['id'], s['id']), {}).get('status') == 'completed'
            for s in steps[:next(i for i, s in enumerate(steps) if s['id'] == step)])]
        row['admission_gates'] = [g for step in reached for g in gate_results(root, manifest, item, step, latest_receipts)]
        admission_blocked = any(g['status'] != 'passed' for g in row['admission_gates'])
        if (admission_blocked or unresolved) and not score:
            row['status'] = 'evaluation_error'
        row['cleanup_layers'] = cleanup_layers(root, manifest, item, case, latest_receipts)
        row['execution_status'] = 'completed' if completed_operations == len(planned) else 'needs_attention' if any(
            receipt and receipt['status'] in {'needs_attention', 'infrastructure_error', 'unsupported_product'} for receipt in operations
        ) or admission_blocked or unresolved or failure else 'running' if any(operations) else 'pending'
        row['planned_prompt_steps'] = len(steps)
        row['completed_prompt_steps'] = sum(bool(receipt and receipt['status'] == 'completed') for receipt in operations[1:])
        provenance = scenarios[item["private_key"]].get("provenance", {"origin": "self_constructed"})
        row["origin"] = provenance["origin"]
        row["source_original_id"] = provenance.get("original_id")
        rows.append(row)
        groups[item["harness"], item["scenario_id"], item["arm"]].append((item, score))
    scenario_results = {}
    for key, entries in groups.items():
        observed = [score for _, score in entries if score]
        complete = len(observed) == manifest["repeats"]
        metrics = defaultdict(list)
        if complete:
            for score in observed:
                per_run = defaultdict(list)
                for check in score["checkpoints"]:
                    per_run[check["metric"]].append(check["value"])
                for metric, values in per_run.items():
                    metrics[metric].append(_mean(values))
        scenario_results[key] = {"scenario_id": key[1], "dimension": entries[0][0]["dimension"],
                                 "arm": key[2], "complete": complete, "valid_repeats": len(observed),
                                 "planned_repeats": len(entries), "score": _mean([score["score"] for score in observed]) if complete else None,
                                 "success_rate": _mean([float(score["success"]) for score in observed]) if complete else None,
                                 "repeat_scores": [score["score"] if score else None for _, score in entries],
                                 "metrics": {metric: _mean(values) for metric, values in metrics.items()}}
    for harness in manifest["harnesses"]:
        selected = [scenario_results[harness, sid, "M+"] for sid in manifest["scenario_ids"]]
        dimensions = {}
        for dimension in {row["dimension"] for row in selected}:
            planned = [row for row in selected if row["dimension"] == dimension]
            valid = [row for row in planned if row["complete"]]
            dimensions[dimension] = {"planned": len(planned), "valid": len(valid),
                                     "score": _mean([row["score"] for row in valid]),
                                     "success_rate": _mean([row["success_rate"] for row in valid])}
        metrics = {metric: {"value": _mean([row["metrics"][metric] for row in selected if metric in row["metrics"]]),
                            "valid_scenarios": sum(metric in row["metrics"] for row in selected), "direction": direction}
                   for metric, direction in METRICS.items()}
        deltas = []
        pairs = []
        for sid in manifest["scenario_ids"]:
            case = next(value for key, value in scenarios.items() if key.startswith(sid + '/r'))
            if not case["experience_gain"]:
                continue
            experienced, cold = scenario_results[harness, sid, "M+"], scenario_results.get((harness, sid, "C0"))
            if experienced["complete"] and cold and cold["complete"]:
                delta = experienced["score"] - cold["score"]
                deltas.append(delta)
                pairs.append({"scenario_id": sid, "delta": delta,
                              "repeat_deltas": [a - b for a, b in zip(experienced["repeat_scores"], cold["repeat_scores"])]})
        valid = [row for row in selected if row["complete"]]
        paired[harness] = {"scenario_count": len(deltas), "delta": _mean(deltas), "pairs": pairs,
                           "bootstrap_95": _interval(deltas, digest({"seed": manifest["seed"], "harness": harness}))}
        units[harness] = {"planned_scenarios": len(selected), "valid_scenarios": len(valid),
                          "score": _mean([row["score"] for row in valid]),
                          "success_rate": _mean([row["success_rate"] for row in valid]),
                          "dimensions": dimensions, "metrics": metrics,
                          "scenario_results": [scenario_results[harness, sid, arm]
                                               for sid in manifest["scenario_ids"] for arm in ("C0", "M+")],
                          "episode_status_counts": dict(Counter(row["status"] for row in rows if row["harness"] == harness))}
        execution_rows = [row for row in rows if row['harness'] == harness]
        units[harness]['execution'] = {'planned_episodes': len(execution_rows),
            'completed_episodes': sum(row['execution_status'] == 'completed' for row in execution_rows),
            'planned_prompt_steps': sum(row['planned_prompt_steps'] for row in execution_rows),
            'completed_prompt_steps': sum(row['completed_prompt_steps'] for row in execution_rows),
            'needs_attention_episodes': sum(row['execution_status'] == 'needs_attention' for row in execution_rows)}
    common = [sid for sid in manifest["scenario_ids"]
              if all(scenario_results[harness, sid, "M+"]["complete"] for harness in manifest["harnesses"])]
    return {"contract": CONTRACT, "dataset_id": manifest["dataset_id"], "batch_id": manifest["batch_id"],
            "mode": manifest["mode"], "report_status": "FIXTURE_ONLY" if manifest["mode"] == "fixture"
            else "COMPLETED" if len(scores) == len(manifest["episodes"]) else "PARTIAL" if scores else "UNSCORED",
            "manifest_sha256": digest(manifest), "baseline": manifest["baseline"],
            "causal_claim": manifest["causal_claim"], "episode_count": len(rows), "units": units,
            "memory_channel_policy": manifest["memory_channel_policy"],
            "scheduling_policy": manifest.get('scheduling_policy', 'legacy_unspecified'),
            "source_composition": manifest.get("source_composition", {"self_constructed": 20}),
            "background_observation_counts": dict(Counter("observed_settled" if receipt.get("background_settled") is True
                                                          else receipt.get("memory_observation", {}).get("status", "unverified")
                                                          for receipt in receipts)),
            "experience_gain": paired, "common_scenarios": common,
            "common_scores": {harness: _mean([scenario_results[harness, sid, "M+"]["score"] for sid in common])
                              for harness in manifest["harnesses"]},
            "episodes": rows, "internal_retrieval_metrics": {"status": "unobservable", "recall_at_k": None},
            "scoring_errors": scoring_errors,
            "memory_state_observations": {"counts": dict(observation_counts), "stages": dict(observation_stages),
                                           "interpretation": "Known local file snapshots; text presence is not semantic scoring or proof of formation"},
            "resource_metrics": {"status": "unavailable", "reason": "No complete memory/background resource adapter admitted"},
            "interpretation": "Fixed diagnostic scenarios; repeats are not independent scenarios. Shared-account cold-first contrasts historical experience, not a memory-module ablation."}


def write_report(root, output, *, include_fixture=False):
    report = aggregate(root, include_fixture=include_fixture)
    output = Path(output)
    require(not output.exists(), "OUTPUT_EXISTS", str(output))
    output.mkdir(parents=True)
    publish(output / "report.json", report)
    def percentage(value):
        return "-" if value is None else f"{value * 100:.2f}%"
    lines = ["# 记忆场景端到端评测报告", "", f"状态：{report['report_status']}。批次：{report['batch_id']}。", "",
             "模拟结果仅验证协议链路，不能作为任何 Harness 的能力成绩。" if report["mode"] == "fixture"
             else "使用当前登录账号，按冻结顺序先执行冷启动，再执行有经验条件。记忆作用域以阶段原始证据为准。", "",
             "| 单元 | 执行链完成/计划 | Prompt 步骤完成/计划 | 需处理执行链 |", "| --- | --- | --- | --- |"]
    lines.insert(4, "数据来源构成：" + json.dumps(report["source_composition"], ensure_ascii=False) + "。开源适配分数不等同官方原基准分数。")
    for harness, unit in report['units'].items():
        execution = unit['execution']
        lines.append(f"| {harness} | {execution['completed_episodes']}/{execution['planned_episodes']} | {execution['completed_prompt_steps']}/{execution['planned_prompt_steps']} | {execution['needs_attention_episodes']} |")
    lines += ['', '执行完成表示请求终态与证据交接完成，不等于记忆形成、答案正确或已经评分；fixture 统计仅为模拟。', '',
              '| 单元 | 有效场景/计划场景 | 任务进度分 | 任务成功率 | 完整配对场景 | 经验增益 |', '| --- | --- | --- | --- | --- | --- |']
    for harness, unit in report["units"].items():
        gain = report["experience_gain"][harness]
        delta = "-" if gain["delta"] is None else f"{gain['delta'] * 100:+.2f} pp"
        lines.append(f"| {harness} | {unit['valid_scenarios']}/{unit['planned_scenarios']} | {percentage(unit['score'])} | {percentage(unit['success_rate'])} | {gain['scenario_count']} | {delta} |")
    lines += ["", "内部检索 Recall@k 不可观测；后台记忆与全周期资源未完整接入，均保留未知。", "",
              f"所选单元共同可评场景：{', '.join(report['common_scenarios']) or '无'}。", "",
              "| 单元 | 维度 | 有效/计划 | 进度分 | 成功率 |", "| --- | --- | --- | --- | --- |"]
    for harness, unit in report["units"].items():
        for dimension, row in sorted(unit["dimensions"].items()):
            lines.append(f"| {harness} | {dimension} | {row['valid']}/{row['planned']} | {percentage(row['score'])} | {percentage(row['success_rate'])} |")
    lines += ["", "| episode | 来源 | 原题ID | 状态 | 分数 |", "| --- | --- | --- | --- | --- |"]
    for row in report["episodes"]:
        lines.append(f"| {row['id']} | {row['origin']} | {row['source_original_id'] or '-'} | {row['status']} | {percentage(row['score'])} |")
    lines += ["", "每个场景先平均检查点与独立重复，再跨场景汇总；未完成重复不进入完整场景均值。",
              "异常与未评分保持在冻结全集中，不补能力零分；经验增益只纳入预先指定的正向场景及完整配对。",
              "完整指标、各次结果、共同集合和场景级 bootstrap 区间见同源 report.json。", ""]
    gated = [r for r in report['episodes'] if r['admission_gates'] or r['cleanup_layers']]
    if gated:
        lines += ['| episode | 准入门禁 | 行为检查通过/已观察 | 已知存储残留 | 环境重置 |', '| --- | --- | --- | --- | --- |']
        for row in gated:
            cleanup = row['cleanup_layers'] or {}
            observed = [b for b in cleanup.get('behavior', []) if b['status'] in {'passed', 'failed'}]
            gates = ', '.join(g['gate_id'] + ':' + g['status'] for g in row['admission_gates']) or '未到门禁'
            storage = ', '.join(s['step_id'] + ':' + s['status'] for s in cleanup.get('known_storage', [])) or '-'
            lines.append(f"| {row['id']} | {gates} | {sum(b['status'] == 'passed' for b in observed)}/{len(observed)} | {storage} | 未准入 |")
        lines += ['', '精确 JSON 回忆只证明本轮行为。渠道为引用冻结原件的独立审核；行为、可见文件、旧来源、真实周期与环境重置分别判断，不自动升格。', '']
    publish(output / "report.md", "\n".join(lines).encode())
    return {"report_json": str(output / "report.json"), "report_markdown": str(output / "report.md"),
            "status": report["report_status"]}
