import {createHash} from 'node:crypto';
import {CdpClient, discoverMainTarget} from './astronstudio-cdp.mjs';
import {runCapture} from '../../vendor/e2e-shared/desktop-runtime/process.mjs';
import {inspectMacDesktopAppProcess} from '../../vendor/e2e-shared/desktop-app-discovery/index.mjs';
import {ASTRONSTUDIO_APP_PROFILE} from '../../vendor/e2e-shared/desktop-app-discovery/profiles.mjs';
import {readNativeForegroundApp} from './astronstudio-native-foreground.mjs';

const hash = value => createHash('sha256').update(value).digest('hex');
const require = (ok, code) => {if (!ok) throw Error('ASTRONSTUDIO_UI_VISIBILITY_' + code);};
export async function ensureExecutionUiVisible(config, report, overrides={}) {
  const api={discoverMainTarget,connect:CdpClient.connect,runCommand:runCapture,foreground:readNativeForegroundApp,
    inspect:appPath=>inspectMacDesktopAppProcess({profile:ASTRONSTUDIO_APP_PROFILE,appPath}),
    sleep:ms=>new Promise(r=>setTimeout(r,ms)),now:Date.now,activationTimeoutMs:5000,...overrides};
  require(report.process?.running&&report.process.identity_verified&&report.gui?.unlocked
    &&report.cdp?.ready&&report.cdp.owned_by_main_process&&report.cdp.endpoint===config.endpoint
    &&report.app?.path===config.appPath,'UNVERIFIED_APP_OR_GUI');
  const target=await api.discoverMainTarget(config.endpoint,10000),client=await api.connect(target.webSocketDebuggerUrl);
  const read=()=>client.evaluate('({visibility:document.visibilityState,focus:document.hasFocus(),route:location.hash})');
  const result={profile:'owned-native-visible-send/v2',changed:false,native_open_calls:0,page_bring_to_front_calls:0,
    prompt_send_calls:0,app_restart_calls:0,app_pid:report.process.pid};
  try {
    result.before=await read();
    result.native_before=await api.foreground();
    if(result.before.visibility==='visible'&&result.native_before.pid===report.process.pid){result.after=result.before;result.native_after=result.native_before;return result;}
    await client.send('Page.bringToFront');result.page_bring_to_front_calls++;
    await api.sleep(100);let view=await read();
    let foreground=await api.foreground();
    if(view.visibility!=='visible'||foreground.pid!==report.process.pid) {
      const processInfo=await api.inspect(config.appPath);
      require(processInfo?.pid===report.process.pid&&processInfo.started_at===report.process.started_at
        &&processInfo.command&&hash(processInfo.command)===report.process.command_sha256,'APP_CHANGED_BEFORE_ACTIVATION');
      const opened=await api.runCommand('/usr/bin/open',['-a',config.appPath],{capture:true,allowFailure:true,timeoutMs:5000});
      require(opened.code===0,'NATIVE_ACTIVATION_FAILED');result.native_open_calls++;
      const deadline=api.now()+api.activationTimeoutMs;
      let stableAt=null;
      for(;;){view=await read();foreground=await api.foreground();
        const ready=view.visibility==='visible'&&foreground.pid===report.process.pid;
        if(ready){stableAt??=api.now();if(api.now()-stableAt>=200)break;}else stableAt=null;
        require(api.now()<deadline,'NOT_VISIBLE_OR_NOT_NATIVE_FOREGROUND');await api.sleep(100);}
    }
    const finalProcess=await api.inspect(config.appPath);
    require(finalProcess?.pid===report.process.pid&&finalProcess.started_at===report.process.started_at
      &&finalProcess.command&&hash(finalProcess.command)===report.process.command_sha256,'APP_CHANGED_AFTER_ACTIVATION');
    require(view.visibility==='visible'&&foreground.pid===report.process.pid,'NOT_VISIBLE_OR_NOT_NATIVE_FOREGROUND');
    result.changed=true;result.after=view;result.native_after=foreground;return result;
  } finally {client.close();}
}
