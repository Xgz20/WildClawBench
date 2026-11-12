"""Apply a reviewed source-reference update explicitly allowed by the task."""
import hashlib
import json
from pathlib import Path

import reference_supplement

DATA = Path(__file__).resolve().parents[1]/'data/acl2024-qa-reference-revision-v1.json'
DATA_SHA256 = '2840abedaf3895fceef2b1ae6d877c8957c9bd5c34c8dc41aa38e5c1de845a9b'


def registry():
    raw = DATA.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA256:
        raise ValueError('REFERENCE_REVISION_REGISTRY_DRIFT')
    return json.loads(raw)


def policy(root, manifest):
    task = manifest.get('identity', {}).get('task_id')
    if task != '01_Information_Search_Organization_task_001_acl2024_long_context_qa':
        return None
    if not reference_supplement.validate(root, manifest):
        return None
    revision = registry()
    if manifest['digests']['contract_sha256'] != revision['original_contract_sha256']:
        return None
    supplement = json.loads((root/reference_supplement.DIRECTORY/'manifest.json').read_bytes())
    references = {row['sha256']: row['path'] for row in supplement['files']}
    corrected = references.get(revision['corrected_reference_sha256'])
    reviewed = references.get(revision['independent_review_sha256'])
    if corrected is None and reviewed is None:
        return None
    if corrected is None or reviewed is None:
        raise ValueError('REFERENCE_REVISION_REVIEW_AND_REFERENCE_REQUIRED')
    if not supplement.get('authorization_reference', '').strip():
        raise ValueError('REFERENCE_REVISION_AUTHORIZATION_REQUIRED')
    return {
        'profile': revision['profile'], 'task_id': task,
        'registry_sha256': hashlib.sha256(DATA.read_bytes()).hexdigest(),
        'reference_supplement_manifest_sha256': hashlib.sha256((root/reference_supplement.DIRECTORY/'manifest.json').read_bytes()).hexdigest(),
        'corrected_reference_path': reference_supplement.DIRECTORY+'/'+corrected,
        'independent_review_path': reference_supplement.DIRECTORY+'/'+reviewed,
        'historical_Q': 56, 'effective_Q': 57, 'paper_count': 11,
        'source_reference_sha256': revision['original_reference_sha256'],
        'corrected_reference_sha256': revision['corrected_reference_sha256'],
        'formula_and_weights_changed': False,
        'response_field': 'reference_revision_review',
        'response_instructions': '填写Q=57、m=唯一匹配参考QA数、matched_qa_ids=实际匹配的QA001至QA057清单；条目不重复且数量等于m。C3a按原floor(20*m/Q)/20计算。',
        'instruction': '原任务允许集合外有效QA经正式原文复核、更新参考后重评。本次已完成独立参考复核及用户授权，修正参考只新增LongBench/TriviaQA，原56条及11篇论文保留。C3a的当前固定参考集合Q为57，原Rubric中当前Q=56为历史冻结注记，不再作为本次分母；按原公式floor(20*m/Q)/20及25分权重评分，不自行扩大集合。其他事实和来源项按修正参考与原文核对，不能把新有效QA当成不存在的对象；公式、分值锚点、论文范围、原作答和过程要求均不变。原规则评分使用的11篇论文集合及PDF义务不变。补正参考和复核材料属于评测输入，不能计作候选交付或候选行为。',
    }


def validate_response(expected, response):
    if expected is None:
        return
    row = next((r for r in response.get('criteria', []) if r.get('key') == 'C3a_qa_coverage'), None)
    if row is None or row.get('status') != 'judged':
        return
    review = response.get('reference_revision_review')
    if not isinstance(review, dict) or review.get('Q') != expected['effective_Q']:
        raise ValueError('REFERENCE_REVISION_Q_REQUIRED')
    count = review.get('m'); ids = review.get('matched_qa_ids')
    allowed = {f'QA{i:03}' for i in range(1,58)}
    if (isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 57
            or not isinstance(ids, list) or not all(isinstance(i, str) for i in ids)
            or len(ids) != count or len(set(ids)) != count
            or not set(ids) <= allowed):
        raise ValueError('REFERENCE_REVISION_MATCH_LEDGER_INVALID')
    expected_score = (20 * count // 57) / 20
    if isinstance(row.get('score'), bool) or not isinstance(row.get('score'), (int,float)) or abs(row['score'] - expected_score) > 1e-10:
        raise ValueError('REFERENCE_REVISION_C3A_FORMULA_MISMATCH')
