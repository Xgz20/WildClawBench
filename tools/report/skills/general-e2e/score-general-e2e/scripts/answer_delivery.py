"""A completed conversation answer is not erased by a trailing bookkeeping reply."""
import ast
import hashlib

TASK = '01_Information_Search_Organization_task_007_rice_awd_field_trials'
CONTRACT_SHA = '4a8f2374c86b713fb7d25469176df613e9fc781300a438ad3899e185c9da0a02'
SOURCE_SHA = 'e105ee4485e19056ff8bdfade41d481a48873090199d208c020f254fe1834e88'
DATASET = {'id': 'general-custom116-v1', 'digest': '8a066c60dfb1b45403b5b792f9cd6264a5ee639e9cd263b8dc0acfc2031dcb01'}
PROFILE = 'completed-public-answer-delivery/v1'
POLICY = {
    'profile': PROFILE,
    'candidate_answer_scope': '同一已完成用户回合的完整公开答复窗口；显式final/end_turn仍按最后显式终稿处理。',
    'judgment': '按原子事实评价最终保留的交付：明确后续纠错覆盖旧说法；未撤回的矛盾按原Rubric处理。进度说明、待验证假设、工具返回和隐藏思考不当作正式答案，不任意择优挑选中间草稿。末尾仅更新计划或完成摘要不抹去此前实际向用户交付的完整答复。',
    'original_transcript_and_terminal_receipt_preserved': True,
    'fact_or_acquisition_credit_assigned_by_adapter': False,
}

FUNCTION = '''def _final_answer(transcript):
    if not isinstance(transcript,list) or not transcript:
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: nonempty transcript required')
    rows=[]
    for index,outer in enumerate(transcript):
        if not isinstance(outer,dict):continue
        row=outer
        for key in ('payload','message'):
            if isinstance(row.get(key),dict):row=row[key]
        rows.append((index,row))
    starts=[i for i,row in rows if row.get('type')=='task_started' or row.get('role')=='user']
    start=max(starts,default=0)
    current=[(i,row) for i,row in rows if i>=start]
    completed=[(i,row) for i,row in current if row.get('type')=='task_complete']
    if completed:current=[(i,row) for i,row in current if i<=completed[-1][0]]
    explicit=[(i,row) for i,row in current if row.get('role')=='assistant'
              and (row.get('channel')=='final' or row.get('channel') in (None,'') and row.get('end_turn') is True)]
    if explicit:
        index,message=explicit[-1]
        return _visible_text(message),{'status':'explicit_final','event_index':index,'delivery_profile':'completed-public-answer-delivery/v1'}
    if not completed:
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: final answer cannot be determined')
    end,terminal=completed[-1]
    current=[(i,row) for i,row in current if i<=end]
    messages=[(i,row,_visible_text(row)) for i,row in current
              if row.get('role')=='assistant' and row.get('channel') not in ('commentary','analysis','reasoning') and _visible_text(row)]
    receipt=terminal.get('last_agent_message')
    if receipt is not None and not isinstance(receipt,str):
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: malformed final-answer receipt')
    if not messages:
        if receipt:
            raise ValueError('EVALUATOR_EVIDENCE_MISSING: completed answer missing from public messages')
        return '',{'status':'completed_without_answer','event_index':end,'delivery_profile':'completed-public-answer-delivery/v1'}
    if 'last_agent_message' in terminal and _visible_text({'content':receipt or ''})!=messages[-1][2]:
        raise ValueError('EVALUATOR_EVIDENCE_MISSING: terminal/public-answer mismatch')
    answer='\\n\\n'.join('### 公开助手答复（原事件序号 '+str(i)+'）\\n\\n'+text for i,row,text in messages)
    return answer,{'status':'completed_public_delivery_window','event_index':end,'start_index':start,
                  'message_event_indices':[i for i,row,text in messages],
                  'delivery_profile':'completed-public-answer-delivery/v1',
                  'terminal_last_message_sha256':hashlib.sha256((receipt or '').encode()).hexdigest()}
'''


def marker(contract, contract_sha, dataset):
    if (contract.get('task_id') == TASK and contract_sha == CONTRACT_SHA
            and {key: dataset.get(key) for key in DATASET} == DATASET
            and hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest() == SOURCE_SHA):
        return {'profile': PROFILE, 'contract_sha256': CONTRACT_SHA, 'source_sha256': SOURCE_SHA}
    return None


def policy(manifest, contract):
    frozen = manifest.get('runtime', {}).get('answer_delivery_profile')
    if frozen is None:
        return None
    expected = marker(contract, manifest['digests']['contract_sha256'], manifest['dataset'])
    if expected is None or frozen != expected:
        raise ValueError('ANSWER_DELIVERY_PROFILE_MISMATCH')
    return POLICY


def effective_source(manifest, original, current, prior):
    if policy(manifest, {'task_id': manifest.get('identity', {}).get('task_id'), 'automated_checks': original}) is None:
        return current, prior
    nodes = [n for n in ast.parse(current).body if isinstance(n, ast.FunctionDef) and n.name == '_final_answer']
    if len(nodes) != 1:
        raise ValueError('ANSWER_DELIVERY_SOURCE_MISMATCH')
    old = ast.get_source_segment(current, nodes[0])
    if not old or current.count(old) != 1:
        raise ValueError('ANSWER_DELIVERY_SOURCE_MISMATCH')
    effective = current.replace(old, FUNCTION.rstrip())
    receipt = {'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1', 'correction_id': PROFILE,
        'task_id': TASK, 'contract_sha256': CONTRACT_SHA, 'original_source_sha256': SOURCE_SHA,
        'effective_source_sha256': hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten': False, 'numeric_decisions_assigned': False,
        'answer_delivery_policy': POLICY,
        'reason': '只修复对已完成会话公开交付的抽取边界，完整保留窗口与终态绑定、后续纠错和矛盾；不以最后一条收尾摘要抹掉已交付答复，不选择最长或最高分消息。原25个事实/取证联合单元、原分档、关键错误上限及100分权重不变，事实与取证仍由独立裁判逐项判断。'}
    if prior:
        receipt['prior_correction'] = prior
    return effective, receipt
