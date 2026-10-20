/* Run the installed CLI's version command offline and inspect its real resolver.
 * No auth import, desktop task, model request or installed-file modification.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn,execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {WorkBuddyCdpClient} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';

const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const specPath=path.resolve(process.argv[2]),root=path.dirname(specPath),spec=JSON.parse(fs.readFileSync(specPath));
if(spec.contract!=='workbuddy-home-runtime-synthetic/v1'||spec.synthetic_only!==true
  ||!root.includes('/debug-workspace/e2e-evaluate/memory-e2e/')||fs.realpathSync(root)!==root
  ||spec.home!==root+'/app-home'||spec.tmp!==root+'/tmp'||spec.argv.length!==1||spec.argv[0]!=='--version'
  ||!Number.isSafeInteger(spec.port)||spec.port<9300||spec.port>9400)throw Error('WB_HOME_PROBE_SPEC');
for(const item of [spec.binary,spec.cli,spec.profile])
  if(fs.realpathSync(item.path)!==item.path||sha(fs.readFileSync(item.path))!==item.sha256)throw Error('WB_HOME_PROBE_DRIFT');
if(spec.binary.path!=='/Applications/WorkBuddy.app/Contents/MacOS/Electron'
  ||spec.cli.path!=='/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/dist/codebuddy-lite-wb.mjs')throw Error('WB_HOME_INSTALLED_ONLY');
for(const name of ['customization.json'])
  if(fs.existsSync(path.join(path.dirname(path.dirname(spec.cli.path)),name)))throw Error('WB_HOME_CUSTOM_SNAPSHOT_PRESENT');
// --version does not naturally call getHomeDir. Pause at the native entry,
// initialize its own customization bootstrap and invoke its own path utility.
const text=fs.readFileSync(spec.cli.path,'utf8'),needle='__webpack_require__(__webpack_require__.s=75374)',offset=text.indexOf(needle);
if(offset<0||text.indexOf(needle,offset+1)!==-1)throw Error('WB_HOME_RESOLVER_UNIQUE');
const before=text.slice(0,offset),lineNumber=before.split('\n').length-1;
const columnNumber=before.length-before.lastIndexOf('\n')-1;
const out=fs.openSync(root+'/stdout','wx',0o600),err=fs.openSync(root+'/stderr','wx',0o600);
const child=spawn('/usr/bin/sandbox-exec',['-f',spec.profile.path,spec.binary.path,
  '--inspect-brk=127.0.0.1:'+spec.port,spec.cli.path,...spec.argv],
  {cwd:spec.home,env:{PATH:'/usr/bin:/bin:/usr/sbin:/sbin',HOME:spec.os_home,USER:process.env.USER,LOGNAME:process.env.LOGNAME,
    LANG:'en_US.UTF-8',ELECTRON_RUN_AS_NODE:'1',CODEBUDDY_CONFIG_DIR:spec.home,WORKBUDDY_CONFIG_DIR:spec.home,TMPDIR:spec.tmp+'/'},stdio:['ignore',out,err]});
fs.closeSync(out);fs.closeSync(err);let terminal=null;
child.on('exit',(code,signal)=>{terminal={code,signal}});
const result={contract:spec.contract,at:new Date().toISOString(),pid:child.pid,synthetic_only:true,
  source_sha256:sha(fs.readFileSync(fileURLToPath(import.meta.url))),model_prompts:0,auth_imported:false,
  observations:[],inspector_pauses:[],application_admitted:false};
fs.writeFileSync(root+'/probe-source.mjs',fs.readFileSync(fileURLToPath(import.meta.url)),{flag:'wx',mode:0o600});
let client;
try {
  let target;
  for(let i=0;i<100&&!terminal;i++){
    try{const targets=await(await fetch('http://127.0.0.1:'+spec.port+'/json/list')).json();if(targets.length===1){target=targets[0];break}}catch{}
    await new Promise(ok=>setTimeout(ok,50));
  }
  if(!target?.webSocketDebuggerUrl||target.type!=='node')throw Error('WB_HOME_INSPECTOR_NOT_READY');
  const owner=execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+spec.port,'-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim();
  if(owner!==String(child.pid))throw Error('WB_HOME_INSPECTOR_OWNER');
  client=await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl,10000);
  let resolvePause;
  const pauses=[],waitPause=()=>new Promise(ok=>{if(pauses.length)ok(pauses.shift());else resolvePause=ok});
  client.socket.addEventListener('message',event=>{
    const message=JSON.parse(String(event.data));
    if(message.method==='Debugger.paused'){
      if(resolvePause){const done=resolvePause;resolvePause=null;done(message.params)}else pauses.push(message.params);
    }
  });
  await client.send('Debugger.enable');
  const breakpoint=await client.send('Debugger.setBreakpointByUrl',{urlRegex:'codebuddy-lite-wb\\.mjs$',lineNumber,columnNumber});
  result.breakpoint={...breakpoint,lineNumber,columnNumber};
  await client.send('Runtime.runIfWaitingForDebugger');
  const deadline=Date.now()+15000;
  while(Date.now()<deadline&&!terminal){
    const pause=await Promise.race([waitPause(),new Promise(ok=>setTimeout(()=>ok(null),1000))]);
    if(!pause)continue;
    const frame=pause.callFrames[0];
    result.inspector_pauses.push({reason:pause.reason,hits:pause.hitBreakpoints,
      frames:pause.callFrames.slice(0,3).map(f=>({function:f.functionName,url:f.url,location:f.location}))});
    if(pause.hitBreakpoints?.includes(breakpoint.breakpointId)){
      await client.send('Debugger.removeBreakpoint',{breakpointId:breakpoint.breakpointId});
      const evaluated=await client.send('Debugger.evaluateOnCallFrame',{callFrameId:frame.callFrameId,
        expression:'(()=>{__webpack_require__(41008).K_();return {resolved:__webpack_require__(9890).P.getHomeDir(),product_snapshot:__webpack_require__(43394).f()??null,environment:process.env.CODEBUDDY_CONFIG_DIR,os_home:process.getBuiltinModule("node:os").homedir()}})()',returnByValue:true});
      if(evaluated.exceptionDetails)throw Error('WB_HOME_RESOLVER_EVALUATION:'+evaluated.exceptionDetails.text);
      result.observations.push({function:frame.functionName,location:frame.location,value:evaluated.result.value,
        resolver_invocation:'diagnostic_native_bootstrap_and_pathutils_at_entry',desktop_backend_verified:false});
      await client.send('Debugger.resume');break;
    }
    await client.send('Debugger.resume');
  }
  await client.send('Debugger.disable');
  // Detach instead of evaluating in a context that --version may already close.
}catch(error){result.error=String(error.stack||error)}
finally{
  client?.close();
  for(let i=0;i<100&&!terminal;i++)await new Promise(ok=>setTimeout(ok,100));
  result.exit=terminal;
  result.pass=terminal?.code===0&&result.observations.length===1&&result.observations[0].value.resolved===spec.home
    &&result.observations[0].value.product_snapshot===null&&!result.error;
  result.at_end=new Date().toISOString();
  fs.writeFileSync(root+'/result.json',JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
  console.log(JSON.stringify(result));
  if(!result.pass)process.exitCode=2;
}
