/* Synthetic OS/protocol admission for the source-built native controller. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const folder=path.resolve(process.argv[2]),control=path.join(folder,'control');
const ready=path.join(control,'broker-ready.json');
for(let n=0;!fs.existsSync(ready)&&n<300;n++)await new Promise(r=>setTimeout(r,50));
const ws=new WebSocket(JSON.parse(fs.readFileSync(ready)).url),pending=new Map(),events=[];
let nextId=0;
ws.onmessage=event=>{const msg=JSON.parse(event.data);if(msg.id!==undefined&&pending.has(String(msg.id))){pending.get(String(msg.id))(msg);pending.delete(String(msg.id))}else events.push(msg)};
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
const request=async(method,params)=>{
  const id=++nextId,promise=new Promise(resolve=>pending.set(String(id),resolve));
  ws.send(JSON.stringify({id,method,params}));
  return await Promise.race([promise,new Promise((_,reject)=>setTimeout(()=>reject(Error('PROBE_TIMEOUT '+method)),30000).unref())]);
};
const u=relative=>pathToFileURL(path.join(folder,relative)).href;
const allowed=path.join(folder,'synthetic/allowed'),rows=[];
const sandbox={permissions:{type:'managed',network:'restricted',file_system:{type:'restricted',entries:[
  ['/', 'read'],[allowed,'write'],[path.join(allowed,'native-private'),'none'],[path.join(allowed,'native-readonly'),'read']
].map(([p,access])=>({path:{type:'path',path:pathToFileURL(p).href},access}))}},cwd:u('synthetic/allowed'),windowsSandboxLevel:'disabled'};
const osDenied=reply=>!!reply.error&&/(Operation not permitted|Permission denied|os error (?:1|13)\b)/i.test(reply.error.message);
function record(label,reply,pass){rows.push({label,pass,reply})}
async function processRun(id,argv,options={}){
  const start=await request('process/start',{processId:id,argv,cwd:u('synthetic/allowed'),env:{},tty:false,arg0:null,sandbox,...options});
  for(let n=0;!events.some(e=>e.method==='process/closed'&&e.params?.processId===id)&&n<300;n++)await new Promise(r=>setTimeout(r,50));
  const output=events.filter(e=>e.method==='process/output'&&e.params?.processId===id&&e.params.stream==='stdout').map(e=>Buffer.from(e.params.chunk,'base64').toString()).join('');
  const exit=events.find(e=>e.method==='process/exited'&&e.params?.processId===id);
  return {start,output,exit};
}
try{
  const init=await request('initialize',{clientName:'memory-e2e-native-composition-probe'});
  if(!init.result?.sessionId)throw Error('PROBE_INITIALIZE');
  ws.send(JSON.stringify({method:'initialized',params:{}}));
  for(const [label,relative,deny] of [
    ['current-read','synthetic/allowed/current.md',false],['native-private','synthetic/allowed/native-private/fact.txt',true],
    ['non-target','synthetic/non-target/canary.txt',true],['old-case','old-case-r1/memory.md',true],['old-repeat','same-case-r1/memory.md',true],
    ['old-repeat-alias','synthetic/allowed/old-repeat-alias/memory.md',true]]){
    const reply=await request('fs/readFile',{path:u(relative),sandbox});record(label,reply,deny?osDenied(reply):!!reply.result?.dataBase64);
  }
  for(const [label,permissions] of [['nil',null],['disabled',{type:'disabled'}],['external',{type:'external',network:'enabled'}]]){
    const context=permissions?{...sandbox,permissions}:null;
    const reply=await request('fs/readFile',{path:u('synthetic/non-target/canary.txt'),sandbox:context});record('forced-native-fs-'+label,reply,osDenied(reply));
  }
  // The old lexical-intersection implementation leaked on this exact shape.
  for(const access of ['read','write']){
    const explicit=structuredClone(sandbox);
    explicit.permissions.file_system.entries.push({path:{type:'path',path:u('synthetic/allowed/alias')},access});
    for(const relative of ['synthetic/allowed/alias/canary.txt','synthetic/non-target/canary.txt']){
      const reply=await request('fs/readFile',{path:u(relative),sandbox:explicit});record('native-canonical-grant-'+access+'-'+relative,reply,osDenied(reply));
    }
  }
  const opened=await request('fs/open',{handleId:'current-stream',path:u('synthetic/allowed/current.md'),sandbox:null});
  record('stream-open-current',opened,!!opened.result);
  const first=await request('fs/readBlock',{handleId:'current-stream',offset:0,len:128});
  record('stream-read-current',first,!!first.result&&Buffer.from(first.result.chunk??'','base64').toString()==='SYNTHETIC-CURRENT-ONE');
  fs.writeFileSync(path.join(allowed,'current.md'),'SYNTHETIC-CURRENT-TWO');
  const second=await request('fs/readBlock',{handleId:'current-stream',offset:0,len:128});
  record('stream-retains-live-native-descriptor',second,!!second.result&&Buffer.from(second.result.chunk??'','base64').toString()==='SYNTHETIC-CURRENT-TWO');
  const closed=await request('fs/close',{handleId:'current-stream'});record('stream-close',closed,!!closed.result);
  const forbidden=await request('fs/open',{handleId:'forbidden-stream',path:u('same-case-r1/memory.md'),sandbox:null});record('stream-old-repeat-denied-by-os',forbidden,osDenied(forbidden));
  const py=process.env.MEMORY_E2E_PYTHON;
  const fixture=await processRun('inherited-fixture',[py,path.join(process.env.MEMORY_E2E_REPO,'eval_memory_e2e/os_boundary.py'),'_fixture-probe','--lease-dir',folder]);
  let parsed;try{parsed=JSON.parse(fixture.output)}catch{}
  record('native-command-and-child-filesystem-fixture',fixture,fixture.exit?.params.exitCode===0&&parsed?.pass===true);
  const arg0=await processRun('argv0',['/bin/sh','-c','printf "%s|%s" "$0" "$CANARY_ENV"'],{arg0:'SYNTHETIC_ARG0',env:{CANARY_ENV:'SYNTHETIC_ENV'},sandbox:null});
  record('argv0-environment-stdout-preserved',arg0,arg0.exit?.params.exitCode===0&&arg0.output==='SYNTHETIC_ARG0|SYNTHETIC_ENV');
  const policyCode="import os,json,time;from eval_memory_e2e.os_boundary import check_policy;from pathlib import Path;p=Path(os.environ['PROBE_ROOT']);print(json.dumps({'pid':os.getpid(),'denied':check_policy(os.getpid(),p/'synthetic/non-target/canary.txt','file-read-data'),'old_repeat':check_policy(os.getpid(),p/'same-case-r1/memory.md','file-read-data'),'allowed':check_policy(os.getpid(),p/'synthetic/allowed/control.txt','file-read-data')}),flush=True);time.sleep(2)";
  const held=await processRun('os-policy',[py,'-c',policyCode],{env:{PROBE_ROOT:folder,PYTHONPATH:process.env.MEMORY_E2E_REPO},sandbox:null});
  let policies;try{policies=JSON.parse(held.output)}catch{}
  record('real-worker-os-policy',held,held.exit?.params.exitCode===0&&policies?.denied===1&&policies?.old_repeat===1&&policies?.allowed===0);
  fs.writeFileSync(path.join(folder,'probe-result.json'),JSON.stringify({pass:rows.every(r=>r.pass),rows,fixture:parsed,os_policy:policies,events,model_prompts:0},null,2)+'\n',{flag:'wx',mode:0o600});
  process.exitCode=rows.every(r=>r.pass)?0:1;
}catch(error){
  fs.writeFileSync(path.join(folder,'probe-error.json'),JSON.stringify({reason:error.stack,rows,events})+'\n',{flag:'wx',mode:0o600});process.exitCode=1;
}finally{ws.close()}
