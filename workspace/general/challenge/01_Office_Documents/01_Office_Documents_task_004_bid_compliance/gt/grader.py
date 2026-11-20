"""H004 field/certificate/provenance rules; natural-language truth is semantic."""
import hashlib
import json
import os
from pathlib import Path
import runpy


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(root):
    root=Path(root).resolve();gt=root/'gt'
    truth=read(gt/'expected.json');raw=read(gt/'source_facts.json');oracle=read(gt/'business_oracle.json')
    contract=read(gt/'artifact_contract.json');boundary_spec=read(gt/'counterexamples.json')
    protected=read(gt/'protected_sha256.json');sources=read(gt/'evidence_index.json')['records'];evidence=read(gt/'evidence_requirements.json')
    native=runpy.run_path(str(gt/'native_text.py'));office=runpy.run_path(str(gt/'office_runtime.py'));io=runpy.run_path(str(gt/'structured_io.py'))
    if len(truth['issues'])!=35 or len(raw['requirements'])!=35 or len(sources)!=107 or truth['cutoff']!=raw['cutoff']:
        raise ValueError('H004 private GT incomplete')
    if any(item['source_sha256']!=protected[item['source']] for item in sources.values()):raise ValueError('H004 source index mismatch')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    output_dir=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']);output_dir.mkdir(parents=True,exist_ok=True)
    workbook=root/contract['workbook'];workbook_ok=False;workbook_error=None;matrix={};matrix_meta={}
    recalc=None
    if workbook.is_file() and not workbook.is_symlink():
        try:
            initial=native['extract_native_text'](workbook,max_chars=1_000_000)
            if initial['truncated']:workbook_error='workbook projection limit'
            else:workbook_ok=True
        except (native['NativeTextError'],OSError) as exc:workbook_error=str(exc)
        if workbook_ok:
            lock=read(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']))
            recalc=office['recalculate_xlsx'](workbook,lock,output_dir/'candidate-workbook')
            projection=native['extract_native_text'](recalc['path'],max_chars=1_000_000)
            if projection['truncated']:raise RuntimeError('trusted Office result projection limit')
            matrix,matrix_meta=io['workbook_rows'](projection,contract)
    else:workbook_error='workbook missing or not a regular file'
    response=root/contract['response'];word={};word_ok=False;word_error=None
    if response.is_file() and not response.is_symlink():
        try:
            projection=native['extract_native_text'](response,max_chars=500_000)
            if not projection['truncated']:
                word=io['response_rows'](projection,contract);word_ok=True
            else:word_error='response projection limit'
        except (native['NativeTextError'],OSError) as exc:word_error=str(exc)
    else:word_error='response missing or not a regular file'
    gap_path=root/contract['gaps'];gap_rows={};gap_schema=False
    if gap_path.is_file() and not gap_path.is_symlink() and gap_path.stat().st_size<1_000_000:
        try:gap_rows,gap_schema=io['gap_rows'](gap_path.read_text(encoding='utf-8-sig'),contract)
        except (UnicodeError,OSError):pass
    expected={row['req_id']:row for row in truth['issues']};ids=set(expected)
    checks={}
    for identity,label in expected.items():
        row=matrix.get(identity,{});present=row.get('_present',set())
        fields={key:bool(key in present and row[key]==label[key]) for key in ('mandatory','draft_status','coverage','certificate_status')}
        fields['revised_coverage']=word.get(identity,{}).get('coverage')==label['coverage']
        checks[identity]=fields
    issue_score=sum(sum(fields[key]*weight for key,weight in oracle['per_issue_weights'].items()) for fields in checks.values())/35
    mandatory_ids=set(truth['mandatory_gap_ids'])
    gap_checks={identity:bool(identity in gap_rows and gap_rows[identity].get('coverage')==expected[identity]['coverage']
                and gap_rows[identity].get('missing_evidence','').strip() and gap_rows[identity].get('proposed_action','').strip()) for identity in mandatory_ids}
    gap_score=.4*float(set(gap_rows)==mandatory_ids)+.6*sum(gap_checks.values())/len(gap_checks)
    business=oracle['issue_mean_weight']*issue_score+oracle['mandatory_gap_weight']*gap_score
    grouped={}
    for group in boundary_spec['groups']:
        grouped[group['key']]=sum(all(checks[identity][field] for field in group['fields']) for identity in group['req_ids'])/len(group['req_ids'])
    boundary=sum(grouped.values())/len(grouped)
    role_checks={}
    for identity,label in expected.items():
        row=matrix.get(identity,{});present=row.get('_present',set());roles={}
        for field in evidence['source_fields']:
            cited=io['parse_refs'](row.get(field),field,contract) if field in present else None
            needed=io['parse_refs'](label[field],field,contract)
            valid=bool(cited is not None and needed==cited)
            if valid:
                for source,record_id in cited:
                    if field=='revised_refs':
                        valid &= source=='results/response_revised.docx' and record_id in word and word[record_id].get('coverage') is not None
                    else:
                        record=sources.get(record_id)
                        valid &= bool(record and record['source']==source and record['source_sha256']==protected[source])
            roles[field]=bool(valid)
        role_checks[identity]=roles
    evidence_score=sum(sum(roles.values())/len(evidence['source_fields']) for roles in role_checks.values())/35
    full_matrix=bool(workbook_ok and set(matrix)==ids and not matrix_meta.get('conflicting_fields')
                     and all(set(contract['required_fields'])-{'req_id'}<=row['_present'] for row in matrix.values()))
    full_word=bool(word_ok and set(word)==ids and all(row.get('coverage') in set(contract['coverage_aliases'].values()) and row.get('body','').strip() for row in word.values()))
    descriptions=sum(all(field in matrix.get(identity,{}).get('_present',set()) and str(matrix[identity].get(field) or '').strip()
                         for field in ('requirement','risk','next_step')) for identity in ids)/35
    delivery=(float(full_matrix)+float(full_word)+float(gap_schema)+descriptions+float(intact))/5
    if not workbook_ok and not word_ok and not gap_schema:delivery=0.0
    if not intact:boundary,delivery,evidence_score=0.0,0.0,0.0
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence_score}
    scores['overall_score']=min(1.0,sum(scores[key]*weight for key,weight in oracle['checkpoint_weights'].items()))
    observations={'schema_version':'h004-rule-observations/v1','scores':scores,'case_checks':checks,'boundary_groups':grouped,
        'mandatory_gap_checks':gap_checks,'mandatory_gap_ids_actual':sorted(gap_rows),'mandatory_gap_score':gap_score,
        'role_bindings':role_checks,'workbook_parseable':workbook_ok,'workbook_error':workbook_error,
        'matrix_schema_complete':full_matrix,'matrix_meta':matrix_meta,'response_parseable':word_ok,'response_error':word_error,
        'response_structure_complete':full_word,'gaps_schema':gap_schema,'input_unchanged':intact,
        'source_bindings':{'workbook':sha(workbook) if workbook.is_file() else None,'response':sha(response) if response.is_file() else None,
                           'gaps':sha(gap_path) if gap_path.is_file() else None},
        'matrix_actual':{identity:{key:value for key,value in row.items() if not key.startswith('_')} for identity,row in matrix.items()},
        'response_actual':word,'gap_actual':gap_rows,'office_recalculation':recalc['audit'] if recalc else None,
        'semantic_limit':'Explicit fields/provenance only; actual prose must be independently judged against source facts, not keywords.'}
    with (output_dir/'h004-analysis.json').open('x',encoding='utf-8') as handle:
        json.dump(observations,handle,ensure_ascii=False,indent=2);handle.write('\n')
    return {'scores':scores,'observations':observations}


def grade(root):
    result=evaluate(root)
    print(json.dumps({'kind':'h004-rule-summary/v1','scores':result['scores'],'boundary_groups':result['observations']['boundary_groups']},ensure_ascii=False))
    return result['scores']
