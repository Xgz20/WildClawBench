/* End-to-end service launch under an outer OS boundary; synthetic only. */
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import net from 'node:net';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {StringDecoder} from 'node:string_decoder';
import * as cp from 'node:child_process';
import * as asyncHooks from 'node:async_hooks';
import {centerCoordinationPaths} from '../../eval_memory_e2e/native/workbuddy-native-policy.mjs';

const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const check=(ok,why)=>{if(!ok)throw Error(why)};
const mode=process.argv[2],specPath=path.resolve(process.argv[3]),root=path.dirname(specPath),spec=JSON.parse(fs.readFileSync(specPath));
check(['orchestrate','backend'].includes(mode)&&spec.contract==='workbuddy-executor-gateway-synthetic/v1'
  &&spec.synthetic_only===true&&spec.account_uid.startsWith('SYNTHETIC-')
  &&root.includes('/debug-workspace/e2e-evaluate/memory-e2e/')&&fs.realpathSync(root)===root,'WB_GATEWAY_PROBE_SPEC');
for(const item of [spec.center,spec.profile,...(spec.center_profile?[spec.center_profile]:[]),spec.native_cli,spec.peer_addon,...Object.values(spec.sources),...Object.values(spec.modules)])
  check(fs.realpathSync(item.path)===item.path&&sha(fs.readFileSync(item.path))===item.sha256,'WB_GATEWAY_PROBE_SOURCE_DRIFT');
const cache=new Map(),builtins=new Map([[35317,cp],[91943,fsp],[69278,net],[13193,{StringDecoder}],[16698,asyncHooks],[77030,net]]);
function load(id){
  if(builtins.has(id))return builtins.get(id);if(cache.has(id))return cache.get(id);
  const item=spec.modules[id];check(item,'WB_GATEWAY_PROBE_UNEXPECTED_IMPORT_'+id);const exports={};cache.set(id,exports);
  vm.runInNewContext(fs.readFileSync(item.path,'utf8'),{process,Buffer,console,setTimeout,clearTimeout,setInterval,clearInterval,setImmediate,clearImmediate},
    {filename:item.path,timeout:1000})(null,exports,load);return exports;
}
async function until(test,budget=10000){const end=Date.now()+budget;while(Date.now()<end){if(test())return;await new Promise(ok=>setTimeout(ok,50))}throw Error('WB_GATEWAY_PROBE_WAIT_TIMEOUT')}
function row(pid){
  const raw=cp.execFileSync('/bin/ps',['-p',String(pid),'-o','ppid=,lstart=,command='],{encoding:'utf8'}).trim();
  const m=raw.match(/^(\d+)\s+((?:\S+\s+){4}\S+)\s+(.*)$/);check(m,'WB_GATEWAY_PROBE_PID');
  return {pid,ppid:Number(m[1]),started:m[2].replace(/\s+/g,' '),command:m[3]};
}
function publish(name,value){fs.writeFileSync(root+'/'+name,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600})}
function ownSpawn(command,args,env,name){
  // Match the real desktop backend's pipes. Passing regular evidence files as
  // stdout/stderr makes Node inspect paths outside its allowed unit at startup.
  const out=fs.createWriteStream(root+'/'+name+'.stdout',{flags:'wx',mode:0o600}),err=fs.createWriteStream(root+'/'+name+'.stderr',{flags:'wx',mode:0o600});
  const process=cp.spawn(command,args,{cwd:spec.app_home,env,stdio:['ignore','pipe','pipe']});
  process.stdout.pipe(out);process.stderr.pipe(err);
  const owned={process,exit:null};process.on('exit',(code,signal)=>{owned.exit={code,signal}});return owned;
}

