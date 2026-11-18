"""Two explicit news column names; preserve original scoring and old profiles."""
from __future__ import annotations
import hashlib
import re
from io import BytesIO

TASK = '02_Office_task_003_news_event_multifile_extract'
CONTRACT_SHA = 'aa0729866b2e01eed5afded886a72633140bbe0478335969b37e088b687296a2'
SOURCE_SHA = 'e7500c47aec4d700e217546cb9efcbc25b06fa360586eaa79b0b191d68826dd5'
PRIOR_SOURCE_SHA = 'f93566fe176758953c40c63f1747a8248a864948588f7a02393f59e1b51f3702'
DATASET = {'id': 'general-custom70-v6', 'digest': '20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'}
PROFILE = 'news-two-explicit-equivalent-column-names/v1'
ERROR_KIND = 'news-native-header-extraction-review/v1'
HEADINGS = {'alias_seen': '别名/原文名称', 'merged_source_count': '报道片段总数'}

BRIDGE = r'''
_news_explicit_equivalent_names = {'alias_seen': '别名/原文名称', 'merged_source_count': '报道片段总数'}
for _news_field, _news_heading in _news_explicit_equivalent_names.items():
    COLUMNS[_news_field] = COLUMNS[_news_field] + [_news_heading]
_news_explicit_names_previous_reader = read_workbook

def read_workbook(data):
    # Use the original table/header selection. Multiple aliases for the same
    # newly recognized field are ambiguous and require review, never last-wins.
    workbook = openpyxl.load_workbook(BytesIO(data), data_only=True, read_only=False, keep_links=False)
    try:
        for key, names in SHEETS.items():
            matched = [s for s in workbook if norm(s.title) in {norm(n) for n in names}]
            if len(matched) != 1:
                continue  # The original reader retains missing/ambiguous-table handling.
            sheet = matched[0]
            if sheet.max_row > 4000 or sheet.max_column > 120:
                raise EvidenceError('Workbook dimensions exceed evidence extraction capacity; review required')
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            for merge in sheet.merged_cells.ranges:
                value = rows[merge.min_row-1][merge.min_col-1]
                for r in range(merge.min_row-1, merge.max_row):
                    for c in range(merge.min_col-1, merge.max_col):
                        rows[r][c] = value
            lookup = {norm(alias): field for field in FIELDS[key] for alias in COLUMNS[field]}
            candidates = [(len({lookup[norm(v)] for v in row if norm(v) in lookup}), -i, row)
                          for i, row in enumerate(rows[:15])]
            if not candidates:
                continue
            score, _, header = max(candidates, key=lambda item: (item[0], item[1]))
            if score < 2:
                continue
            for field, heading in _news_explicit_equivalent_names.items():
                if field not in FIELDS[key] or norm(heading) not in [norm(v) for v in header]:
                    continue
                aliases = {norm(v) for v in COLUMNS[field]}
                if sum(norm(v) in aliases for v in header) != 1:
                    raise EvidenceError('Ambiguous explicit news equivalent column; review required: ' + field)
    finally:
        workbook.close()
    return _news_explicit_names_previous_reader(data)
'''


def marker(contract, contract_sha, dataset):
    if (contract.get('task_id') == TASK and contract_sha == CONTRACT_SHA
            and {k: dataset.get(k) for k in DATASET} == DATASET
            and hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest() == SOURCE_SHA):
        return {'profile': PROFILE, 'contract_sha256': CONTRACT_SHA, 'source_sha256': SOURCE_SHA,
                'prior_effective_source_sha256': PRIOR_SOURCE_SHA, 'headings': HEADINGS,
                'bridge_sha256': hashlib.sha256(BRIDGE.encode()).hexdigest()}
    return None


def effective_source(manifest, original, current, prior):
    frozen = manifest.get('runtime', {}).get('news_header_equivalence_profile')
    if frozen is None:
        return current, prior
    expected = marker({'task_id': manifest['identity']['task_id'], 'automated_checks': original},
                      manifest['digests']['contract_sha256'], manifest['dataset'])
    if (expected is None or frozen != expected
            or hashlib.sha256(current.encode()).hexdigest() != PRIOR_SOURCE_SHA):
        raise ValueError('NEWS_EXPLICIT_HEADER_PROFILE_MISMATCH')
    effective = current + '\n' + BRIDGE
    receipt = {'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1',
               'correction_id': PROFILE, 'task_id': TASK, 'contract_sha256': CONTRACT_SHA,
               'original_source_sha256': SOURCE_SHA, 'prior_effective_source_sha256': PRIOR_SOURCE_SHA,
               'effective_source_sha256': hashlib.sha256(effective.encode()).hexdigest(),
               'equivalent_headings': HEADINGS, 'candidate_rewritten': False,
               'numeric_decisions_assigned': False, 'rubric_and_weights_changed': False,
               'reason': '仅识别两项明确等价中文表头，保留原单元格、完整取证、20组别名/来源分母、五类十格比较、数值函数及12/8分权重；重复字段拒绝，未知表头不推断。'}
    if prior:
        receipt['prior_correction'] = prior
    return effective, receipt


