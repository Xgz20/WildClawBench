"""Typed figure audit with real Office recomputation; complete visual reasoning remains semantic."""
from pathlib import Path
import hashlib,json,os,re,runpy

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def finding_coverage(text):
    text=text or '';ids=set(re.findall(r'C0*([1-8])(?!\d)',text,re.I))
    for start,end in re.findall(r'C0*([1-8])\s*(?:[-–—~～]|至|到|to)\s*C?0*([1-8])(?!\d)',text,re.I):
        if int(start)<=int(end):ids.update(str(i) for i in range(int(start),int(end)+1))
    charts=all(re.search(r'(?:图\s*'+letter+r'|(?:chart|figure)[\s_-]*'+letter+r'(?:\.png)?)',text,re.I) for letter in ['A','B','C','D'])
    return bool(text.strip() and ids==set('12345678') and charts)
def grade(root):
    root=Path(root).resolve();gt=root/'gt'
    truth=read(gt/'expected.json');oracle=read(gt/'business_oracle.json');contract=read(gt/'artifact_contract.json')
    protected=read(gt/'protected_sha256.json');evidence=read(gt/'evidence_requirements.json');review=read(gt/'annotation_reconciliation.json');counter=read(gt/'counterexamples.json')
    if (oracle['expected_sha256']!=sha(gt/'expected.json') or oracle['source_annotation_sha256']!=sha(gt/'annotation_reconciliation.json')
        or truth['source_sha256']!=protected or evidence['source_sha256']!=protected or review['source_sha256']!=protected
        or review['human_expert_review'] is not False or review['open_annotation_issues'] or review['reviewers']!=2
        or set(truth['claims'])!={f'C{i:02}' for i in range(1,9)} or set(truth['readings'])!={f'R{i:02}' for i in range(1,21)}
        or not evidence['semantic_judge_required'] or set(counter['boundary_groups'])!=set(oracle['boundary_groups'])):raise ValueError('H022 private source contracts disagree')
    for name,digest in contract['private_helper_sha256'].items():
        if sha(gt/name)!=digest:raise ValueError('H022 private helper drift: '+name)
    io=runpy.run_path(str(gt/'artifact_io.py'));office=io['OFFICE'];mean=io['mean']
    for name in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):raise RuntimeError('missing managed H022 scoring context: '+name)
    lock=read(os.environ['GENERAL_E2E_OFFICE_LOCK']);office['validate_office_lock'](lock)
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('derived evidence must stay outside frozen Workspace')
    derived.mkdir(parents=True,exist_ok=True)
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    errors={};recalculation=None;observed_sheets=[];claims={};readings={};metadata={}
    def attempt(name,action):
        try:return action()
        except io['CandidateError'] as exc:errors[name]=str(exc);return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in io['CONTENT_ERRORS']:raise
            errors[name]=exc.code;return None
    original=attempt('workbook',lambda:io['workbook'](root/contract['workbook']))
    if original is not None:
        recalculation=attempt('recalculation',lambda:office['recalculate_xlsx'](root/contract['workbook'],lock,derived/'recalculated',timeout_seconds=90))
        if recalculation:
            observed_sheets=attempt('native_values',lambda:io['workbook'](recalculation['path'])) or []
            claims,readings,metadata=io['collect'](observed_sheets,contract)
    findings=attempt('findings',lambda:io['text'](root/contract['findings']))
    claims_check={};reading_check={};normalized={};claim_evidence={};reading_evidence={}
    for identity,label in truth['claims'].items():
        rows=claims.get(identity,[]);checks=[]
        for row in rows:
            value=row['values'];checks.append({'decision':io['decision'](value.get('decision'),contract)==label['decision'],
                'reason_present':bool(io['clean'](value.get('reason')))})
        claims_check[identity]={'decision':bool(rows) and all(c['decision'] for c in checks),'reason_present':bool(rows) and all(c['reason_present'] for c in checks),'copies':len(rows)}
    for identity,rules in oracle['reading_rules'].items():
        rows=readings.get(identity,[]);checks=[];bounds=[]
        for row in rows:
            actual,actual_unit=io['normalized_bounds'](row,rules['unit'],contract);axis=io['axis'](row['values'].get('axis'),contract)
            numeric=False;informative=False
            if actual:
                low,high=actual;band=rules['band'];center=(low+high)/2
                numeric=low<high and low<=band[1]+1e-8 and high>=band[0]-1e-8 and band[0]-rules['center_margin']<=center<=band[1]+rules['center_margin']
                informative=low<high and high-low<=rules['max_width']+1e-8
            checks.append({'unit':actual is not None,'axis':axis in rules['allowed_axes'],'numeric_interval':bool(numeric),'informative_interval':bool(informative)})
            bounds.append({'bounds':actual,'unit':actual_unit,'axis':axis,'location':row['location']})
        reading_check[identity]={key:bool(rows) and all(c[key] for c in checks) for key in ['unit','axis','numeric_interval','informative_interval']}
        reading_check[identity]['copies']=len(rows);normalized[identity]=bounds
    def row_ok(identity):return all(reading_check[identity][key] for key in ['unit','axis','numeric_interval','informative_interval'])
    def first_bounds(identity):
        values=normalized[identity]
        if not values or values[0]['bounds'] is None:return None
        first=values[0]['bounds']
        return first if all(v['bounds'] is not None and all(abs(a-b)<1e-9 for a,b in zip(first,v['bounds'])) for v in values) else None
    propagation={}
    for identity,(left,right,operation) in oracle['derived_dependencies'].items():
        required=identity in {'R13','R20'} or any(v['axis']=='derived' for v in normalized[identity])
        target=first_bounds(identity);a=first_bounds(left);b=first_bounds(right)
        if not required:propagation[identity]=row_ok(identity);continue
        if not (target and a and b):propagation[identity]=False;continue
        expected=[a[0]-b[1],a[1]-b[0]] if operation=='subtract' else [a[0]/b[1],a[1]/b[0]] if b[0]>0 and b[1]>0 else None
        tolerance=.001 if identity=='R20' else .1 if identity=='R13' else 1.
        propagation[identity]=bool(expected and target[0]<=expected[0]+tolerance and target[1]>=expected[1]-tolerance and row_ok(identity))
    def boxes(row):
        value=row['values'];out=io['regions'](value.get('source_regions'))
        if not out and all(k in value for k in ['x0','y0','x1','y1']):out=io['regions'](json.dumps([value[k] for k in ['x0','y0','x1','y1']]))
        return out
    def base_targets(identity):
        if identity in evidence['reading_targets']:return [identity]
        return [item for item in oracle['derived_dependencies'][identity][:2]]
    for identity,label in truth['readings'].items():
        rows=readings.get(identity,[]);good=[]
        for row in rows:
            own=boxes(row);source=io['image_file'](row['values'].get('source_file'));targets=base_targets(identity)
            file_ok=source=='chart_pages/chart_'+label['chart']+'.png'
            mark_ok=file_ok and all(io['hit'](own,evidence['reading_targets'][item]['data_target']) for item in targets)
            if identity in {'R13','R20'}:
                axis_ok=file_ok and all(any(io['hit'](boxes(dep_row),evidence['reading_targets'][item]['axis_target']) for dep_row in readings.get(item,[])) for item in targets)
            else:axis_ok=file_ok and io['hit'](own,evidence['reading_targets'][identity]['axis_target'])
            good.append({'file':file_ok,'data_region':mark_ok,'axis_region':axis_ok,'boxes':own})
        reading_evidence[identity]={'score':mean(mean([r['data_region'],r['axis_region']]) for r in good) if rows else 0.,'copies':good}
    for identity,label in truth['claims'].items():
        rows=claims.get(identity,[]);good=[];dependencies=evidence['claim_readings'][identity]
        chart=truth['readings'][dependencies[0]]['chart']
        for row in rows:
            own=boxes(row);value=row['values'];file_ok=io['image_file'](value.get('source_file'))=='chart_pages/chart_'+chart+'.png'
            cited=set(re.findall(r'R0*([1-9][0-9]?)(?!\d)',io['clean'](value.get('reading_ids'))+' '+io['clean'](value.get('source_regions')),re.I))
            cited={'R'+f'{int(v):02}' for v in cited}
            direct=all(io['hit'](own,evidence['reading_targets'][item]['data_target']) for item in dependencies)
            linked=set(dependencies)<=cited and all(reading_evidence[item]['score']==1. for item in dependencies)
            located=file_ok and (direct or linked)
            footnote=identity!='C08' or io['hit'](own,evidence['statistical_unknown_footnote'])
            good.append({'file':file_ok,'data_regions_or_bound_readings':located,'critical_footnote':footnote,'boxes':own})
        claim_evidence[identity]={'score':mean(r['file'] and r['data_regions_or_bound_readings'] and r['critical_footnote'] for r in good) if rows else 0.,'copies':good}
    decision_score=mean(r['decision'] for r in claims_check.values())
    interval_score=mean(mean(r[key] for key in ['unit','axis','numeric_interval','informative_interval']) for r in reading_check.values())
    business=.45*decision_score+.55*interval_score
    selected=lambda names:mean(row_ok(name) for name in names)
    boundaries={
      'dual_axis_and_units':mean([selected(['R01','R02','R03','R04']),claims_check['C01']['decision'],claims_check['C02']['decision']]),
      'stacked_components':mean([selected([f'R{i:02}' for i in range(5,11)]),propagation['R06'],propagation['R09'],claims_check['C03']['decision'],claims_check['C04']['decision']]),
      'cumulative_increment':mean([selected(['R11','R12','R13']),propagation['R13'],claims_check['C05']['decision']]),
      'unidentifiable_precision':mean([claims_check['C06']['decision'],row_ok('R11'),row_ok('R12'),propagation['R13']]),
      'truncated_axis_ratio':mean([selected(['R14','R15','R20']),propagation['R20'],claims_check['C07']['decision']]),
      'statistical_and_causal_unknown':mean([claims_check['C08']['decision'],selected([f'R{i:02}' for i in range(14,20)]),claim_evidence['C08']['score']])}
    if set(boundaries)!=set(oracle['boundary_groups']):raise ValueError('H022 boundary map differs from private contract')
    valid_claim_set=set(claims)==set(truth['claims']);valid_reading_set=set(readings)==set(truth['readings'])
    label_conflicts=[identity for identity,rows in claims.items() if len({io['decision'](r['values'].get('decision'),contract) for r in rows})>1]
    required_rows=all(claims_check[name]['reason_present'] for name in claims_check) and all(all(k in r['values'] and bool(io['clean'](r['values'][k])) for k in contract['required_reading_fields']) for rows in readings.values() for r in rows)
    findings_ok=finding_coverage(io['clean'](findings))
    delivery=mean([bool(observed_sheets),valid_claim_set and valid_reading_set and not label_conflicts,required_rows,findings_ok,intact]) if original is not None or findings else 0.
    bound_score=mean([*(r['score'] for r in reading_evidence.values()),*(r['score'] for r in claim_evidence.values())])
    scores={'business_correctness':business,'boundary_cases':mean(boundaries.values()),'delivery_integrity':delivery,'evidence_binding':bound_score}
    if not intact:scores={key:0. for key in scores}
    scores['overall_score']=sum(scores[key]*weight for key,weight in oracle['checkpoint_weights'].items())
    observation={'schema_version':'h022-rule-observations/v1','scores':scores,'input_unchanged':intact,'claim_checks':claims_check,'reading_checks':reading_check,
      'normalized_intervals':normalized,'propagation_checks':propagation,'boundary_groups':boundaries,'claim_evidence':claim_evidence,'reading_evidence':reading_evidence,
      'parse_metadata':metadata,'claim_set_complete':valid_claim_set,'reading_set_complete':valid_reading_set,'label_conflicts':label_conflicts,'findings_complete':findings_ok,
      'errors':errors,'recalculation':recalculation['audit'] if recalculation else None,'semantic_limit':oracle['semantic_limit'],
      'source_bindings':{name:sha(root/name) if (root/name).is_file() and not (root/name).is_symlink() else None for name in [contract['workbook'],contract['findings']]}}
    with (derived/'h022-analysis.json').open('x',encoding='utf-8') as handle:json.dump(observation,handle,ensure_ascii=False,indent=2);handle.write('\n')
    return scores
