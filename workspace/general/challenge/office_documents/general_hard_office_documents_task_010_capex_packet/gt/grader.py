"""H010: independent financial truth, actual input response and native handoff facts."""
from pathlib import Path
import hashlib,json,os,runpy

def private(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def grade(root):
    root=Path(root).resolve();gt=root/'gt'
    expected=private(gt/'expected.json');oracle=private(gt/'business_oracle.json');contract=private(gt/'artifact_contract.json')
    protected=private(gt/'protected_sha256.json');verification=private(gt/'source_verification.json')
    counterexamples=private(gt/'counterexamples.json');evidence_contract=private(gt/'evidence_requirements.json')
    if (expected['status']!='source_verified_before_reference' or verification['status']!='pass'
        or expected['source_sha256']!=protected or verification['files']!=protected
        or expected['enumerated_count']!=81 or not counterexamples['boundaries'] or not evidence_contract['calculation']):
        raise ValueError('H010 private truth/source contracts do not agree')
    io=runpy.run_path(str(gt/'artifact_io.py'));budget=runpy.run_path(str(gt/'budget_checks.py'))
    handoff=runpy.run_path(str(gt/'handoff_checks.py'));renderer=runpy.run_path(str(gt/'render_checks.py'))
    office=io['OFFICE'];derived_path=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    lock_path=os.environ.get('GENERAL_E2E_OFFICE_LOCK');render_path=os.environ.get('GENERAL_E2E_OFFICE_RENDER_LOCK')
    if not derived_path or not lock_path or not render_path:raise RuntimeError('H010 requires managed Office and DOCX render locks')
    derived=Path(derived_path);lock=private(lock_path);render_lock=private(render_path)
    office['validate_office_lock'](lock);office['validate_office_render_lock'](render_lock)
    if render_lock['profile']!=office['DOCX_RENDER_PROFILE'] or render_lock['office_runtime']!=lock:raise RuntimeError('H010 runtime profile conflict')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and io['sha'](root/name)==digest for name,digest in protected.items())
    errors={};objects={};tables={k:{'rows':{},'duplicates':[],'origins':[]} for k in contract['tables']}
    original=None;calculated=None;word_model=None;html_model=None;ledger={};render=None
    path=root/contract['files']['budget']
    try:
        original=io['workbook'](path)
        result=office['recalculate_xlsx'](path,lock,derived/'baseline-budget')
        calculated=io['workbook'](result['path']);tables=budget['table_set'](calculated,contract,io);objects['budget']=True
    except io['CandidateError'] as exc:errors['budget']=str(exc);objects['budget']=False
    path=root/contract['files']['application']
    try:
        word_model=io['word'](path);objects['application']=True
        try:render=renderer['render'](path,render_lock,derived/'application',word_model,io)
        except office['OfficeRuntimeError'] as exc:
            if exc.code in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:
                render={'basic_fit':False,'candidate_input_unsupported':exc.code}
            else:raise
    except io['CandidateError'] as exc:errors['application']=str(exc);objects['application']=False
    try:html_model=io['html'](root/contract['files']['plan']);objects['plan']=True
    except io['CandidateError'] as exc:errors['plan']=str(exc);objects['plan']=False
    try:ledger=io['json_object'](root/contract['files']['ledger']);objects['ledger']=True
    except io['CandidateError'] as exc:errors['ledger']=str(exc);objects['ledger']=False
    word_tables=io['word_tables'](word_model) if word_model else [];html_tables=html_model['tables'] if html_model else []
    word_rows=io['budget_rows'](word_tables,contract['budget_header_aliases']);html_rows=io['budget_rows'](html_tables,contract['budget_header_aliases'])
    word_blocks=io['word_blocks'](word_model) if word_model else [];html_blocks=html_model['blocks'] if html_model else []
    numeric=budget['baseline_checks'](tables,expected,oracle,contract,io)
    facts=handoff['analyze'](ledger,word_rows,html_rows,word_blocks,html_blocks,numeric['choice'],expected,contract,root,io)
    binding=handoff['evidence'](ledger,tables,word_rows,html_rows,word_model,numeric['choice'],root,io)
    probes=budget['responses'](root/contract['files']['budget'],original,tables,expected,oracle,contract,io,lock,derived/'input-response') if original and calculated else []
    mean=io['mean'];source_score=mean(v['pass'] for v in numeric['source_checks'].values())
    business=.25*mean(numeric['phase_checks'].values())+.20*mean(numeric['line_checks'].values())+.20*source_score
    business+=.10*numeric['option_score']+.15*mean(facts['budget_checks'].values())+.10*float(numeric['minimum_selection'])
    unknown=mean([*facts['unknown_checks'].values(),*facts['gate_checks'].values(),facts['next_check_present']])
    unknown*=float(not any(facts['unsupported_numeric_claims'].values()))
    boundary=.50*mean(v['pass'] for v in probes)+.25*mean(v for group in facts['schedule_checks'].values() for v in group.values())
    boundary+=.15*mean([*numeric['quote_checks'].values(),*facts['exclusion_checks']])+.10*unknown
    complete_lines=set(tables['lines']['rows'])==set(contract['line_ids']) and all(tables['lines']['rows'].values())
    complete_phases=set(tables['phases']['rows'])=={'P1','P2'} and all(tables['phases']['rows'].values())
    formulas=mean(bool(row and all('formula' in (row['cells'].get(k) or {}) for k in ['equipment_gross','installation_gross','maintenance_gross','crew_days'])) for row in [tables['lines']['rows'].get(id) for id in contract['line_ids']])
    native=mean([bool(complete_lines and complete_phases and formulas==1),bool(word_model and word_model['tables'] and word_model['paragraphs'] and set(word_rows)=={'P1','P2'}),
        bool(html_model and set(html_rows)=={'P1','P2'}),bool(objects['ledger'] and set(ledger)>={'selected_vendors','phase_totals','schedule','quote_exclusions','unknowns','gates','evidence'})])
    scope=bool(complete_lines and complete_phases and facts['scope_ok'])
    packaging=mean([bool(html_model and html_model['self_contained']),bool(intact and any(objects.values())),scope])
    delivery=.40*mean(objects.values())+.25*native+.20*float(bool(render and render.get('basic_fit')))+.15*packaging
    evidence=mean([mean(v.values()) for v in binding.values()]+[mean(facts['schedule_reference_checks']),mean(facts['exclusion_reference_checks'])])
    if not intact:boundary=delivery=evidence=0.
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence}
    scores['overall_score']=sum(scores[k]*w for k,w in oracle['checkpoint_weights'].items())
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H010 score out of range')
    observations={'schema_version':'h010-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,
        'parsed_outputs':objects,'numeric':numeric,'handoff':facts,'bindings':binding,'input_responses':probes,
        'native_deliveries':native,'formula_presence':formulas,'scope_ok':scope,'render':render,
        'limit':'Rules observe native data, actual cleared-cache calculations/input responses, PDF text and static HTML. Full semantic and visual quality requires independent Judge.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h010-analysis.json').open('x',encoding='utf-8') as handle:
        json.dump(observations,handle,ensure_ascii=False,indent=2,default=str);handle.write('\n')
    return scores
