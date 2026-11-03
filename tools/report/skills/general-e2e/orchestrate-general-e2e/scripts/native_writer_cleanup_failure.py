"""Retain the exact old Office001 post-success native cleanup failure."""
import hashlib
import json
from pathlib import PurePosixPath

TASK='02_Office_task_001_multi_source_project_report'
ERROR_KIND='office001-native-post-success-cleanup-error/v1'
CONTRACT='e9a5af34ea74f642f1f8966bdb25a42ff179fae6b23f16b17d085164b1601902'
SOURCE='98d2e59396ce97e43333ce6b164cd1c0073ff023f70e39a3ff90d0272716cec1'
DATASET={'id':'general-custom70-v2','digest':'001016f24b4bc20f96733592ea4aabe6a3b8e1e5bfd0dbc9052254ea36430c0e'}
PROBE='runtime/workspace/evaluator_evidence/office001-native/probe/probe-result.json'
PREFIX='Unresolved rule evidence; use embedded run() for six-state results: '

def evidence(rt,attempt,m,contract):
    if (contract.get('task_id')!=TASK or m.get('dataset')!=DATASET or m['digests']['contract_sha256']!=CONTRACT
        or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!=SOURCE
        or m.get('runtime',{}).get('office001_native_profile',{}).get('profile')!='office001-validated-native-writer-api/v1'):
        raise ValueError('NATIVE_CLEANUP_FAILURE_PROFILE_INVALID')
    audit=rt._read_json(attempt/'rule-audit.json');worker=rt._read_json(attempt/'worker/result.json')
    probe=rt._read_json(attempt/PROBE);facts=probe.get('native_facts',{});error=worker.get('error',{})
    if (audit.get('status')!='failed' or worker.get('ok') is not False or worker.get('result') is not None
        or error.get('type')!='RuntimeError' or not error.get('message','').startswith(PREFIX)
        or (attempt/'rule-component.json').exists() or (attempt/'semantic').exists()
        or not (attempt/'rule-review/response.json').is_file()
        or probe.get('status')!='evaluator_error' or probe.get('java_exit_code')!=0
        or probe.get('server_exit_code')!=255 or probe.get('timed_out') is not False
        or probe.get('startup_error') is not None or probe.get('cleanup_residual')!=[]
        or probe.get('input_bytes_unchanged') is not True or probe.get('candidate_rewritten') is not False
        or probe.get('native_profile_archive') is not None
        or facts.get('status')!='pass' or facts.get('control_opened')!='true' or facts.get('opened')!='true'
        or facts.get('body_persisted')!='true' or facts.get('phase')!='native_reopen'
        or not facts.get('required_tables','').isdigit() or int(facts['required_tables'])<2
        or facts.get('table_edits_persisted')!=facts['required_tables']):
        raise ValueError('NATIVE_CLEANUP_FAILURE_NOT_EXACT')
    detail=json.loads(error['message'][len(PREFIX):])
    if (set(detail)!={'automated.c5_editability'} or detail['automated.c5_editability'].get('status')!='evaluator_error'
        or detail['automated.c5_editability'].get('score') is not None
        or detail['automated.c5_editability'].get('evidence')!=[probe]):
        raise ValueError('NATIVE_CLEANUP_FAILURE_WORKER_BINDING')
    actions=probe.get('cleanup_actions',[])
    if (len(actions)!=1 or actions[0].get('signal')!='SIGTERM'
        or not any(p.get('pid')==actions[0].get('pid') and p.get('command_sha256')
            and '-env:UserInstallation=' in p.get('command','') for p in probe.get('process_identities',[]))):
        raise ValueError('NATIVE_CLEANUP_FAILURE_STOP_BINDING')
    paths=[attempt/PROBE,attempt/'judge-infrastructure-block-v1.json']
    required={'editable-copy.docx','native-receipt.properties','java.stderr','native-saved.docx','candidate-native.pdf','server.stderr','server.stdout','java.stdout'}
    if {p.get('path') for p in probe.get('artifacts',[])}!=required:raise ValueError('NATIVE_CLEANUP_FAILURE_ARTIFACT_SCOPE')
    for item in probe['artifacts']:
        rel=PurePosixPath(item['path'])
        if rel.is_absolute() or any(p in ('.','..') for p in rel.parts):raise ValueError('NATIVE_CLEANUP_FAILURE_PATH')
        path=(attempt/PROBE).parent/rel
        if (path.is_symlink() or not path.is_file() or path.stat().st_size!=item['size']
            or rt._sha256_file(path)!=item['sha256']):raise ValueError('NATIVE_CLEANUP_FAILURE_EVIDENCE_DRIFT')
        paths.append(path)
    return paths
