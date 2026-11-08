"""Exact-contract, explicitly validated macOS native editability backend.

The original public numeric grade and semantic rubric remain frozen. Windows
keeps its original WPS COM path; old attempts have no native-backend marker.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import native_writer_runtime

PROFILE='office001-validated-native-writer-api/v1'
PROFILE_V2='office001-validated-native-writer-api/v2'
PROFILE_V3='office001-validated-native-writer-api/v3'
TASK='02_Office_task_001_multi_source_project_report'
CONTRACT_SHA='f6386914c4ab0208f66feb75dbce2a61eccf7a384c289cc3a138ce61b048d11e'
SOURCE_SHA='98d2e59396ce97e43333ce6b164cd1c0073ff023f70e39a3ff90d0272716cec1'
EVIDENCE='evaluator_evidence/office001-native'
RUNTIME_SOURCE_SHA='ad10b76ad2ba4cdc9b5f295b01b05c86b51e24f04ba0578a542fcf4162ec906d'
RUNTIME_SOURCE_SHA_V2='86b2af4182f0a974b94df84dd099e2e3c485e5c0eb66c5b2533654e3e0114698'
JAVA_SOURCE_SHA='0fad706f4fdd35940659c311d36e5e784a958c08bd435faa1d88623af28b7348'
JAVA_SOURCE_SHA_V3='4946e7f9d7caf37264030c7eb79387a551802eb25ecda19c116f3eafdcce0bc4'


from source_identities import accepted_contracts

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def marker(contract,contract_sha256):
    if (sys.platform!='darwin' or contract.get('task_id')!=TASK or contract_sha256 not in accepted_contracts(CONTRACT_SHA)
            or hashlib.sha256(contract.get('automated_checks','').encode('utf-8')).hexdigest()!=SOURCE_SHA):
        return None
    envelope=Path(sys.executable).absolute().parent.parent/'general-e2e-native-writer.json'
    if not envelope.exists():return None
    record=json.loads(envelope.read_text(encoding='utf-8'))
    if record.get('schema_version')!=native_writer_runtime.SCHEMA or record.get('status')!='VALIDATED_REAL_NATIVE_EDIT_SAVE_REOPEN':
        raise ValueError('OFFICE001_NATIVE_RUNTIME_NOT_VALIDATED')
    for key in ['configuration','launcher','validation']:
        if sha(record[key]['path'])!=record[key]['sha256']:
            raise ValueError('OFFICE001_NATIVE_RUNTIME_ENVELOPE_DRIFT')
    configuration=json.loads(Path(record['configuration']['path']).read_text(encoding='utf-8'))
    native_writer_runtime.validate_configuration(configuration)
    source=Path(native_writer_runtime.__file__).parent/'native_writer/NativeDocxEditProbe.java'
    if (configuration['java_source']['sha256']!=sha(source) or sha(source)!=JAVA_SOURCE_SHA_V3
            or configuration['runner']['sha256']!=RUNTIME_SOURCE_SHA_V2
            or configuration['jar']['sha256']!=native_writer_runtime.JAR_SHA256):
        raise ValueError('OFFICE001_NATIVE_IMPLEMENTATION_MISMATCH')
    smoke=json.loads(Path(record['validation']['path']).read_text(encoding='utf-8'))
    if (smoke.get('status')!='pass' or smoke.get('input_bytes_unchanged') is not True
            or smoke.get('cleanup_residual') or not shutdown_valid(smoke,Path(record['validation']['path']).parent) or smoke.get('java_exit_code')!=0
            or smoke.get('native_facts',{}).get('body_persisted')!='true'
            or int(smoke.get('native_facts',{}).get('table_edits_persisted','0'))<2):
        raise ValueError('OFFICE001_NATIVE_API_SMOKE_INVALID')
    return {'profile':PROFILE_V3,'contract_sha256':contract_sha256,'source_sha256':SOURCE_SHA,
            'configuration_file':record['configuration'],'configuration':configuration,
            'configuration_content_sha256':canonical(configuration),'launcher':record['launcher'],
            'validation':record['validation'],'evidence_directory':EVIDENCE}


def policy(manifest,source=None):
    frozen=manifest.get('runtime',{}).get('office001_native_profile')
    if frozen is None:return None
    if (not isinstance(frozen,dict) or manifest.get('identity',{}).get('task_id')!=TASK
            or manifest.get('digests',{}).get('contract_sha256') not in accepted_contracts(CONTRACT_SHA)
            or frozen.get('profile') not in {PROFILE,PROFILE_V2,PROFILE_V3} or frozen.get('contract_sha256') not in accepted_contracts(CONTRACT_SHA)
            or frozen.get('source_sha256')!=SOURCE_SHA or frozen.get('evidence_directory')!=EVIDENCE
            or not isinstance(frozen.get('configuration'),dict)
            or frozen.get('configuration_content_sha256')!=canonical(frozen.get('configuration'))
            or (source is not None and hashlib.sha256(source.encode('utf-8')).hexdigest()!=SOURCE_SHA)):
        raise ValueError('OFFICE001_NATIVE_FROZEN_PROFILE_MISMATCH')
    config=frozen['configuration']
    expected_runner=RUNTIME_SOURCE_SHA if frozen['profile']==PROFILE else RUNTIME_SOURCE_SHA_V2
    expected_java=JAVA_SOURCE_SHA_V3 if frozen['profile']==PROFILE_V3 else JAVA_SOURCE_SHA
    if (config.get('runner',{}).get('sha256')!=expected_runner
            or config.get('java_source',{}).get('sha256')!=expected_java
            or config.get('jar',{}).get('sha256')!=native_writer_runtime.JAR_SHA256):
        raise ValueError('OFFICE001_NATIVE_FROZEN_IMPLEMENTATION_MISMATCH')
    return frozen


BRIDGE = '''
def _ge2e_native_file_sha(path):
    return _ge2e_native_hashlib.sha256(_ge2e_native_Path(path).read_bytes()).hexdigest()

def native_probe(candidate,output,budget,control):
    if _ge2e_native_sys.platform!='darwin':
        return _ge2e_original_office_native_probe(candidate,output,budget,control)
    root=_ge2e_native_Path(candidate).parent.parent
    evidence=root/_GE2E_OFFICE_NATIVE['evidence_directory']
    command=[_GE2E_OFFICE_NATIVE['launcher']['path'],'--source',str(candidate),'--control',str(control),
             '--output-root',str(evidence/'probe'),'--timeout-seconds',str(max(1,min(180,budget)))]
    try:
        for item in [_GE2E_OFFICE_NATIVE['launcher'],_GE2E_OFFICE_NATIVE['configuration_file']]:
            if _ge2e_native_file_sha(item['path'])!=item['sha256']:
                raise ValueError('Frozen native Writer runtime drift')
        configuration=_ge2e_native_json.loads(_ge2e_native_Path(_GE2E_OFFICE_NATIVE['configuration_file']['path']).read_text(encoding='utf-8'))
        if configuration!=_GE2E_OFFICE_NATIVE['configuration']:
            raise ValueError('Frozen native Writer configuration differs')
        done=_ge2e_native_subprocess.run(command,capture_output=True,timeout=max(1,min(180,budget))+15)
        (evidence/'helper.stdout.json').write_bytes(done.stdout)
        (evidence/'helper.stderr').write_bytes(done.stderr)
        receipt=_ge2e_native_json.loads(done.stdout.decode('utf-8'))
        observed=receipt.get('status')
        if (done.returncode!=0 or receipt.get('input_bytes_unchanged') is not True
                or receipt.get('cleanup_residual') or receipt.get('java_exit_code')!=0 or receipt.get('server_exit_code')!=0):
            return result('evaluator_error',reason='Validated native Writer probe failed; preserve actual receipt',evidence=[receipt]),receipt
        if observed=='pass':
            return result('pass',1,'Actual native body and required-table edits saved and reopened',[receipt]),receipt
        if observed=='candidate_not_editable':
            return result('fail',0,'Native document lacks the original required editable body/tables',[receipt]),receipt
        if observed=='candidate_not_openable':
            return result('fail',0,'Candidate cannot open in native application that opened known-good control',[receipt]),receipt
        return result('evaluator_error',reason='Native editability remains unavailable',evidence=[receipt]),receipt
    except Exception as error:
        failure={'status':'evaluator_error','error':str(error),'command':command,'candidate_rewritten':False}
        (evidence/'native-failure.json').write_text(_ge2e_native_json.dumps(failure,ensure_ascii=False,indent=2),encoding='utf-8')
        return result('evaluator_error',reason='Native Writer evaluator unavailable; no candidate zero',evidence=[failure]),failure

def _ge2e_office_render_pages(source,directory):
    if not source.is_file():return {'status':'missing','path':str(source)}
    import fitz as _ge2e_fitz
    directory.mkdir()
    pages=[]
    try:
        with _ge2e_fitz.open(source) as document:
            for index,page in enumerate(document):
                target=directory/('page-'+str(index+1).zfill(4)+'.png')
                page.get_pixmap(matrix=_ge2e_fitz.Matrix(1.25,1.25)).save(target)
                pages.append({'page':index+1,'path':str(target),'sha256':_ge2e_native_file_sha(target)})
        return {'status':'complete','source_sha256':_ge2e_native_file_sha(source),'page_count':len(pages),'pages':pages}
    except Exception as error:
        return {'status':'unavailable','error':str(error),'source_sha256':_ge2e_native_file_sha(source),'pages':pages,'complete':False}

def grade(transcript,workspace_path):
    root=_ge2e_native_Path(workspace_path).resolve()
    evidence=root/_GE2E_OFFICE_NATIVE['evidence_directory']
    cursor=root
    for segment in _GE2E_OFFICE_NATIVE['evidence_directory'].split('/'):
        cursor=cursor/segment
        if cursor.is_symlink():raise RuntimeError('Native evaluator output traverses a link')
    if evidence.exists() or evidence.is_symlink():raise RuntimeError('Native evaluator output already exists')
    evidence.mkdir(parents=True)
    if not evidence.resolve().is_relative_to(root):raise RuntimeError('Unsafe native evaluator output')
    scope={'role':'grader_generated_evidence','candidate_output':False,'not_agent_action_evidence':True,
           'profile':_GE2E_OFFICE_NATIVE['profile'],'original_contract_sha256':_GE2E_OFFICE_NATIVE['contract_sha256'],
           'original_source_sha256':_GE2E_OFFICE_NATIVE['source_sha256'],'original_public_numeric_formula_retained':True}
    (evidence/'scope.json').write_text(_ge2e_native_json.dumps(scope,ensure_ascii=False,indent=2),encoding='utf-8')
    values=_ge2e_original_office_grade(transcript,workspace_path)
    pages={'docx_native':_ge2e_office_render_pages(evidence/'probe/candidate-native.pdf',evidence/'docx-pages'),
           'candidate_pdf':_ge2e_office_render_pages(root/'results/project_report.pdf',evidence/'pdf-pages'),
           'not_agent_action_evidence':True}
    (evidence/'rendered-pages.json').write_text(_ge2e_native_json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
    return values
'''

# Kept as source text so the managed Worker runs this same small, read-only
# evidence check without importing a mutable controller module. v1 is unchanged.
SHUTDOWN_VALIDATOR = '''
def _ge2e_shutdown_valid(receipt,root):
    if receipt.get('server_exit_code')==0:return True
    proof=receipt.get('post_completion_cleanup') or {}
    facts=receipt.get('native_facts') or {}
    actions=receipt.get('cleanup_actions') or []
    if (proof.get('profile')!='bound-native-post-completion-cleanup/v1'
        or receipt.get('server_exit_code') not in [255,-15,143]
        or receipt.get('timed_out') is not False or receipt.get('startup_error') is not None
        or receipt.get('cleanup_residual') or receipt.get('java_exit_code')!=0
        or receipt.get('input_bytes_unchanged') is not True or facts.get('status')!='pass'
        or facts.get('control_opened')!='true' or facts.get('opened')!='true'
        or facts.get('phase')!='native_reopen' or facts.get('body_persisted')!='true'
        or not facts.get('required_tables','').isdigit() or int(facts['required_tables'])<2
        or facts.get('table_edits_persisted')!=facts['required_tables']
        or len(actions)!=1 or actions[0].get('signal')!='SIGTERM'
        or not any(p.get('pid')==actions[0].get('pid') and p.get('command_sha256')
                   and '-env:UserInstallation=' in p.get('command','')
                   for p in receipt.get('process_identities',[]))):return False
    for key,name in [('receipt_sha256','native-receipt.properties'),('saved_sha256','native-saved.docx'),('pdf_sha256','candidate-native.pdf')]:
        path=_ge2e_native_Path(root)/name
        if path.is_symlink() or not path.is_file() or _ge2e_native_file_sha(path)!=proof.get(key):return False
    return True
'''

def shutdown_valid(receipt,root):
    namespace={'_ge2e_native_Path':Path,'_ge2e_native_file_sha':sha}
    exec(SHUTDOWN_VALIDATOR,namespace)
    return namespace['_ge2e_shutdown_valid'](receipt,root)

BRIDGE_V2=SHUTDOWN_VALIDATOR+BRIDGE.replace("receipt.get('server_exit_code')!=0", "not _ge2e_shutdown_valid(receipt,evidence/'probe')")


def effective_source(manifest,source,current,previous_receipt):
    frozen=policy(manifest,source)
    if frozen is None:return current,previous_receipt
    # The managed Worker accepts exactly one grade definition. Rename only
    # these two declarations; their bodies and original numeric math stay intact.
    for old,new in [('def native_probe(candidate,output,budget,control):',
                     'def _ge2e_original_office_native_probe(candidate,output,budget,control):'),
                    ('def grade(transcript: list, workspace_path: str) -> dict:',
                     'def _ge2e_original_office_grade(transcript: list, workspace_path: str) -> dict:')]:
        if current.count(old)!=1:raise ValueError('OFFICE001_NATIVE_SOURCE_DECLARATION_MISMATCH')
        current=current.replace(old,new)
    imports='\nimport json as _ge2e_native_json\nimport hashlib as _ge2e_native_hashlib\nimport subprocess as _ge2e_native_subprocess\nimport sys as _ge2e_native_sys\nfrom pathlib import Path as _ge2e_native_Path\n'
    bridge=BRIDGE if frozen['profile']==PROFILE else BRIDGE_V2
    effective=current+imports+'\n_GE2E_OFFICE_NATIVE = '+repr(frozen)+'\n'+bridge
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':frozen['profile'],
             'task_id':TASK,'contract_sha256':CONTRACT_SHA,'original_source_sha256':SOURCE_SHA,
             'effective_source_sha256':hashlib.sha256(effective.encode('utf-8')).hexdigest(),
             'native_configuration_sha256':frozen['configuration_file']['sha256'],
             'evaluator_evidence_directory':EVIDENCE,'candidate_rewritten':False,
             'reason':'新macOS评分attempt显式冻结已实测原生Writer API，按原正文和必需表格编辑/保存/重开条件取证；保持原public numeric-v2规则、语义Rubric和权重，旧attempt/Windows COM路径不变。'}
    if previous_receipt:receipt['prior_correction']=previous_receipt
    return effective,receipt
