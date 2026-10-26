"""Disposable native author specimens; no semantic Judge or Harness scores."""
from contextlib import contextmanager
from copy import deepcopy
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(path,callback):
    output=io.BytesIO()
    with zipfile.ZipFile(path) as source,zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            value=callback(item.filename,source.read(item))
            if value is not None:target.writestr(item,value)
    path.write_bytes(output.getvalue())


def mutate_workbook(path,variant,labels):
    changes={}
    if variant=='keyword_all_covered':
        changes={f'{column}{row}':'已覆盖' for row in range(6,41) for column in ('C','D')}
    elif variant=='hardware_masks_software':
        for number in (7,14,22,33):changes.update({f'C{number+5}':'已覆盖',f'D{number+5}':'已覆盖'})
    elif variant=='ignore_expiry':
        for number in (29,30):changes.update({f'C{number+5}':'已覆盖',f'D{number+5}':'已覆盖',f'E{number+5}':'有效'})
    elif variant=='all_certificates_expired':
        for number in range(27,33):changes.update({f'D{number+5}':'待核实',f'E{number+5}':'过期'})
    elif variant=='wrong_scope_accepted':changes.update({'C36':'已覆盖','D36':'已覆盖','E36':'有效'})
    elif variant=='missing_proof_is_unmet':
        for number in (22,29,30,31):changes[f'D{number+5}']='不满足'
    elif variant=='invent_capabilities':
        for number in (14,19,22,26):changes[f'D{number+5}']='已覆盖'
    elif variant=='missing_description_header':changes['H5']=None
    elif variant=='missing_certificate_header':changes['E5']=None

    def transform(name,raw):
        if name=='xl/workbook.xml' and variant=='equivalent_layout':
            node=ET.fromstring(raw)
            for index,sheet in enumerate(node.find(S+'sheets')):sheet.set('name','Equivalent'+str(index))
            return ET.tostring(node,encoding='utf-8',xml_declaration=True)
        if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
            node=ET.fromstring(raw);cells={cell.attrib['r']:cell for cell in node.iter(S+'c')}
            if name=='xl/worksheets/sheet1.xml':
                for address,value in changes.items():
                    cell=cells[address]
                    for child in list(cell):cell.remove(child)
                    cell.attrib.pop('t',None)
                    if value is not None:
                        cell.set('t','inlineStr');ET.SubElement(ET.SubElement(cell,S+'is'),S+'t').text=value
                if variant=='wrong_formula_correct_cache':
                    for index,label in enumerate(labels):
                        cell=cells[f'D{index+6}']
                        for child in list(cell):cell.remove(child)
                        cell.set('t','str');ET.SubElement(cell,S+'f').text='"已覆盖"';ET.SubElement(cell,S+'v').text=label['coverage']
                if variant=='equivalent_boolean_mandatory':
                    for index,label in enumerate(labels):
                        cell=cells[f'B{index+6}']
                        for child in list(cell):cell.remove(child)
                        cell.set('t','b');ET.SubElement(cell,S+'v').text='1' if label['mandatory']=='是' else '0'
                    for cell in node.iter(S+'c'):
                        formula=cell.find(S+'f')
                        if formula is not None:cell.remove(formula)
                if variant=='missing_requirement_row':
                    data=node.find(S+'sheetData')
                    for row in list(data):
                        if row.attrib.get('r')=='27':data.remove(row)
                if variant=='conflicting_duplicate':
                    data=node.find(S+'sheetData');row=deepcopy(next(row for row in data if row.attrib.get('r')=='24'))
                    row.set('r','41')
                    for cell in row.findall(S+'c'):
                        column=re.match(r'[A-Z]+',cell.attrib['r'])[0];cell.set('r',column+'41')
                        if column=='D':
                            for child in list(cell):cell.remove(child)
                            cell.set('t','inlineStr');ET.SubElement(ET.SubElement(cell,S+'is'),S+'t').text='已覆盖'
                    data.append(row)
            if name=='xl/worksheets/sheet2.xml' and variant in {'fabricated_evidence','wrong_real_evidence'}:
                cell=cells['D19'];cell.clear();cell.set('r','D19');cell.set('t','inlineStr')
                ET.SubElement(ET.SubElement(cell,S+'is'),S+'t').text='response.docx#F999' if variant=='fabricated_evidence' else 'response.docx#F003'
            if name=='xl/worksheets/sheet2.xml' and variant=='false_reference_not_empty':
                cell=cells['E6'];cell.clear();cell.set('r','E6');cell.set('t','b');ET.SubElement(cell,S+'v').text='0'
            if variant=='equivalent_layout':
                for cell in node.iter(S+'c'):
                    formula=cell.find(S+'f')
                    if formula is not None:cell.remove(formula)
                data=node.find(S+'sheetData');rows=list(data);body=[row for row in rows if 6<=int(row.attrib.get('r','0'))<=40]
                ordered=list(reversed(body))
                for number,row in enumerate(ordered,6):
                    row.set('r',str(number))
                    for cell in row.findall(S+'c'):
                        column=re.match(r'[A-Z]+',cell.attrib['r'])[0];cell.set('r',column+str(number))
                for row in body:data.remove(row)
                for row in ordered:data.append(row)
                last='H' if name.endswith('sheet1.xml') else 'F'
                columns=dict(zip('ABCDEFGH'[:ord(last)-64],reversed('ABCDEFGH'[:ord(last)-64])))
                for cell in node.iter(S+'c'):
                    match=re.fullmatch(r'([A-Z]+)([0-9]+)',cell.attrib['r']);cell.set('r',columns.get(match[1],match[1])+match[2])
            return ET.tostring(node,encoding='utf-8',xml_declaration=True)
        return raw
    package(path,transform)


