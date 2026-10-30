"""Prove a narrowly permitted Office input metadata variant without rewriting it."""
import base64 as _ge2e_base64
import hashlib as _ge2e_hashlib
import io as _ge2e_io
import json as _ge2e_json
from pathlib import Path as _ge2e_Path
import zipfile as _ge2e_zipfile
from xml.etree import ElementTree as _ge2e_et


def _ge2e_xml_signature(element):
    return (element.tag, tuple(sorted(element.attrib.items())), element.text or '',
            tuple(_ge2e_xml_signature(child) for child in element))


def _ge2e_office_parts(data):
    with _ge2e_zipfile.ZipFile(_ge2e_io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 20000:
            raise ValueError('Invalid OPC member inventory')
        if sum(member.file_size for member in archive.infolist()) > 128*1024*1024:
            raise ValueError('OPC expansion exceeds resource limit')
        return {name: archive.read(name) for name in names}


def _ge2e_custom_properties(data):
    if data is None:
        return {}, {}
    root = _ge2e_et.fromstring(data)
    ns = '{http://schemas.openxmlformats.org/officeDocument/2006/custom-properties}'
    if root.tag != ns + 'Properties':
        raise ValueError('Invalid custom-properties root')
    ordinary, cwm = {}, {}
    names, ids = set(), set()
    for child in root:
        name = child.get('name')
        pid = child.get('pid')
        if child.tag != ns + 'property' or not name or name in names or not pid or pid in ids:
            raise ValueError('Invalid custom property')
        names.add(name); ids.add(pid)
        target = cwm if name.startswith('CWM') else ordinary
        target[name] = _ge2e_xml_signature(child)
    return ordinary, cwm


def _ge2e_metadata_registration(data, part):
    root = _ge2e_et.fromstring(data)
    kept = []
    removed = 0
    for child in root:
        custom = False
        if part == '_rels/.rels' and child.get('Type') == 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties':
            if child.get('Target', '').lstrip('/') != 'docProps/custom.xml' or child.get('TargetMode') not in (None, 'Internal'):
                raise ValueError('Invalid custom-properties relationship')
            custom = True
        elif part == '[Content_Types].xml' and child.get('PartName') == '/docProps/custom.xml':
            if child.get('ContentType') != 'application/vnd.openxmlformats-officedocument.custom-properties+xml':
                raise ValueError('Invalid custom-properties content type')
            custom = True
        if custom:
            removed += 1
        else:
            kept.append(_ge2e_xml_signature(child))
    if removed > 1:
        raise ValueError('Duplicate custom-properties registration')
    return (root.tag, tuple(sorted(root.attrib.items())), tuple(sorted(kept))), removed


def compare_office_cwm(original, candidate, expected_sha256):
    """Return proof only when all business OPC members are byte-identical."""
    if _ge2e_hashlib.sha256(original).hexdigest() != expected_sha256:
        raise ValueError('Canonical public input digest mismatch')
    left, right = _ge2e_office_parts(original), _ge2e_office_parts(candidate)
    metadata = {'docProps/custom.xml', '_rels/.rels', '[Content_Types].xml'}
    if (set(left) - metadata) != (set(right) - metadata):
        return None
    if any(left[name] != right[name] for name in set(left) - metadata):
        return None
    old_properties, old_cwm = _ge2e_custom_properties(left.get('docProps/custom.xml'))
    new_properties, new_cwm = _ge2e_custom_properties(right.get('docProps/custom.xml'))
    if old_properties != new_properties or not new_cwm:
        return None
    for part in ['_rels/.rels', '[Content_Types].xml']:
        if part not in left or part not in right:
            return None
        before, _ = _ge2e_metadata_registration(left[part], part)
        after, registrations = _ge2e_metadata_registration(right[part], part)
        if before != after or registrations != 1:
            return None
    return {'profile': 'canonical-public-office-cwm-only/v1',
            'canonical_sha256': expected_sha256,
            'candidate_sha256': _ge2e_hashlib.sha256(candidate).hexdigest(),
            'business_members_byte_identical': True,
            'changed_metadata_members': sorted(name for name in metadata if left.get(name) != right.get(name)),
            'cwm_property_names': sorted(new_cwm), 'candidate_rewritten': False}


def _general_e2e_public_input_matches(path, expected_sha256, workspace):
    # This lookup is inserted from the pinned public dataset payload by the scorer.
    baseline = _GENERAL_E2E_PUBLIC_INPUT_BASELINES.get(expected_sha256)
    if baseline is None or baseline['path'] != path.relative_to(workspace).as_posix():
        return False
    try:
        proof = compare_office_cwm(_ge2e_base64.b64decode(baseline['base64'], validate=True),
                                   path.read_bytes(), expected_sha256)
    except (ValueError, KeyError, _ge2e_zipfile.BadZipFile, _ge2e_et.ParseError):
        return False
    if proof is None:
        return False
    evidence_dir = workspace / '评分证据'
    evidence_dir.mkdir(exist_ok=True)
    evidence_file = evidence_dir / '00_公开Office输入元数据兼容审计.json'
    if evidence_dir.is_symlink() or not evidence_dir.resolve().is_relative_to(workspace.resolve()):
        raise ValueError('Unsafe public-input evidence directory')
    if evidence_file.exists() and (evidence_file.is_symlink() or evidence_file.stat().st_nlink != 1):
        raise ValueError('Unsafe public-input evidence file')
    proofs = _ge2e_json.loads(evidence_file.read_text(encoding='utf-8')) if evidence_file.exists() else []
    proof['public_input_path'] = baseline['path']
    proofs.append(proof)
    evidence_file.write_text(_ge2e_json.dumps(proofs, ensure_ascii=False, indent=2), encoding='utf-8')
    return True
