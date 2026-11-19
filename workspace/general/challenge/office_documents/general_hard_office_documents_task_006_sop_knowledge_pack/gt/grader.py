"""H006 explicit business fields, safe DAG endpoints and source/section bindings."""
from pathlib import Path
import csv,hashlib,json,os,runpy,zipfile
import xml.etree.ElementTree as ET

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mean(values):return sum(values)/len(values) if values else 0.0

def evaluate(root):
    root=Path(root).resolve();gt=root/'gt'
    truth=read(gt/'expected.json');oracle=read(gt/'business_oracle.json');contract=read(gt/'artifact_contract.json')
    boundary_spec=read(gt/'counterexamples.json');protected=read(gt/'protected_sha256.json')
    sources=read(gt/'evidence_index.json')['records'];requirements=read(gt/'evidence_requirements.json')['required_sources']
    model=read(gt/'model_validation.json')
    io=runpy.run_path(str(gt/'structured_io.py'));native=runpy.run_path(str(gt/'native_text.py'))
    expected={row['incident_id']:row for row in truth['incidents']};ids=set(expected)
    if ids!={'I%02d'%n for n in range(1,11)} or len(sources)!=49 or set(requirements)!=ids or model['status']!='PASS':
        raise ValueError('H006 private GT incomplete')
    if any(record['source_sha256']!=protected[record['source']] for record in sources.values()):raise ValueError('H006 source index mismatch')
    if any(not set(refs)<=set(sources) for refs in requirements.values()):raise ValueError('H006 required source index incomplete')
    if model['protected_sha256']!=protected:raise ValueError('H006 physical validation binding mismatch')
    intact=all((root/path).is_file() and not (root/path).is_symlink() and sha(root/path)==digest for path,digest in protected.items())
    artifacts={};errors={};metadata={};parseable={};hashes={}
    for kind in ('csv','operator','supervisor'):
        path=root/contract[kind];hashes[kind]=sha(path) if path.is_file() and not path.is_symlink() else None
        artifacts[kind]={};metadata[kind]={};parseable[kind]=False
        if not path.is_file() or path.is_symlink() or path.stat().st_size>5_242_880:
            errors[kind]='missing, unsafe or oversized candidate artifact';continue
        if kind=='csv':
            try:artifacts[kind],metadata[kind]=io['csv_rows'](path,contract);parseable[kind]=True
            except (UnicodeError,csv.Error,OSError) as exc:errors[kind]=str(exc)
        else:
            try:
                projection=native['extract_native_text'](path,max_chars=1_000_000)
                if projection['truncated']:errors[kind]='candidate projection exceeds limit';continue
                artifacts[kind],metadata[kind]=io['docx_rows'](projection,path,contract);parseable[kind]=True
            except (native['NativeTextError'],OSError,ET.ParseError,zipfile.BadZipFile) as exc:errors[kind]=str(exc)
    checks={};path_checks={};evidence_checks={}
    for identity,label in expected.items():
        row=artifacts['csv'].get(identity,{});steps=row.get('steps',[])
        position={node:i for i,node in enumerate(steps)}
        path_checks[identity]={'required_nodes':set(label['required_steps'])<=set(steps),
            'safe_endpoint':set(steps)==set(label['required_steps']) and len(steps)==len(set(steps)),
            'partial_order':all(a in position and b in position and position[a]<position[b] for a,b in label['required_edges'])}
        case={}
        for kind in ('csv','operator','supervisor'):
            fields=oracle[{'csv':'coverage_fields','operator':'operator_fields','supervisor':'supervisor_fields'}[kind]]
            actual=artifacts[kind].get(identity,{})
            for field in fields:
                if field=='path':ok='steps' in actual.get('_present',[]) and all(path_checks[identity].values())
                elif field=='forbidden':
                    known=set(contract['forbidden'].values())
                    ok='forbidden_steps' in actual.get('_present',[]) and set(label['forbidden_steps'])<=set(actual['forbidden_steps'])<=known
                else:
                    wanted=io['norm'](field,';'.join(label[field]) if isinstance(label[field],list) else label[field],contract)
                    ok=field in actual.get('_present',[]) and actual[field]==wanted
                case[kind+'.'+field]=bool(ok)
        checks[identity]=case
        cited=set(row.get('source_refs',[]));needed=set(requirements[identity])
        source_score=(len(cited&needed)/len(needed)) if cited<=set(sources) else 0.0
        bindings={'source_coverage':source_score}
        for kind in ('operator','supervisor'):
            actual=artifacts[kind].get(identity,{})
            required=[field for field in contract[kind+'_fields'] if field!='incident_id']
            bindings[kind+'_section']=float(io['bound_fields'](row.get(kind+'_ref',''),Path(contract[kind]).name,actual,required))
        evidence_checks[identity]=bindings
    parts={}
    for kind in ('csv','operator','supervisor'):
        parts[kind]=mean([value for case in checks.values() for field,value in case.items() if field.startswith(kind+'.')])
    business=parts['csv']*oracle['artifact_weights']['coverage']+parts['operator']*oracle['artifact_weights']['operator']+parts['supervisor']*oracle['artifact_weights']['supervisor']
    boundaries={group['key']:mean([checks[identity][field] for identity in group['ids'] for field in group['fields']]) for group in boundary_spec['groups']}
    boundary=mean(list(boundaries.values()))
    complete={};descriptions={}
    for kind in ('csv','operator','supervisor'):
        required=[field for field in contract['required_csv' if kind=='csv' else kind+'_fields'] if field!='incident_id']
        complete[kind]=parseable[kind] and set(artifacts[kind])==ids and all(set(required)<=set(row['_present']) for row in artifacts[kind].values()) and not metadata[kind].get('conflicts')
        if kind=='csv':complete[kind]&=bool(metadata[kind].get('schema'))
        field={'csv':'explanation','operator':'operator_action','supervisor':'supervision_action'}[kind]
        descriptions[kind]=mean([bool(artifacts[kind].get(identity,{}).get(field)) for identity in ids])
    delivery=mean([*complete.values(),mean(list(descriptions.values())),intact]) if any(parseable.values()) else 0.0
    evidence=mean([mean(list(item.values())) for item in evidence_checks.values()])
    if not intact:boundary=delivery=evidence=0.0
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence}
    scores['overall_score']=min(1.0,sum(scores[key]*weight for key,weight in oracle['checkpoint_weights'].items()))
    observations={'schema_version':'h006-rule-observations/v1','scores':scores,'case_checks':checks,'path_checks':path_checks,
        'artifact_business':parts,'boundary_groups':boundaries,'evidence_checks':evidence_checks,
        'parseable':parseable,'errors':errors,'structure_complete':complete,'description_presence':descriptions,
        'metadata':metadata,'input_unchanged':intact,'source_bindings':hashes,'actual':artifacts,
        'semantic_limit':'Explicit fields and source/section locations only. Natural-language truth, practical integration, contradictions and unsupported promises require independent Judge.'}
    evidence_dir=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if evidence_dir:
        output=Path(evidence_dir);output.mkdir(parents=True,exist_ok=True)
        with (output/'h006-analysis.json').open('x',encoding='utf-8') as handle:json.dump(observations,handle,ensure_ascii=False,indent=2);handle.write('\n')
    else:
        # Plain stdlib Workers preserve a SHA-bound stdout log; Office is not needed for DOCX fields.
        print(json.dumps(observations,ensure_ascii=False,sort_keys=True))
    return {'scores':scores,'observations':observations}

def grade(root):
    result=evaluate(root)
    print(json.dumps({'kind':'h006-rule-summary/v1','scores':result['scores'],'boundary_groups':result['observations']['boundary_groups']},ensure_ascii=False))
    return result['scores']
