/** Reversible settings validation for the evaluated desktop clients only. */
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, open, readFile, writeFile, chmod } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { WorkBuddyCdpClient } from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
import { requireGui } from './common.mjs';
import { assertWorkBuddyNativeIdle } from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/execute.mjs';

export const TARGETS = Object.freeze({
  WorkBuddy: { port: 9229, title: 'WorkBuddy', app: '/Applications/WorkBuddy.app', keys: ['generate'] },
  QwenWork: { port: 9250, title: '千问办公', app: '/Applications/QwenWorkCN.app', keys: ['automatic', 'awareness'] },
  DoubaoWork: { port: 9260, title: '豆包工作', app: '/Applications/DoubaoWork.app', keys: ['enabled'] },
});
export function targetFor(harness) {
  if (!Object.hasOwn(TARGETS, harness)) throw Error('CONFIG_TARGET_NOT_ALLOWED');
  return TARGETS[harness];
}
export function selectClientPage(pages,harness){
  const target=targetFor(harness);
  const matches=pages.filter(p=>p.type==='page'&&(harness==='DoubaoWork'
    ? /^(?:chrome|doubaowork):\/\/doubaowork-chat\/chat(?:[/?#]|$)/.test(p.url||'') : p.title===target.title));
  if(matches.length!==1)throw Error('CONFIG_CLIENT_PAGE_AMBIGUOUS');
  return matches[0];
}
const digest = value => createHash('sha256').update(value).digest('hex');
const pause = ms => new Promise(ok => setTimeout(ok, ms));
const DOM = `
const visible=e=>e instanceof Element&&e.getBoundingClientRect().width>0&&getComputedStyle(e).visibility!=='hidden';
const all=s=>[...document.querySelectorAll(s)].filter(visible);
const panel=h==='WorkBuddy'?document.querySelector('.memory-settings-panel'):
  h==='QwenWork'?all('[role=dialog]').find(e=>e.innerText.includes('意识模式')):
  all('[data-testid="settings_modal"]').find(e=>e.innerText.includes('管理记忆'));
const candidates=panel?[...panel.querySelectorAll('[role=switch]')].filter(visible):[];
const pick=k=>{
  const matches=candidates.filter(e=>{
    if(h==='WorkBuddy'||h==='DoubaoWork')return true;
    const t=e.parentElement?.parentElement?.innerText||'';
    return k==='awareness'?t.startsWith('意识模式'):t.startsWith('自动记忆');
  });
  if(matches.length!==1)throw Error('CONFIG_SWITCH_AMBIGUOUS:'+k+':'+matches.length);
  return matches[0];
};
const value=e=>e.tagName==='INPUT'?e.checked:e.getAttribute('aria-checked')==='true';
`;
function expression(harness, body) { return `(()=>{const h=${JSON.stringify(harness)};${DOM}${body}})()`; }

async function readSettings(client, harness) {
  return client.evaluate(expression(harness, `
    if(!panel||candidates.length===0)return {ready:false};
    const keys=${JSON.stringify(targetFor(harness).keys)};
    const observed=k=>{
      try{return value(pick(k));}catch(error){
        if(h==='QwenWork'&&k==='automatic'&&value(pick('awareness'))===false)return null;
        throw error;
      }
    };
    return {ready:true,values:Object.fromEntries(keys.map(k=>[k,observed(k)])),
      settings_scope:h==='QwenWork'?'local-awareness-main':'current-account',
      memory_data_deleted:false};`));
}
async function clickSwitch(client, harness, key) {
  await requireGui();
  await client.send('Page.bringToFront');
  await client.evaluate(expression(harness, `const e=pick(${JSON.stringify(key)});e.scrollIntoView({block:'center'});return true;`));
  await pause(250);
  const point = await client.evaluate(expression(harness, `
    const e=pick(${JSON.stringify(key)});const surface=e.tagName==='INPUT'?(e.closest('label')||e):e;
    const r=surface.getBoundingClientRect();
    const x=r.left+r.width/2,y=r.top+r.height/2,hit=document.elementFromPoint(x,y);
    if(!hit||!surface.contains(hit)||e.disabled)throw Error('CONFIG_SWITCH_NOT_REACHABLE');
    return {x,y};`));
  if(harness==='QwenWork') {
    // This release applies switch clicks but can leave Input mouse acknowledgements
    // pending. The exact DOM switch is reversible and is verified after its handler.
    await client.evaluate(expression(harness,`pick(${JSON.stringify(key)}).click();return true;`));
    return;
  }
  for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased']) {
    await client.send('Input.dispatchMouseEvent', {type, ...point, button: type==='mouseMoved'?'none':'left', clickCount:1});
  }
}
async function waitValue(client, harness, key, expected) {
  let last;
  for(let i=0;i<40;i++) {
    last=await readSettings(client,harness);
    if(last.ready&&last.values[key]===expected) { await pause(250); return readSettings(client,harness); }
    await pause(100);
  }
  throw Error('CONFIG_READBACK_TIMEOUT:'+JSON.stringify(last));
}
async function connect(harness) {
  const target=targetFor(harness);
  await requireGui();
  const pids=execFileSync('/usr/sbin/lsof',['-nP',`-iTCP:${target.port}`,'-sTCP:LISTEN','-t'],{encoding:'utf8'})
    .trim().split(/\s+/).filter(Boolean);
  if(new Set(pids).size!==1)throw Error('CONFIG_ENDPOINT_OWNER_AMBIGUOUS');
  const command=execFileSync('/bin/ps',['-p',pids[0],'-o','command='],{encoding:'utf8'}).trim();
  if(!command.startsWith(target.app+'/Contents/'))throw Error('CONFIG_ENDPOINT_OWNER_MISMATCH');
  const pages=await (await fetch(`http://127.0.0.1:${target.port}/json/list`,{signal:AbortSignal.timeout(3000)})).json();
  const page=selectClientPage(pages,harness);
  const client=await WorkBuddyCdpClient.connect(page.webSocketDebuggerUrl,6000);
  return {client,identity:{harness,pid:Number(pids[0]),app:target.app,endpoint_port:target.port,
    command_sha256:digest(command),page_id:page.id}};
}
const DOUBAO_MEMORY_ENTRY = String.raw`(()=>{const panel=document.querySelector('[data-testid="settings_modal"]');if(!panel)return false;
  const labels=[...panel.querySelectorAll('div,span')].filter(e=>!e.children.length&&e.getClientRects().length&&e.innerText.trim()==='记忆');
  if(labels.length!==1)return false;let e=labels[0];for(let i=0;e&&e!==panel&&i<8;i++,e=e.parentElement){
    const text=e.innerText.replace(/\s/g,'');const key=Object.keys(e).find(k=>k.startsWith('__reactProps$'));
    if(['记忆已启用','记忆已关闭','记忆已开启','记忆已禁用'].includes(text)&&typeof e[key]?.onClick==='function'){e.click();return true;}
  }return false})()`;
const DOUBAO_ACCOUNT_POINT = String.raw`(()=>{const update=document.querySelector('[data-testid="new_chat_button"][aria-label="完成更新"]');
  if(!update)return null;const buttons=[...update.parentElement.querySelectorAll('button[aria-haspopup="menu"]')].filter(e=>e.getClientRects().length);
  if(buttons.length!==1)return null;const e=buttons[0],r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
  if(!e.contains(document.elementFromPoint(x,y)))return null;return {x,y,open:e.getAttribute('data-state')==='open'||e.getAttribute('aria-expanded')==='true'}})()`;
const DOUBAO_SETTINGS_MENU = String.raw`(()=>{const es=[...document.querySelectorAll('[role="menuitem"]')].filter(e=>e.getClientRects().length);
  const matches=(e,names)=>names.includes(e.innerText.trim())||[...e.querySelectorAll('*')].some(c=>!c.children.length&&names.includes(c.textContent.trim()));
  const memory=es.filter(e=>matches(e,['管理记忆','记忆管理','记忆'])),settings=es.filter(e=>matches(e,['设置']));
  const target=memory.length===1?memory:settings;if(target.length!==1)return false;target[0].click();return true})()`;
async function waitMemoryPanel(client,harness){
  let entered=false;
  for(let i=0;i<40;i++){
    if((await readSettings(client,harness)).ready)return;
    if(harness==='DoubaoWork'&&!entered)entered=await client.evaluate(DOUBAO_MEMORY_ENTRY);
    await pause(100);
  }
  throw Error('CONFIG_MEMORY_PANEL_NOT_READY');
}
async function openSettings(client,harness) {
  if((await readSettings(client,harness)).ready)return;
  if(harness==='DoubaoWork'&&await client.evaluate(`Boolean([...document.querySelectorAll('[data-testid="settings_modal"]')].find(e=>e.getClientRects().length))`)){
    await waitMemoryPanel(client,harness);return;
  }
  if(harness==='WorkBuddy') {
    await client.evaluate(`(()=>{location.hash='settings/memory';return true})()`);
  } else {
    const clicked=await client.evaluate(`(()=>{const es=[...document.querySelectorAll('button')].filter(e=>
      e.getBoundingClientRect().width>0&&['设置','Settings'].includes(e.getAttribute('aria-label')||e.title));
      if(es.length!==1)return false;es[0].click();return true})()`);
    if(!clicked&&harness==='DoubaoWork'){
      let point=await client.evaluate(DOUBAO_ACCOUNT_POINT);
      if(!point)throw Error('CONFIG_SETTINGS_ENTRY_NOT_VISIBLE');
      const click=async p=>{for(const type of ['mouseMoved','mousePressed','mouseReleased'])await client.send('Input.dispatchMouseEvent',{
        type,x:p.x,y:p.y,button:type==='mouseMoved'?'none':'left',clickCount:1});};
      if(!point.open)await click(point);
      let selected=false,retried=false;
      for(let i=0;i<30;i++){
        selected=await client.evaluate(DOUBAO_SETTINGS_MENU);if(selected)break;
        // Menu navigation is idempotent only while the exact trigger is closed.
        if(i===10&&!retried){point=await client.evaluate(DOUBAO_ACCOUNT_POINT);
          if(point&&!point.open){await client.send('Page.bringToFront');await click(point);retried=true;}}
        await pause(100);
      }
      if(!selected)throw Error('CONFIG_MEMORY_SETTINGS_MENU_UNVERIFIED');
    }else if(!clicked)throw Error('CONFIG_SETTINGS_ENTRY_NOT_VISIBLE');
  }
  await waitMemoryPanel(client,harness);
}
export async function roundtripValues({read,change,log,keys}) {
  const baseline=await read();
  if(!baseline.ready)throw Error('CONFIG_BASELINE_NOT_READY');
  const changed=[];
  let failure=null;
  try {
    for(const key of keys) {
      const current=await read();
      if(JSON.stringify(current.values)!==JSON.stringify(baseline.values))throw Error('CONFIG_BASELINE_DRIFT');
      const desired=!baseline.values[key];
      await log({kind:'SWITCH_INTENT',key,before:baseline.values[key],desired});
      changed.push({key,desired});
      await change(key,desired);
      const after=await read();
      if(after.values[key]!==desired)throw Error('CONFIG_MUTATION_NOT_OBSERVED');
      await log({kind:'SWITCH_VERIFIED',key,values:after.values});
      await log({kind:'RESTORE_INTENT',key,desired:baseline.values[key]});
      await change(key,baseline.values[key]);
      const restored=await read();
      if(JSON.stringify(restored.values)!==JSON.stringify(baseline.values))throw Error('CONFIG_RESTORE_MISMATCH');
      changed.pop();
      await log({kind:'RESTORE_VERIFIED',key,values:restored.values});
    }
  } catch(error) { failure=error; }
  // A failed click may still have taken effect. Re-read and restore only our known value.
  for(const {key,desired} of changed.reverse()) {
    const current=await read();
    if(current.values[key]===desired) {
      await log({kind:'RECOVERY_RESTORE_INTENT',key,desired:baseline.values[key]});
      await change(key,baseline.values[key]);
    }
  }
  const final=await read();
  const restored=JSON.stringify(final.values)===JSON.stringify(baseline.values);
  await log({kind:'FINAL_STATE',restored,values:final.values,error:failure?.message??null});
  if(!restored)throw Error('CONFIG_RESTORE_INCOMPLETE');
  if(failure)throw failure;
  return {baseline,final,restored};
}

export async function runConfiguration(request) {
  const target=targetFor(request.harness); // Reject Codex before filesystem or transport access.
  if(!['inspect','roundtrip'].includes(request.action))throw Error('CONFIG_ACTION_NOT_ALLOWED');
  if(request.action==='roundtrip') {
    const probe=JSON.parse(await readFile(request.preflight_file,'utf8'));
    const observed=Date.parse(probe.probed_at||probe.observed_at||probe.captured_at||'');
    if(!Number.isFinite(observed)||Date.now()-observed>1800000||observed>Date.now()+5000)throw Error('CONFIG_FRESH_PREFLIGHT_REQUIRED');
    if(request.harness==='WorkBuddy') {if(probe.status!=='PASS')throw Error('CONFIG_PREFLIGHT_FAILED');assertWorkBuddyNativeIdle(probe);}
    if(request.harness==='QwenWork'&&(probe.native_state?.database?.active_or_pending_count!==0||probe.execution_environment?.verified!==true))throw Error('CONFIG_QWEN_NOT_IDLE');
    if(request.harness==='DoubaoWork'&&probe.status!=='passed')throw Error('CONFIG_DOUBAO_PREFLIGHT_FAILED');
  }
  const output=resolve(request.output_dir);
  if(!output.startsWith('/Users/gzx/debug-workspace/e2e-evaluate/memory-e2e/'))throw Error('CONFIG_EVIDENCE_ROOT');
  await mkdir(output,{recursive:true,mode:0o700});
  await chmod(output,0o700);
  const handle=await open(join(output,'owner.json'),'wx');
  await handle.writeFile(JSON.stringify({id:randomUUID(),harness:request.harness,action:request.action}));
  await handle.sync();await handle.close();
  const {client,identity}=await connect(request.harness);
  const log=async value=>{
    const f=await open(join(output,'events.jsonl'),'a');
    try{await f.writeFile(JSON.stringify({at:new Date().toISOString(),...value})+'\n');await f.sync();}finally{await f.close();}
  };
  let baseline;
  try {
    await log({kind:'IDENTITY_VERIFIED',identity});
    execFileSync('/usr/bin/open',['-a',target.app]);
    await client.send('Page.bringToFront');
    await pause(250);
    await openSettings(client,request.harness);
    const read=()=>readSettings(client,request.harness);
    baseline=await read();
    await log({kind:'BASELINE',...baseline});
    const screenshot=async name=>{const r=await client.send('Page.captureScreenshot',{format:'png'});
      await writeFile(join(output,name+'.png'),Buffer.from(r.data,'base64'),{flag:'wx'});};
    await screenshot('before');
    let result={baseline,final:baseline,restored:true};
    if(request.action==='roundtrip')result=await roundtripValues({read,keys:target.keys,log,
      change:async(key,value)=>{
        const current=await read();if(current.values[key]!==value)await clickSwitch(client,request.harness,key);
        const after=await waitValue(client,request.harness,key,value);
        if(after.values[key]!==value)throw Error('CONFIG_SETTLED_VALUE_MISMATCH');
      }});
    await screenshot('after');
    const receipt={contract:'wildclawbench.memory-config/v1',status:'PASS',...identity,action:request.action,
      ...result,verification:'ui_readback_only',memory_write_verified:false,global_memory_reset_performed:false,
      excluded_clients:['Codex'],created_at:new Date().toISOString()};
    await writeFile(join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
    return receipt;
  } catch(error) {
    const final=await readSettings(client,request.harness).catch(()=>null);
    const restored=baseline?.ready&&final?.ready?JSON.stringify(baseline.values)===JSON.stringify(final.values):null;
    const receipt={contract:'wildclawbench.memory-config/v1',status:'NEEDS_ATTENTION',...identity,
      action:request.action,baseline:baseline??null,final,restored,error:String(error.message),
      memory_write_verified:false,global_memory_reset_performed:false,excluded_clients:['Codex'],
      created_at:new Date().toISOString()};
    await writeFile(join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
    return receipt;
  } finally { client.close(); }
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href) {
  try{let input='';for await(const c of process.stdin)input+=c;console.log(JSON.stringify(await runConfiguration(JSON.parse(input))));}
  catch(error){console.error(error.stack||error);process.exitCode=2;}
}
