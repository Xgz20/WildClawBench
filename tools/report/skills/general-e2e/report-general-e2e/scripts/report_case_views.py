"""Frozen task definitions and comparable per-case/per-unit score views."""
from collections import Counter
import hashlib
import json
import re

SECTION_KEYS = {"Prompt": "prompt", "Expected Behavior": "expected", "Grading Criteria": "criteria",
                "Automated Checks": "checks", "Workspace Path": "workspace", "Skills": "skills",
                "Env": "env", "Warmup": "warmup"}


def parse_task(text):
    result = {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if match:
        front = match.group(1)
        task_id = re.search(r"^id:\s*(.+)$", front, re.M)
        result["task_id"] = task_id.group(1).strip().strip("\"'") if task_id else None
        tags = re.search(r"^tags:[ \t]*(.*)$", front, re.M)
        if tags:
            inline = tags.group(1).strip()
            if inline:
                result["tags"] = ", ".join(x.strip().strip("\"'") for x in inline.strip("[]").split(","))
            else:
                block = front[tags.end():]
                values = []
                for line in block.splitlines():
                    if not line.strip():
                        continue
                    item = re.match(r"^\s+-\s+(.+)$", line)
                    if not item:
                        break
                    values.append(item.group(1).strip().strip("\"'"))
                result["tags"] = ", ".join(values)
        text = text[match.end():]
    key, lines, fence = None, [], None
    def finish():
        if key:
            result[key] = "\n".join(lines).strip()
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)[0]
            elif marker.group(1)[0] == fence:
                fence = None
        heading = re.match(r"^##\s+(.+?)\s*$", line) if fence is None else None
        if heading:
            finish()
            key, lines = SECTION_KEYS.get(heading.group(1)), []
        elif key:
            lines.append(line)
    finish()
    return result


def frozen_task_definition(task_meta, execution, score, score_path, resolve_file, sha256_file):
    definition = {"task_id": task_meta["task_id"], "sources": [], "status": "unavailable"}
    # Old/unfinished returns may lack a scoring attempt. Never read today's
    # repository task to fill historical evidence gaps.
    if score_path is None or not (score_path.parent / "attempt-manifest.json").exists():
        return definition
    manifest_path = resolve_file(score_path.parent, "attempt-manifest.json", "scoring attempt manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity = manifest.get("identity", {})
    expected = {**execution["identity"]}
    attempt = expected.pop("attempt_id")
    expected.update(execution_attempt_id=attempt, scoring_attempt_id=score["identity"]["attempt_id"])
    if identity != expected or manifest.get("dataset") != execution["dataset"]:
        raise ValueError("REPORT_TASK_DEFINITION_IDENTITY_MISMATCH")
    for role, digest_key in (("task", "task_sha256"), ("contract", "contract_sha256")):
        path = resolve_file(score_path.parent, manifest["paths"][role], f"frozen {role}")
        digest = sha256_file(path)
        if digest != manifest.get("digests", {}).get(digest_key):
            raise ValueError("REPORT_TASK_DEFINITION_DRIFT")
        if role == "task":
            definition.update(parse_task(path.read_text(encoding="utf-8")))
        else:
            contract = json.loads(path.read_text(encoding="utf-8"))
            if contract.get("task_id") != task_meta["task_id"]:
                raise ValueError("REPORT_TASK_CONTRACT_IDENTITY_MISMATCH")
            for source, target in (("expected_behavior", "expected"), ("grading_criteria", "criteria"), ("automated_checks", "checks")):
                if isinstance(contract.get(source), str):
                    definition[target] = contract[source]
        definition[role + "_sha256"] = digest
        definition["sources"].append({"path": manifest["paths"][role], "sha256": digest})
    if definition["task_id"] != task_meta["task_id"]:
        raise ValueError("REPORT_TASK_SOURCE_IDENTITY_MISMATCH")
    definition["status"] = "complete"
    return definition


def excerpt(value, max_chars=550, max_lines=12):
    if value is None or value == "":
        return None
    value = str(value)
    lines = value.splitlines()
    short = "\n".join(lines[:max_lines])[:max_chars]
    return short + "\n…（完整内容见报告 JSON）" if short != value else value


def declaration(value):
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"\s*(```|~~~)[^\n]*\n(.*?)\1\s*", value, re.S)
    if match:
        return match.group(2).strip() or None
    return value


