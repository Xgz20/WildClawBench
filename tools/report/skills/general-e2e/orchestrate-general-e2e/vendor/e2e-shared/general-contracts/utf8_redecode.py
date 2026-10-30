"""Bound, append-only recapture of Qwen evidence affected by pipe UTF-8 decoding."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import copy, hashlib, json, os, re, shutil

PROFILE = 'bound-qwen-native-utf8-redecode/v1'
EXTRA_NAMES = {
 'redecode_provenance':'provenance.json',
 'redecode_original_record':'original-execution-record.json',
 'redecode_original_manifest':'original-evidence-manifest.json',
 'redecode_original_collect_receipt':'original-unit-collect-receipt.json',
 'redecode_original_native':'original-native-engine-snapshot.json',
 'redecode_original_transcript':'original-transcript.jsonl',
 'redecode_original_final':'original-final-response.md',
}

def sha(data):return hashlib.sha256(data).hexdigest()
def encode(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def require(ok,message):
 if not ok:raise ValueError('UTF8_REDECODE_'+message)
def child(root,name):
 rel=PurePosixPath(name);require(not rel.is_absolute() and '..' not in rel.parts and '\\' not in name,'PATH_INVALID')
 target=Path(root).joinpath(*rel.parts);require(target.resolve().is_relative_to(Path(root).resolve()) and target.is_file() and not target.is_symlink(),'SOURCE_INVALID');return target
def artifact(root,path):
 data=Path(path).read_bytes();return {'path':Path(path).relative_to(root).as_posix(),'sha256':sha(data),'size':len(data)}
def verify_ref(document,path,data):
 rows=[x for x in document['artifacts'] if x['path']==path]
 require(len(rows)==1 and rows[0]['sha256']==sha(data) and rows[0]['size']==len(data),'SOURCE_REFERENCE_MISMATCH')
def utf8_only(old,new,path='',changes=None):
 if old==new:return
 if isinstance(old,str) and isinstance(new,str):
  pattern=''.join('[^\\x00-\\x7f]' if x and set(x)=={'\ufffd'} and len(x)>=2 else re.escape(x) for x in re.split('(\ufffd+)',old))
  require('\ufffd' in old and re.fullmatch(pattern,new) is not None,'NON_UTF8_CHANGE:'+path)
  if changes is not None:changes.append({'path':path,'original_sha256':sha(old.encode()),'redecoded_sha256':sha(new.encode())})
 elif isinstance(old,dict) and isinstance(new,dict) and old.keys()==new.keys():
  for key in old:utf8_only(old[key],new[key],path+'.'+key,changes)
 elif isinstance(old,list) and isinstance(new,list) and len(old)==len(new):
  for i,(a,b) in enumerate(zip(old,new)):utf8_only(a,b,path+'['+str(i)+']',changes)
 else:raise ValueError('UTF8_REDECODE_NON_UTF8_CHANGE:'+path)
def verify_native(old,new,changes=None):
 require(old['profile']==new['profile']=='qwenwork-opencode-sqlite-v1','NATIVE_PROFILE')
 for field in ('session_id','conversation_id','sub_chat_id','local_project_id','cwd'):
  require(old['host']['record'][field]==new['host']['record'][field],'NATIVE_IDENTITY')
 for table in ('parts','messages'):
  a={x['id']:dict(x,data=json.loads(x['data'])) for x in old['native'][table]}
  b={x['id']:dict(x,data=json.loads(x['data'])) for x in new['native'][table]}
  utf8_only(a,b,'native.'+table,changes)
 a={x['id']:{k:v for k,v in x.items() if k!='time_updated'} for x in old['native']['sessions']}
 b={x['id']:{k:v for k,v in x.items() if k!='time_updated'} for x in new['native']['sessions']}
 utf8_only(a,b,'native.sessions',changes)

def completion_sources(unit,record_path,evidence):
 profile=evidence.get('collection',{}).get('trace_utf8_redecode')
 if not profile:return None
 require(profile.get('profile')==PROFILE,'PROFILE_INVALID')
 root=Path(record_path).parent/'trace/raw/utf8-redecode'
 data={key:(root/name).read_bytes() for key,name in EXTRA_NAMES.items()}
 data['redecode_native']=(Path(record_path).parent/'trace/raw/native-engine-snapshot.json').read_bytes()
 data['redecode_transcript']=(Path(record_path).parent/'trace/transcript.jsonl').read_bytes()
 return child(unit,profile['collection_receipt_path']),data

def verify_completion(execution,evidence,collected,files,source_paths):
 profile=evidence.get('collection',{}).get('trace_utf8_redecode')
 if not profile:return
 require(profile.get('profile')==PROFILE,'PROFILE_INVALID')
 proof=json.loads(files['redecode_provenance']);old=json.loads(files['redecode_original_record'])
 old_manifest=json.loads(files['redecode_original_manifest']);old_receipt=json.loads(files['redecode_original_collect_receipt'])
 require(proof['profile']==PROFILE and old['identity']==execution['identity']==proof['identity'],'IDENTITY')
 require(old['phase']=='COMPLETED' and old['session']['verified'] and old['prompt']['send_status']=='sent','ORIGINAL_NOT_COMPLETE')
 expected=copy.deepcopy(old)
 for key in ('transcript_path','trace_index_path','final_response_path'):expected['evidence'][key]=execution['evidence'][key]
 expected['resource_metrics_path']=execution['resource_metrics_path'];require(expected==execution,'EXECUTION_CHANGED')
 require(old_receipt['scope']==collected['scope'] and old_receipt['dataset']==collected['dataset']
   and old_receipt['task_ids']==collected['task_ids'] and old_receipt['tasks']==collected['tasks'],'RECEIPT_SCOPE_CHANGED')
 verify_ref(old_receipt,proof['original_record_path'],files['redecode_original_record'])
 verify_ref(old_receipt,proof['original_manifest_path'],files['redecode_original_manifest'])
 require(proof['original_collect_receipt_sha256']==sha(files['redecode_original_collect_receipt']),'ORIGINAL_RECEIPT_DIGEST')
 for key,path in [('redecode_original_native',proof['original_native_path']),('redecode_original_transcript',old['evidence']['transcript_path']),('redecode_original_final',old['evidence']['final_response_path'])]:verify_ref(old_manifest,path,files[key])
 verify_ref(evidence,proof['redecoded_native_path'],files['redecode_native'])
 verify_ref(evidence,execution['evidence']['transcript_path'],files['redecode_transcript'])
 verify_native(json.loads(files['redecode_original_native']),json.loads(files['redecode_native']))
 utf8_only([json.loads(x) for x in files['redecode_original_transcript'].splitlines()],[json.loads(x) for x in files['redecode_transcript'].splitlines()],'transcript')
 utf8_only(files['redecode_original_final'].decode(),files['final_response'].decode(),'final_response')
 require(proof['candidate_bytes_changed'] is False and proof['native_prompt_resends']==0,'REPAIR_SCOPE')


def publish(unit_root,captures,repair_id,stop_proof_path):
 unit=Path(unit_root).resolve();require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]*',repair_id) is not None,'REPAIR_ID')
 manifest=json.loads((unit/'manifest.json').read_text());require(set(captures)==set(manifest['task_ids']),'FULL_SCOPE_REQUIRED')
 stop_bytes=Path(stop_proof_path).read_bytes();stop=json.loads(stop_bytes);require(stop.get('bound_app_and_engine_processes_after')==[] and stop.get('native_engine_root_session_count')==len(manifest['task_ids']) and stop.get('all_native_engine_roots_belong_to_original_frozen_queue') is True,'PROCESS_BARRIER_REQUIRED')
 receipt_path=unit/'receipts/collect-evidence-receipt.json';receipt_bytes=receipt_path.read_bytes();receipt=json.loads(receipt_bytes)
 root=unit/'evidence/trace-recaptures'/repair_id;require(not root.exists(),'OUTPUT_EXISTS');root.mkdir(parents=True)
 selected={};new_receipt=copy.deepcopy(receipt);new_receipt['created_at']=datetime.now(timezone.utc).isoformat();new_receipt['artifacts']=[]
 new_receipt_path=unit/'receipts'/(repair_id+'-collect-evidence-receipt.json');require(not new_receipt_path.exists(),'RECEIPT_EXISTS')
 changes_by_task={}
 for tid in manifest['task_ids']:
  candidates=list((unit/'evidence/tasks'/tid).glob('*/execution-record.json'));require(len(candidates)==1,'ORIGINAL_RECORD_AMBIGUOUS')
  old_path=candidates[0];old_bytes=old_path.read_bytes();old=json.loads(old_bytes);old_manifest_path=old_path.with_name('evidence-manifest.json');old_manifest_bytes=old_manifest_path.read_bytes();old_manifest=json.loads(old_manifest_bytes)
  verify_ref(receipt,old_path.relative_to(unit).as_posix(),old_bytes);verify_ref(receipt,old_manifest_path.relative_to(unit).as_posix(),old_manifest_bytes)
  for ref in old_manifest['artifacts']:
   path=unit/ref['path'];data=os.readlink(path).encode() if path.is_symlink() else path.read_bytes();require(sha(data)==ref['sha256'] and len(data)==ref['size'],'ORIGINAL_ARTIFACT_DRIFT')
  capture=Path(captures[tid]).resolve();require(capture.is_relative_to(unit),'CAPTURE_OUTSIDE_UNIT');dest=root/tid;shutil.copytree(capture,dest)
  state=json.loads((dest/'execution/automation-state.json').read_text());require(state['identity']==old['identity'] and state['session']['session_id']==old['session']['session_id'] and state['session']['cwd']==old['session']['cwd'] and state['human_assistance']==old['human_assistance'],'CAPTURE_IDENTITY')
  old_index=json.loads(child(unit,old['evidence']['trace_index_path']).read_text());new_index=json.loads((dest/'trace/trace-index.json').read_text());require(old_index['identity']==new_index['identity'] and old_index['calls']==new_index['calls'],'TRACE_IDENTITY')
  original_native=child(unit,str(PurePosixPath(old['evidence']['trace_index_path']).parent/'raw/native-engine-snapshot.json')).read_bytes();new_native=(dest/'trace/raw/native-engine-snapshot.json').read_bytes();changes=[];verify_native(json.loads(original_native),json.loads(new_native),changes)
  original_transcript=child(unit,old['evidence']['transcript_path']).read_bytes();new_transcript=(dest/'trace/transcript.jsonl').read_bytes();utf8_only([json.loads(x) for x in original_transcript.splitlines()],[json.loads(x) for x in new_transcript.splitlines()],'transcript',changes)
  original_final=child(unit,old['evidence']['final_response_path']).read_bytes();new_final=(dest/'execution/final-response.md').read_bytes();utf8_only(original_final.decode(),new_final.decode(),'final_response',changes)
  new_record=copy.deepcopy(old);prefix=dest.relative_to(unit).as_posix()
  new_record['evidence'].update(transcript_path=prefix+'/trace/transcript.jsonl',trace_index_path=prefix+'/trace/trace-index.json',final_response_path=prefix+'/final-response.md');new_record['resource_metrics_path']=prefix+'/resource-metrics.json';(dest/'final-response.md').write_bytes(new_final)
  proof={'profile':PROFILE,'identity':old['identity'],'original_record_path':old_path.relative_to(unit).as_posix(),'original_manifest_path':old_manifest_path.relative_to(unit).as_posix(),'original_native_path':str(PurePosixPath(old['evidence']['trace_index_path']).parent/'raw/native-engine-snapshot.json'),'redecoded_native_path':prefix+'/trace/raw/native-engine-snapshot.json','original_collect_receipt_sha256':sha(receipt_bytes),'process_stop_proof_sha256':sha(stop_bytes),'candidate_bytes_changed':False,'native_prompt_resends':0,'utf8_only_changes':changes}
  raw=dest/'trace/raw/utf8-redecode';raw.mkdir();originals={'redecode_provenance':encode(proof),'redecode_original_record':old_bytes,'redecode_original_manifest':old_manifest_bytes,'redecode_original_collect_receipt':receipt_bytes,'redecode_original_native':original_native,'redecode_original_transcript':original_transcript,'redecode_original_final':original_final}
  for key,name in EXTRA_NAMES.items():(raw/name).write_bytes(originals[key])
  (raw/'process-stop-proof.json').write_bytes(stop_bytes)
  for path in sorted(raw.iterdir()):new_index['raw_trace'].append({'path':path.relative_to(dest/'trace').as_posix(),'sha256':sha(path.read_bytes()),'size':path.stat().st_size})
  (dest/'trace/trace-index.json').write_bytes(encode(new_index));resource=json.loads((dest/'resource-metrics.json').read_text());old_resource=json.loads(child(unit,old['resource_metrics_path']).read_text());require(resource['metrics']==old_resource['metrics'],'RESOURCE_METRICS_CHANGED')
  sources=[artifact(dest,dest/'execution/automation-state.json'),artifact(dest,dest/'trace/trace-index.json')]+[dict(x,path='trace/'+x['path']) for x in [*new_index['raw_trace'],*new_index.get('binding_evidence',[])]];resource['collection']['sources']=sources;resource['collection']['metric_sources']={key:[x['path'] for x in sources] for key in resource['collection']['metric_sources']};(dest/'resource-metrics.json').write_bytes(encode(resource))
  keep=[x for x in old_manifest['artifacts'] if x['path'].startswith(old_path.parent.relative_to(unit).as_posix()+'/candidate/') or x['path']==old_manifest['collection']['process_cleanup_path']]
  artifacts=keep+[artifact(unit,x) for x in sorted(dest.rglob('*')) if x.is_file() and x.name not in {'execution-record.json','evidence-manifest.json'}]
  evidence=copy.deepcopy(old_manifest);evidence['collected_at']=datetime.now(timezone.utc).isoformat();evidence['artifacts']=artifacts;evidence['collection'].update(collector='qwenwork-native-utf8-redecode',version='1.0.0',execution_record_path=prefix+'/execution-record.json',trace_utf8_redecode={'profile':PROFILE,'collection_receipt_path':new_receipt_path.relative_to(unit).as_posix()})
  record_path=dest/'execution-record.json';record_path.write_bytes(encode(new_record));(dest/'evidence-manifest.json').write_bytes(encode(evidence));selected[tid]=str(record_path);changes_by_task[tid]=len(changes)
  for path in [record_path,dest/'evidence-manifest.json',unit/old_manifest['collection']['process_cleanup_path'],unit/old_manifest['collection']['candidate_artifact_path']]:new_receipt['artifacts'].append(artifact(unit,path))
 new_receipt['artifacts'].sort(key=lambda x:x['path']);new_receipt_path.write_bytes(encode(new_receipt));require(receipt_path.read_bytes()==receipt_bytes,'ORIGINAL_RECEIPT_CHANGED')
 for tid,path in selected.items():
  path=Path(path);execution=json.loads(path.read_text());evidence=json.loads(path.with_name('evidence-manifest.json').read_text());_,extra=completion_sources(unit,path,evidence);extra['final_response']=child(unit,execution['evidence']['final_response_path']).read_bytes();verify_completion(execution,evidence,new_receipt,extra,{})
 return {'status':'VERIFIED','profile':PROFILE,'selected_execution_records':selected,'collection_receipt':str(new_receipt_path),'collection_receipt_sha256':sha(new_receipt_path.read_bytes()),'original_receipt_sha256':sha(receipt_bytes),'utf8_change_counts':changes_by_task,'candidate_bytes_changed':False,'native_prompt_resends':0}
