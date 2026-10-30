"""Narrow, source-bound grader implementation repairs; frozen rubrics stay intact."""
from __future__ import annotations

import hashlib


EVIDENCE_PAGING_PROFILE = "complete-paged-grader-evidence/v1"
_PAGED_RULES = {
    "02_Office_task_002_html_report_quadrant_ppt": (
        "9be11b175636ff50b7d2a1b588665c4f2c0c4e9a787d4d2a4ebee81846cec958",
        "    if any(len(t)>19000 for t in docs.values()) or sum(map(len,docs.values()))>74000:",
        "    if any(len(t.encode('utf-8'))>4*1024*1024 for t in docs.values()) or sum(len(t.encode('utf-8')) for t in docs.values())>16*1024*1024:",
    ),
    "02_Office_task_028_inspection_notice_provenance": (
        "b07de671ee37090df73d6276f8819ecc5048f00595d8717ca48bdee682e7ebb6",
        "    if sum(len(t) for _, t in payloads) > 60000:",
        "    if any(len(t.encode('utf-8'))>4*1024*1024 for _,t in payloads) or sum(len(t.encode('utf-8')) for _,t in payloads)>16*1024*1024:",
    ),
}


def effective_source(task_id: str, source: str):
    entry = _PAGED_RULES.get(task_id)
    digest = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if entry is None or digest != entry[0]:
        return source, None
    _, old, new = entry
    if source.count(old) != 1:
        raise ValueError("DATASET_RULE_CORRECTION_SOURCE_MISMATCH")
    effective = source.replace(old, new)
    return effective, {
        "schema_version": "wildclawbench.general-e2e-rule-source-correction/v1",
        "correction_id": EVIDENCE_PAGING_PROFILE,
        "task_id": task_id,
        "original_source_sha256": digest,
        "effective_source_sha256": hashlib.sha256(effective.encode('utf-8')).hexdigest(),
        "reason": "评分取证完整落盘并通过既有分页接口查询；调整传输资源上限，不截断证据，不改变题面、检查点、权重或分值锚点。",
        "evidence_policy": {"truncation_allowed": False, "page_query_required": True,
                            "max_file_bytes": 4*1024*1024, "max_total_bytes": 16*1024*1024},
    }
