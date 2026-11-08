"""Recreate selected report inputs from original archives; retain host variants."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import hashlib
import json
import shutil
import zipfile
import run_general_e2e as run


def materialize(source, target, archives):
    source=source.resolve(strict=True)
    if target.exists() or target.is_symlink():raise ValueError('CANONICAL_REPORT_TARGET_EXISTS')
    _,manifest=run.manifest_for(source,'batch')
    index=run.load_import_index(source,manifest)
    expected={}
    for unit in manifest['units']:
        uid=unit['unit_id'];entry=index['units'][uid]
        chosen=[x for x in entry['imports'] if x['package_id']==entry['selected_package_id']]
        if len(chosen)!=1:raise ValueError('CANONICAL_REPORT_SELECTION_REQUIRED')
        item=chosen[0];expected[item['archive_sha256']]={'unit_id':uid,**item}
    if len(expected)!=len(manifest['units']) or len(archives)!=len(expected):
        raise ValueError('CANONICAL_REPORT_EXACT_ARCHIVE_SCOPE_REQUIRED')
    selected=[]
    for archive in archives:
        digest=run.sha256_file(archive)
        if digest not in expected:raise ValueError('CANONICAL_REPORT_ARCHIVE_NOT_SELECTED')
        row=expected.pop(digest)
        with zipfile.ZipFile(archive) as z:
            members=[n for n in z.namelist() if n.endswith('/package-manifest.json') and n.count('/')==1]
            if len(members)!=1:raise ValueError('CANONICAL_REPORT_MANIFEST_AMBIGUOUS')
            package=json.loads(z.read(members[0]))
        if package['package_id']!=row['package_id'] or package['identity']['unit_id']!=row['unit_id']:
            raise ValueError('CANONICAL_REPORT_ARCHIVE_IDENTITY_MISMATCH')
        selected.append((archive,row,digest))
    if expected:raise ValueError('CANONICAL_REPORT_ARCHIVE_MISSING')
    target.mkdir(parents=True)
    locks=[]
    for name in ['manifest.json','report-config.json']:
        shutil.copyfile(source/name,target/name)
        locks.append({'source':str(source/name),'copy':str(target/name),'sha256':run.sha256_file(target/name)})
    imports=[]
    for archive,row,digest in selected:
        imported=run.import_return(SimpleNamespace(batch_root=target,archive=archive,receipt=None))
        selection=run.select_import(SimpleNamespace(batch_root=target,unit_id=row['unit_id'],package_id=row['package_id']))
        imports.append({'archive':str(archive),'archive_sha256':digest,'package_id':row['package_id'],
            'unit_id':row['unit_id'],'original_import_target':str(source/row['target']),
            'canonical_import_target':imported['target'],'selection':selection})
    receipt={'schema_version':'general-e2e-canonical-report-source-projection/v1','status':'PASS',
        'source_batch_root':str(source),'canonical_snapshot_root':str(target),
        'original_import_index_sha256':run.sha256_file(run.import_index_path(source)),
        'source_locks':locks,'imports':imports,'original_imports_changed':False,
        'original_archives_changed':False,'score_or_business_bytes_changed':False,
        'authority':'Exactly selected original ZIP bytes; host-modified original imports retained separately'}
    run.write_new_json(target/'canonical-source-projection.json',receipt)
    return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-batch-root',type=Path,required=True)
    p.add_argument('--snapshot-root',type=Path,required=True);p.add_argument('--archive',type=Path,action='append',required=True)
    a=p.parse_args();result=materialize(a.source_batch_root,a.snapshot_root,a.archive)
    print(json.dumps({'status':result['status'],'units':len(result['imports']),
        'canonical_snapshot_root':result['canonical_snapshot_root'],'original_imports_changed':False}))


if __name__=='__main__':main()
