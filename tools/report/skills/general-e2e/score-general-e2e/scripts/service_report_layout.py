"""Preserve explicit ticket/event links across a Markdown report's own tables."""
import hashlib

TASK = '02_Office_task_012_service_channel_ticket_daily'
CONTRACT_SHA = 'f83880ffb8709bb48b676214e0abf8b8a941bfa974960241bf3e328828f0ddab'
SOURCE_SHA = 'f1acab4a1b024ba786f6a2abdbbc23936a6a051dfafdccac0c0c36cc9b331d5b'
DATASET = {'id': 'general-custom116-v1', 'digest': '8a066c60dfb1b45403b5b792f9cd6264a5ee639e9cd263b8dc0acfc2031dcb01'}
LEGACY_PROFILE = 'service-report-linked-tables/v1'
PROFILE = 'service-report-linked-tables/v2'

OLD_DETAIL = "        is_detail=bool(not is_event_table and ('ticket' in cmap or 'key' in cmap) and set(cmap)&{'status','progress','latest','records','combined_state'})"
NEW_DETAIL = """        action_headers={norm(x) for x in ['下一步动作','下一步行动','跟进建议','要核实的结果','核实结果']}
        is_action_table=(any(norm(h) in action_headers for h in head) and 'latest' not in cmap and 'records' not in cmap)
        is_detail=bool(not is_event_table and not is_action_table and ('ticket' in cmap or 'key' in cmap) and set(cmap)&{'status','progress','latest','records','combined_state'})"""
OLD_PARSE = "    detail,metrics,counters,audit=parse_report(text,include_audit=True)"
NEW_PARSE = OLD_PARSE + "\n    diagnostics['linked_event_appendix']=_service_bind_event_appendix(detail,audit,amap,ticket_to_key)"
HELPER = '''

def _service_bind_event_appendix(detail,audit,amap,ticket_to_key):
    # Copy only the candidate's explicit foreign-key relationships. Never fill
    # missing IDs, states, timestamps, or source rows from the reference data.
    def canonical(row):
        raw=row.get('key','').strip(' `*')
        declared=tickets(row.get('ticket','')+' '+raw)
        key=amap.get(raw,raw) if raw else ''
        if key not in set(ticket_to_key.values()):
            key=ticket_to_key.get(declared[0],key) if declared else key
        return key
    mains=defaultdict(list)
    for row in detail:mains[canonical(row)].append(row)
    links=[]
    for event in audit:
        if not event.get('is_event_table'):continue
        rids=ids(event.get('records',''),'records')
        sources=ids(event.get('sources',''),'sources')
        key=canonical(event)
        # Missing/ambiguous main objects and one-to-many event cells do not get
        # rescued. Original audit checks still reject wrong/swapped source links.
        if len(rids)!=1 or len(sources)!=1 or not key or len(mains.get(key,[]))!=1:continue
        main=mains[key][0]
        existing=ids(main.get('records',''),'records')
        prior_sources=ids(main.get('sources',''),'sources')
        main['records']=' '.join(dict.fromkeys(existing+rids))
        main['sources']=' '.join(dict.fromkeys(prior_sources+sources))
        links.append({'main_line':main['line'],'event_line':event['line'],'canonical':key,
                      'record_id':rids[0],'source_row':sources[0]})
    return links
'''
HEADLINE_HELPER = '''

def _service_headline_counts(lines,metrics):
    # The report itself must declare the scalar. Do not infer it from GT or the
    # number of rows, and do not borrow a target/forecast/next-day quantity.
    pattern=r'^\\s*[-*]?\\s*(记录量|工单量)\\s*[:：]\\s*(?:([^=＝\\n]*)[=＝]\\s*)?[*`]*([0-9]+)[*`]*\\s*(?:条|件|个|单)?[。.]?\\s*$'
    for index,line in enumerate(lines):
        match=re.fullmatch(pattern,line)
        if not match or re.search(r'预计|预测|目标|次日|明日|上日|上期',match[2] or ''):continue
        name='candidate' if match[1]=='记录量' else 'unique'
        metrics[name].append({'value':int(match[3]),'line':index+1,'raw':line})
'''


def marker(contract, contract_sha, dataset):
    if (contract.get('task_id') == TASK and contract_sha == CONTRACT_SHA
            and {key: dataset.get(key) for key in DATASET} == DATASET
            and hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest() == SOURCE_SHA):
        return {'profile': PROFILE, 'contract_sha256': CONTRACT_SHA, 'source_sha256': SOURCE_SHA}
    return None


def effective_source(manifest, original, current, prior):
    frozen = manifest.get('runtime', {}).get('service_report_layout_profile')
    if frozen is None:
        return current, prior
    expected = marker({'task_id': manifest['identity']['task_id'], 'automated_checks': original},
                      manifest['digests']['contract_sha256'], manifest['dataset'])
    legacy = {**expected, 'profile': LEGACY_PROFILE} if expected is not None else None
    if expected is None or frozen not in (expected, legacy) or current != original:
        raise ValueError('SERVICE_REPORT_LAYOUT_PROFILE_MISMATCH')
    effective = current
    for old, new in ((" 'key':['事项标识'", " 'key':['归一事项标识','事项标识'"),
                     (" 'status':['当前状态'", " 'status':['日报状态','当前状态'"),
                     (OLD_DETAIL, NEW_DETAIL), (OLD_PARSE, NEW_PARSE)):
        if effective.count(old) != 1:
            raise ValueError('SERVICE_REPORT_LAYOUT_SOURCE_MISMATCH')
        effective = effective.replace(old, new)
    effective += HELPER
    if frozen['profile'] == PROFILE:
        old="    counters={family:defaultdict(list) for family in ('category','status','progress','priority')}"
        if effective.count(old)!=1:raise ValueError('SERVICE_REPORT_HEADLINE_SOURCE_MISMATCH')
        effective=effective.replace(old,"    _service_headline_counts(lines,metrics)\n"+old)+HEADLINE_HELPER
    return effective, {
        'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1', 'correction_id': frozen['profile'],
        'task_id': TASK, 'contract_sha256': CONTRACT_SHA, 'original_source_sha256': SOURCE_SHA,
        'effective_source_sha256': hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten': False, 'numeric_decisions_assigned': False,
        'reason': ('识别归一事项标识、日报状态等价表头；区分跟进建议表与主工单明细，避免同一工单的建议被重复计为对象；接受候选事件附录中显式的工单外键、record_id/source_row关联。只复制候选自身明确关系，不补写参考字段，重复主表、错配来源、范围/状态/别名及原70/30评分继续按原规则判断。'
                   if frozen['profile']==LEGACY_PROFILE else
                   '在v1表角色与显式附录关联修复上，识别记录量/工单量中带说明及等号的明确数量声明。不从GT或明细行数推算标题数量，目标/预测/次日数量不准入；原范围、状态、金额、分母和70/30权重不变。'),
    }