def mutate_response(path,variant,labels,raw_source):
    def transform(name,raw):
        if name!='word/document.xml':return raw
        node=ET.fromstring(raw)
        if variant=='equivalent_word_table':
            body=node.find(W+'body');section=body.find(W+'sectPr')
            for child in list(body):body.remove(child)
            table=ET.SubElement(body,W+'tbl');grid=ET.SubElement(table,W+'tblGrid')
            for _ in range(3):ET.SubElement(grid,W+'gridCol',{W+'w':'3000'})
            records=[['req_id','coverage','response']]
            facts={row['req_id']:row for row in raw_source['requirements']}
            for label in reversed(labels):records.append([label['req_id'],label['coverage'],facts[label['req_id']]['fact_text']+' '+label['next_step']])
            for values in records:
                row=ET.SubElement(table,W+'tr')
                for value in values:
                    cell=ET.SubElement(row,W+'tc');ET.SubElement(ET.SubElement(ET.SubElement(cell,W+'p'),W+'r'),W+'t').text=value
            if section is not None:body.append(section)
        elif variant in {'contradict_revised_status','ambiguous_word_status','equivalent_word_aliases'}:
            for item in node.iter(W+'t'):
                if not item.text:continue
                if variant=='contradict_revised_status' and item.text.startswith('R019 '):item.text=item.text.replace('不满足','已覆盖')
                elif variant=='ambiguous_word_status' and item.text.startswith('R001 '):item.text=item.text.replace('已覆盖','已覆盖/待核实')
                elif variant=='equivalent_word_aliases' and '[覆盖结论' in item.text:
                    for before,after in [('部分覆盖','partial'),('已覆盖','covered'),('待核实','unverified'),('不满足','unmet')]:item.text=item.text.replace(before,after)
                    item.text=re.sub(r'^R([0-9]{3})',r'r\1',item.text)
        return ET.tostring(node,encoding='utf-8',xml_declaration=True)
    package(path,transform)


@contextmanager
def environment(lock,output):
    values={'GENERAL_E2E_OFFICE_LOCK':str(lock),'GENERAL_E2E_RULE_EVIDENCE_DIR':str(output)}
    before={key:os.environ.get(key) for key in values};os.environ.update(values)
    try:yield
    finally:
        for key,value in before.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


