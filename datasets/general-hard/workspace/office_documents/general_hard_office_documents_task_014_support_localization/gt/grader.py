"""H014 deterministic routing, coverage and source observations; semantics belong to the Judge."""
from pathlib import Path
import hashlib,json,os,runpy

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mean(items):
    values=list(items)
    return sum(values)/len(values) if values else 0.
def grade(root):
    root=Path(root).resolve();gt=root/'gt'
    truth=read(gt/'expected.json');contract=read(gt/'artifact_contract.json');oracle=read(gt/'business_oracle.json')
    protected=read(gt/'protected_sha256.json');review=read(gt/'language_review_v2.json')
    evidence=read(gt/'evidence_requirements.json');counter=read(gt/'counterexamples.json')
    if (truth['status']!='source_truth_and_authorized_model_reviews_accepted' or truth['source_sha256']!=protected
        or oracle['expected_sha256']!=sha(gt/'expected.json') or oracle['review_sha256']!=sha(gt/'language_review_v2.json')
        or review['human_expert_review'] is not False or review['open_records']
        or set(truth['cases'])!={f'C{i:02}' for i in range(1,19)}
        or set(truth['faq_claims'])!={f'K{i:02}' for i in range(1,13)}
        or not evidence['semantic_judge_required'] or not counter['semantic_controls']):raise ValueError('H014 private contracts disagree')
    for name,digest in contract['private_helper_sha256'].items():
        if sha(gt/name)!=digest:raise ValueError('H014 private helper drift: '+name)
    io=runpy.run_path(str(gt/'artifact_io.py'));office=io['OFFICE']
    for name in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):raise RuntimeError('missing managed scoring context: '+name)
    lock=read(os.environ['GENERAL_E2E_OFFICE_LOCK']);render_lock=read(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK'])
    office['validate_office_lock'](lock);office['validate_office_render_lock'](render_lock)
    if render_lock['office_runtime']!=lock or 'docx' not in office['office_render_lock_formats'](render_lock):raise RuntimeError('H014 mismatching Word runtime lock')
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('derived evidence must be outside frozen Workspace')
    derived.mkdir(parents=True,exist_ok=True)
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    errors={};documents={};renders={}
    def attempt(name,action):
        try:return action()
        except io['CandidateError'] as exc:errors[name]=str(exc);return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in io['CONTENT_ERRORS']:raise
            errors[name]=exc.code;return None
    for lang,path in contract['documents'].items():
        doc=attempt(lang,lambda p=path:io['word'](root/p));documents[lang]=doc
        if doc:renders[lang]=attempt(lang+'_render',lambda p=path,l=lang,d=doc:io['render'](root/p,render_lock,derived/l,d['paragraphs']))
    parsed=attempt('replies',lambda:io['replies'](root/contract['replies'],contract['csv_columns']))
    rows,meta=parsed if parsed else ({},{'columns':[],'duplicates':[],'empty_ids':0})
    duplicate_cases=set(meta['duplicates']);routing={};reply_coverage={};case_refs={}
    valid_facts={f'F{i:02}' for i in range(1,13)}
    for identity,label in truth['cases'].items():
        row=rows.get(identity,{});exists=bool(row) and identity not in duplicate_cases
        routing[identity]=bool(exists and row.get('locale')==label['locale'] and row.get('topic_id')==label['topic_id'] and row.get('decision')==label['decision'])
        reply_coverage[identity]=bool(exists and row.get('reply'))
        refs=io['refs'](row.get('source_refs',''))
        case_refs[identity]=bool(exists and set(evidence['cases'][identity])<=refs<=valid_facts)
    topic_coverage={};topic_refs={};doc_complete={}
    for lang,path in contract['documents'].items():
        doc=documents[lang];render=renders.get(lang);topics=doc['topics'] if doc else {};duplicates=set(doc['duplicate_ids']) if doc else set()
        topic_coverage[lang]={};topic_refs[lang]={}
        for identity in truth['faq_claims']:
            parts=topics.get(identity,[])
            # Accept a table row containing both heading and answer, or normal paragraphs.
            content=parts[1:] if len(parts)>1 else ['\n'.join(parts[0].splitlines()[1:])] if parts else []
            actual=[p for p in content if p.strip() and not io['refs'](p)]
            # A legitimate paragraph can combine a body and citation.
            if not actual:actual=[p for p in content if len(io['canon'](p).split('release_notes.md')[0])>0]
            topic_coverage[lang][identity]=bool(identity not in duplicates and actual)
            refs=io['refs']('\n'.join(parts))
            topic_refs[lang][identity]=bool(set(evidence['faq'][identity])<=refs<=valid_facts)
        doc_complete[lang]=bool(doc and doc['body_editable'] and not doc['pending_revisions'] and not duplicates
            and set(topics)==set(truth['faq_claims']) and all(topic_coverage[lang].values()) and render and render['basic_fit'])
    csv_complete=bool(parsed and set(rows)==set(truth['cases']) and not meta['duplicates'] and not meta['empty_ids']
        and all(reply_coverage.values()) and all(row.get('locale')==truth['cases'][identity]['locale'] and row.get('topic_id')==truth['cases'][identity]['topic_id'] for identity,row in rows.items() if identity in truth['cases']))
    scores={'case_routing':mean(routing.values()),'faq_coverage':mean(v for rows_ in topic_coverage.values() for v in rows_.values()),
            'delivery_integrity':mean([*doc_complete.values(),csv_complete,intact]),
            'evidence_binding':mean([*case_refs.values(),*(v for rows_ in topic_refs.values() for v in rows_.values())])}
    if not intact:scores={k:0. for k in scores}
    scores['overall_score']=sum(scores[key]*weight for key,weight in oracle['checkpoint_weights'].items())
    observation={'schema_version':'h014-rule-observations/v1','scores':scores,'input_unchanged':intact,'case_routing':routing,
        'reply_coverage':reply_coverage,'faq_coverage':topic_coverage,'case_reference_ids':case_refs,'faq_reference_ids':topic_refs,
        'documents_complete':doc_complete,'csv_complete':csv_complete,'csv_metadata':meta,'errors':errors,
        'observed_documents':documents,'observed_replies':rows,'render':renders,
        'source_bindings':{path:sha(root/path) if (root/path).is_file() and not (root/path).is_symlink() else None for path in [*contract['documents'].values(),contract['replies']]},
        'semantic_limit':oracle['semantic_limit']}
    with (derived/'h014-analysis.json').open('x',encoding='utf-8') as handle:json.dump(observation,handle,ensure_ascii=False,indent=2);handle.write('\n')
    return scores
