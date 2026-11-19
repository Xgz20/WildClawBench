"""Author controls over disposable native packages; not semantic Judge scores."""
from copy import deepcopy
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import runpy
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mutate(path, variant):
    with zipfile.ZipFile(path) as archive:
        parts = {item.filename: archive.read(item) for item in archive.infolist()}
    document = ET.fromstring(parts['word/document.xml'])
    rels = ET.fromstring(parts['word/_rels/document.xml.rels'])
    fields = list(document.iter(W+'fldSimple'))
    if variant == 'equivalent_native':
        remapped = {}
        for node in document.iter(W+'bookmarkStart'):
            old = node.attrib[W+'name']; remapped[old] = 'other_' + old; node.set(W+'name', remapped[old])
        for parent in document.iter():
            for child in list(parent):
                if child.tag != W+'fldSimple': continue
                code = child.attrib[W+'instr']
                for before, after in remapped.items(): code = code.replace(before, '"' + after + '"')
                cursor = list(parent).index(child)
                sequence = []
                for kind in ('begin', 'code', 'separate'):
                    run = ET.Element(W+'r')
                    if kind == 'code': ET.SubElement(run, W+'instrText').text = code
                    else: ET.SubElement(run, W+'fldChar', {W+'fldCharType': kind})
                    sequence.append(run)
                sequence.extend(deepcopy(list(child)))
                end = ET.Element(W+'r'); ET.SubElement(end, W+'fldChar', {W+'fldCharType': 'end'}); sequence.append(end)
                parent.remove(child)
                for index, item in enumerate(sequence): parent.insert(cursor+index, item)
        relation_names = {}
        for number, item in enumerate(rels, 1):
            old = item.attrib['Id']; item.set('Id', 'different' + str(number)); relation_names[old] = item.attrib['Id']
        for node in document.iter():
            if R+'id' in node.attrib: node.set(R+'id', relation_names[node.attrib[R+'id']])
        for parent in document.iter():
            for child in list(parent):
                if child.tag == W+'t' and child.text and len(child.text) > 3:
                    index = list(parent).index(child); value = child.text; child.text = value[:len(value)//2]
                    remainder = ET.Element(W+'t'); remainder.text = value[len(value)//2:]; parent.insert(index+1, remainder)
    elif variant in {'stale_reference_display', 'wrong_reference_target', 'dangling_deleted_target'}:
        field = next(field for field in fields if 'clause_acceptance' in field.attrib[W+'instr'])
        if variant == 'stale_reference_display': field.find('.//'+W+'t').text = '5'
        else: field.set(W+'instr', field.attrib[W+'instr'].replace('clause_acceptance', 'clause_liability' if variant == 'wrong_reference_target' else 'clause_training'))
    elif variant == 'flatten_native_refs':
        for parent in document.iter():
            for child in list(parent):
                if child.tag == W+'fldSimple':
                    index = list(parent).index(child); children = deepcopy(list(child)); parent.remove(child)
                    for offset, item in enumerate(children): parent.insert(index+offset, item)
    elif variant == 'drop_table_column':
        table = list(document.iter(W+'tbl'))[1]
        grid = table.find(W+'tblGrid'); grid.remove(list(grid)[2])
        for row in table.findall(W+'tr'): row.remove(row.findall(W+'tc')[2])
    elif variant == 'display_only_email':
        for item in rels:
            if item.attrib.get('Target') == 'mailto:legal-notice@beiling.example': item.set('Target', 'mailto:notice@beiling.example')
    elif variant in {'modify_protected_total', 'modify_protected_cap'}:
        before, after = ('60000', '61000') if variant == 'modify_protected_total' else ('20%', '25%')
        item = next(node for node in document.iter(W+'t') if node.text and before in node.text)
        item.text = item.text.replace(before, after)
    elif variant == 'rewrite_unapproved':
        current = ''
        for paragraph in document.find(W+'body').findall(W+'p'):
            visible = ''.join(node.text or '' for node in paragraph.iter(W+'t'))
            title = re.fullmatch(r'第[0-9]+条\s*(.*)', visible)
            if title: current = title[1]; continue
            if current in {'项目与主体', '服务范围', '保密', '通知与送达', '生效与附件'} and visible:
                for child in list(paragraph):
                    if child.tag != W+'pPr': paragraph.remove(child)
                ET.SubElement(ET.SubElement(paragraph, W+'r'), W+'t').text = '双方对本项事项另行协商，不再沿用此前具体约定。'
    elif variant == 'overbroad_sla':
        table = list(document.iter(W+'tbl'))[1]
        for row in table.findall(W+'tr')[1:]:
            cells = row.findall(W+'tc')
            label = ''.join(node.text or '' for node in cells[0].iter(W+'t'))
            if label in {'一般咨询', '账单咨询'}:
                value = next(cells[1].iter(W+'t')); value.text = '2小时' if label == '一般咨询' else '7个工作日'
    elif variant == 'numeric_table_formats':
        table = list(document.iter(W+'tbl'))[0]
        for row in table.findall(W+'tr')[1:]:
            node = next(row.findall(W+'tc')[2].iter(W+'t')); node.text = format(float(node.text), ',.3f')
    parts['word/document.xml'] = ET.tostring(document, encoding='utf-8', xml_declaration=True)
    if variant == 'invalid_grid_value':
        cell = next(document.iter(W+'tc')); props = cell.find(W+'tcPr')
        ET.SubElement(props, W+'gridSpan', {W+'val': 'invalid'})
        parts['word/document.xml'] = ET.tostring(document, encoding='utf-8', xml_declaration=True)
    parts['word/_rels/document.xml.rels'] = ET.tostring(rels, encoding='utf-8', xml_declaration=True)
    if variant == 'active_blank_even_header':
        settings = ET.fromstring(parts['word/settings.xml'])
        ET.SubElement(settings, W+'evenAndOddHeaders')
        parts['word/settings.xml'] = ET.tostring(settings, encoding='utf-8', xml_declaration=True)
    if variant == 'missing_relationships': parts.pop('word/_rels/document.xml.rels')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(parts, reverse=True): archive.writestr(name, parts[name])
    path.write_bytes(stream.getvalue())


def validate(exec_root, gt_root, task_path=None, office_roundtrip=None):
    exec_root, gt_root = Path(exec_root).resolve(), Path(gt_root).resolve()
    reference = gt_root / 'reference/results'
    variants = ['reference', 'equivalent_native', 'numeric_table_formats', 'original_unchanged', 'rewrite_unapproved',
        'stale_reference_display', 'wrong_reference_target', 'dangling_deleted_target', 'invalid_grid_value', 'flatten_native_refs', 'drop_table_column', 'display_only_email',
        'modify_protected_total', 'modify_protected_cap', 'overbroad_sla', 'missing_relationships', 'active_blank_even_header', 'stale_audit',
        'malformed_audit', 'missing_audit', 'missing_contract', 'protected_input_change', 'missing_gt']
    if office_roundtrip: variants.append('office_roundtrip')
    results = {}
    with tempfile.TemporaryDirectory(prefix='h003-author-') as temporary:
        base = Path(temporary)
        for name in variants:
            root = base / name
            shutil.copytree(exec_root, root)
            shutil.copytree(gt_root, root/'gt', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'authoring_validation.json'))
            shutil.copytree(reference, root/'results')
            doc = root/'results/contract_revised.docx'; audit_path = root/'results/changes.json'
            audit = json.loads(audit_path.read_text(encoding='utf-8'))
            if name == 'original_unchanged': shutil.copy2(exec_root/'contract.docx', doc)
            elif name == 'office_roundtrip': shutil.copy2(office_roundtrip, doc)
            elif name in {'equivalent_native', 'numeric_table_formats', 'rewrite_unapproved', 'stale_reference_display', 'wrong_reference_target', 'dangling_deleted_target', 'invalid_grid_value',
                          'flatten_native_refs', 'drop_table_column', 'display_only_email', 'modify_protected_total', 'modify_protected_cap', 'overbroad_sla', 'missing_relationships', 'active_blank_even_header'}:
                mutate(doc, name)
            if name == 'stale_audit': audit['result_sha256'] = '0'*64
            elif name == 'malformed_audit': audit['changes'][0]['change_id'] = {'invalid': True}
            else: audit['result_sha256'] = sha(doc)
            audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            if name == 'missing_audit': audit_path.unlink()
            elif name == 'missing_contract': doc.unlink()
            elif name == 'protected_input_change':
                with (root/'contract.docx').open('ab') as handle: handle.write(b'changed')
            elif name == 'missing_gt': (root/'gt/expected.json').unlink()
            before = {path.name: sha(path) for path in (root/'results').iterdir()}
            try: value = runpy.run_path(str(root/'gt/grader.py'))['evaluate'](root)
            except FileNotFoundError:
                assert name == 'missing_gt'; results[name] = {'status': 'evaluation_error', 'score': None, 'error': 'FileNotFoundError'}; continue
            assert before == {path.name: sha(path) for path in (root/'results').iterdir()}, 'grader modified candidate'
            scores, observations = value['scores'], value['observations']
            if name in {'reference', 'equivalent_native', 'numeric_table_formats', 'office_roundtrip'}:
                assert abs(scores['overall_score']-1) < 1e-9, (name, value)
            else: assert scores['overall_score'] < .999, (name, scores)
            if name in {'modify_protected_total', 'modify_protected_cap'}: assert scores['business_correctness'] == scores['boundary_cases'] == 0
            if name in {'stale_reference_display', 'wrong_reference_target', 'flatten_native_refs'}: assert observations['boundary_groups']['native_references'] < 1
            if name == 'dangling_deleted_target': assert observations['case_checks']['C06']['score'] < 1
            if name == 'invalid_grid_value': assert observations['parse_error'] and scores['business_correctness'] == 0
            if name == 'drop_table_column':
                assert scores['business_correctness'] == 1 and not observations['table_checks']['services']
            if name == 'display_only_email': assert observations['case_checks']['C07']['requirements'] == [True, False]
            if name in {'rewrite_unapproved', 'overbroad_sla'}:
                assert scores['business_correctness'] == 0 and not observations['scope_unchanged']
            if name == 'missing_relationships': assert scores['business_correctness'] > .5 and not observations['native_clean']
            if name == 'active_blank_even_header': assert not observations['preservation_checks']['header'] and scores['business_correctness'] == 0
            if name in {'missing_audit', 'stale_audit', 'malformed_audit'}: assert scores['business_correctness'] == scores['boundary_cases'] == 1
            if name == 'protected_input_change': assert scores['boundary_cases'] == scores['delivery_integrity'] == scores['evidence_binding'] == 0
            results[name] = {'scores': scores, 'checks': observations['case_checks'], 'boundary_groups': observations['boundary_groups']}
        if task_path:
            root = base/'actual-md'
            shutil.copytree(exec_root, root); shutil.copytree(gt_root, root/'gt'); shutil.copytree(reference, root/'results')
            section = Path(task_path).read_text(encoding='utf-8').split('## Automated Checks', 1)[1].split('## LLM Judge Rubric', 1)[0]
            source = re.search(r'```python\s*\n(.*?)```', section, re.S)[1]; namespace = {}
            exec(compile(source, 'h003-actual-task-md', 'exec'), namespace)
            result = namespace['grade'](workspace_path=str(root)); assert abs(result['overall_score']-1)<1e-9
            results['actual_md_reference'] = {'scores': result}
    hashes = {path.relative_to(gt_root).as_posix(): sha(path) for path in sorted(gt_root.rglob('*')) if path.is_file()
              and path.name != 'authoring_validation.json' and path.suffix != '.pyc' and '__pycache__' not in path.parts}
    return {'schema_version': 'h003-author-validation/v1', 'status': 'PASS', 'controls': results, 'gt_sha256': hashes,
            'office_roundtrip_binding': {'alternative_docx_sha256': sha(office_roundtrip), 'reference_docx_sha256': sha(reference/'contract_revised.docx')} if office_roundtrip else None,
            'limit': 'Native package author controls; no independent legal human review, semantic Judge, four-Harness run or empirical difficulty.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--exec-root', required=True, type=Path); parser.add_argument('--gt-root', required=True, type=Path)
    parser.add_argument('--task-path', type=Path); parser.add_argument('--office-roundtrip', type=Path); args = parser.parse_args()
    result = validate(args.exec_root, args.gt_root, args.task_path, args.office_roundtrip)
    (args.gt_root/'authoring_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'scores': {key: value.get('scores', value) for key, value in result['controls'].items()}}, ensure_ascii=False))
