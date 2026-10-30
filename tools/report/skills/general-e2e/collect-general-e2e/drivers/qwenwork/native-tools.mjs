/** Read-only, owner-bound OpenCode tool registry metadata. Never invokes a tool. */
import {createHash} from 'node:crypto';
import {readFile,writeFile,mkdir,lstat,realpath} from 'node:fs/promises';
import {resolve,join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runCapture} from '../../vendor/e2e-shared/desktop-runtime/process.mjs';
import {verifyQwenEngineEvidence} from '../../vendor/e2e-shared/qwenwork-native-state/engine-sqlite.mjs';

const sha=value=>createHash('sha256').update(value).digest('hex');
const check=(ok,message)=>{if(!ok)throw Error('QWEN_NATIVE_TOOLS_'+message)};
export const PROFILE='bound-qwen-live-tool-catalog/v1';
const json=bytes=>JSON.parse(bytes.toString('utf8'));
const encode=value=>Buffer.from(JSON.stringify(value,null,2)+'\n');
const read=async path=>{check((await lstat(path)).isFile()&&!(await lstat(path)).isSymbolicLink(),'UNSAFE_FILE');const b=await readFile(path);check(b.length<=8*1024*1024,'BUDGET');return b};

export function validateNativeToolCatalog(proof,files,{state,evidence,config,configSha256}) {
 check(proof?.profile===PROFILE,'PROFILE');
 check(['batch_id','unit_id','task_id','attempt_id'].every(k=>proof.identity?.[k]===state.identity[k])
   &&Object.keys(proof.identity||{}).length===4,'IDENTITY');
 check(proof.config_sha256===configSha256,'CONFIG');
 const native=evidence.native.sessions.find(s=>s.id===proof.native_session_id);
 const model=native&&(typeof native.model==='string'?JSON.parse(native.model):native.model);
 check(native&&native.parent_id===null&&resolve(native.directory)===resolve(state.session.cwd)
   &&proof.host_session_id===state.session.session_id&&proof.cwd===resolve(state.session.cwd),'SESSION');
 check(model?.providerID===proof.model?.providerID&&model?.id===proof.model?.id,'MODEL');
 const captured=Date.parse(proof.captured_at),sent=Date.parse(state.prompt.sent_at),end=Date.parse(state.execution.finished_at);
 check(Number.isFinite(captured)&&captured>=sent&&(!Number.isFinite(end)||captured<=end),'CAPTURE_TIME');
 for(const [name,ref] of Object.entries(proof.files||{}))check(files[name]&&sha(files[name])===ref.sha256&&files[name].length===ref.size,'FILE_DRIFT');
 check(Object.keys(proof.files||{}).sort().join(',')==='catalog,probe,session','FILE_SET');
 const probe=json(files.probe),session=json(files.session),catalog=json(files.catalog);
 check(sha(files.probe)===config.control.probe_sha256&&probe.execution_environment?.verified===true
   &&probe.execution_environment.listener?.pid===proof.owner.app_pid
   &&probe.execution_environment.listener?.process_start_identity===proof.owner.app_started_at
   &&probe.execution_environment.listener?.command_sha256===proof.owner.app_command_sha256,'APP_OWNER');
 check(session.id===proof.native_session_id&&resolve(session.directory)===proof.cwd,'HTTP_SESSION');
 check(proof.owner.verified===true&&proof.owner.cwd===proof.cwd&&Number.isInteger(proof.owner.pid)
   &&proof.owner.pid>0&&proof.owner.started_at&&/^[a-f0-9]{64}$/u.test(proof.owner.command_sha256||''),'PROCESS');
 const endpoint=new URL(proof.endpoint);
 check(endpoint.protocol==='http:'&&endpoint.hostname==='127.0.0.1'&&endpoint.port
   &&endpoint.pathname==='/'&&!endpoint.username&&!endpoint.password&&!endpoint.search,'ENDPOINT');
 check(proof.method==='GET'&&proof.authentication_read===false&&proof.tool_invoked===false,'READ_ONLY');
 check(Array.isArray(catalog)&&catalog.length>0&&new Set(catalog.map(t=>t.id)).size===catalog.length
   &&catalog.every(t=>typeof t.id==='string'&&t.id&&typeof t.description==='string'
     &&t.parameters&&typeof t.parameters==='object'&&!Array.isArray(t.parameters)),'CATALOG');
 check(proof.coverage==='observed-provider-model-tool-registry; other registries not asserted','COVERAGE');
 return {tool_count:catalog.length,native_session_id:proof.native_session_id,model:proof.model,coverage:proof.coverage};
}

