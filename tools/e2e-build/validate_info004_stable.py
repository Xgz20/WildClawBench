#!/usr/bin/env python3
"""Validate the closed Info004 packet and every scored evidence reference.

No network, Harness or semantic Judge is called. Optional raw-source checking
compares exact excerpts against previously captured primary pages.
"""
from pathlib import Path
import argparse,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src.utils.task_parser import parse_task_md

TASK='01_Information_Search_Organization_task_004_luxun_national_character_source_comparison'
WORKSPACE=ROOT/'workspace/general_e2e/01_Information_Search_Organization/task_004_luxun_national_character_source_comparison_stable_v1'
def validate(*,raw_source_root=None):
    task=parse_task_md(ROOT/'tasks/general_e2e/01_Information_Search_Organization'/f'{TASK}.md')
    packet_path=WORKSPACE/'exec/materials/materials-manifest.json';packet=json.loads(packet_path.read_text())
    assert packet['network_required'] is False and packet['source_count']==7
    assert packet['required_material_ids']==['M1','M2','M3','M4','M5','R1','R2']
    cards={}
    for row in packet['files']:
        path=packet_path.parent/row['path'];data=path.read_bytes()
        assert not path.is_symlink() and hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['size']
        if 'material_id' not in row:continue
        card=json.loads(data);assert card['material_id']==row['material_id']
        assert len({p['id'] for p in card['paragraphs']})==len(card['paragraphs'])
        assert re.fullmatch('[a-f0-9]{64}',card['source']['original_response_sha256'])
        for p in card['paragraphs']:
            assert p['text'].strip() and hashlib.sha256(p['text'].encode()).hexdigest()==p['sha256']
        cards[card['material_id']]=card
    assert len(cards)==7
    index=json.loads((WORKSPACE/'gt/reference_sources.json').read_text())
    assert index['public_manifest_sha256']==hashlib.sha256(packet_path.read_bytes()).hexdigest()
    assert index['known_unresolved_claims']==[]
    proof=index['criterion_evidence'];data=(WORKSPACE/'gt'/proof['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==proof['sha256'];mapping=json.loads(data)
    assert mapping['public_manifest_sha256']==index['public_manifest_sha256']
    criteria={r['key']:r for r in task['rubric_criteria']}
    assert set(mapping['criteria'])==set(criteria) and len(criteria)==22
    assert sum(c['weight'] for c in criteria.values())==98
    assert task['grading_weights']=={'automated':.02,'llm_judge':.98}
    assert 'claim_review_units' not in task['judge_evidence']
    assert criteria['scholar_claim_binding']['allowed_scores']==[0.,.5,1.]
    refs=0
    for key,row in mapping['criteria'].items():
        assert row['weight']==criteria[key]['weight'] and row['evidence_refs']
        for ref in row['evidence_refs']:
            mid,part=ref.split('#');card=cards[mid]
            assert part in card or any(p['id']==part for p in card['paragraphs']),ref
            refs+=1
    assert list(mapping['fixed_research_units'])==['1','2']
    assert sum(row['budget'] for row in mapping['fixed_research_units'].values())==4
    namespace={};exec(compile(task['automated_checks'],'<info004-fixed-material-validation>','exec'),namespace)
    assert namespace['EXPECTED_REFERENCE_SHA256']==hashlib.sha256((WORKSPACE/'gt/reference_answer.md').read_bytes()).hexdigest()
    assert namespace['EXPECTED_SOURCE_INDEX_SHA256']==hashlib.sha256((WORKSPACE/'gt/reference_sources.json').read_bytes()).hexdigest()
    assert namespace['EXPECTED_MATERIAL_MANIFEST_SHA256']==hashlib.sha256(packet_path.read_bytes()).hexdigest()
    if raw_source_root is not None:
        from lxml import html
        for mid,card in cards.items():
            data=(raw_source_root/(mid+'.html')).read_bytes()
            assert hashlib.sha256(data).hexdigest()==card['source']['original_response_sha256']
            doc=html.fromstring(data)
            for node in doc.xpath('//script|//style'):node.getparent().remove(node)
            normalize=lambda s:re.sub(r'\s+','',s)
            original=normalize(doc.text_content())
            for row in card['paragraphs']:assert normalize(row['text']) in original,(mid,row['id'])
    return {'status':'PASS','material_count':7,'semantic_criteria':22,'top_level_criteria':23,
        'research_scoring_units':2,'existing_scoring_protocol_reused':True,'verified_criterion_references':refs,'network_called':False,
        'primary_response_and_excerpt_check':raw_source_root is not None,'requires_new_execution':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--raw-source-root',type=Path)
    args=parser.parse_args();print(json.dumps(validate(raw_source_root=args.raw_source_root),ensure_ascii=False,indent=2))
