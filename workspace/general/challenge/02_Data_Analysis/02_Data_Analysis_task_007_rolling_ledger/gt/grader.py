"""Source-first ledger grading, with actual frozen-Office late-entry responses."""
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import hashlib,json,os,runpy

def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt';load=lambda n:json.loads((gt/n).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    contract=load('scoring_contract.json')
    if sha(gt/'grader.py')!=contract['grading_source_sha256']:raise ValueError('H023 grader source drift')
    for name,want in contract['private_sha256'].items():
        if sha(gt/name)!=want:raise ValueError('H023 private scoring drift '+name)
    expected=load('source_expected.json');records=load('source_records.json');protected=load('protected_sha256.json')
    if len(expected['audit'])!=270 or len(records['orders'])!=180 or len(records['payments'])!=90:raise ValueError('H023 incomplete private source oracle')
    io=runpy.run_path(str(gt/'ledger_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));mean=lambda a:sum(a)/len(a) if a else 0.
    for key in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(key):raise RuntimeError('H023 missing managed runtime '+key)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());office['validate_office_lock'](lock)
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H023 derived evidence must be outside frozen Workspace')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    baseline=None;native=None;exception=None;method=None;inventory=None;errors={};responses=[];cap=None
    def candidate(name):
        p=root/'results'/name
        if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=5*1024*1024:raise io['CandidateError']('missing, empty or oversized '+name)
        return p
    def attempt(label,action):
        try:return action()
        except (io['CandidateError'],UnicodeError) as exc:errors[label]=str(exc);return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[label]=exc.code;return None
    def workbook():
        nonlocal native,inventory
        path=candidate('ledger.xlsx');office['_clean_package'](path.read_bytes())
        inventory=io['raw_inventory'](path,records)
        native=office['recalculate_xlsx'](path,lock,derived/'baseline',timeout_seconds=120)
        return io['observe'](native['path'],expected)
    baseline=attempt('ledger',workbook)
    exception=attempt('exceptions',lambda:io['read_exceptions'](candidate('exceptions.csv'),expected))
    method=attempt('method',lambda:io['read_method'](candidate('method.md'),expected))
    # Test editable source bindings in the candidate itself. Formula audit views
    # never qualify as native input. If there are preserved raw snapshots, test
    # every matching literal binding and retain the actual driving response.
    if baseline is not None and intact:
        source=candidate('ledger.xlsx');base_truth=io['truth_map'](expected)
        for name,rid in [('late_invoice','O169'),('late_receipt','P073'),('late_refund','P086')]:
            kind='orders' if rid[0]=='O' else 'payments';record=next(r for r in records[kind] if r['record_id']==rid)
            targets=io['raw_targets'](source,record,kind)
            if len(targets)>8:raise RuntimeError('H023 more than eight equivalent literal input copies require manual binding; no ability zero')
            want=load('scenarios/'+name+'/source_expected.json');truth=io['truth_map'](want)
            affected=[key for key,value in truth.items() if key not in base_truth or value!=base_truth[key]]
            # Only numerical business results prove effective response. Merely
            # editing the input or echoing a new ID is insufficient.
            numeric=[key for key in affected if isinstance(truth[key],(int,float)) or key.rsplit('/',1)[-1] in io['MONEY']]
            if not affected or not numeric:raise ValueError('H023 source-level intervention has no numerical effect')
            trials=[]
            for index,target in enumerate(targets):
                serial=(datetime(2026,10,4,12)-(datetime(1904,1,1) if target['date1904'] else datetime(1899,12,30))).total_seconds()/86400
                edit={key:target[key] for key in ['sheet','cell']}|{'value':serial}
                prepared=office['prepare_xlsx_counterfactual'](source,[edit],derived/name/str(index)/'prepared')
                office['verify_xlsx_counterfactual'](source,prepared['path'],prepared['audit'])
                calc=office['recalculate_xlsx'](prepared['path'],lock,derived/name/str(index)/'calculated',timeout_seconds=120)
                obs=io['observe'](calc['path'],want);checks=obs['checks'];changed=mean([checks.get(key,False) for key in affected]);num=mean([checks.get(key,False) for key in numeric])
                unaffected=all(value for key,value in checks.items() if key in base_truth and key not in affected)
                trials.append({'target':target,'prepared':prepared,'recalculation':calc,'observation':obs,'changed_score':changed,'numeric_response':num,'unaffected_correct':unaffected,'score':changed*unaffected})
            best=max(trials,key=lambda t:t['score']) if trials else None
            responses.append({'name':name,'record_id':rid,'affected_keys':affected,'numeric_keys':numeric,'trials':trials,'score':best['score'] if best else 0.,'numeric_response':best['numeric_response'] if best else 0.})
    b=baseline['scores'] if baseline else {};business=.2*b.get('customers',0)+.25*b.get('flow',0)+.2*b.get('lots',0)+.15*b.get('months',0)+.1*b.get('controls',0)+.1*(exception['score'] if exception else 0)
    grouped=defaultdict(list)
    if baseline:
        for rid,row in expected['audit'].items():
            grouped[row['decision']].extend(value for key,value in baseline['checks'].items() if key.startswith('audit/'+rid+'/'))
    audit_score=mean([mean(values) for values in grouped.values()]);response_score=mean([r['score'] for r in responses]) if len(responses)==3 else 0.
    boundary=.25*audit_score+.75*response_score
    if not baseline or not intact or not inventory or not inventory['complete']:
        business=min(business,.5);boundary=0.;cap='missing baseline, changed protected source or incomplete native raw records'
    elif len(responses)!=3 or not any(r['numeric_response'] for r in responses):
        business=min(business,.5);cap='no correct numerical business response to native late-entry inputs'
    integrity=float(intact and inventory is not None and inventory['complete'] and baseline is not None and baseline['complete'] and exception is not None and exception['complete'] and method is not None and method['complete'] and response_score==1.)
    binding=(.8*(exception['binding_score'] if exception else 0)+.2*(method['score'] if method else 0))*intact
    scores={key:round(value,12) for key,value in {'business_correctness':business,'boundary_cases':boundary*intact,'delivery_integrity':integrity,'evidence_binding':binding}.items()}
    scores['overall_score']=round(sum(scores[key]*weight for key,weight in contract['weights'].items()),12)
    if any(not 0<=value<=1 for value in scores.values()):raise ValueError('H023 invalid score range')
    report={'schema_version':'h023-native-ledger-rule/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'raw_inventory':inventory,'baseline':baseline,'office_baseline':native,'exceptions':exception,'method':method,'responses':responses,'business_cap_reason':cap,'audit_group_score':audit_score,'response_score':response_score,
        'limit':'Automated source, native math, visible table, input-response and bounded disclosed-control consistency only. Not accounting expert prose review, full visual QA, real Harness/model run or measured L4 difficulty.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h023-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    return scores
