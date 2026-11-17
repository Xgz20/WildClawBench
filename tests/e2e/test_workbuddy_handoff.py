from pathlib import Path
import json,tempfile
from src.e2e.agentcube import AgentCubeConfig
from src.e2e.common import atomic_json,read_json
from src.e2e.engine import run_batch,verify_ready
from src.e2e.handoff import prepare_scoring_context
from src.e2e.preparation import prepare_batch
from src.e2e.store import BatchStore
from src.e2e.workbuddy_trace import normalize_workbuddy
from tests.e2e.test_scheduler import FakeDriver,Provider,GUEST


def test_workbuddy_original_seal_and_scoring_skill_handoff_replay():
 with tempfile.TemporaryDirectory() as directory:
  root=Path(directory);repo=Path(__file__).resolve().parents[2]
  batch=prepare_batch(repo,root,{'batch_id':'workbuddy-context','selection':{'scenario':'general','dataset':'general-custom60-v1','task_ids':['03_Social_Interaction_task_003_colleague_leave_reply']},'units':[{'harness':'workbuddy','model':'GLM-5.3','max_mode':False}]})
  provider=Provider()
  class Driver(FakeDriver):
   def execute(self):
    sid='fake-session';self.store.update(self.item['key'],'CREATING',creation_intent_at='created',runtime=self.config.public());self.store.update(self.item['key'],'RUNNING',session_id=sid)
    identity={'batch_id':batch.name+'-r0001','unit_id':self.item['unit_id'],'task_id':self.item['task_id'],'attempt_id':self.item['attempt_id']}
    prompt=(batch/self.task['input_root']/'execution/PROMPT.md').read_text()
    usage={'messageId':'m','conversationRequestId':'req','requestModelName':'GLM-5.3','rawUsage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}}
    rows=[{'type':'message','role':'user','content':[{'type':'input_text','text':prompt}],'timestamp':'2026-11-17T00:00:00Z'},
          {'type':'message','role':'assistant','content':[{'type':'output_text','text':'done'}],'status':'completed','timestamp':'2026-11-17T00:00:01Z','providerData':usage}]
    raw=self.staging/'native/session-123456.jsonl';raw.parent.mkdir();raw.write_text('\n'.join(json.dumps({'sessionId':'session-123456','cwd':GUEST,**row}) for row in rows))
    report={'schema_version':2,'status':'completed'};binding=normalize_workbuddy(raw,identity=identity,prompt=prompt,guest_cwd=GUEST,requested_model='GLM-5.3',report=report,
       product_report={'product_report':True,'workflow':{'workspace':GUEST,'model':'GLM-5.3'}},diagnostics={'model':'GLM-5.3','workspace':GUEST,'max_mode':False})
    atomic_json(self.staging/'metadata/native-binding.json',{k:v for k,v in binding.items() if k!='events'});atomic_json(self.staging/'metadata/report.json',report)
    (self.staging/'collect/workspace').mkdir(parents=True);(self.staging/'collect/workspace/answer.txt').write_text('done');atomic_json(self.staging/'collect/evidence/diagnostics.json',{'product_version':'synthetic'})
    cleanup={'schema':'wildclawbench.agentcube-process-cleanup/v1','phase':'completed','supported':True,'success':True,'platform':'win32','workspace':GUEST,'after':[],'before':[],'quiet_observed_milliseconds':5000}
    return {'identity':identity,'binding':binding,'native_path':'native/'+raw.name,'report':report,'workspace':'collect/workspace','cleanup':cleanup}
  try:
   run_batch(batch,AgentCubeConfig(user_id='test',auth_token='not-real'),driver_factory=lambda **kw:Driver(**kw,provider=provider))
   store=BatchStore(batch);row=store.rows()[0];assert row['phase']=='COMPLETED',row.get('error')
   claim=store.claim_score('fixture',1,mode='streaming');context=prepare_scoring_context(batch,claim['key'],claim['claim_id'])
   assert context['verification']['status']=='PASS'
   record=read_json(Path(context['context_root'])/context['execution_record']);assert record['harness']['id']=='workbuddy'
  finally:
   for path in root.rglob('*'):
    if path.is_dir():path.chmod(0o700)
