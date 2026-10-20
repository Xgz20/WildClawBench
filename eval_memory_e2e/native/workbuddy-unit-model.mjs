/* Model-only preparation of an empty UI. No conversation or prompt is created. */
import fs from 'node:fs';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readWorkBuddyUi,WorkBuddyCdpClient,discoverWorkBuddyMainTarget} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';

const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
export async function prepareUnitModel(ui,scope,{budgetMs=120000,onProgress=()=>{}}={}){
  if(scope.contract!=='workbuddy-case-memory-unit/v1'||!scope.zero_model_bootstrap_only||!scope.model_preferences)
    throw Error('WB_UNIT_MODEL_SPEC');
  const file=scope.root+'/model-selection-prepared.json';
  if(fs.existsSync(file))throw Error('WB_UNIT_MODEL_ALREADY_PREPARED_OBSERVE_ONLY');
  const main=JSON.parse(fs.readFileSync(scope.root+'/gateway.json','utf8')).main;
  function owner(){
    const observed=execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+scope.ports.ui,'-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim();
    if(observed!==String(main.pid))throw Error('WB_UNIT_MODEL_UI_OWNER_CHANGED');
    const row=execFileSync('/bin/ps',['-p',observed,'-o','ppid=,lstart=,command='],{encoding:'utf8'}).trim();
    const parsed=row.match(/^(\d+)\s+((?:\S+\s+){4}\S+)\s+(.*)$/);
    if(!parsed||Number(parsed[1])!==main.ppid||parsed[2].replace(/\s+/g,' ')!==main.started||parsed[3]!==main.command)
      throw Error('WB_UNIT_MODEL_UI_OWNER_CHANGED');
  }
  const samples=[],deadline=Date.now()+budgetMs,replacements=new Set();let identity,lastState,phase='read_only_metadata';
  try{
    while(Date.now()<deadline){
      owner();
      const sample={at:new Date().toISOString()};
      try{
        if(!ui){
          const target=await discoverWorkBuddyMainTarget('http://127.0.0.1:'+scope.ports.ui,5000);
          ui=await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl,30000);replacements.add(ui);sample.reconnected=true;
        }
        sample.target_id=ui.socket?.url?.split('/').pop()??null;
        const view=await readWorkBuddyUi(ui);
        sample.ui_ready=view.editor_count===1&&view.model_count===1&&view.permission_count===1;
        if(!sample.ui_ready){
          samples.push(sample);await new Promise(ok=>setTimeout(ok,500));continue;
        }
        identity=await ui.evaluate("(async()=>({uid:(await window.wb.account.profile())?.uid,ids:((await window.wb.models.list())?.items??[]).map(m=>m.id)}))()");
        sample.uid_present=!!identity?.uid;sample.model_count=identity?.ids?.length??0;
        sample.custom_model_available=identity?.ids?.includes('custom-local:xopglm52')===true;
        if(identity?.uid&&hash(String(identity.uid))!==scope.account_fingerprint)throw Error('WB_UNIT_MODEL_ACCOUNT_MISMATCH');
      }catch(error){
        if(/ACCOUNT_MISMATCH/.test(error.message))throw error;
        if(/WebSocket|连接已关闭|连接失败|connection.*closed|target.*closed/i.test(error.message)){
          ui?.close();ui=null;sample.read_error='startup-connection-closed';
        }else if(/主页面数量异常：0/.test(error.message))sample.read_error='startup-target-not-ready';
        else if(/超时|context|Context|not ready|not defined|No handler|Cannot read properties/i.test(error.message)){
          sample.read_error=/超时/.test(error.message)?'timeout':'startup-context-or-rpc-not-ready';
          // These are metadata reads only. Retire a pre-hydration CDP session;
          // never reconnect by replaying a preference write or page reload.
          ui?.close();ui=null;
        }
        else throw error;
      }
      samples.push(sample);const state=JSON.stringify([sample.uid_present,sample.custom_model_available,sample.read_error]);
      if(state!==lastState){onProgress({event:'model_metadata_observed',...sample});lastState=state}
      if(sample.uid_present&&sample.custom_model_available)break;
      await new Promise(ok=>setTimeout(ok,500));
    }
    if(!identity?.uid||!identity.ids?.includes('custom-local:xopglm52'))throw Error('WB_UNIT_MODEL_METADATA_WAIT_TIMEOUT');
    const before=await readWorkBuddyUi(ui);
    if(before.editor_nonempty_count||before.busy_control_count||before.selected_conversation_id)throw Error('WB_UNIT_MODEL_PREPARATION_BUSY');
    const prefs=scope.model_preferences;
    owner();
    phase='applying_model_preferences';
    await ui.evaluate(`(()=>{const uid=${JSON.stringify(String(identity.uid))},p=${JSON.stringify(prefs)},id='custom-local:xopglm52';
      localStorage.setItem('cb-newtask:model:'+uid,JSON.stringify(p.selection));
      if(p.thinking!==null)localStorage.setItem('cb-thinking-pref:by-model:'+uid,JSON.stringify({[id]:p.thinking}));
      if(p.effort!==null)localStorage.setItem('cb-effort:by-model:'+uid,JSON.stringify({[id]:p.effort}));return true})()`);
    phase='reload_after_applied_preferences';
    await ui.send('Page.reload',{ignoreCache:false});let after;
    const end=Date.now()+30000;
    while(Date.now()<end){
      try{after=await readWorkBuddyUi(ui);if(after.model==='xopglm52'&&!after.editor_nonempty_count&&!after.busy_control_count)break}catch{}
      await new Promise(ok=>setTimeout(ok,200));
    }
    if(after?.model!=='xopglm52')throw Error('WB_UNIT_MODEL_UI_NOT_READY');
    owner();
    const receipt={at:new Date().toISOString(),before,after,metadata_observations:samples,
      catalog_id:'custom-local:xopglm52',wire_model:'xopglm52',account_fingerprint:scope.account_fingerprint,
      model_preferences:prefs,provider_configuration_source_sha256:scope.imported_provider_configuration.source_sha256,
      model_prompts_sent:0,native_request_model_not_yet_observed:true,application_admitted:false};
    fs.writeFileSync(file,JSON.stringify(receipt,null,2)+'\n',{flag:'wx',mode:0o600});return receipt;
  }catch(error){
    fs.writeFileSync(scope.root+'/model-preparation-observations-failed-'+Date.now()+'.json',JSON.stringify({at:new Date().toISOString(),
      phase,reason:error.message,samples,model_prompts_sent:0,application_admitted:false},null,2)+'\n',{flag:'wx',mode:0o600});
    throw error;
  }finally{for(const replacement of replacements)replacement.close()}
}