def checkpoint_items(row):
    values = row.get("checkpoints", {}).get("values", {})
    return [(key, value) for key, value in values.items()
            if key.rsplit(".", 1)[-1] != "overall_score"
            and not re.search(r"(_max$|_calls$|_attempts$|_triggered$|(?:^|\.)penalty)", key)
            and isinstance(value, (int, float)) and not isinstance(value, bool)]


def checkpoint_text(row, *, lost_only=False):
    values = row.get("checkpoints", {}).get("values", {})
    lines = []
    for key, value in checkpoint_items(row):
        maximum = values.get(key[:-7] + "_max") if key.endswith("_earned") else None
        normalized = value/maximum if isinstance(maximum, (int, float)) and maximum > 0 else value
        if lost_only and not 0 <= normalized < 1:
            continue
        lines.append(f"{key}: {value:g}")
    if not lines and not lost_only:
        for item in (row.get("evaluation") or {}).get("criteria", []):
            value = item.get("score")
            lines.append(f"{item['key']}: {value if value is not None else '-'} ({item['status']})")
    if lost_only and row["score_status"] != "valid":
        return "评分未有效，不推断能力失分点"
    return "\n".join(lines) or ("无低于满分的检查点" if lost_only and values else None)


def score_cell(row):
    if row is None:
        return None
    total = row["total_score"]
    head = f"总分：{total * 100:.2f} / 100" if row["score_status"] == "valid" else f"总分：-（{row['score_status']}）"
    detail = checkpoint_text(row)
    return head + ("\n检查点得分（原始量纲）：\n" + detail if detail else "")


def detail_sheet_names(units, labels):
    bases = {u["unit_id"]: re.sub(r"[\\/*?:\[\]]", "_", "评分详情_" + labels[u["unit_id"]]).strip("'") for u in units}
    counts = Counter(name.casefold() for name in bases.values())
    result = {}
    for unit_id, name in bases.items():
        if len(name) > 31 or counts[name.casefold()] > 1:
            name = name[:22] + "~" + hashlib.sha1(unit_id.encode()).hexdigest()[:8]
        result[unit_id] = name
    return result


