/* Hidden workspace controls require an exact native binding, never a guess. */
import {readFile,readdir,realpath} from 'node:fs/promises';
import {DatabaseSync} from 'node:sqlite';
import {queryNativeSessions,queryProjectForThread} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';

export function assertNativeContinuationBinding(binding,expected){
  const {sessions,projects}=binding;
  const selected=sessions.filter(row=>row.thread_id===expected.thread_id);
  if(selected.length!==1||projects.length!==1)throw Error('ASTUDIO_CONTINUATION_AMBIGUOUS');
  const row=selected[0],project=projects[0];
  const terminal=row.status==='completed'||staleRunningProjectionHasTerminalWitness(row,binding.terminal_events??[]);
  if(row.session_id!==expected.session_id||row.turn_id!==expected.previous_turn_id||row.latest_turn_id!==row.turn_id
    ||row.cwd!==expected.workspace||!terminal||row.turn_state!=='completed'||row.active_turn_id
    ||row.session_status!=='ready'||project.project_id!==expected.project_id||project.workspace_root!==expected.workspace)
    throw Error('ASTUDIO_CONTINUATION_BINDING_CHANGED');
  return {session:row,project};
}

async function scopedRolloutEvents(row,paths){
  const matches=[];
  for(const home of [paths.acode,paths.overlay])for(const name of await readdir(home)){
    if(!/^state_\d+\.sqlite$/.test(name))continue;
    const db=new DatabaseSync(home+'/'+name,{readOnly:true});
    try{matches.push(...db.prepare('SELECT rollout_path FROM threads WHERE id=?').all(row.session_id))}finally{db.close()}
  }
  if(matches.length!==1)return [];
  const file=await realpath(matches[0].rollout_path);
  if(![paths.acode,paths.overlay].some(home=>file.startsWith(home+'/sessions/')))throw Error('ASTUDIO_CONTINUATION_ROLLOUT_OUTSIDE_SCOPE');
  return (await readFile(file,'utf8')).trim().split(/\r?\n/).map(s=>JSON.parse(s));
}

export async function readNativeContinuationBinding(database,paths,expected){
  const sessions=await queryNativeSessions(database),projects=await queryProjectForThread(database,expected.thread_id);
  const row=sessions.find(r=>r.thread_id===expected.thread_id);
  const terminal_events=staleCompletedProjection(row)&&row.session_id===expected.session_id&&row.cwd===expected.workspace
    ?await scopedRolloutEvents(row,paths):[];
  return {sessions,projects,terminal_events};
}

export async function verifiedBlockingSessions(sessions,paths,allowedWorkspaces,isBlocking){
  const blocking=[],terminal=[];
  for(const row of sessions.filter(isBlocking)){
    if(allowedWorkspaces.includes(row.cwd)&&staleCompletedProjection(row)&&staleRunningProjectionHasTerminalWitness(row,await scopedRolloutEvents(row,paths)))
      terminal.push({thread_id:row.thread_id,session_id:row.session_id,turn_id:row.turn_id,basis:'completed latest native rollout plus ready session'});
    else blocking.push(row);
  }
  return {blocking,terminal};
}

export async function inspectBoundContinuation(client,prompt,expected,readBinding){
  const bound=assertNativeContinuationBinding(await readBinding(),expected);
  const observed=await client.evaluate(`(()=>{
    const expected=${JSON.stringify(prompt.trim().replaceAll('\r\n','\n'))},thread=${JSON.stringify(expected.thread_id)},cwd=${JSON.stringify(expected.workspace)};
    const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
    const route=decodeURIComponent(location.hash.match(/^#\\/([^/?#]+)/u)?.[1]||'');
    const editors=[...document.querySelectorAll('[data-testid="composer-editor"]')].filter(visible);
    const workspaces=[...document.querySelectorAll('[data-testid="workspace-picker-trigger"], [data-testid="project-picker-trigger"]')].filter(visible);
    const buttons=[...document.querySelectorAll('button[type="submit"][aria-label="发送消息"],button[type="submit"][aria-label="Send message"]')].filter(visible).filter(e=>!e.disabled);
    const dialogs=[...document.querySelectorAll('[role="dialog"], [aria-modal="true"]')].filter(visible);
    const chips=editors.length===1?[...editors[0].querySelectorAll('[role="link"][contenteditable="false"]')]:[];
    const promptMatches=editors.length===1&&(editors[0].innerText||'').trim().replaceAll('\\r\\n','\\n')===expected;
    if(route!==thread||editors.length!==1||!promptMatches||chips.length||dialogs.length||buttons.length!==1||workspaces.length>1
      ||(workspaces.length===1&&workspaces[0].getAttribute('title')!==cwd))return {ready:false,reason:'bound-continuation-dom-changed'};
    const button=buttons[0],form=button.form,rect=button.getBoundingClientRect(),x=rect.left+rect.width/2,y=rect.top+rect.height/2;
    const hit=document.elementFromPoint(x,y);
    if(!form||editors[0].closest('form')!==form||!form.checkValidity()||!hit||!button.contains(hit))return {ready:false,reason:'bound-continuation-form-or-hit'};
    return {ready:true,count:1,x,y,thread_id:thread,workspace_count:workspaces.length};
  })()`);
  return {...observed,native_binding:bound,workspace_verification:'exact-native-session-and-project'};
}

function staleCompletedProjection(row){
  return row?.status==='running'&&row.turn_state==='completed'&&row.session_status==='ready'&&!row.active_turn_id
    &&!!row.completed_at&&!row.error&&!!row.turn_id&&row.latest_turn_id===row.turn_id;
}
export function staleRunningProjectionHasTerminalWitness(row,events){
  if(!staleCompletedProjection(row))return false;
  const started=events.findLastIndex(r=>r.type==='event_msg'&&r.payload?.type==='task_started');
  return started>=0&&events[started].payload.turn_id===row.turn_id
    &&events.slice(started+1).some(r=>r.type==='event_msg'&&r.payload?.type==='task_complete'&&r.payload.turn_id===row.turn_id);
}