export async function loadNativeToolCatalog(proofPath,context) {
 const bytes=await read(proofPath),proof=json(bytes),files={};
 for(const name of ['catalog','session','probe']) {
  const ref=proof.files?.[name];check(ref&&ref.path===name+'.json','RELATIVE_PATH');
  files[name]=await read(join(dirname(proofPath),ref.path));
 }
 const verified=validateNativeToolCatalog(proof,files,context);
 return {proof,bytes,files,verified};
}

async function output(command,args) {const r=await runCapture(command,args,{capture:true});return r.stdout;}
async function processRows() {
 const text=await output('/bin/ps',['-axo','pid=,ppid=,lstart=,command=']);
 return text.split('\n').flatMap(line=>{const m=line.trim().match(/^(\d+)\s+(\d+)\s+(.{24})\s+(.+)$/u);
  return m?[{pid:Number(m[1]),ppid:Number(m[2]),started_at:m[3],command:m[4],command_sha256:sha(m[4])}]:[]});
}
async function request(endpoint,path,query={}) {
 const url=new URL(path,endpoint);for(const [k,v]of Object.entries(query))url.searchParams.set(k,v);
 const response=await fetch(url,{redirect:'manual',signal:AbortSignal.timeout(5000),headers:{Accept:'application/json'}});
 check(response.status===200,'HTTP_STATUS_'+response.status);
 const chunks=[];let size=0;
 for await(const b of response.body){size+=b.length;check(size<=8*1024*1024,'HTTP_BUDGET');chunks.push(b)}
 return Buffer.concat(chunks);
}

