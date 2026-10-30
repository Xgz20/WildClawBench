from pathlib import Path
import copy,json,unittest
from eval_general_e2e.contracts import utf8_redecode as U

def ref(path,data):return {'path':path,'sha256':U.sha(data),'size':len(data)}
def fixture():
 identity={'batch_id':'b','unit_id':'u','task_id':'task','attempt_id':'attempt'}
 old={'identity':identity,'phase':'COMPLETED','session':{'verified':True,'session_id':'host'},'prompt':{'send_status':'sent'},'model':{'actual_id':'model'},'candidate':{'path':'old/candidate','frozen_sha256':'a'*64},'evidence':{'transcript_path':'old/trace/transcript.jsonl','trace_index_path':'old/trace/index.json','final_response_path':'old/final.md'},'resource_metrics_path':'old/resource.json'}
 new=copy.deepcopy(old);new['evidence']={k:v.replace('old/','new/') for k,v in old['evidence'].items()};new['resource_metrics_path']='new/resource.json'
 host={'session_id':'host','conversation_id':'chat','sub_chat_id':'sub','local_project_id':'project','cwd':'/work'}
 native={'profile':'qwenwork-opencode-sqlite-v1','host':{'record':host},'native':{'parts':[{'id':'part','data':json.dumps({'type':'text','text':'中'},ensure_ascii=False)}],'messages':[{'id':'message','data':'{"role":"assistant"}'}],'sessions':[{'id':'root','time_updated':1,'model':'model'}]}}
 old_native=copy.deepcopy(native);old_native['native']['parts'][0]['data']=json.dumps({'type':'text','text':'��'},ensure_ascii=False)
 old_trace=U.encode({'type':'assistant_message','content':'��'});new_trace=U.encode({'type':'assistant_message','content':'中'})
 # JSONL fixtures are single compact records.
 old_trace=json.dumps({'type':'assistant_message','content':'��'},ensure_ascii=False).encode()+b'\n';new_trace=json.dumps({'type':'assistant_message','content':'中'},ensure_ascii=False).encode()+b'\n'
 old_final='��'.encode();final='中'.encode();files={'redecode_original_record':U.encode(old),'redecode_original_native':U.encode(old_native),'redecode_native':U.encode(native),'redecode_original_transcript':old_trace,'redecode_transcript':new_trace,'redecode_original_final':old_final,'final_response':final}
 old_manifest={'identity':identity,'artifacts':[ref('old/trace/raw/native.json',files['redecode_original_native']),ref(old['evidence']['transcript_path'],old_trace),ref(old['evidence']['final_response_path'],old_final)]};files['redecode_original_manifest']=U.encode(old_manifest)
 receipt={'scope':{'batch_id':'b','unit_id':'u'},'dataset':{'id':'dataset','digest':'d'},'task_ids':['task'],'tasks':[{'task_id':'task','attempt_id':'attempt','status':'partial'}],'artifacts':[ref('old/record.json',files['redecode_original_record']),ref('old/evidence-manifest.json',files['redecode_original_manifest'])]};files['redecode_original_collect_receipt']=U.encode(receipt)
 proof={'profile':U.PROFILE,'identity':identity,'original_record_path':'old/record.json','original_manifest_path':'old/evidence-manifest.json','original_native_path':'old/trace/raw/native.json','redecoded_native_path':'new/trace/raw/native.json','original_collect_receipt_sha256':U.sha(files['redecode_original_collect_receipt']),'candidate_bytes_changed':False,'native_prompt_resends':0};files['redecode_provenance']=U.encode(proof)
 evidence={'identity':identity,'collection':{'trace_utf8_redecode':{'profile':U.PROFILE}},'artifacts':[ref(proof['redecoded_native_path'],files['redecode_native']),ref(new['evidence']['transcript_path'],new_trace)]};collected=copy.deepcopy(receipt)
 return new,evidence,collected,files

class Utf8RedecodeTests(unittest.TestCase):
 def test_multibyte_character_and_emoji_only(self):
  U.utf8_only({'text':'文��🙂'},{'text':'文字🙂'});U.utf8_only('��','🙂')
  for old,new in [('abc','abd'),('��x','中y'),('��','ab'),('�','中')]:
   with self.subTest(old=old,new=new),self.assertRaises(ValueError):U.utf8_only(old,new)
 def test_shape_changes_fail(self):
  for a,b in [({'a':1},{'a':2}),([1],[1,2]),({'a':1},{'b':1})]:
   with self.assertRaises(ValueError):U.utf8_only(a,b)
 def test_completion_binds_original_and_redecoded_sources(self):
  args=fixture();U.verify_completion(*args,{})
 def test_legacy_without_profile_stays_unchanged(self):U.verify_completion({}, {}, {}, {}, {})
 def test_model_candidate_and_scope_changes_fail(self):
  for field in ['model','candidate','scope']:
   new,evidence,collected,files=fixture()
   if field=='model':new['model']['actual_id']='other'
   elif field=='candidate':new['candidate']['frozen_sha256']='b'*64
   else:collected['task_ids']=['other']
   with self.subTest(field=field),self.assertRaises(ValueError):U.verify_completion(new,evidence,collected,files,{})
 def test_original_record_tampering_fails(self):
  new,evidence,collected,files=fixture();files['redecode_original_record']+=b' '
  with self.assertRaises(ValueError):U.verify_completion(new,evidence,collected,files,{})
 def test_semantic_transcript_change_fails(self):
  new,evidence,collected,files=fixture();files['redecode_transcript']=b'{"content":"other"}\n';evidence['artifacts'][-1]=ref(new['evidence']['transcript_path'],files['redecode_transcript'])
  with self.assertRaises(ValueError):U.verify_completion(new,evidence,collected,files,{})
 def test_native_identity_and_extra_part_fail(self):
  for kind in ['identity','part']:
   a=json.loads(fixture()[3]['redecode_original_native']);b=copy.deepcopy(a)
   if kind=='identity':b['host']['record']['session_id']='other'
   else:b['native']['parts'].append({'id':'extra','data':'{}'})
   with self.subTest(kind=kind),self.assertRaises(ValueError):U.verify_native(a,b)
