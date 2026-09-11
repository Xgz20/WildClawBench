"""Render checked statistics and human findings into diagnosis / R&D Markdown."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_diagnosis_profile import finite, fingerprint, load, nonnegative
from analyze_diagnosis import verify_profile


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def table(headers, rows):
    return "\n".join(["| "+" | ".join(headers)+" |", "| "+" | ".join("---" for _ in headers)+" |"] +
                     ["| "+" | ".join(cell(v) for v in row)+" |" for row in rows])


def number(value, decimals=0):
    return f"{value:,.{decimals}f}" if finite(value) else "不可用"


def percentage(value):
    return f"{value:+.2f}%" if finite(value) else "不可比"


def unit_label(row):
    version = row["execution"].get("harness_version") or "unknown"
    return f"{row['harness']} {version}@{row['model']}"


def validate_findings(profile, data):
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise ValueError("findings must be an object containing a findings array")
    index = {(r["unit"],r["task_id"],r.get("run_id") or Path(r["run_dir"]).name):r for r in profile["records"]}
    ids = set()
    for finding in data["findings"]:
        required = ("id", "target", "title", "layer", "confidence", "observation", "scope", "task_ids",
                    "impact", "evidence", "counterevidence", "recommendation", "validation", "finding_type")
        if not isinstance(finding, dict) or any(key not in finding for key in required):
            raise ValueError("finding is missing required fields")
        for key in ("id", "title", "layer", "confidence", "observation", "recommendation", "validation", "finding_type"):
            if not isinstance(finding[key], str) or not finding[key].strip():
                raise ValueError(f"finding {key} must be nonempty text")
        target = finding["target"]
        if (not isinstance(target, dict) or target.get("kind") not in ("model", "harness")
                or not isinstance(target.get("id"), str) or not target["id"].strip()):
            raise ValueError("finding target needs kind and id")
        if not any(r[target["kind"]] == target["id"] for r in profile["records"]):
            raise ValueError("finding target is outside profile")
        if not isinstance(finding["scope"], dict):
            raise ValueError("finding scope must record coverage")
        for dimension in ("tasks", "runs"):
            affected = finding["scope"].get("affected_"+dimension)
            examined = finding["scope"].get("examined_"+dimension)
            if not nonnegative(affected, True) or not nonnegative(examined, True) or affected > examined:
                raise ValueError("finding scope requires valid affected/examined task and run counts")
        for key in ("task_ids", "counterevidence"):
            if not isinstance(finding[key], list) or not all(isinstance(v, str) for v in finding[key]):
                raise ValueError(f"finding {key} must be a text array")
        known_tasks = {r["task_id"] for r in profile["records"]}
        if not finding["task_ids"] or set(finding["task_ids"])-known_tasks:
            raise ValueError("finding task_ids must refer to selected tasks")
        if finding["id"] in ids:
            raise ValueError("duplicate finding id")
        ids.add(finding["id"])
        if finding["layer"] not in ("L1a", "L1b", "L2", "L3", "L4", "uncertain"):
            raise ValueError("invalid attribution layer")
        if finding["confidence"] not in ("confirmed", "probable", "hypothesis", "unresolved"):
            raise ValueError("invalid evidence confidence")
        if finding["finding_type"] not in ("confirmed_problem", "optimization_candidate", "unresolved"):
            raise ValueError("invalid finding type")
        if not isinstance(finding["impact"],dict) or any(not isinstance(finding["impact"].get(k),str)
                                                      for k in ("observed","causal","not_proven")):
            raise ValueError("impact must separate observed, causal, and not_proven")
        if not isinstance(finding["evidence"], list) or not finding["evidence"]:
            raise ValueError("finding requires evidence")
        runtime_count = 0
        for e in finding["evidence"]:
            if not isinstance(e, dict) or not all(isinstance(e.get(k),str) and e[k].strip()
                                                 for k in ("source","locator","excerpt")):
                raise ValueError("evidence needs source, locator, excerpt")
            source = Path(e["source"])
            if not source.is_absolute() or not source.is_file():
                raise ValueError("evidence source must be an existing absolute file")
            if e.get("sha256") and fingerprint(source) != e["sha256"]:
                raise ValueError("finding evidence fingerprint changed")
            if e.get("line") is not None:
                line = e["line"]
                if isinstance(line,bool) or not isinstance(line,int) or line < 1 or line > len(source.read_text(encoding="utf-8").splitlines()):
                    raise ValueError("evidence line is out of bounds")
            if e.get("evidence_type", "runtime") == "source_code":
                if not e.get("commit") or not e.get("symbol"):
                    raise ValueError("source evidence requires commit and symbol")
                continue
            if e.get("evidence_type", "runtime") != "runtime":
                raise ValueError("unsupported evidence_type")
            key = (e.get("unit"),e.get("task_id"),e.get("run_id"))
            if key not in index:
                raise ValueError("evidence unit/task_id/run_id is not in selected runs")
            if e["task_id"] not in finding["task_ids"]:
                raise ValueError("evidence task is not declared by finding")
            if not source.resolve().is_relative_to(Path(index[key]["run_dir"]).resolve()):
                raise ValueError("runtime evidence source is outside the named run")
            runtime_count += 1
        if runtime_count == 0:
            raise ValueError("evaluation finding needs runtime evidence, not source code alone")
    return data["findings"]


def render(profile, analysis, findings, audience="diagnosis"):
    index = {(r["unit"],r["task_id"],r.get("run_id") or Path(r["run_dir"]).name):r for r in profile["records"]}
    labels = {r["unit"]:unit_label(r) for r in profile["records"]}
    title = "Harness 与模型研发排查报告" if audience == "rd" else "Harness 与模型诊断报告"
    parts = [f"# {title}", "\n## 范围与统计口径\n",
             f"目标 Harness：{profile.get('target_harness') or '未指定'}；目标模型：{profile.get('target_model') or '未指定'}。"
             f"选中 {len(profile['records'])} 个 run，{len(analysis['units'])} 个单元。",
             "证据选择："+json.dumps(profile.get("selection", {}),ensure_ascii=False)+"。",
             "缺失矩阵格："+json.dumps(profile.get("scope", {}).get("missing_matrix_cells", []),ensure_ascii=False)+"。"
             "发现阶段问题："+json.dumps(profile.get("discovery_issues", []),ensure_ascii=False)+"。",
             "总 token 含缓存输入和输出，reasoning 不重复相加；不是费用。耗时是任务累计秒数，非批次墙钟或纯推理时间。"
             "请求数为各 Harness 记录口径，不直接等于思考轮数。不同 API、输出上限、日期或端点未控制时只说明关联。",
             "资源缺失/非法时完整总量显示不可用；coverage 中的 known_subtotal 仅是已知样本小计，不用小计计算跨单元增幅。"
             "单任务相同分数不代表产物质量所有方面一致。原始评分不改。",
             "该报告由结构化统计和人工问题账本渲染；工具不会自动证明根因或确认实验效果。"]
    if not findings:
        parts.append("**尚未录入人工核验问题：以下仅为统计观察，不是完整根因诊断。**")
    parts += ["\n## 全量资源与得分\n", table(
        ["单元", "run/可用评分任务数", "平均得分/100", "总 token", "累计秒", "请求", "资源覆盖 token/时间/请求"],
        [[labels[u],f"{s['runs']}/{s['scored_tasks']}",number(s["mean_score_pct"],4),number(s["tokens"]["total"]),number(s["elapsed_seconds_sum"],2),
          number(s["requests"]),f"{s['tokens']['coverage_runs']}/{s['elapsed_coverage_runs']}/{s['request_coverage_runs']}（分母 {s['runs']}）"]
         for u,s in analysis["units"].items()])]
    parts.append("执行状态、评分可统计性、异常判定是三个维度；可纳入评分不代表无异常，REVIEW 也不等于评分自动作废。")
    parts.append(table(["单元", "执行状态（run）", "评分可统计性（run）", "异常判定（run）"],
                       [[labels[u], json.dumps(s["execution_status"],ensure_ascii=False),
                         json.dumps(s.get("validity",{}),ensure_ascii=False),
                         json.dumps(s.get("anomaly_verdicts",{}),ensure_ascii=False)] for u,s in analysis["units"].items()]))
    incomplete = [[labels[u],metric,v["status"],f"{v['coverage_runs']}/{v['expected_runs']}",number(v["known_subtotal"],2)]
                  for u,s in analysis["units"].items() for metric,v in s["resource_coverage"].items()
                  if v["status"] != "complete"]
    if incomplete:
        parts += ["资源不完整，以下仅为已知样本小计，不可替代完整总量：",
                  table(["单元","指标","状态","覆盖 run","已知小计"],incomplete)]
    parts.append("\n## 配对统计与敏感性分析\n")
    if not analysis["pairs"]:
        parts.append("当前证据面没有可用对照组合；只有全量观察，不能据此判断目标独有的问题。需要对照时显式选择包含对侧单元的证据范围。")
    for p in analysis["pairs"]:
        parts += [f"\n### {labels[p['target_unit']]} 对 {labels[p['comparison_unit']]}\n",
                  "增幅 = 目标/对照−1；仅按任务配对，不宣称严格控制变量。",
                  table(["切片", "任务数", "同契约/不同/未知", "token 增幅", "累计耗时增幅", "请求增幅"],
                        [[name,s["tasks"],"/".join(str(s["contract_states"][k]) for k in ("same","different","unknown")),
                          percentage(s["changes"]["total_tokens"]["relative_pct"]),
                          percentage(s["changes"]["elapsed_seconds_sum"]["relative_pct"]),
                          percentage(s["changes"]["requests"]["relative_pct"])] for name,s in p["slices"].items()]),
                  "自动长尾：按本对照目标侧更高的耗时差降序选择，仅作后验敏感性。所选任务："+
                  ("、".join(p["tail_selection"]["selected_task_ids"]) or "无")+"。",
                  "双方使用相同排除集合；不表示删去问题任务等于修复。多 run 歧义任务未自动挑选："+
                  ("、".join(p["ambiguous_multi_run_tasks"]) or "无")+"。",
                  "仅目标侧任务："+("、".join(p["target_only_tasks"]) or "无")+"；仅对照侧任务："+
                  ("、".join(p["comparison_only_tasks"]) or "无")+"。",
                  "显式排除任务："+("、".join(p["explicit_exclusions"]) or "无")+"。"]
        tail_rows = [r for r in p["slices"]["all_paired"]["run_pairs"] if r["task_id"] in p["tail_selection"]["selected_task_ids"]]
        if tail_rows:
            evidence_rows = []
            for r in tail_rows:
                for side,unit in (("target",p["target_unit"]),("comparison",p["comparison_unit"])):
                    run_id = r[side+"_run_id"]
                    run = index[(unit,r["task_id"],run_id)]
                    path = Path(run["run_dir"])/"usage.json"
                    label = f"{labels[unit]}｜{r['task_id']}｜usage.json"
                    evidence_rows.append([r["task_id"],labels[unit],run_id,f"[{label}](<{path}>)" if path.is_file() else "usage.json 缺失"])
            parts.append(table(["完整任务 ID", "单元", "run_id", "长尾核验入口"], evidence_rows))
    parts.append("\n## 人工核验问题与改进项\n")
    grouped = defaultdict(list)
    for f in findings:
        grouped[(f["target"]["kind"], f["target"]["id"])].append(f)
    types = {"confirmed_problem":"确认的问题", "optimization_candidate":"优化候选", "unresolved":"尚未证明"}
    for (kind,target), entries in sorted(grouped.items()):
        parts.append(f"\n### {kind}：{target}\n")
        parts.append(table(["问题", "类型", "归因/强度"],
                           [[f["id"]+" "+f["title"], types[f["finding_type"]], f["layer"]+" / "+f["confidence"]] for f in entries]))
        for f in entries:
            parts.extend(render_finding(f,labels,types))
    parts += ["\n## 验证边界\n", "源文件核验："+json.dumps(analysis.get("verification",{}),ensure_ascii=False)+"。",
              "源码快照："+json.dumps(profile.get("source_snapshot"),ensure_ascii=False)+"。记录源码 commit 不等于已匹配评测二进制。",
              "本次报告生成不运行模型、候选代码或修复实验。人工深读范围以问题账本中的任务和 run 为准，不能将全量统计等同全量语义审计。"]
    return "\n\n".join(parts)+"\n"


def render_finding(f, labels, types):
    parts = [f"\n#### {f['id']} {f['title']}\n",
                  f"类型：{types[f['finding_type']]}；归因：{f['layer']}；证据等级：{f['confidence']}。",
                  "观察："+f["observation"], "范围："+json.dumps(f["scope"],ensure_ascii=False),
                  "观察到的影响："+f["impact"]["observed"], "已证明的因果："+f["impact"]["causal"],
                  "尚未证明："+f["impact"]["not_proven"]]
    evidence_rows=[]
    for e in f["evidence"]:
        path=e["source"]+(":"+str(e["line"]) if e.get("line") else "")
        label=f"{labels.get(e.get('unit'),'源码 '+e.get('commit',''))}｜{e.get('task_id',e.get('symbol',''))}｜{Path(e['source']).name}:{e['locator']}"
        evidence_rows.append([e.get("task_id","源码"),e.get("run_id","—"),e.get("call_id") or "未提供",
                              e.get("request_id") or "未提供",f"[{label}](<{path}>)",e["excerpt"]])
    parts += [table(["完整任务 ID", "run_id", "call_id", "request_id", "证据", "必要摘录"],evidence_rows),
              "反例/替代解释："+("；".join(f["counterevidence"]) or "未提供，不能视为不存在"),
              "建议："+f["recommendation"], "验收："+f["validation"]]
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--findings", type=Path)
    parser.add_argument("--audience", choices=["diagnosis","rd"], default="diagnosis")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        profile,analysis=load(args.profile),load(args.analysis)
        if analysis.get("profile_sha256") != fingerprint(args.profile):
            raise ValueError("analysis does not match profile fingerprint")
        verification=verify_profile(profile)
        analysis["verification"]=verification
        findings=validate_findings(profile,load(args.findings)) if args.findings else []
        if args.output.exists() and not args.overwrite:
            raise ValueError("output exists; use a new path or explicitly --overwrite")
        text=render(profile,analysis,findings,args.audience)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("w" if args.overwrite else "x",encoding="utf-8") as stream:
            stream.write(text)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"report: {args.output}; human findings: {len(findings)}")


if __name__ == "__main__":
    main()
