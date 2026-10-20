/** Installed native sandbox protocol, synthetic-only; no desktop/model dispatch. */
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
import vm from 'node:vm';
import crypto from 'node:crypto';
import {StringDecoder} from 'node:string_decoder';
import {spawn,execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {startNativeProfileProxy} from '../../eval_memory_e2e/native/workbuddy-native-policy.mjs';
import * as childProcess from 'node:child_process';
import * as asyncHooks from 'node:async_hooks';
import {fileURLToPath} from 'node:url';

const checksum=data=>crypto.createHash('sha256').update(data).digest('hex');
const specPath=path.resolve(process.argv[2]),spec=JSON.parse(fs.readFileSync(specPath));
if(spec.contract!=='workbuddy-native-center-synthetic-probe/v2'||spec.synthetic_only!==true
  ||spec.application_integration_allowed!==false||!spec.uid.startsWith('SYNTHETIC-')
  ||!/^\/tmp\/wcbm-wb-[a-f0-9]+\.sock$/.test(spec.socket))throw Error('SYNTHETIC_SPEC_REQUIRED');
const root=path.dirname(specPath);
if(!root.includes('/debug-workspace/e2e-evaluate/memory-e2e/')||fs.realpathSync(root)!==root
  ||spec.app_home!==root+'/app-home'||spec.tmp!==root+'/tmp')throw Error('SYNTHETIC_ROOT_REQUIRED');
for(const item of [spec.binary,spec.profile,...Object.values(spec.modules),...(spec.profile_proxy?[spec.peer_addon,spec.policy_module]:[])]){
  if(fs.realpathSync(item.path)!==item.path||checksum(fs.readFileSync(item.path))!==item.sha256)
    throw Error('FROZEN_SOURCE_DRIFT');
}
if(fs.existsSync(spec.socket))throw Error('FRESH_SOCKET_REQUIRED');
const ownSource=fs.readFileSync(fileURLToPath(import.meta.url));
fs.writeFileSync(root+'/probe-source.mjs',ownSource,{flag:'wx',mode:0o600});
const cache=new Map();
const builtins=new Map([[35317,childProcess],[91943,fsp],[69278,net],[13193,{StringDecoder}]]);
builtins.set(16698,asyncHooks);builtins.set(77030,net);
function load(id){
  if(builtins.has(id))return builtins.get(id);
  if(cache.has(id))return cache.get(id);
  const source=spec.modules[id];if(!source)throw Error('UNEXPECTED_NATIVE_SDK_IMPORT_'+id);
  const exports={};cache.set(id,exports);
  vm.runInNewContext(fs.readFileSync(source.path,'utf8'),{process,Buffer,console,setTimeout,clearTimeout,
    setInterval,clearInterval,setImmediate,clearImmediate},
    {filename:source.path,timeout:1000})(null,exports,load);
  return exports;
}
const sdk=load(34094),protocol=load(65649);
const config={appHome:spec.app_home,ipcAddress:spec.socket,cipher:{detectMaxFileSizeBytes:1048576}};
const out=fs.openSync(root+'/center.stdout','wx',0o600),err=fs.openSync(root+'/center.stderr','wx',0o600);
const child=spawn('/usr/bin/sandbox-exec',['-f',spec.profile.path,spec.binary.path,'--config',JSON.stringify(config),'--app_home',spec.app_home],
  {cwd:spec.app_home,env:{PATH:process.env.PATH,HOME:spec.os_home,USER:process.env.USER,
    LOGNAME:process.env.LOGNAME,LANG:'en_US.UTF-8',TMPDIR:spec.tmp+'/',
    SANDBOX_CENTER_IPC_ADDRESS:spec.socket,SANDBOX_CENTER_UID:spec.uid,
    WORKBUDDY_CONFIG_DIR:spec.app_home,CODEBUDDY_CONFIG_DIR:spec.app_home},stdio:['ignore',out,err]});
fs.closeSync(out);fs.closeSync(err);
const result={contract:spec.contract,at:new Date().toISOString(),pid:child.pid,socket:spec.socket,
  source_sha256:checksum(ownSource),synthetic_only:true,model_prompts:0,real_memory_reads:0,
  requests:[],application_admitted:false};
fs.writeFileSync(root+'/running.json',JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
let exit=null;child.on('exit',(code,signal)=>{exit={code,signal}});
let proxy=null,expectedCli=null;
if(spec.profile_proxy){
  const socketPath=spec.profile_proxy.socket;
  const denied=[root+'/synthetic-non-target',root+'/native-private',...spec.profile_proxy.real_non_target_literals];
  const kernelPeer=createRequire(import.meta.url)(spec.peer_addon.path).peer;
  result.profile_proxy={socket:socketPath,requests:[],audits:[],rejections:[],application_admitted:false};
  proxy=await startNativeProfileProxy({socketPath,upstreamPath:spec.socket,uid:spec.uid,deniedRoots:denied,
    assertFrozen(){
      for(const item of [spec.profile,spec.peer_addon,spec.policy_module])
        if(checksum(fs.readFileSync(item.path))!==item.sha256)throw Error('POLICY_SOURCE_DRIFT');
    },
    authorize(socket){
      const peer=kernelPeer(socket._handle.fd);
      if(!expectedCli||peer.pid!==expectedCli.pid||peer.uid!==process.getuid())throw Error('UNAUTHORIZED_OS_PEER');
      const row=execFileSync('/bin/ps',['-p',String(peer.pid),'-o','ppid=,lstart=,command='],{encoding:'utf8'}).trim();
      if(!row.startsWith(String(process.pid)+' ')||!row.includes(spec.native_executor.path+' --config '))
        throw Error('NATIVE_EXECUTOR_IDENTITY');
      if(expectedCli.row&&expectedCli.row!==row)throw Error('NATIVE_EXECUTOR_IDENTITY_DRIFT');
      expectedCli.row=row;
      return {...peer,process_identity:row};
    },
    audit(event){
      if(event.event==='request')result.profile_proxy.requests.push(event);
      else if(event.event==='connection_rejected')result.profile_proxy.rejections.push(event);
      else result.profile_proxy.audits.push(event);
      if(event.event==='cached_profile_verified')result.profile_proxy.cached_profiles_verified=(result.profile_proxy.cached_profiles_verified??0)+1;
    }});
  // A controller process with the correct synthetic UID still has the wrong OS PID.
  result.profile_proxy.unauthorized_peer={pid:process.pid,attempted:true};
  await new Promise((ok,no)=>{const socket=net.createConnection(socketPath),timer=setTimeout(()=>{socket.destroy();no(Error('UNAUTHORIZED_PEER_NOT_CLOSED'))},2000);
    socket.on('connect',()=>socket.write(JSON.stringify({messageId:'spoofed',command:'sandbox.rules.get_rules',uid:spec.uid,data:{_client:{pid:process.pid}}})+'\n'));
    socket.on('data',()=>{clearTimeout(timer);socket.destroy();no(Error('UNAUTHORIZED_PEER_RECEIVED_DATA'))});
    socket.on('error',()=>{});socket.on('close',()=>{clearTimeout(timer);ok()});
  });
}
const client=sdk.createSandboxCenterClient({clientRole:'memory-e2e-synthetic-probe',startMode:'connect-only',
  resolveRuntimeContext:()=>({appHome:spec.app_home,uid:spec.uid,socketPath:spec.socket,executablePath:spec.binary.path})});
const session='SYNTHETIC-memory-e2e';
async function request(command,data={}){
  try{
    const value=await client.request(command,data,{sessionId:session,timeoutMs:5000});
    result.requests.push({command,ok:true,value});return value;
  }catch(error){result.requests.push({command,ok:false,error:String(error.message)});return undefined}
}
try{
  for(let i=0;i<100&&!fs.existsSync(spec.socket)&&!exit;i++)await new Promise(ok=>setTimeout(ok,50));
  if(exit)throw Error('NATIVE_CENTER_EXITED_'+JSON.stringify(exit));
  await request(protocol.SANDBOX_RULES_COMMANDS.GET_RULES);
  for(const platform of ['darwin','macos'])
    await request(protocol.SANDBOX_RULES_COMMANDS.FETCH_PROFILE,{platform,sessionId:session});
  await request(protocol.SANDBOX_RULES_COMMANDS.SET_FILE_RULES,{category:'global',rules:[
    {path:'**',action:'read=allow|write=allow|delete=allow',isDirectory:false},
    {path:root+'/synthetic-non-target',action:'read=deny|write=deny|delete=deny',isDirectory:true},
    ...(spec.native_executor?[{path:root+'/native-private',action:'read=deny|write=deny|delete=deny',isDirectory:true}]:[]),
  ]});
  for(const platform of ['darwin','macos'])
    await request(protocol.SANDBOX_RULES_COMMANDS.FETCH_PROFILE,{platform,sessionId:session});
  await request(protocol.SANDBOX_RULES_COMMANDS.GET_RULES);
  await request(protocol.SANDBOX_MONITOR_COMMANDS.QUERY_SESSION_METRICS,{sessionId:session});
  if(spec.native_executor){
    const binary=spec.native_executor;
    if(fs.realpathSync(binary.path)!==binary.path||checksum(fs.readFileSync(binary.path))!==binary.sha256)
      throw Error('NATIVE_EXECUTOR_BINARY_DRIFT');
    const address='wcbm-wb-cli-'+crypto.randomBytes(8).toString('hex');
    const cliOut=fs.openSync(root+'/cli.stdout','wx',0o600),cliErr=fs.openSync(root+'/cli.stderr','wx',0o600);
    const nativeArgs=['--config',JSON.stringify({extraPath:[],enableGlobalProjection:false,ipcAddress:address}),
      '--rule_decision','center','--uid',spec.uid,'--app_home',spec.app_home];
    const outer=spec.native_executor_inside_outer!==false;
    const cli=spawn(outer?'/usr/bin/sandbox-exec':binary.path,
      outer?['-f',spec.profile.path,binary.path,...nativeArgs]:nativeArgs,
      {cwd:spec.app_home,env:{PATH:process.env.PATH,HOME:spec.os_home,USER:process.env.USER,
        LOGNAME:process.env.LOGNAME,LANG:'en_US.UTF-8',TMPDIR:spec.tmp+'/',
        SANDBOX_CENTER_IPC_ADDRESS:spec.profile_proxy?.socket??spec.socket,SANDBOX_CENTER_UID:spec.uid,
        WORKBUDDY_CONFIG_DIR:spec.app_home,CODEBUDDY_CONFIG_DIR:spec.app_home},stdio:['ignore',cliOut,cliErr]});
    expectedCli={pid:cli.pid};
    fs.closeSync(cliOut);fs.closeSync(cliErr);let cliExit=null;cli.on('exit',(code,signal)=>{cliExit={code,signal}});
    const cliSdk=load(84283),commands=load(68331).SANDBOX_COMMANDS;
    const cliClient=cliSdk.createSandboxCliClient();const notifications=[];
    cliClient.addReverseListener({commands:[commands.PROCESS_OUTPUT,commands.PROCESS_EXIT,commands.REPORT_EVENT]},message=>{notifications.push(message)});
    result.native_executor={pid:cli.pid,address,inside_outer:outer,
      role:outer?'nested_sandbox_counterexample':'trusted_native_executor_synthetic_baseline',tests:[],notifications};
    try{
      await cliClient.connect({address,connectTimeoutMs:5000,requestTimeoutMs:5000});
      await cliClient.sendRequest(session,commands.OPEN_SESSION,{workingDir:spec.app_home});
      const cases=['control','synthetic-non-target','native-private',...(spec.profile_proxy?['alias-read','write-denied']:[])];
      if(spec.profile_proxy){fs.symlinkSync(root+'/synthetic-non-target',spec.app_home+'/protected-alias','dir')}
      for(const name of cases){
        const target=name==='control'?spec.app_home+'/control.txt':name==='alias-read'?spec.app_home+'/protected-alias/fact.txt':
          name==='write-denied'?root+'/synthetic-non-target/denied-write':root+'/'+name+'/fact.txt';
        const executable=name==='write-denied'?'/usr/bin/touch':'/bin/cat';
        const args=[target];
        const started=await cliClient.sendRequest(session,commands.RUN_EXECUTABLE,
          {executable,args,cwdDir:spec.app_home,timeoutMs:3000,
            executionMode:'sandbox',stdoutMode:'pipe',stdinMode:'pipe',killProcessTree:true,
            env:{PATH:'/usr/bin:/bin',LANG:'en_US.UTF-8',TMPDIR:spec.tmp+'/'}});
        for(let i=0;i<100&&!notifications.some(x=>x.command===commands.PROCESS_EXIT&&x.data?.processId===started.processId);i++)
          await new Promise(ok=>setTimeout(ok,50));
        result.native_executor.tests.push({name,target,executable,args,started,
          events:notifications.filter(x=>x.data?.processId===started.processId)});
      }
    }catch(error){result.native_executor.error=String(error.stack||error)}
    finally{
      try{await cliClient.sendRequest(session,commands.CLOSE_SESSION,{})}catch(error){result.native_executor.close_error=String(error.message)}
      await cliClient.disconnect();
      if(!cliExit)cli.kill('SIGTERM');
      for(let i=0;i<100&&!cliExit;i++)await new Promise(ok=>setTimeout(ok,100));
      result.native_executor.exit=cliExit;
    }
  }
  result.probe_completed=true;
}catch(error){result.error=String(error.stack||error)}
finally{
  await request(protocol.SANDBOX_SESSION_COMMANDS.CLOSE_SESSION,{sessionId:session});
  await request(protocol.SANDBOX_CENTER_LIFECYCLE_COMMANDS.SHUTDOWN);
  client.close();
  if(proxy)await proxy.close();
  for(let i=0;i<100&&!exit;i++)await new Promise(ok=>setTimeout(ok,100));
  result.exit=exit;result.native_shutdown_verified=exit?.code===0;
  if(result.native_executor){
    const samples=result.native_executor.tests.map(t=>({name:t.name,
      exit_codes:t.events.filter(e=>e.command==='ProcessExit').map(e=>e.data.exitCode),
      output:t.events.filter(e=>e.command==='ProcessOutput').map(e=>Buffer.from(e.data.data,'base64').toString('utf8')).join('')}));
    result.native_executor.samples=samples;
    if(spec.profile_proxy){
      result.synthetic_data_worker_boundary_pass=samples.length===5&&samples.every(t=>t.name==='control'
        ?t.exit_codes.length===1&&t.exit_codes[0]===0&&t.output.includes('SYNTHETIC-ALLOW')
        :t.exit_codes.length===1&&t.exit_codes[0]!==0&&t.output.includes('Operation not permitted'))
        &&result.profile_proxy.rejections.length===1&&result.profile_proxy.rejections[0].reason==='UNAUTHORIZED_OS_PEER'
        &&result.profile_proxy.audits.some(a=>a.event==='connection_authorized')
        &&result.profile_proxy.audits.filter(a=>a.event==='profile_composed').length>0
        &&result.profile_proxy.audits.filter(a=>a.event==='profile_composed').every(a=>a.original_native_fragments_preserved&&!a.controller_grants_appended)
        &&result.profile_proxy.cached_profiles_verified>0
        &&!fs.existsSync(root+'/synthetic-non-target/denied-write');
      if(!result.synthetic_data_worker_boundary_pass)process.exitCode=2;
    }
  }
  result.at_end=new Date().toISOString();
  fs.writeFileSync(root+'/result.json',JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
  console.log(JSON.stringify({pid:child.pid,requests:result.requests.map(x=>({command:x.command,ok:x.ok,error:x.error,
    value_type:x.ok?typeof x.value:undefined})),exit,result:root+'/result.json',
    synthetic_data_worker_boundary_pass:result.synthetic_data_worker_boundary_pass,application_admitted:false}));
  if(!result.probe_completed||!result.native_shutdown_verified)process.exitCode=2;
}
