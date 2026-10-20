/* Experimental controller bridge. Not admitted for model sends by this file.
 * Every process/FS request is intersected with a frozen mandatory native policy.
 * The installed exec-server, not this bridge, builds/applies the native sandbox.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import readline from 'node:readline';
import {createRequire} from 'node:module';
import {spawn,execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url), hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const specPath=path.resolve(process.argv[2]),spec=JSON.parse(fs.readFileSync(specPath));
const specHash=hash(fs.readFileSync(specPath)), root=path.dirname(specPath);
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const bundle=path.join(repo,'tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/node_modules/playwright-core/lib/utilsBundle.js');
const bundleImpl=path.join(path.dirname(bundle),'utilsBundleImpl/index.js');
if(spec.contract!=='astudio-native-exec-experiment/v1'||spec.sources[specPath]||!spec.python||!spec.kernel
  ||spec.synthetic_only!==true||spec.application_integration_allowed!==false||!spec.diagnostic_peer||spec.lease)
  throw Error('NATIVE_EXEC_SPEC_REJECTED');
const {wsServer:WebSocketServer}=require(bundle);
const sources={...spec.sources,[bundle]:spec.bundle_sha256,[bundleImpl]:spec.bundle_impl_sha256};
function frozen(){
  if(hash(fs.readFileSync(specPath))!==specHash)throw Error('NATIVE_EXEC_SPEC_DRIFT');
  for(const [file,sha] of Object.entries(sources))if(hash(fs.readFileSync(file))!==sha)throw Error('NATIVE_EXEC_SOURCE_DRIFT');
}
frozen();
const audit=row=>fs.appendFileSync(path.join(root,'proxy-audit.jsonl'),JSON.stringify({at:new Date().toISOString(),...row})+'\n',{mode:0o600});
const peers=new Set(),server=http.createServer((req,res)=>{res.writeHead(404);res.end()});
const wsServer=new WebSocketServer({noServer:true,maxPayload:16*1024*1024,perMessageDeflate:false});
let stopping=false;
function processTable(){
  const rows=new Map();
  for(const line of execFileSync('/bin/ps',['-axo','pid=,ppid=,lstart=,args='],{encoding:'utf8'}).trim().split('\n')){
    const match=line.trim().match(/^(\d+)\s+(\d+)\s+((?:\S+\s+){4}\S+)\s+(.*)$/);
    if(match)rows.set(Number(match[1]),{pid:Number(match[1]),ppid:Number(match[2]),started:match[3].replace(/\s+/g,' '),command:match[4]});
  }
  return rows;
}
function authorized(socket){
  // Match the connecting socket, not an HTTP-supplied pid or bearer assertion.
  const listing=execFileSync('/usr/sbin/lsof',['-nP',`-iTCP:${socket.remotePort}`,'-sTCP:ESTABLISHED','-Fpn'],{encoding:'utf8'});
  let selected=null,current=null;
  for(const line of listing.split('\n')){
    if(line.startsWith('p'))current=Number(line.slice(1));
    if(line===`n127.0.0.1:${socket.remotePort}->127.0.0.1:${socket.localPort}`)selected=current;
  }
  const table=processTable(),row=table.get(selected);
  if(!row)throw Error('NATIVE_EXEC_PEER_UNKNOWN');
  if(row.pid!==spec.diagnostic_peer.pid||row.started!==spec.diagnostic_peer.started
    ||row.command!==spec.diagnostic_peer.command
    ||!row.command.includes(path.join(repo,'eval_memory_e2e/native/astudio-native-exec-probe.mjs')+' ')
    ||row.command.startsWith('/Applications/AStudio.app/'))
    throw Error('NATIVE_EXEC_PEER_REJECTED');
  return row;
}
server.on('upgrade',(req,socket,head)=>{
  try{
    frozen();
    if(stopping||req.url!==spec.token_path||req.headers.origin)throw Error('NATIVE_EXEC_CHANNEL_REJECTED');
    const peer=authorized(socket);
    wsServer.handleUpgrade(req,socket,head,ws=>wsServer.emit('connection',ws,peer));
  }catch(exc){audit({event:'connection_rejected',reason:exc.message});socket.destroy()}
});
wsServer.on('connection',(ws,peer)=>{
  frozen();
  // The native exec-server is a controller: no arbitrary executable or argv
  // is accepted here. Candidate commands execute in its native sandbox workers.
  const env={PATH:process.env.PATH,HOME:process.env.HOME,USER:process.env.USER,LOGNAME:process.env.LOGNAME,
    SHELL:'/bin/zsh',LANG:'en_US.UTF-8',ACODE_HOME:spec.acode_home,TMPDIR:spec.temp+'/'};
  const child=spawn(spec.kernel,['exec-server','--listen','stdio://'],{env,cwd:spec.runtime,stdio:['pipe','pipe','pipe']});
  const record={ws,child,peer};peers.add(record);
  audit({event:'native_controller_started',pid:child.pid,peer_pid:peer.pid});
  child.stderr.on('data',bytes=>fs.appendFileSync(path.join(root,`exec-server-${child.pid}.stderr`),bytes,{mode:0o600}));
  readline.createInterface({input:child.stdout}).on('line',line=>{if(ws.readyState===1)ws.send(line)});
  ws.on('message',bytes=>{
    let message;
    try{
      frozen(); message=JSON.parse(bytes.toString());
      const result=JSON.parse(execFileSync(spec.python,['-m','eval_memory_e2e.native_sandbox','--transform-spec',specPath],
        {cwd:repo,input:JSON.stringify(message),encoding:'utf8',timeout:15000,maxBuffer:20*1024*1024,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}}));
      if(!result.ok)throw Error(result.reason);
      audit({event:'request',method:message.method??'response',id:message.id??null,
        original_sandbox_sha256:hash(Buffer.from(JSON.stringify(message.params?.sandbox??null))),
        enforced_sandbox_sha256:hash(Buffer.from(JSON.stringify(result.message.params?.sandbox??null)))});
      child.stdin.write(JSON.stringify(result.message)+'\n');
    }catch(exc){
      audit({event:'request_rejected',method:message?.method??null,reason:exc.message});
      if(message?.id!==undefined&&ws.readyState===1)ws.send(JSON.stringify({id:message.id,error:{code:-32602,message:'MANDATORY_NATIVE_POLICY_REJECTED'}}));
      else ws.close(1008,'mandatory native policy rejected');
    }
  });
  ws.on('close',()=>{child.stdin.end()});
  child.on('exit',(code,signal)=>{audit({event:'native_controller_exited',pid:child.pid,code,signal});peers.delete(record);ws.close()});
  child.on('error',exc=>{audit({event:'native_controller_error',reason:exc.message});ws.close()});
});
server.listen(0,'127.0.0.1',()=>{
  const port=server.address().port;
  fs.writeFileSync(path.join(root,'proxy-ready.json'),JSON.stringify({pid:process.pid,port,
    url:`ws://127.0.0.1:${port}${spec.token_path}`,spec_sha256:specHash,at:new Date().toISOString()})+'\n',{mode:0o600,flag:'wx'});
});
process.on('SIGTERM',()=>{stopping=true;server.close();for(const {ws} of peers)ws.close();if(!peers.size)process.exit(0)});
setInterval(()=>{
  const table=processTable();
  const controllers=[...peers].map(({child,peer})=>({identity:table.get(child.pid),peer}));
  fs.writeFileSync(path.join(root,'proxy-status.json'),JSON.stringify({pid:process.pid,stopping,controllers,at:new Date().toISOString()})+'\n',{mode:0o600});
  if(stopping&&!peers.size)process.exit(0);
},500).unref();
