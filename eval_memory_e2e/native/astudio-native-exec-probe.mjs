/* Synthetic protocol probe; never sends a model prompt. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const folder=path.resolve(process.argv[2]),ready=path.join(folder,'proxy-ready.json');
for(let i=0;!fs.existsSync(ready)&&i<200;i++)await new Promise(r=>setTimeout(r,50));
const ws=new WebSocket(JSON.parse(fs.readFileSync(ready)).url),pending=new Map(),events=[];
let seq=0;
ws.onmessage=event=>{
  const message=JSON.parse(event.data);
  if(message.id!==undefined&&pending.has(message.id)){pending.get(message.id)(message);pending.delete(message.id)}
  else events.push(message);
};
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
async function request(method,params){
  const id=++seq;
  const result=new Promise(resolve=>pending.set(id,resolve));
  ws.send(JSON.stringify({id,method,params}));
  return await Promise.race([result,new Promise((_,reject)=>setTimeout(()=>reject(Error('NATIVE_PROBE_TIMEOUT '+method)),20000).unref())]);
}
const init=await request('initialize',{clientName:'memory-e2e-synthetic-probe'});
if(!init.result?.sessionId)throw Error('NATIVE_PROBE_INITIALIZE');
ws.send(JSON.stringify({method:'initialized',params:{}}));
const u=value=>pathToFileURL(path.join(folder,'fixture',value)).href;
const entries=[['/','read'],[path.join(folder,'fixture/workspace'),'write'],
  [path.join(folder,'fixture/workspace/readonly'),'read'],[path.join(folder,'fixture/workspace/private'),'none']]
  .map(([p,access])=>({path:{type:'path',path:pathToFileURL(p).href},access}));
const sandbox={permissions:{type:'managed',file_system:{type:'restricted',entries},network:'restricted'},
  cwd:u('workspace'),windowsSandboxLevel:'disabled'};
const rows=[];
const canonical=await request('fs/canonicalize',{path:u('workspace/fact.txt'),sandbox});
rows.push({label:'allowed-native-canonicalize',reply:canonical,pass:!!canonical.result});
const listing=await request('fs/readDirectory',{path:u('workspace'),sandbox});
rows.push({label:'allowed-native-directory-read',reply:listing,pass:!!listing.result});
for(const [label,params,denied] of [
  ['allowed-read',{path:u('workspace/fact.txt'),sandbox},false],
  ['native-private-read',{path:u('workspace/private/fact.txt'),sandbox},true],
  ['outer-denied-read',{path:u('non-target/fact.txt'),sandbox},true],
  ['outer-denied-read-no-native-policy',{path:u('non-target/fact.txt'),sandbox:null},true],
  ['outer-denied-symlink',{path:u('workspace/alias/fact.txt'),sandbox},true],
]){
  const reply=await request('fs/readFile',params);
  rows.push({label,expected_denied:denied,reply,pass:denied?!!reply.error:!!reply.result?.dataBase64});
}
const snapshot=await request('process/start',{processId:'invalid-snapshot',argv:['/usr/bin/true'],cwd:u('workspace'),env:{},tty:false,arg0:null,
  sandbox,shellSnapshot:{shell:{name:'zsh',path:'/bin/zsh'}}});
rows.push({label:'pre-sandbox-shell-snapshot-rejected',reply:snapshot,pass:!!snapshot.error});
const unknown=await request('unknown/data/read',{path:u('non-target/fact.txt')});
rows.push({label:'unknown-api-rejected',reply:unknown,pass:!!unknown.error});
const code=`import os,json,sys,time,socket\nfrom pathlib import Path\np=Path(sys.argv[1]);rows=[]\nfor label,rel,op,denied in [('allowed-read','workspace/fact.txt','read',False),('allowed-write','workspace/new','write',False),('native-readonly-write','workspace/readonly/new','write',True),('native-private-read','workspace/private/fact.txt','read',True),('native-private-stat','workspace/private/fact.txt','stat',True),('outer-denied-read','non-target/fact.txt','read',True),('outer-denied-stat','non-target/fact.txt','stat',True),('outer-denied-list','non-target','list',True),('native-outside-write','other-runtime/new','write',True),('outer-denied-alias','workspace/alias/fact.txt','read',True),('outer-denied-data-alias','/System/Volumes/Data'+str(p/'non-target/fact.txt'),'read',True),('denied-hardlink','workspace/linked','link',True)]:\n try:\n  target=Path(rel) if rel.startswith('/') else p/rel\n  if op=='read':target.read_bytes()\n  elif op=='write':target.write_text('SYNTHETIC')\n  elif op=='stat':target.stat()\n  elif op=='link':os.link(p/'non-target/fact.txt',target)\n  else:list(target.iterdir())\n  rows.append({'label':label,'denied':False,'pass':not denied})\n except OSError as e:rows.append({'label':label,'denied':True,'errno':e.errno,'pass':denied and e.errno in (1,13)})\nprint(json.dumps({'worker_pid':os.getpid(),'results':rows}),flush=True)\ntime.sleep(3)\n`;
const started=await request('process/start',{processId:'matrix',argv:[process.env.MEMORY_E2E_PYTHON,'-c',code,path.join(folder,'fixture')],
  cwd:u('workspace'),env:{},tty:false,arg0:null,sandbox});
for(let i=0;!events.some(e=>e.method==='process/closed')&&i<150;i++)await new Promise(r=>setTimeout(r,100));
rows.push({label:'native-process-start',reply:started,pass:!!started.result});
const output=events.filter(e=>e.method==='process/output'&&e.params?.stream==='stdout').map(e=>Buffer.from(e.params.chunk,'base64').toString()).join('');
let matrix=null;try{matrix=JSON.parse(output)}catch{}
const exited=events.find(e=>e.method==='process/exited');
const pass=rows.every(row=>row.pass)&&matrix?.results.every(row=>row.pass)&&exited?.params.exitCode===0;
fs.writeFileSync(path.join(folder,'probe-result.json'),JSON.stringify({pass,rows,matrix,events},null,2)+'\n',{mode:0o600,flag:'wx'});
ws.close();
process.exitCode=pass?0:1;
