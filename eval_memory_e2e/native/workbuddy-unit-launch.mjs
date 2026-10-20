/* Zero-model desktop bootstrap supervisor; it never sends application prompts. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn,execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {WorkBuddyCdpClient,discoverWorkBuddyMainTarget,readWorkBuddyUi} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
import {buildUnitMemoryRules,centerCoordinationPaths,nativeCenterEpochPath} from './workbuddy-native-policy.mjs';
import {prepareUnitModel} from './workbuddy-unit-model.mjs';

const scopePath=path.resolve(process.argv[2]),root=path.dirname(scopePath),scope=JSON.parse(fs.readFileSync(scopePath));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const check=(ok,reason)=>{if(!ok)throw Error(reason)};
check(scope.contract==='workbuddy-case-memory-unit/v1'&&scope.root===root&&scope.zero_model_bootstrap_only===true
  &&scope.application_admitted===false&&fs.realpathSync(root)===root,'WB_UNIT_BOOTSTRAP_SPEC');
for(const item of [scope.peer_addon,...Object.values(scope.sources),...['binary','center','native_cli','asar','cli','renderer_ui'].map(k=>scope.installation[k])])
  check(fs.realpathSync(item.path)===item.path&&hash(fs.readFileSync(item.path))===item.sha256,'WB_UNIT_BOOTSTRAP_DRIFT');
const publish=(name,value)=>fs.writeFileSync(root+'/'+name,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});
const item=p=>({path:p,sha256:hash(fs.readFileSync(p))});
function row(pid){
  const raw=execFileSync('/bin/ps',['-p',String(pid),'-o','ppid=,lstart=,command='],{encoding:'utf8'}).trim();
  const m=raw.match(/^(\d+)\s+((?:\S+\s+){4}\S+)\s+(.*)$/);check(m,'WB_UNIT_PROCESS_IDENTITY');
  return {pid,ppid:Number(m[1]),started:m[2].replace(/\s+/g,' '),command:m[3]};
}
async function until(test,budget=15000){const end=Date.now()+budget;while(Date.now()<end){if(await test())return;await new Promise(ok=>setTimeout(ok,100))}throw Error('WB_UNIT_BOOTSTRAP_WAIT_TIMEOUT')}
function owned(command,args,env,name){
  const child=spawn(command,args,{cwd:scope.app_home,env,stdio:['ignore','pipe','pipe']});
  child.stdout.pipe(fs.createWriteStream(root+'/'+name+'.stdout',{flags:'wx',mode:0o600}));
  child.stderr.pipe(fs.createWriteStream(root+'/'+name+'.stderr',{flags:'wx',mode:0o600}));return child;
}
for(const port of Object.values(scope.ports)){
  let owner='';try{owner=execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+port,'-sTCP:LISTEN','-t'],{encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim()}catch{}
  check(!owner,'WB_UNIT_CONTROL_PORT_IN_USE');
}
publish('launching.json',{at:new Date().toISOString(),supervisor:row(process.pid),scope_sha256:hash(fs.readFileSync(scopePath)),model_prompts:0});
const env={...process.env,WORKBUDDY_CONFIG_DIR:scope.app_home,CODEBUDDY_CONFIG_DIR:scope.app_home,
  WORKBUDDY_USER_DATA_DIR:scope.app_home+'/app',TMPDIR:scope.temp+'/'};
delete env.ELECTRON_RUN_AS_NODE;delete env.NODE_OPTIONS;delete env.WCB_MEMORY_WB_GATEWAY;
for(const key of ['CODEX_HOME','CODEX_API_KEY','OPENAI_API_KEY','OPENAI_BASE_URL','ACODE_HOME','ACODE_API_KEY',
  'ASTUDIO_HOME','ASTUDIO_ACODE_HOME','ASTUDIO_ACODE_BIN','ACODE_EXEC_SERVER_URL'])delete env[key];
const app=scope.installation.binary.path,main=owned(app,['--inspect-brk=127.0.0.1:'+scope.ports.main_inspector,
  '--remote-debugging-port='+scope.ports.ui,'--remote-debugging-address=127.0.0.1','--user-data-dir='+scope.app_home+'/app'],env,'main');
let mainExit=null,gateway,gatewayExit=null,client,applicationResumeIntent=false;
main.on('exit',(code,signal)=>{mainExit={code,signal}});
try{
  let target;
  await until(async()=>{check(!mainExit,'WB_UNIT_MAIN_EXITED');try{const t=await(await fetch('http://127.0.0.1:'+scope.ports.main_inspector+'/json/list')).json();if(t.length===1&&t[0].type==='node'){target=t[0];return true}}catch{}return false});
  check(execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+scope.ports.main_inspector,'-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim()===String(main.pid),'WB_UNIT_MAIN_INSPECTOR_OWNER');
  client=await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl,15000);
  let resolvePause;const paused=new Promise(ok=>{resolvePause=ok});
  client.socket.addEventListener('message',event=>{const m=JSON.parse(String(event.data));if(m.method==='Debugger.paused')resolvePause(m.params)});
  await client.send('Debugger.enable');await client.send('Runtime.runIfWaitingForDebugger');
  const pause=await Promise.race([paused,new Promise((_,no)=>setTimeout(()=>no(Error('WB_UNIT_ENTRY_PAUSE_TIMEOUT')),10000))]);
  const centerSocket=nativeCenterEpochPath(scope.app_home,main.pid);
  const memoryUnit={debugRoot:scope.debug_root,allowedPaths:[scope.app_home,scope.temp,scope.candidate],
    readLiterals:[root+'/gateway.json',root+'/scope.json',root+'/backend.sb',root+'/center.sb']};
  const home=scope.os_home;
  const denied=['.codex','.workbuddy','.qwenworkcn','.doubaowork','.acode','.codebuddy',
    'Library/Application Support/Codex','Library/Application Support/ChatGPT','Library/Application Support/WorkBuddy',
    'Library/Application Support/WorkBuddyExtension','Library/Application Support/QwenWorkCN','Library/Application Support/DoubaoWork']
    .map(p=>home+'/'+p).concat(root+'/synthetic-non-target');
  const aliases=values=>values.flatMap(p=>[p,'/System/Volumes/Data'+p]);
  const base='(version 1)\n(allow default)\n(deny file-read* file-write*\n'+aliases(denied).map(p=>'(subpath '+JSON.stringify(p)+')').join('\n')+')\n(deny appleevent-send)\n';
  const auth=home+'/Library/Application Support/CodeBuddyExtension/Data/Public/auth';
  const authRead=aliases([auth]).map(p=>'(require-all (subpath '+JSON.stringify(p)+')\n'
    +['workbuddy-desktop.info','workbuddy-desktop.info.logout'].map(n=>'(require-not (literal '+JSON.stringify(p+'/'+n)+'))').join('\n')+')').join('\n');
  const authRule='(deny file-read* file-write*\n'+authRead+')\n';
  fs.writeFileSync(root+'/backend.sb',base+authRule+buildUnitMemoryRules(memoryUnit).join('\n')+'\n',{flag:'wx',mode:0o600});
  fs.writeFileSync(root+'/center.sb',base+authRule+buildUnitMemoryRules({...memoryUnit,writeLiterals:centerCoordinationPaths(scope.app_home,centerSocket)}).join('\n')+'\n',{flag:'wx',mode:0o600});
  const backendGuard=scope.sources.guard;
  const backendArgs=['--inspect=127.0.0.1:'+scope.ports.backend_inspector,'--require',backendGuard.path,
    '/Applications/WorkBuddy.app/Contents/Resources/app.asar/main/daemon-app-server-entry.js','--stdio'];
  const gatewaySpec={contract:'workbuddy-owned-executor-gateway/v1',mode:'workbuddy-owned-session',application_admitted:false,
    main:row(main.pid),backend_command:[app,...backendArgs].join(' '),node:app,os_home:home,app_home:scope.app_home,temp:scope.temp,
    account_uid:scope.account_uid,native_cli:scope.installation.native_cli,peer_addon:scope.peer_addon,sources:scope.sources,
    control_socket:'/tmp/wcbm-wb-control-'+crypto.randomBytes(8).toString('hex')+'.sock',center_socket:centerSocket,
    denied_roots:[...denied,auth],memory_unit:memoryUnit};
  publish('gateway.json',gatewaySpec);
  gateway=owned(process.execPath,[scope.sources.gateway.path,root+'/gateway.json'],{...env,ELECTRON_RUN_AS_NODE:'1'},'gateway');
  gateway.on('exit',(code,signal)=>{gatewayExit={code,signal}});
  await until(()=>{check(!gatewayExit,'WB_UNIT_GATEWAY_EXITED');return fs.existsSync(root+'/gateway-ready.json')});
  const spec={contract:'workbuddy-main-os-boundary/v1',main_pid:main.pid,app_home:scope.app_home,temp:scope.temp,
    backend_profile:item(root+'/backend.sb'),center_profile:item(root+'/center.sb'),gateway_spec:item(root+'/gateway.json'),
    backend_guard:backendGuard,center_binary:scope.installation.center,native_cli:scope.installation.native_cli,
    center_socket:centerSocket,backend_inspector_port:scope.ports.backend_inspector};
  publish('main-spawn-spec.json',spec);
  const expression=`process.getBuiltinModule('node:module').createRequire(${JSON.stringify(scope.sources.main_guard.path)})(${JSON.stringify(scope.sources.main_guard.path)}).install(${JSON.stringify(spec)})`;
  const installed=await client.send('Debugger.evaluateOnCallFrame',{callFrameId:pause.callFrames[0].callFrameId,expression,returnByValue:true});
  check(!installed.exceptionDetails&&installed.result?.value?.installed===true,'WB_UNIT_MAIN_GUARD_INSTALL');
  publish('main-guard-installed.json',{at:new Date().toISOString(),result:installed.result.value,entry:pause.callFrames[0].location});
  applicationResumeIntent=true;
  await client.send('Debugger.resume');await client.send('Debugger.disable');
  await until(async()=>{check(!mainExit,'WB_UNIT_MAIN_EXITED');try{return (await fetch('http://127.0.0.1:'+scope.ports.ui+'/json/version')).ok}catch{return false}},60000);
  await client.evaluate("setTimeout(()=>process.getBuiltinModule('node:inspector').close(),50);true");client.close();client=null;
  // Node's asynchronous inspector close must finish before opening the next
  // renderer CDP session. A close request alone is not a restoration receipt.
  await until(()=>{
    try{return !execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+scope.ports.main_inspector,'-t'],
      {encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim()}
    catch(error){if(error.status===1)return true;throw error}
  },10000);
  publish('main-inspector-closed.json',{at:new Date().toISOString(),main_pid:main.pid,port:scope.ports.main_inspector,no_open_socket_verified:true});
  if(scope.model_preferences){
    let target;
    await until(async()=>{
      check(!mainExit,'WB_UNIT_MAIN_EXITED');
      try{target=await discoverWorkBuddyMainTarget('http://127.0.0.1:'+scope.ports.ui,5000);return true}
      catch(error){if(String(error.message).includes('WorkBuddy 主页面数量异常：0'))return false;throw error}
    },30000);
    const ui=await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl,30000);
    try{
      await prepareUnitModel(ui,scope,{onProgress:event=>console.log(JSON.stringify(event))});
    }finally{ui.close()}
  }
  publish('desktop-bootstrap-ready.json',{at:new Date().toISOString(),main:row(main.pid),gateway:row(gateway.pid),center_socket:centerSocket,
    backend_inspector_port:scope.ports.backend_inspector,model_prompts:0,account_verified:!!scope.model_preferences,
    configured_model_id:scope.model_preferences?.selection?.id??null,native_request_model_not_yet_observed:true,os_boundary_attested:false,
    application_admitted:false,ordinary_instance_restarted:false});
  console.log(JSON.stringify({ready:true,main_pid:main.pid,root,model_prompts:0,application_admitted:false}));
}catch(error){
  publish('desktop-bootstrap-failed.json',{at:new Date().toISOString(),reason:String(error.stack||error),main_pid:main.pid,
    main_exit:mainExit,gateway_pid:gateway?.pid,gateway_exit:gatewayExit,model_prompts:0,application_admitted:false});
  console.error(String(error.stack||error));client?.close();
  if(!applicationResumeIntent&&!mainExit){
    publish('unstarted-main-stop.json',{at:new Date().toISOString(),main:row(main.pid),reason:'failed before application entry resume; zero UI/model operations'});
    main.kill('SIGTERM');
  }
}
// Keep main's parent identity stable. Only normal UI quit ends an app unit.
await until(()=>!!mainExit,12*60*60*1000);
publish('desktop-main-exited.json',{at:new Date().toISOString(),exit:mainExit,model_prompts_sent_by_supervisor:0});
if(gateway&&!gatewayExit){gateway.kill('SIGTERM');await until(()=>!!gatewayExit,10000)}
publish('desktop-supervisor-exited.json',{at:new Date().toISOString(),main_exit:mainExit,gateway_exit:gatewayExit});
