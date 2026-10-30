import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtemp,rm,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {openExactProjectConversation} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';

async function fixture(mode){
 const temp=await realpath(await mkdtemp(join(tmpdir(),'astron-route-'))),workspace=join(temp,'workspace'),path=join(temp,'state.sqlite');
 const db=new DatabaseSync(path);
 db.exec(`CREATE TABLE projection_projects(project_id TEXT,workspace_root TEXT,deleted_at TEXT);
 CREATE TABLE projection_threads(thread_id TEXT,project_id TEXT,latest_turn_id TEXT,deleted_at TEXT);
 CREATE TABLE projection_thread_messages(thread_id TEXT); CREATE TABLE projection_turns(thread_id TEXT);
 CREATE TABLE projection_thread_sessions(thread_id TEXT); CREATE TABLE projection_pending_interactions(thread_id TEXT,status TEXT);`);
 db.prepare('INSERT INTO projection_projects VALUES(?,?,NULL)').run('target',workspace);
 db.prepare('INSERT INTO projection_projects VALUES(?,?,NULL)').run('old',join(temp,'other'));
 db.exec("INSERT INTO projection_threads VALUES('old-route','old',NULL,NULL)");
 db.prepare('INSERT INTO projection_threads VALUES(?,?,NULL,NULL)').run('target-route',['wrong-native-after-click','native-binding-delayed'].includes(mode)?'old':'target');
 if(mode==='used-target')db.exec("INSERT INTO projection_thread_messages VALUES('target-route')");
 db.close();let editorReads=0,workspaceReads=0,clicked=0,route=mode==='same-pristine-route'?'target-route':'old-route';const sends=[];
 const client={send:async(name)=>{sends.push(name)},evaluate:async text=>{
  if(text.includes('link_chips:')){
   editorReads++;if(mode==='route-changed'&&editorReads>=2)route='target-route';
   if(mode==='native-binding-delayed'&&clicked&&editorReads>=6){const update=new DatabaseSync(path);update.exec("UPDATE projection_threads SET project_id='target' WHERE thread_id='target-route'");update.close();}
   return {thread_id:route,editor_count:1,editor_text:'',link_chips:[]};
  }
  if(text.includes('dialog_count:'))return {editor_count:1,editor_empty:mode!=='foreign-draft',dialog_count:0,stop_count:0};
  if(text.includes('workspace-picker-trigger')){
   workspaceReads++;return {count:1,path:mode==='same-pristine-route'&&workspaceReads===1?join(temp,'other'):workspace,menu_open:false,label:'workspace'};
  }
  if(text.includes('viewport_width'))return {count:1,x:20,y:20,viewport_width:100,viewport_height:100};
  if(text.includes('scrollIntoView'))return null;
  if(text.includes('buttons[0].click()')){clicked++;route='target-route';return {clicked:true,rows:1,buttons:1};}
  if(text.includes('interactive:'))return {count:1,interactive:true};
  if(text.includes('inert:'))return {count:1,inert:false,hidden:null};
  throw Error('Unexpected readonly UI query');
 }};
 return {temp,workspace,path,client,clicks:()=>clicked,sends};
}

test('a late route switch uses the fresh exact native route without clicking another conversation',async()=>{
 const f=await fixture('route-changed');try{const value=await openExactProjectConversation(f.client,f.workspace,f.path,500,{forceNew:true});assert.equal(value.thread_id,'target-route');assert.equal(value.project_id,'target');assert.equal(f.clicks(),0);assert.equal(f.sends.length,0);}finally{await rm(f.temp,{recursive:true,force:true})}
});
test('picker path with an old pristine native project navigates the exact target New conversation',async()=>{
 const f=await fixture('wrong-pristine-project');try{const value=await openExactProjectConversation(f.client,f.workspace,f.path,500,{forceNew:true});assert.equal(value.thread_id,'target-route');assert.equal(value.project_id,'target');assert.equal(f.clicks(),1);assert.deepEqual(f.sends,['Input.dispatchMouseEvent']);}finally{await rm(f.temp,{recursive:true,force:true})}
});
test('a delayed picker may settle on the same exact unused native route after New conversation',async()=>{
 const f=await fixture('same-pristine-route');try{const value=await openExactProjectConversation(f.client,f.workspace,f.path,500,{forceNew:true});assert.equal(value.thread_id,'target-route');assert.equal(value.method,'native-pristine-project-conversation');assert.equal(value.project_id,'target');assert.equal(f.clicks(),1);assert.deepEqual(f.sends,['Input.dispatchMouseEvent']);}finally{await rm(f.temp,{recursive:true,force:true})}
});
test('UI route and absolute path wait for a delayed exact native project binding before admission',async()=>{
 const f=await fixture('native-binding-delayed');try{const value=await openExactProjectConversation(f.client,f.workspace,f.path,3000,{forceNew:true});assert.equal(value.thread_id,'target-route');assert.equal(value.project_id,'target');assert.equal(f.clicks(),1);assert.deepEqual(f.sends,['Input.dispatchMouseEvent']);}finally{await rm(f.temp,{recursive:true,force:true})}
});
for(const mode of ['foreign-draft','wrong-native-after-click','used-target'])test('unsafe route remains blocked: '+mode,async()=>{
 const f=await fixture(mode);try{await assert.rejects(openExactProjectConversation(f.client,f.workspace,f.path,500,{forceNew:true}),/AstronStudio/);if(mode==='foreign-draft')assert.equal(f.clicks(),0);}finally{await rm(f.temp,{recursive:true,force:true})}
});
