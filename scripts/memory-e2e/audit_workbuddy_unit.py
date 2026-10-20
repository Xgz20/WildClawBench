"""Record live terminal evidence before UI quit, then verify normal unit closure."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval_memory_e2e.batch import load_batch
from eval_memory_e2e.io import events, publish, verify_artifact
from eval_memory_e2e.os_boundary import process_table
from eval_memory_e2e.runner import next_action
from eval_memory_e2e.workbuddy_scope import attest


def sha(data):
    return hashlib.sha256(data).hexdigest()


def audit(root, stage):
    manifest = load_batch(root)
    spec = json.loads((root/'scope.json').read_text())
    provider = spec['imported_provider_configuration']
    model_sha = sha(Path(provider['source_path']).read_bytes())
    assert model_sha == provider['source_sha256'], 'Ordinary model configuration changed'
    if stage == 'preclose':
        assert all(next_action(root, episode['id'])['status'] == 'COMPLETED' for episode in manifest['episodes'])
        profile = manifest['profiles']['WorkBuddy']
        value = attest(profile['workbuddy_scope'], profile['non_target_memory_boundary'])
        metadata = value['native_metadata']
        assert all(s['status'] == 'completed' for s in metadata['sessions'])
        assert metadata['automation_running_count'] == 0 and not metadata['automation_run_statuses']
        table = process_table()
        pids = {value['main_pid']}
        while True:
            added = {pid for pid,row in table.items() if row['ppid'] in pids} - pids
            if not added:
                break
            pids |= added
        gateway = json.loads((root/'desktop-bootstrap-ready.json').read_text())['gateway']
        pids.add(gateway['pid'])
        value.update(owned_processes=[table[pid] for pid in sorted(pids) if pid in table],
                     ordinary_model_sha256=model_sha, memory_background_observable=False,
                     checkMemoryUpdating_used_as_idle_proof=False)
        output = root/'preclose-audit.json'
    else:
        pre = json.loads((root/'preclose-audit.json').read_text())
        table = process_table()
        remaining = [p for p in pre['owned_processes'] if p['pid'] in table
                     and table[p['pid']]['started_at'] == p['started_at']]
        assert not remaining, ('Owned unit processes still live', remaining)
        supervisor = json.loads((root/'desktop-supervisor-exited.json').read_text())
        assert supervisor['main_exit'] == {'code':0,'signal':None}
        assert supervisor['gateway_exit'] == {'code':0,'signal':None}
        alias = json.loads((root/'temp-alias-restored.json').read_text())
        assert alias['removed'] and not Path(alias['alias']).is_symlink()
        result = subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:9229','-iTCP:9336','-iTCP:9337','-sTCP:LISTEN','-t'],capture_output=True,text=True)
        assert result.returncode == 1 and not result.stdout.strip(), 'Control ports still occupied'
        memory = {}
        for e in events(root):
            if e['kind'] == 'MEMORY_OBSERVATION':
                snapshot = json.loads(verify_artifact(root,e['payload']['snapshot']))
                for entry in snapshot['files']:
                    path = Path(entry['source_path'])
                    assert path.is_relative_to(root)
                    if path.is_file() and not path.is_symlink():
                        memory[str(path)] = {'path':str(path),'sha256':sha(path.read_bytes())}
            if e['kind'] != 'RECEIPT' or e['payload']['status'] != 'completed':
                continue
            receipt = e['payload']
            episode = next(x for x in manifest['episodes'] if x['id'] == receipt['episode_id'])
            for entry in receipt.get('candidate_snapshot',[]):
                path = Path(episode['workspaces']['A']) / entry['workspace_path']
                if path.is_file() and not path.is_symlink():
                    memory[str(path)] = {'path':str(path),'sha256':sha(path.read_bytes())}
        value = {'status':'CLOSED','supervisor':supervisor,'temp_alias':alias,'owned_processes_remaining':remaining,
                 'control_listeners':'','ordinary_model_sha256':model_sha,'ordinary_model_unchanged':True,
                 'memory_files':list(memory.values()),'ordinary_instance_reopened':False,'daily_memory_cleared':False,
                 'codex_memory_read_or_changed':False,'formal20_prompts':0}
        output = root/'closed-audit.json'
    publish(output,value)
    return {'status':value['status'],'audit':str(output),'memory_files':len(value.get('memory_files',[]))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--stage',choices=['preclose','closed'],required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.root,args.stage)))
