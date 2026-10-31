"""Preserve OOXML inline layout when Writer invents missing wrap distances."""
import hashlib

TASK = '02_Office_task_022_namc_interview_schedule'
CONTRACT_SHA = '851b94f0c68ba3f2460c996ccb226d543742ad0b2b1eed1859911d6697a65b9c'
SOURCE_SHA = '7f4a4c932ca5e6ff8eae811e158de5d81bf3d1d3a50831bfb3a2fe54d588a86e'
DATASET = {'id': 'general-custom116-v1', 'digest': '8a066c60dfb1b45403b5b792f9cd6264a5ee639e9cd263b8dc0acfc2031dcb01'}
PROFILE = 'namc-writer-inline-distance-defaults/v2'


def marker(contract, contract_sha, dataset):
    if (contract.get('task_id') == TASK and contract_sha == CONTRACT_SHA
            and {k: dataset.get(k) for k in DATASET} == DATASET
            and hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest() == SOURCE_SHA):
        return {'profile': PROFILE, 'contract_sha256': CONTRACT_SHA, 'source_sha256': SOURCE_SHA,
                'attributes': {'distL': '0', 'distR': '0'}, 'only_when_absent': True,
                'scope': 'LibreOffice render-local copy only; source, extent, margins and score policy unchanged'}
    return None


HELPERS = r'''
_general_e2e_namc_inline_audit = []

def _general_e2e_namc_inline_defaults(local, source):
    import io, zipfile, hashlib
    from lxml import etree as _inline_xml
    before = local.read_bytes()
    with zipfile.ZipFile(io.BytesIO(before)) as package:
        members = package.infolist()
        if len({m.filename for m in members}) != len(members):
            raise CandidateRenderError('DOCX_INLINE_COMPATIBILITY_DUPLICATE_MEMBER')
        parts = [(m, package.read(m)) for m in members]
    document = next((blob for member, blob in parts if member.filename == 'word/document.xml'), None)
    if document is None:
        raise CandidateRenderError('DOCX_INLINE_COMPATIBILITY_DOCUMENT_MISSING')
    parser = _inline_xml.XMLParser(resolve_entities=False, no_network=True)
    tree = _inline_xml.fromstring(document, parser)
    if tree.getroottree().docinfo.doctype:
        raise CandidateRenderError('DOCX_INLINE_COMPATIBILITY_DTD_UNSUPPORTED')
    changes = []
    for index, element in enumerate(tree.iter('{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline')):
        for attribute in ('distL', 'distR'):
            if element.get(attribute) is None:
                element.set(attribute, '0')
                changes.append({'inline_index': index, 'attribute': attribute, 'before': None, 'after': '0'})
    if changes:
        rewritten = _inline_xml.tostring(tree, encoding='UTF-8', xml_declaration=True, standalone=True)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as package:
            for member, blob in parts:
                package.writestr(member, rewritten if member.filename == 'word/document.xml' else blob)
        local.write_bytes(output.getvalue())
    _general_e2e_namc_inline_audit.append({
        'profile': 'namc-writer-inline-distance-defaults/v2',
        'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'render_copy_before_sha256': hashlib.sha256(before).hexdigest(),
        'render_copy_after_sha256': hashlib.sha256(local.read_bytes()).hexdigest(),
        'changes': changes, 'source_modified': False,
        'image_extents_page_margins_fonts_text_and_score_policy_changed': False})

'''


def effective_source(manifest, original, current, prior):
    frozen = manifest.get('runtime', {}).get('namc_inline_distance_profile')
    if frozen is None:
        return current, prior
    expected = marker({'task_id': manifest['identity']['task_id'], 'automated_checks': original},
                      manifest['digests']['contract_sha256'], manifest['dataset'])
    old = "    if lo:\n        profile=work/'profile'"
    grade_start = 'def grade(transcript, workspace_path):'
    export = '    export_evidence(root,infos,diag)'
    if (expected is None or frozen != expected or current.count(old) != 1
            or current.count(grade_start) != 1 or current.count(export) != 1):
        raise ValueError('NAMC_INLINE_DISTANCE_PROFILE_MISMATCH')
    effective = current.replace(old, "    if lo:\n        _general_e2e_namc_inline_defaults(local, source)\n        profile=work/'profile'")
    effective = effective.replace(grade_start, grade_start + '\n    _general_e2e_namc_inline_audit.clear()')
    effective = effective.replace(export, export + "\n    diag['inline_distance_compatibility'] = list(_general_e2e_namc_inline_audit)") + HELPERS
    receipt = {'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1',
               'correction_id': PROFILE, 'task_id': TASK, 'contract_sha256': CONTRACT_SHA,
               'original_source_sha256': SOURCE_SHA,
               'effective_source_sha256': hashlib.sha256(effective.encode()).hexdigest(),
               'candidate_rewritten': False, 'reference_rewritten': False,
               'render_local_copy_normalized': True, 'numeric_decisions_assigned': False,
               'reason': '仅在原render函数创建的临时副本上显式补齐行内图片缺省左右距离0，避免Writer凭空加入0.319cm间距。原件与已有显式距离不变；保留图片尺寸、页边距、字体、正文、一页基准、编辑验证、34/66权重及全部原评分公式。每次输入/副本SHA与属性变化保存在Worker原始诊断。'}
    if prior:
        receipt['prior_correction'] = prior
    return effective, receipt