def build_case_views(data, units, labels, table, categories, modalities):
    by_task = {}
    for row in data["tasks"]:
        if row["unit_id"] in by_task.setdefault(row["task_id"], {}):
            raise ValueError("REPORT_DUPLICATE_TASK_RUN")
        by_task[row["task_id"]][row["unit_id"]] = row
    ordered = sorted(by_task, key=lambda task: (next(iter(by_task[task].values())).get("category") or "", int(re.search(r"task_(\d+)", task).group(1)) if re.search(r"task_(\d+)", task) else 999, task))
    compare_rows, meta_by_task = [], {}
    for task_id in ordered:
        rows = by_task[task_id]
        first = next(iter(rows.values()))
        if len({tuple(row.get(key) for key in ("category", "task_name", "difficulty", "modality")) for row in rows.values()}) > 1:
            raise ValueError("REPORT_TASK_METADATA_CONFLICT")
        definitions = [r.get("task_definition", {}) for r in rows.values() if r.get("task_definition", {}).get("status") == "complete"]
        signatures = {(d.get("task_sha256"), d.get("contract_sha256")) for d in definitions}
        if len(signatures) > 1:
            raise ValueError("REPORT_TASK_DEFINITION_CONFLICT")
        definition = definitions[0] if definitions else {}
        meta = [categories.get(first["category"], first["category"]), task_id, first["task_name"], first["difficulty"],
                modalities.get(first["modality"], first["modality"]), definition.get("tags"),
                excerpt(definition.get("prompt")), excerpt(definition.get("expected")), excerpt(definition.get("criteria"))]
        keys = list(dict.fromkeys(key for row in rows.values() for key, _ in checkpoint_items(row)))
        valid = [(unit["unit_id"], rows[unit["unit_id"]]["total_score"]) for unit in units if unit["unit_id"] in rows and rows[unit["unit_id"]]["score_status"] == "valid"]
        best, spread = None, None
        if len(valid) > 1:
            maximum, minimum = max(v for _, v in valid), min(v for _, v in valid)
            best = "、".join(labels[unit] for unit, value in valid if abs(value - maximum) < 1e-12)
            spread = (maximum-minimum)*100
        cells = [excerpt(score_cell(rows.get(unit["unit_id"]))) for unit in units]
        compare_rows.append([*meta, "\n".join(keys) or None, *cells, best, spread])
        meta_by_task[task_id] = meta
    compare = table(["分类", "用例ID", "用例名称", "难度", "模态", "标签", "输入(Prompt)", "预期行为", "评分标准", "检查点",
                     *[f"{labels[u['unit_id']]} 得分" for u in units], "最优单元", "最大分差"], compare_rows,
                    {str(11 + len(units)): "0.00"}, ["每题一行、单元得分并列。总分和分差为百分制，检查点保留原始量纲。有效单元不足两个时最优单元/分差显示-；并列最优全部保留。",
                     "题面来自评分 attempt 中经 SHA 校验的冻结 task.md/contract.json，展示逻辑路径；不读取当前仓库题目覆盖历史。长字段显示节选，完整内容见报告 JSON。"])
    compare["layout"] = "case_compare"
    compare["unit_scores"] = [[by_task[task].get(u["unit_id"], {}).get("total_score") if by_task[task].get(u["unit_id"], {}).get("score_status") == "valid" else None for u in units] for task in ordered]
    sheets = {}
    names = detail_sheet_names(units, labels)
    headers = ["分类", "用例ID", "用例名称", "难度", "模态", "标签", "输入(Prompt)", "预期行为", "评分标准", "Automated Checks",
               "工作目录(Workspace)", "预置技能(Skills)", "环境变量(Env)", "预热(Warmup)", "状态", "总得分", "检查点得分明细", "失分点", "裁判判词", "执行错误",
               "总tokens", "请求数", "工具调用数", "任务耗时(s)", "流程耗时(s)", "执行记录(jsonl)", "评分状态"]
    for unit in units:
        unit_id, detail_rows = unit["unit_id"], []
        for task in ordered:
            row = by_task[task].get(unit_id)
            if row is None:
                continue
            definition = row.get("task_definition", {})
            # Per-unit metadata must keep its own missing fields even if another
            # unit supplied a common definition to the comparison view.
            meta = meta_by_task[task][:5] + [definition.get("tags"), excerpt(definition.get("prompt")), excerpt(definition.get("expected")), excerpt(definition.get("criteria"))]
            reasons = "\n".join(f"{item['key']}: {item.get('reason') or '-'}" for item in (row.get("evaluation") or {}).get("criteria", []))
            errors = [row.get("execution_error"), (row.get("evaluation") or {}).get("error")]
            error_text = "\n".join(json.dumps(error, ensure_ascii=False) for error in errors if error)
            resource = lambda key: row["resource"][key]["value"] if row["resource"][key]["complete"] else None
            detail_rows.append([*meta, excerpt(definition.get("checks")), excerpt(declaration(definition.get("workspace"))), excerpt(declaration(definition.get("skills"))),
                                excerpt(declaration(definition.get("env"))), excerpt(declaration(definition.get("warmup"))), row["execution_status"],
                                row["total_score"]*100 if row["score_status"] == "valid" else None,
                                excerpt(checkpoint_text(row)), excerpt(checkpoint_text(row, lost_only=True)), excerpt(reasons), excerpt(error_text),
                                resource("total_tokens"), resource("request_count"), resource("call_count"), resource("agent_duration_seconds"), resource("duration_seconds"),
                                row.get("tool_calls", {}).get("transcript_path"), row["score_status"]])
        name = names[unit_id]
        sheets[name] = table(headers, detail_rows, {"15": "0.00", "23": "#,##0.000", "24": "#,##0.000"},
                             [f"单元：{labels[unit_id]}。检查点、失分点和判词均来自冻结评分，不重判、不生成根因分析。",
                              "长题面、规则源码和判词仅显示节选，完整内容在报告 JSON；执行记录列是相对所选回传包 unit 根目录的标准 JSONL 路径。",
                              "未加入不适用的超时/多轮统计、根因分析及暂缓的工具质量比率；旧包缺少题面时显示-。"])
        sheets[name]["layout"] = "score_detail"
    return {"case_comparison": compare, "score_details": sheets, "score_detail_order": [names[u["unit_id"]] for u in units], "score_detail_sheet_names": names}
