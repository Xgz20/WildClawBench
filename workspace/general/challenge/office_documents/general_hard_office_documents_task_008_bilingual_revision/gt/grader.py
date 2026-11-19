"""H008 typed facts and actual native literals; full bilingual meaning is semantic."""
from pathlib import Path
import csv,hashlib,json,os,runpy

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mean(values):return sum(values)/len(values) if values else 0.

def evaluate(root):
    root=Path(root).resolve();gt=root/'gt';truth=read(gt/'expected.json');contract=read(gt/'artifact_contract.json');oracle=read(gt/'business_oracle.json')
    protected=read(gt/'protected_sha256.json');index=read(gt/'evidence_index.json')['records'];requirements=read(gt/'evidence_requirements.json')['required_sources']
    model=read(gt/'model_validation.json');counterexamples=read(gt/'counterexamples.json')
    native=runpy.run_path(str(gt/'native_docx.py'));io=runpy.run_path(str(gt/'structured_io.py'));literal=runpy.run_path(str(gt/'native_values.py'))
    expected={row['sentence_id']:row for row in truth['sentences']};comments={row['comment_id']:row for row in truth['comments']}
    ids={f'S{i:02d}' for i in range(1,17)};rids={f'R{i:02d}' for i in range(1,13)}
    if set(expected)!=ids or set(comments)!=rids or len(index)!=56 or set(requirements)!=ids or model['status']!='PASS':raise ValueError('H008 private oracle incomplete')
    if model['protected_sha256']!=protected or any(record['source_sha256']!=protected[record['source']] for record in index.values()):raise ValueError('H008 source evidence binding mismatch')
    if any(not set(refs)<=set(index) for refs in requirements.values()):raise ValueError('H008 required evidence index incomplete')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    documents={};errors={};parsed={};blocks={};block_metadata={}
    for kind,prefix in [('document','S'),('review','R')]:
        try:
            documents[kind]=native['read_document'](root/contract[kind]);parsed[kind]=True
            blocks[kind],block_metadata[kind]=io['id_blocks'](documents[kind],prefix)
        except (native['CandidateDocumentError'],OSError) as exc:
            documents[kind]=None;parsed[kind]=False;blocks[kind]={};block_metadata[kind]={};errors[kind]=str(exc)
    reviews,review_metadata=io['review_table'](documents['review'],contract) if documents['review'] else ({},{})
    ledger={};ledger_meta={};ledger_ok=False;ledger_path=root/contract['ledger']
    if ledger_path.is_file() and not ledger_path.is_symlink() and ledger_path.stat().st_size<=1_048_576:
        try:ledger,ledger_meta=io['csv_rows'](ledger_path,contract);ledger_ok=True
        except (OSError,UnicodeError,csv.Error) as exc:errors['ledger']=str(exc)
    else:errors['ledger']='missing/unsafe/oversized alignment CSV'
    fact_checks={};unknown={};row_checks={};term_checks={};ref_checks={};actual_facts={}
    terms={row['term_id']:row for row in truth['terms']}
    for identity,label in expected.items():
        row=ledger.get(identity,{});present=set(row.get('_present',[]))
        facts,unknown[identity]=io['normalize_facts'](row.get('facts_json'),label['facts'],contract)
        actual_facts[identity]=facts;fact_checks[identity]={key:key in facts and facts[key]==value for key,value in label['facts'].items()}
        row_checks[identity]={'decision':'decision' in present and row['decision']==label['decision'],
          'comment_id':'comment_id' in present and row['comment_id']==label['comment_id'],
          'term_ids':'term_ids' in present and row['term_ids']==label['term_ids']}
        body=blocks['document'].get(identity)
        term_checks[identity]={term:bool(body and literal['norm'](terms[term]['vi']) in literal['norm'](body['text'])) for term in label['term_ids']}
        refs=row.get('source_refs');needed=set(requirements[identity])
        source_score=len(set(refs)&needed)/len(needed) if isinstance(refs,list) and set(refs)<=set(index) else 0.
        review_id=label['comment_id']
        review_ref=(io['bound_output_ref'](row.get('review_ref'),Path(contract['review']).name,blocks['review'].get(review_id)) if review_id
                    else 'review_ref' in present and not row['review_ref'])
        word_sources=reviews.get(review_id,{}).get('source_refs') if review_id else []
        word_score=(len(set(word_sources)&needed)/len(needed) if isinstance(word_sources,list) and set(word_sources)<=set(index) else 0.) if review_id else float(bool(row))
        ref_checks[identity]={'source_coverage':source_score,'final_ref':float(io['bound_output_ref'](row.get('final_ref'),Path(contract['document']).name,body)),
                             'review_ref':float(review_ref),'review_index_sources':word_score}
    comment_checks={}
    for identity,label in comments.items():
        review=reviews.get(identity,{});sentence=label['sentence_id']
        comment_checks[identity]={'alignment_decision':row_checks[sentence]['decision'],
            'alignment_comment_id':row_checks[sentence]['comment_id'],
            'review_decision':review.get('decision')==label['computed_decision'],
            'review_sentence_id':review.get('sentence_id')==sentence}
    literals,observed=literal['evaluate'](blocks['document'],truth)
    fact_score=mean([mean(list(values.values())) for values in fact_checks.values()])
    literal_score=mean([mean(list(values.values())) for values in literals.values()])
    coverage=mean([identity in blocks['document'] and bool(blocks['document'][identity]['text'].strip()) for identity in ids])
    native_term_score=mean([value for values in term_checks.values() for value in values.values()])
    ledger_term_score=mean([row_checks[identity]['term_ids'] for identity in ids])
    coverage_terms=mean([coverage,native_term_score,ledger_term_score])
    comment_score=mean([mean(list(values.values())) for values in comment_checks.values()])
    business_parts={'declared_facts':fact_score,'native_literal_values':literal_score,'native_coverage_and_terms':coverage_terms,'comment_decisions':comment_score}
    business=sum(business_parts[name]*weight for name,weight in oracle['business_weights'].items())
    def selected_facts(names):return [value for identity in names for value in fact_checks[identity].values()]
    def selected_literals(names):return [value for identity in names for value in literals.get(identity,{}).values()]
    boundaries={
      'subject_declarations':mean(selected_facts(['S01','S02'])+[value for identity in ['S01','S02'] for value in term_checks[identity].values()]),
      'numeric_locale':mean(selected_facts(['S03','S11'])+selected_literals(['S03','S11'])),
      'dates_and_unapproved_change':mean(selected_facts(['S04'])+selected_literals(['S04'])+list(comment_checks['R04'].values())),
      'work_units_and_origins':mean(selected_facts(['S05','S06'])+selected_literals(['S05','S06'])+list(comment_checks['R06'].values())),
      'polarity_and_authority_declarations':mean(selected_facts(['S07','S08','S09','S12'])+[value for identity in ['R07','R08','R09','R12'] for value in comment_checks[identity].values()]),
      'fixed_term_consistency':mean([native_term_score,ledger_term_score]),
      'unchanged_controls':mean(selected_facts(['S13','S14','S15','S16'])+selected_literals(['S13','S14','S15']))}
    if set(boundaries)!=set(counterexamples['groups']):raise ValueError('H008 counterexample group mismatch')
    boundary=mean(list(boundaries.values()))
    final_complete=parsed['document'] and set(blocks['document'])==ids and not block_metadata['document'].get('conflicts')
    review_complete=parsed['review'] and set(blocks['review'])==rids and set(reviews)==rids and not block_metadata['review'].get('conflicts') and not review_metadata.get('conflicts')
    if review_complete:review_complete=all(set(contract['review_table'])-{'comment_id'}<=set(row['_present']) for row in reviews.values())
    csv_complete=ledger_ok and ledger_meta.get('schema') and set(ledger)==ids
    if csv_complete:csv_complete=all(set(contract['alignment_columns'])-{'sentence_id'}<=set(row['_present']) and isinstance(row.get('facts_json'),dict) and set(actual_facts[identity])==set(expected[identity]['facts']) and not unknown[identity] for identity,row in ledger.items())
    descriptions=mean([isinstance(ledger.get(identity,{}).get('explanation_zh'),str) and bool(ledger[identity]['explanation_zh'].strip()) for identity in ids])
    delivery=mean([float(bool(final_complete)),float(bool(review_complete)),float(bool(csv_complete)),descriptions,float(intact)]) if any(parsed.values()) or ledger_ok else 0.
    evidence=mean([mean(list(values.values())) for values in ref_checks.values()])
    if not intact:boundary=delivery=evidence=0.
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence}
    scores['overall_score']=min(1.,sum(scores[name]*weight for name,weight in oracle['checkpoint_weights'].items()))
    observation={'schema_version':'h008-rule-observations/v1','scores':scores,'business_parts':business_parts,'fact_checks':fact_checks,'row_checks':row_checks,
      'native_literal_checks':literals,'native_literal_observed':observed,'native_term_checks':term_checks,'comment_checks':comment_checks,
      'boundary_groups':boundaries,'reference_checks':ref_checks,'ledger_metadata':ledger_meta,'unknown_fact_keys':unknown,
      'parseable':{**parsed,'ledger':ledger_ok},'errors':errors,'final_complete':bool(final_complete),'review_complete':bool(review_complete),
      'ledger_complete':bool(csv_complete),'input_unchanged':intact,'actual_facts':actual_facts,'actual_final':blocks['document'],'actual_review':blocks['review'],
      'source_bindings':{name:sha(root/contract[name]) if (root/contract[name]).is_file() and not (root/contract[name]).is_symlink() else None for name in ('document','review','ledger')},
      'semantic_limit':oracle['semantic_limit']}
    output=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if output:
        path=Path(output);path.mkdir(parents=True,exist_ok=True)
        with (path/'h008-analysis.json').open('x',encoding='utf-8') as handle:json.dump(observation,handle,ensure_ascii=False,indent=2);handle.write('\n')
    else:print(json.dumps(observation,ensure_ascii=False))
    return {'scores':scores,'observations':observation}
def grade(root):return evaluate(root)['scores']
