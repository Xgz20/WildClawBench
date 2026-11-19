"""Separate Data011 business summaries from chart data on the same sheet."""

import hashlib
from inspect import getsource
from io import BytesIO


TASK = "03_Data_Analysis_task_011_new_customer_purchase_funnel_retention"
CONTRACT = "2860256ab1a069c06d740a3fe41d0613682d56ba3ad07fd38119a4055ace3cdf"
SOURCE = "d4455f3f8d8c480a22b2c1f5444d9b1f9338da85baa5ae90fe231a34c7210cec"
DATASET = {
    "id": "general-custom70-v6",
    "digest": "20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288",
}
PROFILE = "funnel-disjoint-summary-tables/v1"
RUNTIME_KEY = "funnel_summary_table_profile"
ERROR_KIND = "funnel-chart-helper-overwrites-summary/v1"
REQUIRED_FIELDS = {
    "漏斗汇总": ("归属渠道", "步骤", "步骤名称", "成熟基数", "到达数", "上步数", "步骤转化率", "累计转化率"),
    "留存汇总": ("归属渠道", "留存周期", "可观察基数", "留存数", "观察不足数", "不适用数", "留存率"),
}


def _ge2e_funnel_summary_columns(headers, required):
    """Keep original layout unless a required heading is duplicated."""
    if not required or all(headers.count(name) < 2 for name in required):
        return tuple(range(len(headers)))
    blocks = []
    start = 0
    for end, heading in enumerate([*headers, ""]):
        if heading:
            continue
        block = headers[start:end]
        if all(block.count(name) == 1 for name in required):
            blocks.append(tuple(range(start, end)))
        start = end + 1
    return blocks[0] if len(blocks) == 1 else ()


def marker(contract, sha, dataset):
    source = contract.get("automated_checks", "")
    if (contract.get("task_id") == TASK and sha == CONTRACT
            and all(dataset.get(key) == value for key, value in DATASET.items())
            and hashlib.sha256(source.encode()).hexdigest() == SOURCE):
        return {"profile": PROFILE, "contract_sha256": CONTRACT, "source_sha256": SOURCE}
    return None


OLD_READER = """                headers=[norm(x) for x in rows[header_at]]
                for row in rows[header_at+1:]:
                    if any(x is not None for x in row):candidate[name].append(dict(zip(headers,row)))"""
NEW_READER = """                headers=[norm(x) for x in rows[header_at]]
                columns = _ge2e_funnel_summary_columns(headers, _GE2E_FUNNEL_FIELDS.get(name))
                for row in rows[header_at+1:]:
                    if any(row[index] is not None for index in columns):
                        candidate[name].append({headers[index]: row[index] for index in columns})"""


def effective_source(manifest, original, current, prior):
    frozen = manifest.get("runtime", {}).get(RUNTIME_KEY)
    if frozen is None:
        return current, prior
    expected = marker({"task_id": manifest["identity"]["task_id"], "automated_checks": original},
                      manifest["digests"]["contract_sha256"], manifest["dataset"])
    if expected is None or frozen != expected or current.count(OLD_READER) != 1:
        raise ValueError("FUNNEL_SUMMARY_TABLE_PROFILE_MISMATCH")
    effective = (current.replace(OLD_READER, NEW_READER) + "\n"
                 + getsource(_ge2e_funnel_summary_columns)
                 + "\n_GE2E_FUNNEL_FIELDS = " + repr(REQUIRED_FIELDS) + "\n")
    receipt = {
        "schema_version": "wildclawbench.general-e2e-rule-source-correction/v1",
        "correction_id": PROFILE,
        "task_id": TASK,
        "contract_sha256": CONTRACT,
        "original_source_sha256": SOURCE,
        "effective_source_sha256": hashlib.sha256(effective.encode()).hexdigest(),
        "candidate_rewritten": False,
        "numeric_decisions_assigned": False,
        "rubric_and_weights_changed": False,
        "reason": "仅在两张汇总页有必需表头重复时，选取空列隔开的唯一完整业务表。缺少唯一表域时不选取。原字段值、数值比较、分母与权重不变。",
    }
    if prior:
        receipt["prior_correction"] = prior
    return effective, receipt


