/** Installed native sandbox protocol, synthetic-only; no desktop/model dispatch. */
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
import vm from 'node:vm';
import crypto from 'node:crypto';
import {StringDecoder} from 'node:string_decoder';
import {spawn} from 'node:child_process';
import * as childProcess from 'node:child_process';
import * as asyncHooks from 'node:async_hooks';
import {fileURLToPath} from 'node:url';

const checksum=data=>crypto.createHash('sha256').update(data).digest('hex');
const specPath=path.resolve(process.argv[2]),spec=JSON.parse(fs.readFileSync(specPath));
if(spec.contract!=='workbuddy-native-center-synthetic-probe/v1'||spec.synthetic_only!==true
  ||spec.application_integration_allowed!==false||!spec.uid.startsWith('SYNTHETIC-')
  ||!/^\/tmp\/wcbm-wb-[a-f0-9]+\.sock$/.test(spec.socket))throw Error('SYNTHETIC_SPEC_REQUIRED');
const root=path.dirname(specPath);
if(!root.includes('/debug-workspace/e2e-evaluate/memory-e2e/')||fs.realpathSync(root)!==root
  ||spec.app_home!==root+'/app-home'||spec.tmp!==root+'/tmp')throw Error('SYNTHETIC_ROOT_REQUIRED');
for(const item of [spec.binary,spec.profile,...Object.values(spec.modules)]){
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
let proxy=null;const proxySockets=new Set();
if(spec.profile_proxy){
  const socketPath=spec.profile_proxy.socket;
  if(!/^\/tmp\/wcbm-wb-proxy-[a-f0-9]+\.sock$/.test(socketPath)||fs.existsSync(socketPath))
    throw Error('FRESH_SYNTHETIC_PROXY_SOCKET_REQUIRED');
  const denied=[root+'/synthetic-non-target',root+'/native-private',...spec.profile_proxy.real_non_target_literals];
  if(denied.some(p=>typeof p!=='string'||!p.startsWith('/Users/')||/[\n\0]/.test(p)))throw Error('PROXY_DENY_PATH');
  result.profile_proxy={socket:socketPath,requests:[],audits:[],application_admitted:false};
  proxy=net.createServer(front=>{
    const upstream=net.createConnection(spec.socket);proxySockets.add(front);proxySockets.add(upstream);
    let input='',output='',composedRevision=null;const pending=new Map();
    front.on('data',bytes=>{
      input+=bytes.toString('utf8');let at;
      while((at=input.indexOf('\n'))>=0){const line=input.slice(0,at);input=input.slice(at+1);if(!line.trim())continue;
        try{const message=JSON.parse(line);if(message.uid!==spec.uid)throw Error('SYNTHETIC_UID_ONLY');
          pending.set(message.messageId,message.command);result.profile_proxy.requests.push({command:message.command,sessionId:message.sessionId??null});upstream.write(line+'\n');
        }catch(error){result.profile_proxy.error=String(error.message);front.destroy();upstream.destroy()}
      }
    });
    upstream.on('data',bytes=>{
      output+=bytes.toString('utf8');let at;
      while((at=output.indexOf('\n'))>=0){let line=output.slice(0,at);output=output.slice(at+1);if(!line.trim())continue;
        try{const message=JSON.parse(line),command=pending.get(message.messageId);pending.delete(message.messageId);
          if(command===protocol.SANDBOX_RULES_COMMANDS.FETCH_PROFILE&&message.success===true){
            const original=message.data.profile;
            if(message.data.upToDate===true&&!original){
              if(composedRevision===null||message.data.serverRevision!==composedRevision)
                throw Error('UNBOUND_CACHED_NATIVE_PROFILE');
              result.profile_proxy.cached_profiles_verified=(result.profile_proxy.cached_profiles_verified??0)+1;
              front.write(line+'\n');continue;
            }
            const rules=JSON.parse(original);
            if(!Array.isArray(rules)||rules.some(x=>typeof x!=='string'))throw Error('NATIVE_PROFILE_SHAPE');
            const escaped=rules.some(x=>x.includes('\\"'));
            const extra=denied.map(p=>'(deny file-read* file-write* (subpath '+JSON.stringify(p)+'))')
              .map(x=>escaped?x.replaceAll('"','\\"'):x);
            const end=original.lastIndexOf(']');if(end<0)throw Error('NATIVE_PROFILE_END');
            message.data.profile=original.slice(0,end)+(rules.length?',':'')+extra.map(x=>JSON.stringify(x)).join(',')+original.slice(end);
            message.data.execParams.deniedReadPaths=[...new Set([...(message.data.execParams.deniedReadPaths??[]),...denied.map(p=>p+'/**')])];
            result.profile_proxy.audits.push({original_profile:original,combined_profile:message.data.profile,
              original_native_fragments_preserved:JSON.stringify(JSON.parse(message.data.profile).slice(0,rules.length))===JSON.stringify(rules),
              mandatory_denies:denied,controller_grants_appended:false});
            composedRevision=message.data.serverRevision;
            line=JSON.stringify(message);
          }
          front.write(line+'\n');
        }catch(error){result.profile_proxy.error=String(error.message);front.destroy();upstream.destroy()}
      }
    });
    for(const s of [front,upstream]){
      s.on('error',error=>{result.profile_proxy.last_transport_error=String(error.message);front.destroy();upstream.destroy()});
      s.on('close',()=>{proxySockets.delete(s);front.destroy();upstream.destroy()});
    }
  });
  await new Promise((ok,no)=>{proxy.once('error',no);proxy.listen(socketPath,ok)});fs.chmodSync(socketPath,0o600);
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
  for(const s of proxySockets)s.destroy();if(proxy)await new Promise(ok=>proxy.close(ok));
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
        &&!result.profile_proxy.error&&result.profile_proxy.audits.length>0
        &&result.profile_proxy.audits.every(a=>a.original_native_fragments_preserved&&!a.controller_grants_appended)
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
