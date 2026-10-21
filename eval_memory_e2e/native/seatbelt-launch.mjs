import {readFile,writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {WorkBuddyCdpClient} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
const [leaseFile,pidText]=process.argv.slice(2),pid=Number(pidText),lease=JSON.parse(await readFile(leaseFile,'utf8'));
if(lease.contract!=='macos-seatbelt-astudio-backend/v1'
  ||Object.hasOwn(lease,'compiled_kernel')||Object.hasOwn(lease,'native_executor'))throw Error('ASTUDIO_PRODUCTION_PACKAGE_REQUIRED');
if(!Number.isSafeInteger(pid)||pid<2)throw Error('SEATBELT_LAUNCH_PID');
const folder=fileURLToPath(new URL('.', 'file://'+leaseFile));
const waitStarted=Date.now();let owner='';
while(Date.now()-waitStarted<10000){
  try{owner=execFileSync('/usr/sbin/lsof',['-nP','-iTCP:9271','-sTCP:LISTEN','-t'],{encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim()}catch{}
  if(owner)break;await new Promise(ok=>setTimeout(ok,100));
}
if(owner!==String(pid))throw Error('SEATBELT_INSPECTOR_OWNER');
const targets=await (await fetch('http://127.0.0.1:9271/json/list')).json();
if(targets.length!==1||targets[0].type!=='node'||!targets[0].webSocketDebuggerUrl)throw Error('SEATBELT_INSPECTOR_TARGET');
const client=await WorkBuddyCdpClient.connect(targets[0].webSocketDebuggerUrl,20000);
try {
  // Let Node finish its own bootstrap, then stop at the application entry.
  // Requiring a module while still in the initial wait can see uninitialized
  // Node internals on the installed Electron runtime.
  let pauseResolve;
  const paused=new Promise(ok=>{pauseResolve=ok});
  const listener=e=>{const event=JSON.parse(String(e.data));if(event.method==='Debugger.paused')pauseResolve(event.params)};
  client.socket.addEventListener('message',listener);
  await client.send('Debugger.enable');
  await client.send('Runtime.runIfWaitingForDebugger');
  const pause=await Promise.race([paused,new Promise((_,no)=>setTimeout(()=>no(Error('SEATBELT_ENTRY_PAUSE_UNVERIFIED')),15000))]);
  client.socket.removeEventListener('message',listener);
  await writeFile(folder+'bootstrap-entry-pause.json',JSON.stringify({reason:pause.reason,
    frames:pause.callFrames.map(f=>({function_name:f.functionName,url:f.url,location:f.location}))},null,2)+'\n',{flag:'wx'});
  const guard=fileURLToPath(new URL('./seatbelt-spawn-guard.cjs',import.meta.url));
  const hash=createHash('sha256').update(await readFile(guard)).digest('hex');
  if(hash!==lease.spawn_guard_sha256)throw Error('SEATBELT_SPAWN_SOURCE_DRIFT');
  const spec={contract:lease.contract,profile:lease.profile,profile_sha256:lease.profile_sha256,
    kernel:lease.kernel,...(lease.astudio_scope?{astudio_scope:lease.astudio_scope}:{})};
  const expression=`(()=>{const m=process.getBuiltinModule('node:module');return m.createRequire(${JSON.stringify(guard)})(${JSON.stringify(guard)}).install(${JSON.stringify(spec)})})()`;
  const evaluated=await client.send('Debugger.evaluateOnCallFrame',{callFrameId:pause.callFrames[0].callFrameId,
    expression,returnByValue:true});
  if(evaluated.exceptionDetails)throw Error(evaluated.exceptionDetails.exception?.description??evaluated.exceptionDetails.text);
  const installed=evaluated.result?.value;
  if(installed?.installed!==true||installed?.profile_sha256!==lease.profile_sha256)throw Error('SEATBELT_INSTALL_RESULT_UNVERIFIED');
  await writeFile(folder+'bootstrap-install.json',JSON.stringify({at:new Date().toISOString(),main_pid:pid,guard_source_sha256:hash,
    entry_pause:{reason:pause.reason,url:pause.callFrames?.[0]?.url,location:pause.callFrames?.[0]?.location},result:installed},null,2)+'\n',{flag:'wx'});
  await client.send('Debugger.resume');
  await client.send('Debugger.disable');
  const started=Date.now();let ready=false;
  while(Date.now()-started<60000){
    try{const r=await fetch('http://127.0.0.1:9240/json/version');if(r.ok){ready=true;break}}catch{}
    await new Promise(ok=>setTimeout(ok,200));
  }
  if(!ready)throw Error('SEATBELT_UI_CDP_NOT_READY');
  // End the temporary main-process debugging endpoint after bootstrap.
  await client.evaluate(`setTimeout(()=>process.getBuiltinModule('node:inspector').close(),50);true`);
  console.log(JSON.stringify({installed:true,main_pid:pid,ui_cdp_ready:true,main_inspector_close_requested:true}));
}finally{client.close()}