def blocker_paths(attempt):
    if (attempt/"judge-review/evaluation-blocker.json").exists():
        import learning_summary_tables
        return learning_summary_tables.blocker_paths(attempt)
    return [attempt / name for name in ("evaluator-issue.json", "review-observations.txt", "review_inspect.py",
            "semantic-response-reviewed-not-imported.json", "semantic-response-precheck.json",
            "grader-evidence/files/评分证据/指标与分析.json",
            "candidate-original/workspace/results/用户行为分析.xlsx")]


def validate_blocker(rt, attempt, manifest, contract, task):
    """Bind the retired attempt to original worker bytes and independently reproduced cells."""
    import learning_summary_tables
    if contract.get("task_id")==learning_summary_tables.TASK:
        return learning_summary_tables.validate_blocker(rt,attempt,manifest,contract,task)
    identity = manifest["identity"]
    if (marker(contract, manifest["digests"]["contract_sha256"], manifest["dataset"]) is None
            or manifest.get("runtime", {}).get(RUNTIME_KEY)
            or (task.get("thread") or {}).get("status") != "COMPLETED"
            or any((attempt / name).exists() for name in
                   ("score.json", "semantic/response.json", "semantic/semantic-component.json"))):
        raise ValueError("FUNNEL_SUMMARY_FAILURE_IDENTITY_INVALID")
    paths = blocker_paths(attempt)
    if any(p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(attempt.resolve()) for p in paths):
        raise ValueError("FUNNEL_SUMMARY_FAILURE_EVIDENCE_INVALID")
    issue = rt._read_json(paths[0])
    if (issue.get("task_id") != TASK or issue.get("scoring_attempt_id") != identity["scoring_attempt_id"]
            or issue.get("issue_code") != "CHART_HELPER_DUPLICATE_HEADING_OVERWRITES_PRIMARY_TABLE_FIELD"
            or issue.get("formal_scoring_complete") is not False or issue.get("formal_total_score") is not None
            or issue["evidence"]["candidate_sha256"] != rt._sha256_file(paths[-1])
            or issue["evidence"]["extraction_sha256"] != rt._sha256_file(paths[-2])
            or issue["preserved_rule_component"]["sha256"] != rt._sha256_file(attempt / "rule-component.json")):
        raise ValueError("FUNNEL_SUMMARY_FAILURE_ISSUE_INVALID")
    audit = rt._read_json(attempt / "rule-audit.json")
    request = rt._read_json(attempt / "worker/request.json")
    worker = rt._read_json(attempt / "worker/result.json")
    if (audit.get("status") != "completed" or audit.get("identity") != identity
            or audit["worker"].get("return_code") != 0
            or audit["worker"].get("request_sha256") != rt._sha256_file(attempt / "worker/request.json")
            or audit["worker"].get("process_tree_cleanup", {}).get("remaining") is not False
            or worker.get("ok") is not True
            or hashlib.sha256(request["automated_checks"].encode()).hexdigest() != SOURCE):
        raise ValueError("FUNNEL_SUMMARY_FAILURE_WORKER_INVALID")
    extracted = rt._read_json(paths[-2])["汇总与修订"]
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    book = load_workbook(BytesIO(paths[-1].read_bytes()), read_only=True, data_only=True)
    try:
        observed = []
        for sheet, field in (("漏斗汇总", "步骤名称"), ("留存汇总", "留存周期")):
            rows = list(book[sheet].values)
            heading_row, heading = next((i, r) for i, r in enumerate(rows)
                                        if set(REQUIRED_FIELDS[sheet]).issubset(r))
            headers = [str(value).strip() if value is not None else "" for value in heading]
            columns = _ge2e_funnel_summary_columns(headers, REQUIRED_FIELDS[sheet])
            primary, = [i for i in columns if headers[i] == field]
            helper = max(i for i, name in enumerate(headers) if name == field)
            body = [(i, r) for i, r in enumerate(rows[heading_row + 1:], heading_row + 2)
                    if any(value is not None for value in r)]
            if headers.count(field) < 2 or primary == helper or len(body) != len(extracted[sheet]):
                raise ValueError("FUNNEL_SUMMARY_FAILURE_OVERWRITE_UNPROVED")
            index, (row_number, row) = next(
                (i, pair) for i, pair in enumerate(body)
                if pair[1][primary] is not None and pair[1][helper] is None
                and extracted[sheet][i][field] is None
            )
            observed.append({"sheet": sheet, "field": field, "primary": f"{get_column_letter(primary + 1)}{row_number}",
                             "helper": f"{get_column_letter(helper + 1)}{row_number}",
                             "value": row[primary], "original_extraction_index": index})
        return observed
    finally:
        book.close()
