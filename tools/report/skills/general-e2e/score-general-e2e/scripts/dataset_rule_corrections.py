"""Narrow, source-bound grader implementation repairs; frozen rubrics stay intact."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import office_input_compat


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
    if task_id == '03_Data_Analysis_task_005_cross_month_returns_regional_sales':
        return _office_public_inputs(source)
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


def _office_public_inputs(source):
    original_sha = 'fb529c42c7a68e5f238e9c80ec71118da3afa875b7deaf5804a943b1403d4904'
    if hashlib.sha256(source.encode('utf-8')).hexdigest() != original_sha:
        return source, None
    baseline_file = Path(__file__).resolve().parents[1] / 'data/public-input-baselines/cross-month-sales-v1.json'
    baseline_bytes = baseline_file.read_bytes()
    baseline_sha = '6608c454e51ff2d508907fb1aa94d54ea1a7c9b032485e810c0db7f76a6911ad'
    if hashlib.sha256(baseline_bytes).hexdigest() != baseline_sha:
        raise ValueError('PUBLIC_OFFICE_BASELINE_SOURCE_DRIFT')
    payload = json.loads(baseline_bytes)
    old = "        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:"
    new = old[:-1] + " and not _general_e2e_public_input_matches(p,item['sha256'],base):"
    if source.count(old) != 1:
        raise ValueError('PUBLIC_OFFICE_INPUT_GUARD_MISMATCH')
    helper = Path(office_input_compat.__file__).read_text(encoding='utf-8')
    baselines = {row['sha256']: {'path': row['path'], 'base64': row['base64']} for row in payload['files']}
    effective = helper + '\n_GENERAL_E2E_PUBLIC_INPUT_BASELINES = ' + repr(baselines) + '\n\n' + source.replace(old, new)
    return effective, {
        'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1',
        'correction_id': 'canonical-public-office-cwm-only/v1',
        'task_id': payload['task_id'], 'original_source_sha256': original_sha,
        'effective_source_sha256': hashlib.sha256(effective.encode('utf-8')).hexdigest(),
        'baseline_catalog_sha256': baseline_sha,
        'canonical_public_input_sha256s': sorted(baselines),
        'reason': '仅接受与原公开输入逐个业务OPC成员字节一致的CWM自定义属性变体，原始文件及SHA保留；其他数据、样式、公式、元数据变化继续阻断。',
        'candidate_rewritten': False,
    }