if(mode==='backend'){
  const result={at:new Date().toISOString(),pid:process.pid,model_prompts:0,tests:[],direct_fs:[],application_admitted:false};
  let service,client;
  try{
    check(process.env.WCB_MEMORY_WB_GATEWAY===root+'/gateway.json','WB_GATEWAY_PROBE_PRELOAD_ENV');
    for(const [name,file] of [['control',spec.app_home+'/control.txt'],['protected',root+'/synthetic-non-target/fact.txt']]){
      try{result.direct_fs.push({name,read:fs.readFileSync(file,'utf8')})}catch(error){result.direct_fs.push({name,error:error.code})}
    }
    if(spec.isolation_probe){
      try{result.direct_fs.push({name:'old-unit',read:fs.readFileSync(spec.isolation_probe.old_fact,'utf8')})}
      catch(error){result.direct_fs.push({name:'old-unit',error:error.code})}
      try{fs.writeFileSync(spec.isolation_probe.external_write,'SHOULD-NOT-BE-WRITTEN');result.direct_fs.push({name:'outside-write',written:true})}
      catch(error){result.direct_fs.push({name:'outside-write',error:error.code})}
    }
    const address='SYNTHETIC_'+crypto.randomBytes(8).toString('hex');
    service=cp.spawn(spec.native_cli.path,['--config',JSON.stringify({extraPath:[],enableGlobalProjection:false,ipcAddress:address}),
      '--rule_decision','center','--uid',spec.account_uid,'--app_home',spec.app_home],
      {stdio:['ignore','ignore','ignore'],env:{PATH:'/usr/bin:/bin',HOME:spec.os_home,USER:process.env.USER,LOGNAME:process.env.LOGNAME,
        LANG:'en_US.UTF-8',TMPDIR:spec.temp+'/',SANDBOX_CENTER_UID:spec.account_uid,SANDBOX_CENTER_IPC_ADDRESS:spec.center_socket}});
    let serviceExit=null,serviceError=null;service.on('close',(code,signal)=>{serviceExit={code,signal}});service.on('error',error=>{serviceError=error.message});
    result.native_pid=service.pid;
    const sdk=load(84283),commands=load(68331).SANDBOX_COMMANDS,events=[];client=sdk.createSandboxCliClient();
    client.addReverseListener({commands:[commands.PROCESS_OUTPUT,commands.PROCESS_EXIT,commands.REPORT_EVENT]},message=>events.push(message));
    await client.connect({address,connectTimeoutMs:5000,requestTimeoutMs:5000});
    const session='SYNTHETIC-gateway-session';await client.sendRequest(session,commands.OPEN_SESSION,{workingDir:spec.app_home});
    fs.symlinkSync(root+'/synthetic-non-target',spec.app_home+'/protected-alias','dir');
    for(const name of ['control','write-control','protected','native-private','alias-read','write-denied',...(spec.isolation_probe?['old-unit','outside-write']:[])]){
      const target=name==='control'?spec.app_home+'/control.txt':name==='alias-read'?spec.app_home+'/protected-alias/fact.txt':
        name==='write-control'?spec.app_home+'/allowed-write':
        name==='old-unit'?spec.isolation_probe.old_fact:name==='outside-write'?spec.isolation_probe.external_write:
        name==='write-denied'?root+'/synthetic-non-target/denied-write':root+'/'+(name==='protected'?'synthetic-non-target':name)+'/fact.txt';
      const command=['write-control','write-denied','outside-write'].includes(name)?'/usr/bin/touch':'/bin/cat';
      const started=await client.sendRequest(session,commands.RUN_EXECUTABLE,{executable:command,args:[target],cwdDir:spec.app_home,
        timeoutMs:3000,executionMode:'sandbox',stdoutMode:'pipe',stdinMode:'pipe',killProcessTree:true,env:{PATH:'/usr/bin:/bin',LANG:'en_US.UTF-8',TMPDIR:spec.temp+'/'}});
      await until(()=>events.some(e=>e.command===commands.PROCESS_EXIT&&e.data?.processId===started.processId));
      const observed=events.filter(e=>e.data?.processId===started.processId);
      result.tests.push({name,started,events:observed,exit:observed.find(e=>e.command===commands.PROCESS_EXIT)?.data.exitCode,
        output:observed.filter(e=>e.command===commands.PROCESS_OUTPUT).map(e=>Buffer.from(e.data.data,'base64').toString('utf8')).join('')});
    }
    await client.sendRequest(session,commands.CLOSE_SESSION,{});
    result.unsafe_mode_rejected=await new Promise((ok,no)=>{
      const socket=net.createConnection('/tmp/'+address+'.sock');let any=false;
      const timer=setTimeout(()=>{socket.destroy();no(Error('UNSAFE_MODE_TIMEOUT'))},3000);
      socket.on('connect',()=>socket.write(JSON.stringify({sessionId:session,messageId:'unsafe',command:'RunExecutable',
        data:{executable:'/bin/cat',args:[root+'/synthetic-non-target/fact.txt'],executionMode:'host'}})+'\n'));
      socket.on('data',()=>{any=true});socket.on('error',()=>{});socket.on('close',()=>{clearTimeout(timer);ok(!any)});
    });
    await client.disconnect();client=null;
    service.kill('SIGTERM');await until(()=>!!serviceExit||!!serviceError);
    result.service_exit=serviceExit;result.service_error=serviceError;
    result.pass=result.direct_fs[0]?.read?.includes('SYNTHETIC-ALLOW')&&result.direct_fs[1]?.error==='EPERM'
      &&(!spec.isolation_probe||result.direct_fs.slice(2).every(t=>t.error==='EPERM'))
      &&result.tests.length===(spec.isolation_probe?8:6)&&result.tests.every(t=>t.name==='control'?t.exit===0&&t.output.includes('SYNTHETIC-ALLOW'):
        t.name==='write-control'?t.exit===0&&fs.existsSync(spec.app_home+'/allowed-write'):
        t.exit!==0&&t.output.includes('Operation not permitted'))&&result.unsafe_mode_rejected&&serviceExit?.code===0&&!serviceError;
  }catch(error){if(error.message==='SYNTHETIC_CENTER_LOCK_DISCOVERY_COMPLETED')result.discovery_complete=true;else result.error=String(error.stack||error)}
  finally{
    if(client)await client.disconnect();
    // Only this synthetic probe's fixed, bounded cat/touch service is owned here.
    if(service&&!service.killed){try{service.kill('SIGTERM')}catch(error){result.cleanup_error=error.message}}
    fs.writeFileSync(spec.app_home+'/backend-result.json',JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
    console.log(JSON.stringify({pass:result.pass,error:result.error,pid:process.pid}));if(!result.pass)process.exitCode=2;
  }
}else{
  const env={PATH:process.env.PATH,HOME:spec.os_home,USER:process.env.USER,LOGNAME:process.env.LOGNAME,
    LANG:'en_US.UTF-8',TMPDIR:spec.temp+'/',WORKBUDDY_CONFIG_DIR:spec.app_home,CODEBUDDY_CONFIG_DIR:spec.app_home,
    SANDBOX_CENTER_UID:spec.account_uid,SANDBOX_CENTER_IPC_ADDRESS:spec.center_socket};
  const result={at:new Date().toISOString(),model_prompts:0,synthetic_only:true,application_admitted:false};
  fs.writeFileSync(root+'/probe-source.mjs',fs.readFileSync(fileURLToPath(import.meta.url)),{flag:'wx',mode:0o600});
  let center,gateway,backend,control;
  try{
    center=ownSpawn('/usr/bin/sandbox-exec',['-f',(spec.center_profile??spec.profile).path,spec.center.path,'--config',JSON.stringify({appHome:spec.app_home,
      ipcAddress:spec.center_socket,cipher:{detectMaxFileSizeBytes:1048576}}),'--app_home',spec.app_home],env,'center');
    result.center_pid=center.process.pid;await until(()=>fs.existsSync(spec.center_socket));
    const sdk=load(34094),protocol=load(65649);control=sdk.createSandboxCenterClient({clientRole:'synthetic-gateway-controller',startMode:'connect-only',
      resolveRuntimeContext:()=>({appHome:spec.app_home,uid:spec.account_uid,socketPath:spec.center_socket,executablePath:spec.center.path})});
    await control.request(protocol.SANDBOX_RULES_COMMANDS.SET_FILE_RULES,{category:'global',rules:[{path:'**',action:'read=allow|write=allow|delete=allow',isDirectory:false}]},{timeoutMs:5000});
    result.center_lock_files=cp.execFileSync('/usr/sbin/lsof',['-nP','-p',String(center.process.pid),'-Fn'],{encoding:'utf8'})
      .split('\n').filter(line=>line.startsWith('n')&&/\.lock(?:$|\s)|\/data\.lock/.test(line)).map(line=>line.slice(1));
    result.expected_center_lock_files=centerCoordinationPaths(spec.app_home,spec.center_socket).slice(1).map(p=>'/private'+p);
    result.center_locks_verified=JSON.stringify(result.center_lock_files.sort())===JSON.stringify(result.expected_center_lock_files.sort());
    check(result.center_locks_verified,'WB_GATEWAY_PROBE_CENTER_COORDINATION_DRIFT');
    if(spec.center_lock_discovery)throw Error('SYNTHETIC_CENTER_LOCK_DISCOVERY_COMPLETED');
    const probe=fileURLToPath(import.meta.url),backendArgs=['--require',spec.sources.guard.path,probe,'backend',specPath];
    const gatewaySpec={contract:'workbuddy-owned-executor-gateway/v1',mode:'synthetic-launch',application_admitted:false,
      os_home:spec.os_home,app_home:spec.app_home,temp:spec.temp,account_uid:spec.account_uid,
      node:spec.node,control_socket:spec.control_socket,center_socket:spec.center_socket,native_cli:spec.native_cli,
      peer_addon:spec.peer_addon,sources:spec.sources,denied_roots:spec.denied_roots,test_parent:row(process.pid),
      memory_unit:spec.memory_unit??null,
      backend_command:[spec.node,...backendArgs].join(' ')};
    publish('gateway.json',gatewaySpec);
    gateway=ownSpawn(process.execPath,[spec.sources.gateway.path,root+'/gateway.json'],env,'gateway');
    result.gateway_pid=gateway.process.pid;await until(()=>fs.existsSync(root+'/gateway-ready.json'));
    backend=ownSpawn('/usr/bin/sandbox-exec',['-f',spec.profile.path,spec.node,...backendArgs],
      {...env,ELECTRON_RUN_AS_NODE:'1',WCB_MEMORY_WB_GATEWAY:root+'/gateway.json'},'backend');
    result.backend_pid=backend.process.pid;
    await until(()=>!!backend.exit,30000);result.backend_exit=backend.exit;
    result.backend=JSON.parse(fs.readFileSync(spec.app_home+'/backend-result.json'));
  }catch(error){if(error.message==='SYNTHETIC_CENTER_LOCK_DISCOVERY_COMPLETED')result.discovery_complete=true;else result.error=String(error.stack||error)}
  finally{
    if(gateway){gateway.process.kill('SIGTERM');try{await until(()=>!!gateway.exit,5000)}catch{}result.gateway_exit=gateway.exit}
    if(control){try{await control.request(load(65649).SANDBOX_CENTER_LIFECYCLE_COMMANDS.SHUTDOWN,{}, {timeoutMs:5000})}catch(error){result.center_shutdown_error=error.message}control.close()}
    if(center){try{await until(()=>!!center.exit,5000)}catch{}result.center_exit=center.exit}
    result.pass=spec.center_lock_discovery
      ?result.discovery_complete===true&&result.center_lock_files?.length>0&&result.center_exit?.code===0
      :result.backend?.pass===true&&result.backend_exit?.code===0&&result.gateway_exit?.code===0&&result.center_exit?.code===0&&!result.error;
    result.at_end=new Date().toISOString();publish('result.json',result);console.log(JSON.stringify({pass:result.pass,error:result.error,result:root+'/result.json'}));if(!result.pass)process.exitCode=2;
  }
}
