/* Controller transport for the separately built native execution service.
 * JSON-RPC payloads and native permission intent are forwarded byte-for-byte.
 * Immutable mandatory denies are applied by Rust after native SBPL generation.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import readline from 'node:readline';
import {createRequire} from 'node:module';
import {spawn,execFileSync} from 'node:child_process';

const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const specPath=path.resolve(process.argv[2]),root=path.dirname(specPath),specBytes=fs.readFileSync(specPath),spec=JSON.parse(specBytes);
if(spec.contract!=='astudio-composed-native-executor/v2'||!['synthetic-admission','astudio-owned-session'].includes(spec.mode))throw Error('NATIVE_BROKER_SPEC');
const require=createRequire(import.meta.url),{wsServer:WebSocketServer}=require(spec.ws_bundle);
const audit=row=>fs.appendFileSync(path.join(root,'broker-events.jsonl'),JSON.stringify({at:new Date().toISOString(),...row})+'\n',{mode:0o600});
function frozen(){
  if(hash(fs.readFileSync(specPath))!==hash(specBytes))throw Error('NATIVE_BROKER_SPEC_DRIFT');
  for(const [file,expected] of Object.entries(spec.sources))if(hash(fs.readFileSync(file))!==expected)throw Error('NATIVE_BROKER_SOURCE_DRIFT');
  if(hash(fs.readFileSync(spec.profile))!==spec.profile_sha256||hash(fs.readFileSync(spec.executor))!==spec.executor_sha256)throw Error('NATIVE_BROKER_BINARY_OR_PROFILE_DRIFT');
}
function table(){
  const rows=new Map();
  for(const raw of execFileSync('/bin/ps',['-axo','pid=,ppid=,lstart=,args='],{encoding:'utf8'}).trim().split('\n')){
    const m=raw.trim().match(/^(\d+)\s+(\d+)\s+((?:\S+\s+){4}\S+)\s+(.*)$/);
    if(m)rows.set(Number(m[1]),{pid:Number(m[1]),ppid:Number(m[2]),started_at:m[3].replace(/\s+/g,' '),command:m[4]});
  }
  return rows;
}
function peer(socket){
  const listing=execFileSync('/usr/sbin/lsof',['-nP',`-iTCP:${socket.remotePort}`,'-sTCP:ESTABLISHED','-Fpn'],{encoding:'utf8',timeout:5000});
  let pid=null,current=null;
  for(const line of listing.split('\n')){
    if(line.startsWith('p'))current=Number(line.slice(1));
    if(line===`n127.0.0.1:${socket.remotePort}->127.0.0.1:${socket.localPort}`)pid=current;
  }
  const rows=table(),row=rows.get(pid);
  if(!row)throw Error('NATIVE_BROKER_PEER_UNKNOWN');
  if(spec.mode==='synthetic-admission'){
    if(row.pid!==spec.test_peer.pid||row.started_at!==spec.test_peer.started_at||row.command!==spec.test_peer.command
      ||row.command.startsWith('/Applications/'))throw Error('NATIVE_BROKER_TEST_PEER_REJECTED');
  }else{
    const main=rows.get(spec.main.pid);
    if(!main||main.started_at!==spec.main.started_at||main.command!==spec.main.command
      ||!row.command.startsWith(spec.application_kernel.path+' ')||!row.command.includes('app-server')
      ||hash(fs.readFileSync(spec.application_kernel.path))!==spec.application_kernel.sha256)throw Error('NATIVE_BROKER_APP_PEER_REJECTED');
    let ancestor=row,seen=new Set();
    while(ancestor&&ancestor.pid!==main.pid&&!seen.has(ancestor.pid)){seen.add(ancestor.pid);ancestor=rows.get(ancestor.ppid)}
    if(ancestor?.pid!==main.pid)throw Error('NATIVE_BROKER_APP_TREE_REJECTED');
  }
  return row;
}
frozen();
const sessions=new Set(),server=http.createServer((req,res)=>{res.writeHead(404);res.end()});
const websockets=new WebSocketServer({noServer:true,maxPayload:16*1024*1024,perMessageDeflate:false});
let stopping=false;
server.on('upgrade',(req,socket,head)=>{
  try{
    frozen();
    if(stopping||req.url!==spec.token_path||req.headers.origin)throw Error('NATIVE_BROKER_CHANNEL_REJECTED');
    const owner=peer(socket);websockets.handleUpgrade(req,socket,head,ws=>websockets.emit('connection',ws,owner));
  }catch(error){audit({event:'connection_rejected',reason:error.message});socket.destroy()}
});
websockets.on('connection',(ws,owner)=>{
  frozen();
  const env={PATH:spec.path_env,HOME:spec.os_home,USER:process.env.USER,LOGNAME:process.env.LOGNAME,
    SHELL:'/bin/zsh',LANG:'en_US.UTF-8',ACODE_HOME:spec.acode_home,TMPDIR:spec.temp+'/'};
  const child=spawn(spec.executor,['--deny-profile',spec.profile,'--audit-dir',spec.policy_audit_dir],
    {env,cwd:spec.runtime,stdio:['pipe','pipe','pipe']});
  const session={ws,child,owner,pending:new Map(),processes:new Set(),handles:new Set(),http:new Set()};sessions.add(session);
  audit({event:'native_controller_started',pid:child.pid,peer:owner});
  child.stderr.on('data',bytes=>fs.appendFileSync(path.join(root,`controller-${child.pid}.stderr`),bytes,{mode:0o600}));
  readline.createInterface({input:child.stdout}).on('line',line=>{
    try{
      const message=JSON.parse(line),request=session.pending.get(String(message.id));
      if(request){
        session.pending.delete(String(message.id));
        if(!message.error&&request.method==='process/start')session.processes.add(request.processId);
        if(!message.error&&request.method==='fs/open')session.handles.add(request.handleId);
        if(!message.error&&request.method==='fs/close')session.handles.delete(request.handleId);
        if(message.error&&request.httpId)session.http.delete(request.httpId);
      }
      if(message.method==='process/closed')session.processes.delete(message.params?.processId);
      if(message.method==='http/request/bodyDelta'&&message.params?.done)session.http.delete(message.params.requestId);
    }catch(error){audit({event:'invalid_native_response',pid:child.pid,reason:error.message});ws.close(1011,'invalid native response');return}
    if(ws.readyState===1)ws.send(line);
  });
  ws.on('message',bytes=>{
    try{
      frozen();const raw=bytes.toString(),message=JSON.parse(raw);
      if(Array.isArray(message))throw Error('NATIVE_BROKER_BATCH_UNSUPPORTED');
      if(message.method&&message.id!==undefined){
        const httpId=message.method==='http/request'&&message.params?.streamResponse?message.params.requestId:null;
        if(httpId)session.http.add(httpId);
        session.pending.set(String(message.id),{method:message.method,processId:message.params?.processId,handleId:message.params?.handleId,httpId});
      }
      audit({event:'request',pid:child.pid,method:message.method??'server-response',id:message.id??null});
      child.stdin.write(raw+'\n');
    }catch(error){audit({event:'channel_failed_closed',reason:error.message});ws.close(1008,'native controller integrity failed')}
  });
  ws.on('close',()=>child.stdin.end());
  ws.on('error',error=>audit({event:'channel_error',reason:error.message}));
  child.on('exit',(code,signal)=>{audit({event:'native_controller_exited',pid:child.pid,code,signal});sessions.delete(session);ws.close()});
  child.on('error',error=>{audit({event:'native_controller_failed',reason:error.message});sessions.delete(session);ws.close()});
  child.stdin.on('error',error=>{audit({event:'native_stdin_closed',reason:error.code});ws.close()});
});
function status(){
  const rows=table();
  const target=path.join(root,'broker-status.json'),temporary=target+'.new';
  fs.writeFileSync(temporary,JSON.stringify({at:new Date().toISOString(),identity:rows.get(process.pid),mode:spec.mode,stopping,
    sessions:[...sessions].map(s=>({identity:rows.get(s.child.pid),owner:s.owner,pending:s.pending.size,active_processes:[...s.processes],open_handles:[...s.handles],active_http:[...s.http]}))})+'\n',{mode:0o600});
  fs.renameSync(temporary,target);
}
server.listen(0,'127.0.0.1',()=>{
  const port=server.address().port;status();
  fs.writeFileSync(path.join(root,'broker-ready.json'),JSON.stringify({identity:table().get(process.pid),port,url:`ws://127.0.0.1:${port}${spec.token_path}`,spec_sha256:hash(specBytes)})+'\n',{mode:0o600,flag:'wx'});
});
process.on('SIGTERM',()=>{
  status();
  if([...sessions].some(s=>s.pending.size||s.processes.size||s.http.size)){audit({event:'shutdown_refused_active_work'});return}
  stopping=true;server.close();for(const {ws} of sessions)ws.close();if(!sessions.size)process.exit(0);
});
setInterval(()=>{status();if(stopping&&!sessions.size)process.exit(0)},500).unref();