export async function captureNativeToolCatalog({journalFile,outputDir}) {
 const journal=json(await read(journalFile));check(journal.session?.verified===true&&journal.send?.state==='confirmed'
   &&journal.send.dispatch_attempt_count===1,'UNBOUND_ATTEMPT');
 const configBytes=await read(join(dirname(journalFile),'config.json')),config=json(configBytes);
 const promptBytes=await read(config.prompt.path);check(sha(promptBytes)===journal.prompt.sha256,'PROMPT');
 const oldBytes=await read(journal.session.prompt_evidence.transcript_path);
 check(sha(oldBytes)===journal.session.prompt_evidence.transcript_sha256,'PROMPT_EVIDENCE');
 const evidence=json(oldBytes),verified=verifyQwenEngineEvidence(evidence,{session:journal.session,prompt:{sha256:sha(promptBytes),content:promptBytes.toString('utf8')}});
 const nativeId=verified.root.id,cwd=resolve(journal.session.cwd),model=JSON.parse(verified.root.model);
 const probeBytes=await read(config.control.probe_path);check(sha(probeBytes)===config.control.probe_sha256,'PROBE');
 const listener=json(probeBytes).execution_environment?.listener,appPid=listener?.pid;check(Number.isInteger(appPid),'APP_PID');
 const before=await processRows(),app=before.find(p=>p.pid===appPid);check(app?.command.startsWith('/Applications/QwenWorkCN.app/Contents/MacOS/QwenWorkCN'),'APP_PROCESS');
 check(app.started_at===listener.process_start_identity&&app.command_sha256===listener.command_sha256,'APP_CHANGED');
 const owned=new Set([appPid]);for(let changed=true;changed;){changed=false;for(const p of before)if(owned.has(p.ppid)&&!owned.has(p.pid)){owned.add(p.pid);changed=true}}
 const candidates=[];
 for(const p of before.filter(p=>owned.has(p.pid)&&p.command.includes('/agent-sdk/components/flash-cli/')&&p.command.includes('/runtime/flash-cli-acp.mjs'))) {
  const actualCwd=(await output('/usr/sbin/lsof',['-a','-p',String(p.pid),'-d','cwd','-Fn'])).split('\n').find(s=>s.startsWith('n'))?.slice(1);
  if(actualCwd!==cwd)continue;
  const sockets=await output('/usr/sbin/lsof',['-nP','-a','-p',String(p.pid),'-iTCP','-sTCP:LISTEN','-Fn']);
  const ports=[...sockets.matchAll(/^n127\.0\.0\.1:(\d+)$/gmu)].map(m=>m[1]);
  if(ports.length===1)candidates.push({...p,cwd,endpoint:'http://127.0.0.1:'+ports[0]});
 }
 check(candidates.length===1,'SDK_OWNER_NOT_UNIQUE');const owner=candidates[0];
 const sessionBytes=await request(owner.endpoint,'/session/'+encodeURIComponent(nativeId));const session=json(sessionBytes);
 check(session.id===nativeId&&resolve(session.directory)===cwd,'SERVER_SESSION_MISMATCH');
 const catalogBytes=await request(owner.endpoint,'/experimental/tool',{directory:cwd,provider:model.providerID,model:model.id});
 const afterRows=await processRows(),after=afterRows.find(p=>p.pid===owner.pid),afterApp=afterRows.find(p=>p.pid===appPid);
 check(after?.started_at===owner.started_at&&after.command_sha256===owner.command_sha256
   &&afterApp?.started_at===app.started_at&&afterApp.command_sha256===app.command_sha256,'OWNER_CHANGED');
 const files={catalog:catalogBytes,session:sessionBytes,probe:probeBytes};
 const proof={profile:PROFILE,identity:journal.identity,host_session_id:journal.session.session_id,native_session_id:nativeId,
  cwd,model:{providerID:model.providerID,id:model.id},config_sha256:sha(configBytes),captured_at:new Date().toISOString(),
  endpoint:owner.endpoint,method:'GET',authentication_read:false,tool_invoked:false,
  coverage:'observed-provider-model-tool-registry; other registries not asserted',
  owner:{verified:true,pid:owner.pid,app_pid:appPid,app_started_at:app.started_at,app_command_sha256:app.command_sha256,
    started_at:owner.started_at,command_sha256:owner.command_sha256,cwd},
  files:Object.fromEntries(Object.entries(files).map(([k,b])=>[k,{path:k+'.json',sha256:sha(b),size:b.length}]))};
 const state={identity:journal.identity,session:journal.session,prompt:{sent_at:journal.prompt.sent_at},execution:{finished_at:journal.execution_state?.execution?.finished_at}};
 const audit=validateNativeToolCatalog(proof,files,{state,evidence,config,configSha256:sha(configBytes)});
 check(await realpath(dirname(outputDir))===resolve(dirname(outputDir)),'OUTPUT_PARENT_SYMLINK');await mkdir(outputDir);
 for(const [k,b]of Object.entries(files))await writeFile(join(outputDir,k+'.json'),b,{flag:'wx',mode:0o600});
 await writeFile(join(outputDir,'proof.json'),encode(proof),{flag:'wx',mode:0o600});
 return {status:'PASS',proof:join(outputDir,'proof.json'),...audit};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
 const args=process.argv.slice(2),value=key=>args[args.indexOf(key)+1];
 try {check(args.length===4&&args.includes('--journal-file')&&args.includes('--output-dir'),'ARGS');
  console.log(JSON.stringify(await captureNativeToolCatalog({journalFile:value('--journal-file'),outputDir:value('--output-dir')}),null,2));
 }catch(error){console.error(error.message);process.exitCode=2}
}
