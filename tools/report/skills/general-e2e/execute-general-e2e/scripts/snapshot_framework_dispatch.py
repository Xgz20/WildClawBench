"""Immutable snapshot of an explicitly authorized, unaccepted dispatch attempt.

The execution workspace must still equal its frozen initial tree. No original
state, workspace, app, model or score is modified by this archiver.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import zipfile
from prepare_quota_retry import inventory, tree_sha, sha, encoded, require, safe, live_unit, check_entries


def archive(unit, auth_path, verify=False):
    unit=unit.resolve(strict=True)
    live_unit(unit)
    raw=auth_path.read_bytes(); auth=json.loads(raw)
    require(auth['schema_version']=='general-e2e.unaccepted-dispatch-retry-authorization/v1'
            and auth['cleanup_authorized'] is True and auth['retry_authorized'] is True,'HUMAN_AUTH')
    task_id=str(safe(auth['task_id'])); new=str(safe(auth['new_attempt_id']))
    require('/' not in task_id and '/' not in new,'PATH')
    root=unit/'.general-e2e/framework-dispatch-recoveries'/task_id/new
    require(root.resolve()==root and root.is_dir(),'RECOVERY_PATH')
    manifest_raw=(unit/'manifest.json').read_bytes(); manifest=json.loads(manifest_raw)
    require(sha(manifest_raw)==auth['unit_manifest_sha256'],'MANIFEST_SHA')
    task=next(t for t in manifest['tasks'] if t['task_id']==task_id)
    if verify:
        record=json.loads((root/'archive-manifest.json').read_bytes())
        require(record['authorization_sha256']==sha(raw),'AUTH_SHA')
        zpath=root/'failed-attempt.zip'
        require(sha(zpath.read_bytes())==record['archive_sha256'],'ARCHIVE_SHA')
        with zipfile.ZipFile(zpath) as z:
            require(len(z.namelist())==len(record['entries']) and set(z.namelist())=={r['archive_path'] for r in record['entries']},'ARCHIVE_SCOPE')
            for r in record['entries']:
                require(sha(z.read(r['archive_path']))==r['sha256'],'ARCHIVE_MEMBER_SHA')
        require(sha((root/'failed-control/automation-state.json').read_bytes())==auth['old_state_sha256'],'OLD_STATE_SHA')
        require(sha((root/'failed-control/execution-record.json').read_bytes())==auth['old_record_sha256'],'OLD_RECORD_SHA')
        require(sha((root/'human-source.json').read_bytes())==auth['human_source']['sha256'],'HUMAN_SOURCE_SHA')
        return dict(status='VERIFIED',archive_sha256=record['archive_sha256'])
    controls=unit/'.general-e2e/execution'/task_id; workspace=unit/str(safe(task['workspace']['path']))
    require(controls.resolve()==controls and workspace.resolve()==workspace,'SOURCE_PATH')
    old=(controls/'automation-state.json').read_bytes(); record=(controls/'execution-record.json').read_bytes()
    require(sha(old)==auth['old_state_sha256'] and sha(record)==auth['old_record_sha256'],'ORIGINAL_SHA')
    state=json.loads(old)
    require(state['identity']=={k:auth[k] for k in ('batch_id','unit_id','task_id')}|{'attempt_id':auth['old_attempt_id']},'IDENTITY')
    require(state['phase']=='NEEDS_ATTENTION' and state['prompt']['send_status']=='uncertain'
            and state['send']['dispatch_attempt_count']==1 and state['session']['verified'] is False,'OLD_BOUNDARY')
    entries=inventory(workspace)
    require(tree_sha(entries)==auth['old_workspace_sha256'],'WORKSPACE_SHA')
    check_entries(workspace,task['workspace']['entries'])
    require({e['path'] for e in inventory(controls)}=={'automation-state.json','execution-record.json'},'UNEXPECTED_CONTROL_FILES')
    source_rows=[]
    for label,source in [('failed-control',controls),('failed-workspace',workspace)]:
        for e in inventory(source):
            require(e['kind'] in ('file','directory'),'UNSUPPORTED_SOURCE')
            source_rows.append(dict(e,archive_path=label+'/'+e['path'],source=source/e['path']))
    zpath=root/'failed-attempt.zip'
    require(not zpath.exists(),'ARCHIVE_EXISTS_USE_VERIFY')
    with zpath.open('xb') as stream, zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as z:
        for r in source_rows:
            b=r['source'].read_bytes() if r['kind']=='file' else b''
            require(sha(b)==r['sha256'],'SOURCE_CHANGED')
            info=zipfile.ZipInfo(r['archive_path'],(1980,1,1,0,0,0))
            info.external_attr=(int(r['mode'],8)|(stat.S_IFDIR if r['kind']=='directory' else stat.S_IFREG))<<16
            z.writestr(info,b)
    require(inventory(workspace)==entries,'WORKSPACE_MOVED_DURING_ARCHIVE')
    (root/'failed-control').mkdir()
    human=Path(auth['human_source']['path']).read_bytes()
    require(sha(human)==auth['human_source']['sha256'],'HUMAN_SOURCE_SHA')
    for name,b in [('failed-control/automation-state.json',old),('failed-control/execution-record.json',record),('human-source.json',human)]:
        target=root/name
        with target.open('xb') as f:f.write(b)
        target.chmod(0o400)
        if hasattr(os,'chflags'):os.chflags(target,target.stat().st_flags|stat.UF_IMMUTABLE)
    if hasattr(os,'chflags'):os.chflags(zpath,zpath.stat().st_flags|stat.UF_IMMUTABLE)
    result=dict(schema_version='general-e2e.unaccepted-dispatch-archive/v1',authorization_sha256=sha(raw),
                archive_sha256=sha(zpath.read_bytes()),entries=[{k:v for k,v in r.items() if k!='source'} for r in source_rows])
    with (root/'archive-manifest.json').open('xb') as f:f.write(encoded(result))
    return dict(status='ARCHIVED',archive_sha256=result['archive_sha256'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--unit-root',required=True);p.add_argument('--authorization',required=True);p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    print(json.dumps(archive(Path(a.unit_root),Path(a.authorization),a.verify_only)))
