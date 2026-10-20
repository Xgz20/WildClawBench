/* Trusted native-service supervisor. Data workers retain native sandboxing;
 * only immutable native service binaries can be launched by this control API.
 */
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import crypto from 'node:crypto';
import {spawn,execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {StringDecoder} from 'node:string_decoder';
import {startNativeProfileProxy} from './workbuddy-native-policy.mjs';

const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const check=(ok,reason)=>{if(!ok)throw Error(reason)};
const specPath=path.resolve(process.argv[2]),root=path.dirname(specPath),specBytes=fs.readFileSync(specPath),spec=JSON.parse(specBytes);
check(spec.contract==='workbuddy-owned-executor-gateway/v1'&&spec.application_admitted===false
  &&['synthetic-launch','workbuddy-owned-session'].includes(spec.mode),'WB_GATEWAY_SPEC');
check(root.includes('/debug-workspace/e2e-evaluate/memory-e2e/')&&fs.realpathSync(root)===root,'WB_GATEWAY_ROOT');
check(spec.app_home===root+'/app-home'&&spec.temp===root+'/tmp','WB_GATEWAY_HOME');
if(spec.mode==='workbuddy-owned-session')check(spec.memory_unit,'WB_GATEWAY_MEMORY_UNIT_REQUIRED');
if(spec.memory_unit){
  for(const value of [...spec.memory_unit.allowedPaths,...spec.memory_unit.readLiterals])
    check(fs.realpathSync(value)===value,'WB_GATEWAY_UNIT_CANONICAL_PATH');
  check(spec.memory_unit.allowedPaths.includes(spec.app_home)&&spec.memory_unit.allowedPaths.includes(spec.temp)
    &&spec.memory_unit.allowedPaths.every(p=>[spec.app_home,spec.temp,root+'/candidate'].includes(p)),'WB_GATEWAY_UNIT_BINDING');
}
check(/^\/tmp\/wcbm-wb-control-[a-f0-9]+\.sock$/.test(spec.control_socket)
  &&!fs.existsSync(spec.control_socket),'WB_GATEWAY_SOCKET');
const log=event=>fs.appendFileSync(root+'/gateway-events.jsonl',JSON.stringify({at:new Date().toISOString(),...event})+'\n',{mode:0o600});
function frozen(){
  check(sha(fs.readFileSync(specPath))===sha(specBytes),'WB_GATEWAY_SPEC_DRIFT');
  for(const item of [spec.native_cli,spec.peer_addon,...Object.values(spec.sources)])
    check(fs.realpathSync(item.path)===item.path&&sha(fs.readFileSync(item.path))===item.sha256,'WB_GATEWAY_SOURCE_DRIFT');
  if(spec.memory_unit)for(const value of [...spec.memory_unit.allowedPaths,...spec.memory_unit.readLiterals])
    check(fs.realpathSync(value)===value,'WB_GATEWAY_UNIT_CANONICAL_DRIFT');
}
function processRow(pid){
  try{
    const raw=execFileSync('/bin/ps',['-p',String(pid),'-o','ppid=,lstart=,command='],{encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim();
    const parsed=raw.match(/^(\d+)\s+((?:\S+\s+){4}\S+)\s+(.*)$/);
    return parsed?{pid,ppid:Number(parsed[1]),started:parsed[2].replace(/\s+/g,' '),command:parsed[3]}:null;
  }catch{return null}
}
function same(row,bound){return !!row&&row.pid===bound.pid&&row.ppid===bound.ppid&&row.started===bound.started&&row.command===bound.command}
frozen();
const kernelPeer=createRequire(import.meta.url)(spec.peer_addon.path).peer;
const jobs=new Map(),sockets=new Set();let stopping=false,backend=null;
function backendIdentity(pid){
  const row=processRow(pid);check(row,'WB_GATEWAY_BACKEND_MISSING');
  if(backend){check(same(row,backend),'WB_GATEWAY_BACKEND_DRIFT');return row}
  if(spec.mode==='synthetic-launch'){
    if(spec.test_backend)check(same(row,spec.test_backend),'WB_GATEWAY_TEST_BACKEND');
    else check(same(processRow(spec.test_parent.pid),spec.test_parent)&&row.ppid===spec.test_parent.pid
      &&row.command===spec.backend_command,'WB_GATEWAY_TEST_BACKEND');
  }
  else {
    const main=processRow(spec.main.pid);check(same(main,spec.main),'WB_GATEWAY_MAIN_DRIFT');
    check(row.ppid===main.pid&&row.command===spec.backend_command,'WB_GATEWAY_BACKEND_IDENTITY');
  }
  backend=row;return row;
}
function helperPeer(socket,action){
  const peer=kernelPeer(socket._handle.fd),row=processRow(peer.pid);
  check(peer.uid===process.getuid()&&row,'WB_GATEWAY_OS_PEER');
  check(row.command===[spec.node,spec.sources.client.path,action,specPath].join(' '),'WB_GATEWAY_HELPER_COMMAND');
  backendIdentity(row.ppid);return peer;
}
function nativePeer(socket,job){
  const peer=kernelPeer(socket._handle.fd);
  check(peer.uid===process.getuid()&&peer.pid===job.child.pid&&same(processRow(peer.pid),job.identity),'WB_GATEWAY_NATIVE_PEER');
  return peer;
}
const allowedCommands=new Set(['Ping','OpenSession','CloseSession','DeleteSession','RunExecutable','GetStatistics',
  'ReportBlockChoice','ProcessWrite','ProcessSendKey','ProcessResize','ProcessKill','ProcessIsAlive','RecordStatistics','AppendUserChoice']);
async function executorProxy(publicPath,privatePath,job){
  check(!fs.existsSync(publicPath),'WB_GATEWAY_EXEC_SOCKET_EXISTS');
  const server=net.createServer(front=>{
    let upstream;const reverse=new Set();
    const reject=error=>{log({event:'executor_channel_rejected',pid:job.child.pid,reason:error.message});front.destroy();upstream?.destroy()};
    try{frozen();const peer=kernelPeer(front._handle.fd);check(peer.uid===process.getuid(),'WB_GATEWAY_EXEC_UID');backendIdentity(peer.pid);
      upstream=net.createConnection(privatePath);sockets.add(front);sockets.add(upstream);
    }catch(error){reject(error);return}
    function lines(socket,consume){
      const decoder=new StringDecoder('utf8');let pending='';
      socket.on('data',bytes=>{try{pending+=decoder.write(bytes);check(Buffer.byteLength(pending)<=16*1024*1024,'WB_GATEWAY_EXEC_SIZE');let at;
        while((at=pending.indexOf('\n'))>=0){const raw=pending.slice(0,at);pending=pending.slice(at+1);if(raw.trim()){frozen();consume(raw,JSON.parse(raw))}}}
        catch(error){reject(error)}});
    }
    lines(front,(raw,message)=>{
      if(message.command){
        check(allowedCommands.has(message.command),'WB_GATEWAY_EXEC_COMMAND');
        if(message.command==='RunExecutable')check(message.data?.executionMode==='sandbox','WB_GATEWAY_EXEC_NATIVE_SANDBOX_REQUIRED');
        check(typeof message.sessionId==='string'&&message.sessionId.length>0,'WB_GATEWAY_EXEC_SESSION');
        log({event:'native_request',command:message.command,pid:job.child.pid,session_id:message.sessionId,
          ...(message.command==='RunExecutable'?{execution_mode:message.data.executionMode}: {})});
      }else{check(reverse.delete(message.messageId),'WB_GATEWAY_EXEC_UNBOUND_REVERSE_RESPONSE')}
      upstream.write(raw+'\n');
    });
    lines(upstream,(raw,message)=>{if(message.command&&message.messageId)reverse.add(message.messageId);front.write(raw+'\n')});
    for(const socket of [front,upstream]){
      socket.on('error',reject);socket.on('end',()=>socket===front?upstream.end():front.end());
      socket.on('close',()=>{sockets.delete(socket);front.destroy();upstream.destroy()});
    }
  });
  await new Promise((ok,no)=>{server.once('error',no);server.listen(publicPath,ok)});fs.chmodSync(publicPath,0o600);
  return server;
}
async function launch(request){
  check(!stopping&&request.command===spec.native_cli.path&&Array.isArray(request.args),'WB_GATEWAY_NATIVE_COMMAND');
  const args=request.args;
  check(args.length===8&&args[0]==='--config'&&args[2]==='--rule_decision'&&args[3]==='center'
    &&args[4]==='--uid'&&args[5]===spec.account_uid&&args[6]==='--app_home'&&args[7]===spec.app_home,'WB_GATEWAY_NATIVE_ARGS');
  const original=JSON.parse(args[1]);
  check(original.enableGlobalProjection===false&&Array.isArray(original.extraPath)
    &&original.extraPath.every(p=>typeof p==='string'&&p.startsWith('/'))
    &&Object.keys(original).sort().join(',')==='enableGlobalProjection,extraPath,ipcAddress'
    &&/^(WorkBuddy_|EditorSdk_|SYNTHETIC_)[a-zA-Z0-9_-]+$/.test(original.ipcAddress),'WB_GATEWAY_NATIVE_CONFIG');
  check(request.env&&request.env.HOME===spec.os_home&&request.env.SANDBOX_CENTER_UID===spec.account_uid
    &&request.env.SANDBOX_CENTER_IPC_ADDRESS===spec.center_socket,'WB_GATEWAY_NATIVE_ENV');
  check(!request.cwd||[spec.app_home,path.dirname(spec.native_cli.path)].includes(request.cwd),'WB_GATEWAY_NATIVE_CWD');
  check(['ignore','pipe'].includes(request.stderr_mode),'WB_GATEWAY_NATIVE_STDERR');
  const id=crypto.randomBytes(24).toString('hex'),privateAddress='wcbm-wb-worker-'+crypto.randomBytes(8).toString('hex');
  const profileSocket='/tmp/wcbm-wb-profile-'+crypto.randomBytes(8).toString('hex')+'.sock';
  const job={id,watchers:new Set(),exit:null,child:null,identity:null,stderrBacklog:[]};
  job.profile=await startNativeProfileProxy({socketPath:profileSocket,upstreamPath:spec.center_socket,
    uid:spec.account_uid,deniedRoots:spec.denied_roots,memoryUnit:spec.memory_unit??null,assertFrozen:frozen,authorize:socket=>nativePeer(socket,job),
    audit:event=>log({...event,event:'profile_'+event.event,job:id})});
  const out=fs.openSync(root+'/'+id+'.stdout','wx',0o600),err=fs.openSync(root+'/'+id+'.stderr','wx',0o600);
  const changed=[...args];changed[1]=JSON.stringify({...original,ipcAddress:privateAddress});
  const env={...request.env,SANDBOX_CENTER_IPC_ADDRESS:profileSocket};
  job.child=spawn(spec.native_cli.path,changed,{cwd:request.cwd??spec.app_home,env,stdio:['ignore',out,request.stderr_mode==='pipe'?'pipe':err]});
  fs.closeSync(out);jobs.set(id,job);
  if(request.stderr_mode==='pipe')job.child.stderr.on('data',bytes=>{
    fs.writeSync(err,bytes);
    const event=JSON.stringify({ok:true,pid:job.child.pid,event:'stderr',data:bytes.toString('base64')})+'\n';
    if(job.watchers.size)for(const socket of job.watchers)socket.write(event);else job.stderrBacklog.push(event);
  });
  job.child.on('error',error=>log({event:'native_spawn_error',job:id,reason:error.message}));
  job.child.on('close',async(code,signal)=>{
    fs.closeSync(err);
    job.exit={code,signal};log({event:'native_exit',job:id,pid:job.child.pid,...job.exit});
    for(const socket of job.watchers)socket.end(JSON.stringify({ok:true,pid:job.child.pid,event:'exit',exit:job.exit})+'\n');
    job.watchers.clear();await job.profile.close();job.executor?.close();
  });
  await new Promise((ok,no)=>{job.child.once('spawn',ok);job.child.once('error',no)});
  job.identity=processRow(job.child.pid);
  check(job.identity?.ppid===process.pid&&job.identity.command.startsWith(spec.native_cli.path+' '),'WB_GATEWAY_SPAWN_IDENTITY');
  const privatePath='/tmp/'+privateAddress+'.sock';
  for(let i=0;i<100&&!fs.existsSync(privatePath)&&!job.exit;i++)await new Promise(ok=>setTimeout(ok,50));
  check(!job.exit&&fs.existsSync(privatePath),'WB_GATEWAY_EXEC_NOT_READY');
  job.executor=await executorProxy('/tmp/'+original.ipcAddress+'.sock',privatePath,job);
  log({event:'native_started',job:id,identity:job.identity,original_ipc:original.ipcAddress,private_ipc:privateAddress,
    args_preserved_except_transport:true,execution_mode_rewriting:false});
  return {ok:true,pid:job.child.pid,job:id};
}
const server=net.createServer(socket=>{
  sockets.add(socket);let input='',received=false;
  socket.setTimeout(15000,()=>socket.destroy());
  socket.on('data',async bytes=>{
    try{
      check(!received,'WB_GATEWAY_ONE_CONTROL_REQUEST');input+=bytes.toString('utf8');check(input.length<=1024*1024,'WB_GATEWAY_CONTROL_SIZE');
      const end=input.indexOf('\n');if(end<0)return;received=true;check(end===input.length-1,'WB_GATEWAY_CONTROL_TRAILING');
      frozen();const request=JSON.parse(input);check(['spawn','watch','kill'].includes(request.action),'WB_GATEWAY_CONTROL_ACTION');
      const peer=helperPeer(socket,request.action);log({event:'control_authenticated',action:request.action,peer});
      if(request.action==='spawn'){socket.end(JSON.stringify(await launch(request))+'\n');return}
      const job=jobs.get(request.job);check(job,'WB_GATEWAY_JOB_UNKNOWN');
      if(request.action==='watch'){
        check(job.watchers.size===0,'WB_GATEWAY_DUPLICATE_WATCHER');
        for(const event of job.stderrBacklog)socket.write(event);job.stderrBacklog.length=0;
        if(job.exit)socket.end(JSON.stringify({ok:true,pid:job.child.pid,event:'exit',exit:job.exit})+'\n');
        else {socket.setTimeout(0);job.watchers.add(socket)}
      }else{
        check(['SIGTERM','SIGKILL','SIGINT','SIGHUP'].includes(request.signal),'WB_GATEWAY_SIGNAL');
        check(!job.exit&&same(processRow(job.child.pid),job.identity),'WB_GATEWAY_SIGNAL_IDENTITY');
        const sent=job.child.kill(request.signal);socket.end(JSON.stringify({ok:true,sent})+'\n');
      }
    }catch(error){log({event:'control_rejected',reason:error.message});socket.end(JSON.stringify({ok:false,error:error.message})+'\n')}
  });
  socket.on('error',error=>log({event:'control_transport_error',reason:error.message}));
  socket.on('close',()=>{sockets.delete(socket);for(const job of jobs.values())job.watchers.delete(socket)});
});
await new Promise((ok,no)=>{server.once('error',no);server.listen(spec.control_socket,ok)});fs.chmodSync(spec.control_socket,0o600);
fs.writeFileSync(root+'/gateway-ready.json',JSON.stringify({pid:process.pid,identity:processRow(process.pid),spec_sha256:sha(specBytes),application_admitted:false})+'\n',{flag:'wx',mode:0o600});
process.on('SIGTERM',()=>{
  if([...jobs.values()].some(job=>!job.exit)){log({event:'shutdown_refused_native_service_alive'});return}
  stopping=true;for(const socket of sockets)socket.destroy();server.close(()=>process.exit(0));
});
