"""Read-only initial Office CWM audit for a proven zero-send preparation.

The CWM comparator below is the existing source-office-metadata-variance/v1
algorithm. Keep old Collect producers unchanged; this standalone Execute input
checker never modifies Workspace files or changes their original manifest SHA.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

CWM = re.compile(r"^CWM[0-9a-fA-F]{32}$")
OFFICE = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm"}
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CP = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
CUSTOM_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
CUSTOM_TYPE = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
META = {"docProps/custom.xml", "[Content_Types].xml", "_rels/.rels"}

def sha(data): return hashlib.sha256(data).hexdigest()
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def structure(node):
    return (node.tag, tuple(sorted(node.attrib.items())), (node.text or "").strip(), tuple(structure(child) for child in node))

def metadata_view(data, path):
    if data is None:
        if path == "docProps/custom.xml": return (f"{{{CP}}}Properties", (), "", ())
        raise ValueError("required relationship metadata missing")
    node = ET.fromstring(data)
    if path == "docProps/custom.xml":
        if node.tag != f"{{{CP}}}Properties": raise ValueError("custom properties namespace")
        for child in list(node):
            if child.tag == f"{{{CP}}}property" and CWM.fullmatch(child.attrib.get("name", "")):
                if (set(child.attrib) != {"fmtid", "pid", "name"}
                    or child.attrib["fmtid"].upper() != "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"
                    or not child.attrib["pid"].isdigit()): raise ValueError("unknown marker attributes")
                node.remove(child)
    elif path == "[Content_Types].xml":
        if node.tag != f"{{{CT}}}Types": raise ValueError("content types namespace")
        for child in list(node):
            if child.attrib.get("PartName") == "/docProps/custom.xml":
                if child.tag != f"{{{CT}}}Override" or child.attrib != {"PartName":"/docProps/custom.xml", "ContentType":CUSTOM_TYPE}:
                    raise ValueError("unknown custom content type")
                node.remove(child)
    else:
        if node.tag != f"{{{REL}}}Relationships": raise ValueError("relationships namespace")
        for child in list(node):
            if child.attrib.get("Type") == CUSTOM_REL:
                if child.tag != f"{{{REL}}}Relationship" or set(child.attrib) != {"Id","Type","Target"} or child.attrib["Target"] != "docProps/custom.xml":
                    raise ValueError("unknown custom relationship")
                node.remove(child)
    return structure(node)

def office_delta(before, after):
    with zipfile.ZipFile(BytesIO(before)) as old, zipfile.ZipFile(BytesIO(after)) as new:
        for z in (old,new):
            infos=z.infolist()
            if len(infos)>10000 or any(i.file_size>32*1024*1024 for i in infos) or sum(i.file_size for i in infos)>256*1024*1024:
                raise ValueError("Office diagnostic size limit")
        a,b=set(old.namelist()),set(new.namelist())
        if len(a)!=len(old.infolist()) or len(b)!=len(new.infolist()): raise ValueError("duplicate ZIP member")
        if a-b or not b-a <= {"docProps/custom.xml"}: raise ValueError("non-metadata ZIP member change")
        changed=[n for n in sorted(a&b) if old.read(n)!=new.read(n)]
        if not set(changed)<=META: raise ValueError("business Office member changed")
        props=ET.fromstring(new.read("docProps/custom.xml"))
        names=[p.attrib.get("name") for p in props if CWM.fullmatch(p.attrib.get("name", ""))]
        if not names:raise ValueError("known Office marker absent")
        for name in META:
            if metadata_view(old.read(name) if name in a else None,name)!=metadata_view(new.read(name) if name in b else None,name):
                raise ValueError("unrelated Office metadata changed: "+name)
        return {"added_members":sorted(b-a),"changed_members":changed,"marker_names":names,"business_members_unchanged":True}


def inside(root, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or not p.parts or any(x in {'.', '..'} for x in p.parts) or '\\' in relative:
        raise ValueError('unsafe relative path')
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink(): raise ValueError('symlink in input path')
    return current


def regular_bytes(path, maximum=64 * 1024 * 1024):
    a = path.lstat()
    if not stat.S_ISREG(a.st_mode) or a.st_size > maximum:
        raise ValueError('unsafe input file')
    data = path.read_bytes(); b = path.lstat()
    if (a.st_ino, a.st_size, a.st_mtime_ns, a.st_ctime_ns) != (b.st_ino, b.st_size, b.st_mtime_ns, b.st_ctime_ns):
        raise ValueError('input changed while reading')
    return data


def protected_write(path, data):
    with path.open('xb') as stream: stream.write(data)
    path.chmod(0o444)
    if sys.platform == 'darwin': os.chflags(path, stat.UF_IMMUTABLE)


def audit(unit, task_id, output):
    unit = Path(unit).absolute()
    if unit.resolve() != unit: raise ValueError('unit path alias')
    manifest_bytes = regular_bytes(unit / 'manifest.json'); manifest = json.loads(manifest_bytes)
    lock = load(unit / '.general-e2e/round-unit.json')
    if lock['batch_id'] != manifest['batch_id'] or lock['unit_id'] != manifest['unit_id']:
        raise ValueError('round input identity')
    archive = inside(unit.parent, lock['execution_package'])
    archive_bytes = regular_bytes(archive, maximum=1024 * 1024 * 1024)
    if sha(archive_bytes) != lock['execution_sha256']: raise ValueError('original execution ZIP drift')
    task = next(t for t in manifest['tasks'] if t['task_id'] == task_id)
    workspace = inside(unit, task['workspace']['path'])
    output = Path(output).absolute()
    relative = output.relative_to(unit).as_posix()
    if not relative.startswith('.general-e2e/queue-repairs/'):
        raise ValueError('audit output outside recovery namespace')
    current = unit
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink(): raise ValueError('output path alias')
        if index == len(parts) - 1: current.mkdir(exist_ok=False)
        elif current.exists():
            if not current.is_dir(): raise ValueError('output ancestor not directory')
        else: current.mkdir()
    artifacts, variants, snapshots = [], [], []
    with zipfile.ZipFile(BytesIO(archive_bytes)) as package:
        names = package.namelist()
        if len(names) != len(set(names)): raise ValueError('duplicate execution member')
        candidates = [n for n in names if (n == 'manifest.json' or n.endswith('/manifest.json'))
                      and package.getinfo(n).file_size == len(manifest_bytes) and package.read(n) == manifest_bytes]
        if len(candidates) != 1: raise ValueError('original manifest bytes not unique')
        prefix = candidates[0][:-len('manifest.json')]
        for entry in task['workspace']['entries']:
            if entry['kind'] != 'file': continue
            file = inside(workspace, entry['path']); current = regular_bytes(file)
            snapshots.append((file, sha(current)))
            if sha(current) == entry['sha256'] and len(current) == entry['size']: continue
            if file.suffix.lower() not in OFFICE: raise ValueError('non-Office input bytes changed')
            member = prefix + task['workspace']['path'] + '/' + entry['path']
            info = package.getinfo(member)
            if info.file_size > 64 * 1024 * 1024 or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('unsafe reference member')
            original = package.read(member)
            if sha(original) != entry['sha256'] or len(original) != entry['size']:
                raise ValueError('reference member does not match original manifest')
            delta = office_delta(original, current)
            record = {'path': entry['path'], 'expected_sha256': entry['sha256'], 'expected_size': entry['size'],
                      'actual_sha256': sha(current), 'actual_size': len(current), 'office_delta': delta}
            for role, data in [('original', original), ('observed', current)]:
                dest = output / ('%03d-%s.bin' % (len(variants) + 1, role)); protected_write(dest, data)
                ref = {'path': dest.relative_to(unit).as_posix(), 'sha256': sha(data), 'size': len(data)}
                artifacts.append(ref); record[role] = ref
            variants.append(record)
    time.sleep(5)
    for file, expected in snapshots:
        if sha(regular_bytes(file)) != expected: raise ValueError('initial Workspace still changing')
    proof = {'schema_version': 'wildclawbench.workbuddy-initial-office-metadata/v1',
             'status': 'PASS_CWM_ONLY', 'profile': 'canonical-cwm-only-initial-input/v1',
             'created_at': datetime.now(timezone.utc).isoformat(),
             'identity': {'batch_id': manifest['batch_id'], 'unit_id': manifest['unit_id'], 'task_id': task_id},
             'execution_manifest_sha256': sha(manifest_bytes), 'execution_package_sha256': lock['execution_sha256'],
             'variants': variants, 'artifacts': artifacts, 'workspace_modified': False,
             'scoring_or_candidate_results_modified': False,
             'validator_sha256': sha(Path(__file__).read_bytes()),
             'python': {'path': sys.executable, 'version': sys.version.split()[0]}}
    target = output / 'manifest.json'; target.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    artifacts = [*artifacts, {'path': target.relative_to(unit).as_posix(), 'sha256': sha(target.read_bytes()), 'size': target.stat().st_size}]
    return {'status': proof['status'], 'proof': str(target), 'artifacts': artifacts, 'variants': variants}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit-root', required=True); parser.add_argument('--task-id', required=True)
    parser.add_argument('--output-root', required=True); args = parser.parse_args()
    print(json.dumps(audit(args.unit_root, args.task_id, args.output_root), ensure_ascii=False))

