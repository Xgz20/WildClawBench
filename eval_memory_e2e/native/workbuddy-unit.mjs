/* Memory-only admission for the audited current WorkBuddy. Legacy General
 * versions and source checks stay unchanged. Never dispatch through an API.
 */
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {memoryPython} from './machine.mjs';
import {WorkBuddyCdpClient,discoverWorkBuddyMainTarget,readWorkBuddyUi} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
export function attestWorkBuddyUnit(profile){
  const unit=profile.workbuddy_scope,b=profile.non_target_memory_boundary;
  if(unit?.contract!=='workbuddy-case-memory-unit/v1'||b?.admitted_adapter!=='macos-seatbelt-workbuddy-unit/v1'
    ||b.required!==true||b.status!=='os_enforced'||profile.memory_protocol?.formal_scoring_allowed!==false)
    throw Error('WORKBUDDY_UNIT_NOT_ADMITTED');
  const helper=fileURLToPath(new URL('../workbuddy_scope.py',import.meta.url));
  const proof=JSON.parse(execFileSync(memoryPython(),[helper,'attest','--scope',unit.scope,'--frozen-json',JSON.stringify(unit),
    '--boundary-json',JSON.stringify(b)],{encoding:'utf8',timeout:30000,maxBuffer:2097152}));
  if(proof.status!=='PASS'||proof.unit_id!==unit.unit_id)throw Error('WORKBUDDY_UNIT_OS_PROOF');
  return proof;
}
export async function connectWorkBuddyUnit(profile,frozen=null){
  const proof=attestWorkBuddyUnit(profile),unit=profile.workbuddy_scope,spec=JSON.parse(fs.readFileSync(unit.scope));
  const endpoint='http://127.0.0.1:'+spec.ports.ui;
  const owner=execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+spec.ports.ui,'-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim();
  if(owner!==String(proof.main_pid))throw Error('WORKBUDDY_UNIT_UI_OWNER');
  const target=await discoverWorkBuddyMainTarget(endpoint,5000);
  if(new URL(target.url).pathname!=='/Applications/WorkBuddy.app/Contents/Resources/app.asar/renderer/index.html')throw Error('WORKBUDDY_UNIT_RENDERER');
  const client=await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl,30000);
  try{
    const ui=await readWorkBuddyUi(client);
    const identity=await client.evaluate(`(async()=>{const p=await window.wb.account.profile(),ids=((await window.wb.models.list())?.items??[]).map(m=>m.id);const pref=JSON.parse(localStorage.getItem('cb-newtask:model:'+p?.uid)??'null');return {uid:p?.uid,ids,pref}})()`);
    if(!identity.uid||sha(String(identity.uid))!==unit.account_fingerprint||!identity.ids.includes('custom-local:xopglm52'))throw Error('WORKBUDDY_UNIT_ACCOUNT_MODEL');
    if(identity.pref?.id!=='custom-local:xopglm52'||identity.pref?.isThinking!==spec.model_preferences.selection.isThinking
      ||identity.pref?.reasoningEffort!==spec.model_preferences.selection.reasoningEffort)throw Error('WORKBUDDY_UNIT_MODEL_PREFERENCE_DRIFT');
    const config={app_version:spec.installation.version,model_display:ui.model??frozen?.model_display,
      permissions:ui.permission??frozen?.permissions,underlying_model:'xopglm52',account_fingerprint:unit.account_fingerprint};
    return {client,ui,config,proof,scoped:true,config_basis:ui.model?'scoped_visible_ui_and_frozen_custom_provider':'scoped_frozen_ui_and_native_requested_model',
      report:{status:'PASS',application:{version:spec.installation.version},process:{running:true,pid:proof.main_pid},
        cdp:{status:'observed'},native_sources:{session_index:{status:'observed',sessions:proof.native_metadata.sessions}}}};
  }catch(error){client.close();throw error}
}
