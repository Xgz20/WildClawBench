"""H009 source-faithful conversion scoring; missing infrastructure remains an error."""
from pathlib import Path
import hashlib,json,os,runpy

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mean(values):return sum(values)/len(values) if values else 0.

def grade(root):
    root=Path(root).resolve();gt=root/'gt'
    expected=read(gt/'expected.json');oracle=read(gt/'business_oracle.json');contract=read(gt/'artifact_contract.json')
    protected=read(gt/'protected_sha256.json');source_verification=read(gt/'source_verification.json')
    evidence_contract=read(gt/'evidence_requirements.json');counterexamples=read(gt/'counterexamples.json')
    source_index=read(gt/'source_evidence_index.json')
    if (expected['source_pdf_sha256']!=protected['source.pdf'] or source_verification['status']!='pass'
        or source_verification['source_sha256']!=protected['source.pdf'] or source_index['source_sha256']!=protected['source.pdf']
        or evidence_contract['required_audit_units']!=len(expected['audit_units']) or not counterexamples['boundaries']):
        raise ValueError('H009 private source contracts do not agree')
    native=runpy.run_path(str(gt/'native_checks.py'));audit=runpy.run_path(str(gt/'audit_checks.py'))
    renderer=runpy.run_path(str(gt/'render_checks.py'));office=renderer['OFFICE']
    render_lock=os.environ.get('GENERAL_E2E_OFFICE_RENDER_LOCK');output=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not render_lock or not output:raise RuntimeError('H009 requires managed Office rendering lock and evidence directory')
    lock=read(render_lock);office['validate_office_render_lock'](lock)
    if lock['profile']!=office['DOCX_RENDER_PROFILE']:raise RuntimeError('H009 requires DOCX render profile')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    document=None;analysis=None;document_error=None;render=None
    document_path=root/contract['document'];ledger_path=root/contract['ledger']
    try:
        document=native['read_document'](document_path);analysis=native['analyze'](document,expected)
    except native['CandidateWordError'] as exc:document_error=str(exc)
    if document is not None:
        try:render=renderer['render_and_measure'](document_path,render_lock,Path(output)/'word',expected,native['canon'],candidate_model=document)
        except office['OfficeRuntimeError'] as exc:
            if exc.code in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:
                render={'status':'candidate_input_unsupported','error':{'code':exc.code,'message':exc.message},'basic_fit':0.,'visible_units':{}}
            else:raise
    if analysis and render and render.get('status')=='rendered':
        for identity,visible in render['visible_units'].items():
            if visible<1:analysis['full_units'][identity]=False
    rows,metadata=audit['read_ledger'](ledger_path)
    audit_checks,audit_complete=audit['evaluate'](rows,metadata,document,analysis,expected)
    if analysis:
        visible=(render or {}).get('visible_units',{})
        table_score=sum(min(analysis['table_scores'][key],visible.get(key,0.))*weight for key,weight in oracle['table_weights'].items())
        paragraph_score=mean([min(value,visible.get(key,0.)) for key,value in analysis['paragraph_checks'].items()])
        note_visibility={note['id']:visible.get(note['target'].get('paragraph',note['target'].get('table')),0.)*visible.get(note['id'],0.) for note in expected['footnotes']}
        notes_score=mean([mean([row['text'],row['attachment']])*note_visibility[key] for key,row in analysis['note_checks'].items()])
        business=.55*table_score+.25*paragraph_score+.20*notes_score
        merge=mean([value*visible.get(key,0.) for key,group in analysis['merge_checks'].items() for value in group])
        merge*=.8+.2*mean([float(not values) for values in analysis['unexpected_merges'].values()])
        numeric_visibility=(render or {}).get('numeric_cell_visibility',{})
        numbers=mean([min(value,numeric_visibility.get(key,visible.get('T02',0.))) for key,value in analysis['numeric_checks'].items()])
        note_binding=mean([row['attachment']*note_visibility[key] for key,row in analysis['note_checks'].items()])
        order=mean(analysis['order_checks']+[float(v) for v in analysis['source_row_orders'].values()])*mean(list(visible.values()))
        boundary=.4*merge+.25*numbers+.25*note_binding+.1*order
        native_source_coverage=mean(list(analysis['paragraph_checks'].values())+list(analysis['table_scores'].values()))
        native_delivery=float(analysis['editable_native_text'] and bool(document['tables']))
        scope=float(not analysis['duplicate_records'] and not analysis['unexpected_rows'] and analysis['body_extra_text_count']==0)
        if document['body_images'] and native_source_coverage<.5:native_delivery=scope=0.
        render_fit=(render or {}).get('basic_fit',0.)
        delivery=mean([native_delivery,float(audit_complete),scope,render_fit])
    else:business=boundary=0.;delivery=.25*float(audit_complete) if metadata.get('parseable') else 0.
    statuses=mean([row['truthful_status'] for row in audit_checks.values()])
    delivery*=.8+.2*statuses
    evidence=mean([mean([row['source_pages'],row['source_locator'],row['target_locator']]) for row in audit_checks.values()])
    if not document and not metadata.get('parseable'):delivery=evidence=0.
    if not intact:boundary=delivery=evidence=0.
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence}
    scores['overall_score']=sum(scores[key]*weight for key,weight in oracle['checkpoint_weights'].items())
    if any(not 0<=value<=1 for value in scores.values()):raise ValueError('H009 score outside declared range')
    details={key:value for key,value in (analysis or {}).items() if key not in {'node_units','node_rows','node_fields','expected_rows'}}
    observation={'schema_version':'h009-rule-observations/v1','scores':scores,'native':details,'document_error':document_error,
        'input_unchanged':intact,'audit_metadata':metadata,'audit_checks':audit_checks,'render':render,
        'candidate_sha256':{'document':sha(document_path) if document_path.is_file() else None,'ledger':sha(ledger_path) if ledger_path.is_file() else None},
        'limit':'Rules observe actual native content, links and frozen PDF. They do not replace independent semantic or complete visual judgment.'}
    destination=Path(output);destination.mkdir(parents=True,exist_ok=True)
    with (destination/'h009-analysis.json').open('x',encoding='utf-8') as handle:json.dump(observation,handle,ensure_ascii=False,indent=2);handle.write('\n')
    return scores
