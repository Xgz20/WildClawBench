import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {PROFILE,validateNativeToolCatalog} from '../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/native-tools.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex'),bytes=x=>Buffer.from(JSON.stringify(x));
function fixture(){
 const identity={batch_id:'b',unit_id:'u',task_id:'t',attempt_id:'a'},cwd='/fixture/workspace';
 const config={control:{probe_sha256:null}},configSha256='a'.repeat(64);
 const state={identity,session:{session_id:'host',cwd},prompt:{sent_at:'2026-10-31T01:00:00Z'},execution:{finished_at:'2026-10-31T01:00:10Z'}};
 const evidence={native:{sessions:[{id:'ses_native',parent_id:null,directory:cwd,model:JSON.stringify({id:'flash',providerID:'openai-compatible'})}]}};
 const files={probe:bytes({execution_environment:{verified:true,listener:{pid:20,process_start_identity:'Sat Oct 31 09:00:00 2026',command_sha256:'c'.repeat(64)}}}),session:bytes({id:'ses_native',directory:cwd}),
  catalog:bytes([{id:'webfetch',description:'Fetch a URL',parameters:{type:'object',required:['url'],properties:{url:{type:'string'}}}}])};
 config.control.probe_sha256=sha(files.probe);
 const proof={profile:PROFILE,identity:structuredClone(identity),cwd,host_session_id:'host',native_session_id:'ses_native',
  model:{id:'flash',providerID:'openai-compatible'},config_sha256:configSha256,captured_at:'2026-10-31T01:00:05Z',
  owner:{verified:true,pid:21,app_pid:20,app_started_at:'Sat Oct 31 09:00:00 2026',app_command_sha256:'c'.repeat(64),started_at:'Sat Oct 31 09:00:00 2026',command_sha256:'b'.repeat(64),cwd},
  endpoint:'http://127.0.0.1:4096',method:'GET',authentication_read:false,tool_invoked:false,
  coverage:'observed-provider-model-tool-registry; other registries not asserted',
  files:Object.fromEntries(Object.entries(files).map(([key,b])=>[key,{path:key+'.json',sha256:sha(b),size:b.length}]))};
 return {proof,files,context:{state,evidence,config,configSha256}};
}
test('exact owner/session/model registry is additional raw evidence with explicit limited coverage',()=>{
 const {proof,files,context}=fixture(),before=JSON.stringify({proof,context});
 assert.equal(validateNativeToolCatalog(proof,files,context).tool_count,1);
 assert.equal(JSON.stringify({proof,context}),before);
});
for(const [name,change]of Object.entries({
 'other-task':x=>x.proof.identity.task_id='elsewhere',
 'other-config':x=>x.proof.config_sha256='c'.repeat(64),
 'other-host':x=>x.proof.host_session_id='other',
 'other-cwd':x=>x.proof.cwd='/other',
 'child-session':x=>x.context.evidence.native.sessions[0].parent_id='parent',
 'other-model':x=>x.proof.model.id='other',
 'old-capture':x=>x.proof.captured_at='2026-10-31T00:00:00Z',
 'post-run-capture':x=>x.proof.captured_at='2026-10-31T02:00:00Z',
 'wrong-app-owner':x=>x.proof.owner.app_pid=999,
 'reused-app-pid':x=>x.proof.owner.app_started_at='later',
 'external-url':x=>x.proof.endpoint='https://example.com',
 'tool-invocation':x=>x.proof.tool_invoked=true,
 'fake-completeness':x=>x.proof.coverage='all tools complete',
 'changed-raw':x=>x.files.catalog=bytes([]),
}))test('native catalog refuses '+name,()=>{const x=fixture();change(x);assert.throws(()=>validateNativeToolCatalog(x.proof,x.files,x.context),/QWEN_NATIVE_TOOLS_/)});
test('unknown catalog shapes remain unavailable rather than becoming empty valid evidence',()=>{
 for(const value of [[],[{id:'x',description:'x',parameters:null}],[{id:'x',description:'x',parameters:{}},{id:'x',description:'x',parameters:{}}]]){
  const x=fixture();x.files.catalog=bytes(value);x.proof.files.catalog={sha256:sha(x.files.catalog),size:x.files.catalog.length};
  assert.throws(()=>validateNativeToolCatalog(x.proof,x.files,x.context),/CATALOG/);
 }
});