def validate(exec_root,gt_root,lock,task_path=None):
    exec_root,gt_root,lock=Path(exec_root).resolve(),Path(gt_root).resolve(),Path(lock).resolve()
    expected=json.loads((gt_root/'expected.json').read_text(encoding='utf-8'))
    raw=json.loads((gt_root/'source_facts.json').read_text(encoding='utf-8'))
    model=runpy.run_path(str(gt_root/'decision_model.py'))['classify'](raw)
    by_id={row['req_id']:row for row in model}
    assert len(model)==35
    for label in expected['issues']:
        assert all(by_id[label['req_id']][key]==label[key] for key in ('mandatory','draft_status','coverage','certificate_status'))
    assert sorted(row['req_id'] for row in model if row['mandatory']=='是' and row['coverage']!='已覆盖')==expected['mandatory_gap_ids']
    variants=['reference','equivalent_layout','equivalent_boolean_mandatory','equivalent_word_table','equivalent_word_aliases','equivalent_optional_notes','keyword_all_covered','hardware_masks_software',
        'ignore_expiry','all_certificates_expired','wrong_scope_accepted','missing_proof_is_unmet','invent_capabilities',
        'wrong_formula_correct_cache','fabricated_evidence','wrong_real_evidence','false_reference_not_empty','contradict_revised_status','ambiguous_word_status','conflicting_duplicate',
        'missing_requirement_row','missing_description_header','missing_certificate_header','wrong_mandatory_gap_set',
        'missing_workbook','missing_response','missing_gaps','corrupt_workbook','protected_input_change','missing_gt']
    results={}
    with tempfile.TemporaryDirectory(prefix='h004-author-') as temporary:
        base=Path(temporary)
        for variant in variants:
            root=base/variant;shutil.copytree(exec_root,root)
            shutil.copytree(gt_root,root/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc','authoring_validation.json'))
            shutil.copytree(gt_root/'reference/results',root/'results')
            workbook=root/'results/traceability.xlsx';response=root/'results/response_revised.docx';gaps=root/'results/gaps.md'
            if variant in {'equivalent_layout','equivalent_boolean_mandatory','keyword_all_covered','hardware_masks_software','ignore_expiry','all_certificates_expired',
                    'wrong_scope_accepted','missing_proof_is_unmet','invent_capabilities','wrong_formula_correct_cache','fabricated_evidence',
                    'wrong_real_evidence','false_reference_not_empty','conflicting_duplicate','missing_requirement_row','missing_description_header','missing_certificate_header'}:
                mutate_workbook(workbook,variant,expected['issues'])
            elif variant in {'equivalent_word_table','equivalent_word_aliases','contradict_revised_status','ambiguous_word_status'}:mutate_response(response,variant,expected['issues'],raw)
            elif variant=='wrong_mandatory_gap_set':
                text=gaps.read_text(encoding='utf-8').replace('| R014 |','| R005 |');gaps.write_text(text,encoding='utf-8')
            elif variant=='equivalent_optional_notes':
                with gaps.open('a',encoding='utf-8') as handle:handle.write('\n## Optional notes\n\n| req_id | coverage |\n|---|---|\n| R005 | partial |\n| R024 | partial |\n')
            elif variant=='missing_workbook':workbook.unlink()
            elif variant=='missing_response':response.unlink()
            elif variant=='missing_gaps':gaps.unlink()
            elif variant=='corrupt_workbook':workbook.write_bytes(b'invalid-xlsx')
            elif variant=='protected_input_change':
                with (root/'requirements.docx').open('ab') as handle:handle.write(b'changed')
            elif variant=='missing_gt':(root/'gt/expected.json').unlink()
            if variant=='wrong_formula_correct_cache':
                native=runpy.run_path(str(gt_root/'native_text.py'))['extract_native_text'](workbook,max_chars=1_000_000)
                io_module=runpy.run_path(str(gt_root/'structured_io.py'))
                rows,_=io_module['workbook_rows'](native,json.loads((gt_root/'artifact_contract.json').read_text(encoding='utf-8')))
                assert all(rows[label['req_id']]['coverage']==label['coverage'] for label in expected['issues'])
            before={path.name:sha(path) for path in (root/'results').iterdir()}
            with environment(lock,base/(variant+'-derived')):
                try:value=runpy.run_path(str(root/'gt/grader.py'))['evaluate'](root)
                except FileNotFoundError:
                    assert variant=='missing_gt';results[variant]={'status':'evaluation_error','score':None,'error':'FileNotFoundError'};continue
            assert before=={path.name:sha(path) for path in (root/'results').iterdir()},'grader changed candidate'
            scores,observations=value['scores'],value['observations']
            if variant in {'reference','equivalent_layout','equivalent_boolean_mandatory','equivalent_word_table','equivalent_word_aliases','equivalent_optional_notes'}:
                assert abs(scores['overall_score']-1)<1e-9,(variant,scores,observations)
            else:assert scores['overall_score']<1-1e-9,(variant,scores)
            if variant in {'keyword_all_covered','hardware_masks_software','ignore_expiry','all_certificates_expired','wrong_scope_accepted','missing_proof_is_unmet','invent_capabilities'}:
                assert scores['business_correctness']<1 and scores['boundary_cases']<1,(variant,scores)
            if variant=='wrong_formula_correct_cache':
                assert not observations['case_checks']['R019']['coverage']
                assert observations['office_recalculation']['formula_caches_cleared']>=38
            if variant in {'fabricated_evidence','wrong_real_evidence'}:
                assert scores['business_correctness']==scores['boundary_cases']==1 and scores['evidence_binding']<1
            if variant=='false_reference_not_empty':assert not observations['role_bindings']['R001']['certificate_refs']
            if variant=='missing_description_header':
                assert scores['business_correctness']==scores['boundary_cases']==scores['evidence_binding']==1 and scores['delivery_integrity']<1
            if variant=='missing_certificate_header':
                assert not observations['case_checks']['R001']['certificate_status'],'missing column was treated as known not-required'
            if variant=='contradict_revised_status':assert not observations['case_checks']['R019']['revised_coverage']
            if variant=='ambiguous_word_status':assert not observations['case_checks']['R001']['revised_coverage']
            if variant=='protected_input_change':assert scores['boundary_cases']==scores['delivery_integrity']==scores['evidence_binding']==0
            results[variant]={'scores':scores,'boundary_groups':observations['boundary_groups']}
        if task_path:
            root=base/'actual-md';shutil.copytree(exec_root,root);shutil.copytree(gt_root,root/'gt');shutil.copytree(gt_root/'reference/results',root/'results')
            section=Path(task_path).read_text(encoding='utf-8').split('## Automated Checks',1)[1].split('## LLM Judge Rubric',1)[0]
            source=re.search(r'```python\s*\n(.*?)```',section,re.S)[1];namespace={}
            exec(compile(source,'h004-actual-task-md','exec'),namespace)
            with environment(lock,base/'actual-md-derived'):score=namespace['grade'](workspace_path=str(root))
            assert abs(score['overall_score']-1)<1e-9;results['actual_md_reference']={'scores':score}
    hashes={path.relative_to(gt_root).as_posix():sha(path) for path in sorted(gt_root.rglob('*')) if path.is_file()
            and path.name!='authoring_validation.json' and path.suffix!='.pyc' and '__pycache__' not in path.parts}
    return {'schema_version':'h004-author-validation/v1','status':'PASS','controls':results,'gt_sha256':hashes,
        'office_runtime':json.loads(lock.read_text(encoding='utf-8')),
        'limit':'Author field/provenance controls and actual trusted Calc; not independent expert prose review, semantic Judge or four-Harness calibration.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exec-root',required=True,type=Path);parser.add_argument('--gt-root',required=True,type=Path)
    parser.add_argument('--office-runtime-lock',required=True,type=Path);parser.add_argument('--task-path',type=Path);args=parser.parse_args()
    result=validate(args.exec_root,args.gt_root,args.office_runtime_lock,args.task_path)
    (args.gt_root/'authoring_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'controls':{key:value.get('scores',value) for key,value in result['controls'].items()}},ensure_ascii=False))