def validate_blocker(rt, attempt, manifest, contract, task):
    """Prove the old parser omission; never assign a replacement rule score."""
    if (marker(contract, manifest['digests']['contract_sha256'], manifest['dataset']) is None
            or (task.get('thread') or {}).get('status') != 'COMPLETED' or task.get('score') is not None
            or any((attempt / p).exists() for p in ['score.json', 'semantic/response.json', 'semantic/semantic-component.json'])
            or manifest.get('runtime', {}).get('news_header_equivalence_profile') is not None
            or manifest.get('runtime', {}).get('shared_rule_source_repair') != {
                'profile': 'news-equivalent-headings-and-explicit-rollup-scope/v1',
                'source_sha256': SOURCE_SHA, 'current_source_sha256': PRIOR_SOURCE_SHA}):
        raise ValueError('NEWS_HEADER_FAILURE_IDENTITY_OR_PHASE_INVALID')
    audit = rt._read_json(attempt / 'rule-audit.json')
    request = rt._read_json(attempt / 'worker/request.json')
    worker = rt._read_json(attempt / 'worker/result.json')
    correction = rt._read_json(attempt / 'rule-source-correction.json')
    if (audit.get('status') != 'completed' or audit.get('identity') != manifest['identity']
            or audit.get('worker', {}).get('return_code') != 0
            or audit.get('worker', {}).get('process_tree_cleanup', {}).get('remaining') is not False
            or audit['worker'].get('request_sha256') != rt._sha256_file(attempt / 'worker/request.json')
            or worker.get('ok') is not True or not (attempt / 'rule-component.json').is_file()
            or hashlib.sha256(request.get('automated_checks', '').encode()).hexdigest() != PRIOR_SOURCE_SHA
            or correction.get('effective_source_sha256') != PRIOR_SOURCE_SHA
            or audit.get('source_correction', {}).get('sha256') != rt._sha256_file(attempt / 'rule-source-correction.json')):
        raise ValueError('NEWS_HEADER_FAILURE_WORKER_BINDING_INVALID')
    blocker = rt._read_json(attempt / 'infrastructure-review.json')
    if (blocker.get('task_id') != TASK or blocker.get('scoring_attempt_id') != manifest['identity']['scoring_attempt_id']
            or blocker.get('origin') != 'evaluator' or blocker.get('status') != 'NEEDS_ATTENTION'
            or any(blocker.get(k) is not False for k in ['formal_score_published', 'semantic_response_imported',
                'verify_score_passed', 'candidate_original_modified', 'rules_rerun', 'harness_rerun'])
            or blocker.get('frozen_component_preserved') is not True):
        raise ValueError('NEWS_HEADER_NATIVE_REVIEW_INVALID')
    expected = {'automated.entity_links': ('entity_mentions', 'alias_seen'),
                'automated.category_rollup': ('category_summary', 'merged_source_count')}
    issues = blocker.get('issues', [])
    if len(issues) != 2 or {x.get('criterion_key') for x in issues} != set(expected):
        raise ValueError('NEWS_HEADER_REVIEW_SCOPE_INVALID')
    evidence_path = attempt / 'grader-evidence/files/evaluator_evidence/03_other_tables.json'
    tables = rt._read_json(evidence_path)['tables']
    originals = list((attempt / manifest['paths']['candidate_original'] / 'results').glob('*.xlsx'))
    if len(originals) != 1 or originals[0].is_symlink():
        raise ValueError('NEWS_HEADER_CANDIDATE_SCOPE_INVALID')
    import openpyxl
    workbook = openpyxl.load_workbook(BytesIO(originals[0].read_bytes()), data_only=True, keep_links=False)
    observations = []
    try:
        for issue in issues:
            table, field = expected[issue['criterion_key']]
            if issue.get('header') != HEADINGS[field]:
                raise ValueError('NEWS_HEADER_REVIEW_HEADING_INVALID')
            location = re.fullmatch(r'(.+)!([A-Z]+)([1-9]\d*):\2([1-9]\d*)', issue.get('candidate_location', ''))
            if location is None:
                raise ValueError('NEWS_HEADER_REVIEW_LOCATION_INVALID')
            reported_sheet, column, first, last = location.groups(); first, last = int(first), int(last)
            extracted = tables.get(table)
            if (not isinstance(extracted, list) or not extracted
                    or any(row.get(field) is not None for row in extracted)):
                raise ValueError('NEWS_HEADER_OMISSION_NOT_PROVEN')
            # The native report may describe a table in prose. Resolve its
            # actual sheet exclusively from the frozen extractor's row locators;
            # retain the claimed label separately and expose any disagreement.
            locations = [re.fullmatch(r'(.+)!row([1-9]\d*)', row.get('_location', '')) for row in extracted]
            if any(item is None for item in locations) or len({item[1] for item in locations}) != 1:
                raise ValueError('NEWS_HEADER_EXTRACTED_LOCATION_INVALID')
            sheet = locations[0][1]
            if (sheet not in workbook.sheetnames or not 1 <= first <= 15
                    or not first < last <= min(4000, workbook[sheet].max_row)
                    or not 1 <= openpyxl.utils.column_index_from_string(column) <= min(120, workbook[sheet].max_column)
                    or workbook[sheet][f'{column}{first}'].value != HEADINGS[field]):
                raise ValueError('NEWS_HEADER_CANDIDATE_HEADING_DRIFT')
            cells = [workbook[sheet][f'{column}{row}'].value for row in range(first+1, last+1)]
            if not any(value is not None and str(value).strip() for value in cells):
                raise ValueError('NEWS_HEADER_OMISSION_NOT_PROVEN')
            observations.append({'criterion': issue['criterion_key'], 'header': HEADINGS[field],
                                 'native_reported_location': issue['candidate_location'],
                                 'observed_location': f'{sheet}!{column}{first}:{column}{last}',
                                 'native_sheet_label_matches': reported_sheet == sheet,
                                 'location_derivation': 'bound original extractor row locators and canonical workbook header',
                                 'extracted_field': field,
                                 'candidate_values_present': True, 'old_extraction_missing': True})
    finally:
        workbook.close()
    return {'profile': PROFILE, 'observations': observations, 'numeric_score_assigned': False,
            'worker_source_sha256': PRIOR_SOURCE_SHA}
