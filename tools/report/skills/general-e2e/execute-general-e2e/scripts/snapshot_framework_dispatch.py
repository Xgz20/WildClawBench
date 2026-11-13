"""Immutable snapshot of an explicitly authorized, unaccepted dispatch attempt.

The execution workspace must equal the frozen initial tree or pass the existing
canonical CWM-only initial-input audit. Business changes remain forbidden.
"""
import argparse
import json
import os
import re
from pathlib import Path
import stat
import zipfile
import uuid
from prepare_quota_retry import inventory, tree_sha, sha, encoded, require, safe, live_unit, check_entries
from initial_office_metadata import audit as audit_initial_office


def control_snapshot(unit, controls, original_controls, state):
    """Keep only hash-bound, same-attempt, zero-send preparation ancestry."""
    entries=inventory(controls)
    expected={'automation-state.json','execution-record.json'}
    history=state.get('history',[])
    require(isinstance(history,list),'PRE_SEND_HISTORY_TYPE')
    refs=[]; seen=set()
    for index,event in enumerate(history):
        if event.get('event')!='ZERO_SEND_PREPARATION_RESUMED':
            continue
        digest=event.get('previous_state_sha256'); record_digest=event.get('previous_record_sha256')
        require(isinstance(digest,str) and re.fullmatch('[a-f0-9]{64}',digest)
                and isinstance(record_digest,str) and re.fullmatch('[a-f0-9]{64}',record_digest)
                and digest not in seen,'PRE_SEND_HISTORY_HASH')
        seen.add(digest)
        names=[f'pre-send-failures/{digest}.json',f'pre-send-failures/{digest}.execution-record.json']
        require(event.get('previous_state_path')==(original_controls/names[0]).relative_to(unit).as_posix()
                and event.get('previous_record_path')==(original_controls/names[1]).relative_to(unit).as_posix(),
                'PRE_SEND_HISTORY_REFERENCE')
        paths=[controls/name for name in names]
        require(all(path.is_file() and not path.is_symlink() and path.resolve()==path for path in paths),
                'PRE_SEND_HISTORY_SOURCE')
        bodies=[path.read_bytes() for path in paths]
        require(sha(bodies[0])==digest and sha(bodies[1])==record_digest,'PRE_SEND_HISTORY_SOURCE_SHA')
        previous,record=[json.loads(body) for body in bodies]
        require(previous.get('identity')==state['identity'] and record.get('identity')==state['identity'],
                'PRE_SEND_HISTORY_IDENTITY')
        require(previous.get('history')==history[:index],'PRE_SEND_HISTORY_PREFIX')
        prompt_sha=previous.get('prompt',{}).get('sha256')
        require(all(previous.get(key)==state.get(key) for key in ('dataset','task_root','candidate_workspace','run_config'))
                and isinstance(prompt_sha,str) and re.fullmatch('[a-f0-9]{64}',prompt_sha)
                and prompt_sha==state.get('prompt',{}).get('sha256'),
                'PRE_SEND_HISTORY_INPUT_BINDING')
        send=previous.get('send',{}); session=previous.get('session',{}); execution=previous.get('execution',{})
        require(previous.get('phase')=='FAILED' and record.get('phase')=='FAILED'
                and previous.get('prompt',{}).get('send_status')=='not_sent'
                and send.get('dispatch_attempt_count')==0
                and send.get('dispatch_armed_at') is None and send.get('dispatch_completed_at') is None
                and session.get('verified') is False
                and all(session.get(key) is None for key in ('thread_id','turn_id','session_id'))
                and execution.get('business_status')=='infrastructure_error'
                and (execution.get('error') or {}).get('code')=='PRE_SEND_DRIVER_ERROR',
                'PRE_SEND_HISTORY_BOUNDARY')
        expected.update(['pre-send-failures',*names])
        refs.append({'state_path':names[0],'state_sha256':digest,'record_path':names[1],
                     'record_sha256':record_digest,'event_index':index})
    # New preparation metadata is copied as original evidence, never dropped.
    # Only the two exact, independently validated UI profiles are registered.
    manifest=json.loads((unit/'manifest.json').read_bytes())
    for entry in entries:
        name=entry['path']
        if re.fullmatch(r'completed-ui-owner-[0-9a-f-]{36}\.proof\.json',name):
            proof_path=controls/name
            proof=json.loads(proof_path.read_bytes())
            snapshot_name=name.replace('.proof.json','.state.json')
            snapshot_path=controls/snapshot_name
            require(proof.get('profile')=='bound-completed-own-unit-ui-navigation/v1'
                    and proof.get('status')=='OWNERSHIP_VERIFIED'
                    and proof.get('target_task_id')==state['identity']['task_id']
                    and proof.get('source_state_snapshot')==snapshot_name
                    and proof.get('prompt_send_calls')==0 and proof.get('dispatch_authorized') is False
                    and proof.get('requires_fresh_visible_probe') is True,
                    'PREPARATION_OWNER_PROFILE')
            require(snapshot_path.is_file() and not snapshot_path.is_symlink()
                    and snapshot_path.resolve()==snapshot_path,'PREPARATION_OWNER_SOURCE')
            owner_raw=snapshot_path.read_bytes()
            require(sha(owner_raw)==proof.get('source_state_sha256'),'PREPARATION_OWNER_SHA')
            owner=json.loads(owner_raw); native=proof.get('native',{})
            tasks=[t for t in manifest['tasks'] if t['task_id']==proof.get('owner_task_id')]
            require(len(tasks)==1 and tasks[0]['task_id']!=state['identity']['task_id'],'PREPARATION_OWNER_TASK')
            task=tasks[0]; source_unit=Path(state['task_root']).parents[2]
            expected_cwd=str(source_unit/str(safe(task['workspace']['path'])))
            require(proof.get('source_state_path')==str(source_unit/'.general-e2e/execution'/task['task_id']/'automation-state.json')
                    and owner.get('identity',{}).get('batch_id')==state['identity']['batch_id']
                    and owner['identity'].get('unit_id')==state['identity']['unit_id']
                    and owner['identity'].get('task_id')==task['task_id'] and owner['identity'].get('attempt_id')
                    and owner.get('dataset')==state.get('dataset')
                    and owner.get('run_config',{}).get('config_digest')==state.get('run_config',{}).get('config_digest')
                    and owner.get('phase')=='COMPLETED' and owner.get('execution',{}).get('business_status')=='completed'
                    and owner['execution'].get('error') is None and owner['execution'].get('finished_at')
                    and owner.get('prompt',{}).get('send_status')=='sent'
                    and owner['prompt'].get('sha256')==task['prompt']['sent_sha256']
                    and owner.get('send',{}).get('dispatch_attempt_count')==1
                    and owner.get('session',{}).get('verified') is True
                    and owner.get('candidate_workspace')==expected_cwd and native.get('cwd')==expected_cwd
                    and all(native.get(k) and native[k]==owner['session'].get(k)
                            for k in ('thread_id','turn_id','session_id','cwd'))
                    and native.get('latest_turn_id')==native.get('turn_id')
                    and native.get('status')=='completed' and native.get('turn_state')=='completed'
                    and native.get('session_status')=='ready' and native.get('active_turn_id') is None and native.get('error') is None,
                    'PREPARATION_OWNER_BINDING')
            expected.update([name,snapshot_name])
        elif re.fullmatch(r'native-visibility-[0-9a-f-]{36}\.json',name):
            proof=json.loads((controls/name).read_bytes())
            v1=proof.get('profile')=='owned-native-visible-send/v1'
            v2=proof.get('profile')=='owned-native-visible-send/v2'
            require((v1 or v2) and proof.get('status')=='PASS'
                    and proof.get('identity')=={k:state['identity'][k] for k in ('batch_id','unit_id','task_id')}
                    and proof.get('run_config_digest')==state.get('run_config',{}).get('config_digest')
                    and proof.get('original_process_identity_reverified') is True
                    and ((v1 and proof.get('changed') is True and proof.get('before',{}).get('visibility')!='visible')
                         or (v2 and isinstance(proof.get('changed'),bool)
                             and isinstance(proof.get('app_pid'),int) and proof.get('app_pid')>1
                             and proof.get('native_after',{}).get('pid')==proof.get('app_pid')
                             and isinstance(proof.get('native_after',{}).get('bundle_id'),str)))
                    and proof.get('after',{}).get('visibility')=='visible'
                    and proof.get('prompt_send_calls')==0 and proof.get('app_restart_calls')==0
                    and proof.get('native_open_calls') in (0,1)
                    and (proof.get('page_bring_to_front_calls')==1 if v1 else proof.get('page_bring_to_front_calls') in (0,1)),
                    'PREPARATION_VISIBILITY_PROFILE')
            expected.add(name)
    require({entry['path'] for entry in entries}==expected
            and all(entry['kind'] in ('file','directory') for entry in entries),'UNEXPECTED_CONTROL_FILES')
    return entries,refs


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
        frozen_state=json.loads((root/'failed-control/automation-state.json').read_bytes())
        controls,lineage=control_snapshot(unit,root/'failed-control',unit/'.general-e2e/execution'/task_id,frozen_state)
        require(record.get('pre_send_failure_history',[])==lineage,'ARCHIVED_CONTROL_HISTORY')
        expected_control=[entry for entry in record['entries'] if entry['archive_path'].startswith('failed-control/')]
        require({entry['path'] for entry in controls}=={entry['path'] for entry in expected_control},'ARCHIVED_CONTROL_SCOPE')
        for current in controls:
            reference=next(entry for entry in expected_control if entry['path']==current['path'])
            require(all(current[key]==reference[key] for key in ('kind','size','sha256')),'ARCHIVED_CONTROL_SHA')
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
    initial=[{k:e[k] for k in ('path','kind','mode','size','sha256')} for e in sorted(task['workspace']['entries'],key=lambda e:e['path'])]
    variance=None
    if entries!=initial:
        require([{k:e[k] for k in ('path','kind','mode')} for e in entries]
                ==[{k:e[k] for k in ('path','kind','mode')} for e in initial],'WORKSPACE_SCOPE_OR_MODE_DRIFT')
        for current,reference in zip(entries,initial):
            if current!=reference:
                require(current['kind']=='file' and Path(current['path']).suffix.lower() in ('.xlsx','.docx','.pptx'),
                        'WORKSPACE_NON_OFFICE_CHANGED')
        require(auth['old_workspace_sha256'] in (tree_sha(initial),tree_sha(entries)),'WORKSPACE_SHA')
        output=unit/'.general-e2e/queue-repairs'/('framework-dispatch-'+new+'-'+str(uuid.uuid4()))
        variance=audit_initial_office(unit,task_id,output)
        require(variance['status']=='PASS_CWM_ONLY','INITIAL_OFFICE_AUDIT')
        require(inventory(workspace)==entries,'WORKSPACE_CHANGED_AFTER_OFFICE_AUDIT')
    else:
        require(tree_sha(entries)==auth['old_workspace_sha256'],'WORKSPACE_SHA')
        check_entries(workspace,task['workspace']['entries'])
    control_entries,pre_send_history=control_snapshot(unit,controls,controls,state)
    source_rows=[]
    for label,source in [('failed-control',controls),('failed-workspace',workspace)]:
        for e in inventory(source):
            require(e['kind'] in ('file','directory'),'UNSUPPORTED_SOURCE')
            source_rows.append(dict(e,archive_path=label+'/'+e['path'],source=source/e['path']))
    if variance:
        for artifact in variance['artifacts']:
            source=unit/str(safe(artifact['path']));require(source.resolve()==source,'AUDIT_SOURCE_ALIAS')
            b=source.read_bytes();require(sha(b)==artifact['sha256'] and len(b)==artifact['size'],'AUDIT_SOURCE_SHA')
            source_rows.append(dict(path=source.name,kind='file',mode=format(stat.S_IMODE(source.stat().st_mode),'04o'),
                                    size=len(b),sha256=sha(b),archive_path='initial-office-metadata/'+source.name,source=source))
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
    require(inventory(controls)==control_entries,'CONTROL_MOVED_DURING_ARCHIVE')
    (root/'failed-control').mkdir()
    human=Path(auth['human_source']['path']).read_bytes()
    require(sha(human)==auth['human_source']['sha256'],'HUMAN_SOURCE_SHA')
    frozen_controls=[]
    for entry in control_entries:
        target=root/'failed-control'/entry['path']
        if entry['kind']=='directory':
            target.mkdir(parents=True,exist_ok=True)
            continue
        body=(controls/entry['path']).read_bytes()
        require(len(body)==entry['size'] and sha(body)==entry['sha256'],'CONTROL_CHANGED_DURING_COPY')
        frozen_controls.append(('failed-control/'+entry['path'],body))
    for name,b in [*frozen_controls,('human-source.json',human)]:
        target=root/name
        with target.open('xb') as f:f.write(b)
        target.chmod(0o400)
        if hasattr(os,'chflags'):os.chflags(target,target.stat().st_flags|stat.UF_IMMUTABLE)
    if hasattr(os,'chflags'):os.chflags(zpath,zpath.stat().st_flags|stat.UF_IMMUTABLE)
    result=dict(schema_version='general-e2e.unaccepted-dispatch-archive/v1',authorization_sha256=sha(raw),
                archive_sha256=sha(zpath.read_bytes()),observed_workspace_sha256=tree_sha(entries),
                initial_workspace_sha256=tree_sha(initial),initial_office_metadata=variance,
                pre_send_failure_history=pre_send_history,
                entries=[{k:v for k,v in r.items() if k!='source'} for r in source_rows])
    with (root/'archive-manifest.json').open('xb') as f:f.write(encoded(result))
    return dict(status='ARCHIVED',archive_sha256=result['archive_sha256'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--unit-root',required=True);p.add_argument('--authorization',required=True);p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    print(json.dumps(archive(Path(a.unit_root),Path(a.authorization),a.verify_only)))
