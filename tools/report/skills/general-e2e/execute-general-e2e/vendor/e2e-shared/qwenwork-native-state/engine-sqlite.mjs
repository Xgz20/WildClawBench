import { createHash } from 'node:crypto';
import { isAbsolute, resolve } from 'node:path';
import { lstat, realpath } from 'node:fs/promises';
import { querySnapshot } from './index.mjs';
export const QWEN_ENGINE_PROFILE = 'qwenwork-opencode-sqlite-v1';
const sha = x => createHash('sha256').update(x).digest('hex');
const sqlId = x => { if (!/^[A-Za-z0-9._:-]+$/u.test(x || '')) throw Error('QWEN_ENGINE_ID_INVALID'); return `'${x}'`; };
const json = x => typeof x === 'string' ? JSON.parse(x) : x;
const require = (ok, error) => { if (!ok) throw Error('QWEN_ENGINE_' + error); };
export function verifyQwenEngineEvidence(evidence, {session, prompt, terminal = false}) {
  require(evidence?.profile === QWEN_ENGINE_PROFILE, 'PROFILE_INVALID');
  const host=evidence.host.record, binding=json(host.sub_chat_ext).engineSessionBindingV1;
  const route=json(host.sub_chat_ext).modelExecutionRouteV2;
  require(host.session_id===session.session_id && host.conversation_id===session.conversation_id
    && host.sub_chat_id===session.sub_chat_id && host.local_project_id===session.local_project_id
    && resolve(host.cwd)===resolve(session.cwd), 'HOST_BINDING_MISMATCH');
  require(binding?.version===1 && binding.engineId==='opencode' && route?.version===2
    && route.engineId==='opencode' && route.modelId==='flash' && route.modeKey==='flash'
    && binding.hostSessionId===host.session_id && binding.subChatId===host.sub_chat_id
    && binding.executionLocationKey==='local' && resolve(binding.workingDirectory)===resolve(host.cwd)
    && binding.storageNamespace===evidence.native.snapshot.database_path, 'ROUTE_BINDING_MISMATCH');
  const root=evidence.native.sessions.filter(x=>x.id===binding.nativeSessionId);
  require(root.length===1 && root[0].parent_id===null && root[0].version==='1.18.18-26102004'
    && resolve(root[0].directory)===resolve(host.cwd), 'SESSION_BINDING_MISMATCH');
  const ids=new Set([root[0].id]);
  for (let changed=true;changed;) { changed=false;for(const row of evidence.native.sessions) if(ids.has(row.parent_id)&&!ids.has(row.id)){ids.add(row.id);changed=true;} }
  require(ids.size===evidence.native.sessions.length && evidence.native.sessions.every(x=>resolve(x.directory)===resolve(host.cwd)), 'CHILD_SCOPE_MISMATCH');
  const inputs=evidence.host.inputs.filter(x=>x.chat_id===host.conversation_id && x.sub_chat_id===host.sub_chat_id);
  require(inputs.length===1 && ['consumed','accepted'].includes(inputs[0].state), 'INPUT_COUNT_OR_STATE_INVALID');
  const params=json(inputs[0].content).params;
  require(params?.chatId===host.conversation_id && params?.subChatId===host.sub_chat_id
    && params.userMessageId===inputs[0].message_id, 'ADMITTED_PROMPT_MISMATCH');
  const publicUsers=evidence.host.messages.filter(x=>x.role==='user');
  require(publicUsers.length===1 && publicUsers[0].message_id===params.userMessageId,'HOST_USER_ID_MISMATCH');
  const publicParts=json(publicUsers[0].parts).filter(x=>x.type==='text');
  require(publicParts.length===1 && sha(publicParts[0].text || '')===prompt.sha256
    && (params.prompt==='' || params.prompt===publicParts[0].text), 'HOST_USER_PROMPT_MISMATCH');
  const messages=evidence.native.messages.map(x=>({...x,parsed:json(x.data)}));
  require(messages.every(x=>ids.has(x.session_id)) && new Set(messages.map(x=>x.id)).size===messages.length, 'MESSAGE_SCOPE_INVALID');
  const msgMap=new Map(messages.map(x=>[x.id,x]));
  const parts=evidence.native.parts.map(x=>({...x,parsed:json(x.data)}));
  require(parts.every(x=>ids.has(x.session_id)&&msgMap.get(x.message_id)?.session_id===x.session_id)
    && new Set(parts.map(x=>x.id)).size===parts.length, 'PART_SCOPE_INVALID');
  const user=messages.filter(x=>x.session_id===root[0].id && x.parsed.role==='user');
  require(user.length===1, 'USER_MESSAGE_COUNT_INVALID');
  const userParts=parts.filter(x=>x.message_id===user[0].id && x.parsed.type==='text');
  require(userParts.length===1 && typeof userParts[0].parsed.text==='string', 'USER_PART_COUNT_INVALID');
  const nativeText=userParts[0].parsed.text, promptText=publicParts[0].text;
  require(nativeText.endsWith(promptText) && nativeText.split(promptText).length===2
    && (nativeText===promptText || nativeText.startsWith('<workspace_context>\n') && nativeText.includes(host.cwd)), 'NATIVE_PROMPT_MISMATCH');
  const assistant=messages.filter(x=>x.session_id===root[0].id && x.parsed.role==='assistant').sort((a,b)=>a.time_created-b.time_created || a.id.localeCompare(b.id));
  const last=assistant.at(-1);
  if(terminal){
    require(!host.stream_id && ['ready','completed','finished','done'].includes(host.native_status), 'HOST_NOT_COMPLETE');
    require(last?.parsed.finish==='stop' && Number.isSafeInteger(last.parsed.time?.completed), 'FINAL_MESSAGE_NOT_COMPLETE');
    require(parts.filter(x=>x.parsed.type==='tool').every(x=>['completed','error'].includes(x.parsed.state?.status)), 'TOOL_NOT_TERMINAL');
    for(const id of ids){const rows=messages.filter(x=>x.session_id===id&&x.parsed.role==='assistant').sort((a,b)=>a.time_created-b.time_created||a.id.localeCompare(b.id));require(rows.at(-1)?.parsed.finish==='stop','CHILD_NOT_COMPLETE');}
  }
  for(const snapshot of [evidence.host.snapshot,evidence.native.snapshot]) require(snapshot?.method==='readonly-source-sqlite-online-backup'
    && snapshot.quick_check==='ok' && /^[a-f0-9]{64}$/u.test(snapshot.snapshot_sha256||'')
    && /^[a-f0-9]{64}$/u.test(snapshot.query_sha256||'') && isAbsolute(snapshot.database_path||''), 'SNAPSHOT_PROVENANCE_INVALID');
  return {binding,route,root:root[0],messages,parts,final_message:last,match_count:1,prompt_sha256:prompt.sha256};
}
export async function captureQwenEngineEvidence({sessionDatabase, session, prompt, terminal=false}) {
  const sid=sqlId(session.session_id), chat=sqlId(session.conversation_id), sub=sqlId(session.sub_chat_id);
  const hostQuery=`SELECT json_object('record',(SELECT json_object('session_id',s.session_id,'conversation_id',c.id,'sub_chat_id',s.id,'local_project_id',c.local_project_id,'cwd',json_extract(p.root_paths,'$[0]'),'stream_id',s.stream_id,'native_status',CASE WHEN s.stream_id IS NOT NULL THEN 'running' ELSE coalesce(json_extract(c.ext,'$.taskStatus'),'ready') END,'sub_chat_ext',s.ext) FROM sub_chats s JOIN chats c ON c.id=s.chat_id JOIN local_projects p ON p.id=c.local_project_id WHERE s.id=${sub} AND c.id=${chat} AND s.session_id=${sid} AND c.deleted_at IS NULL),'inputs',(SELECT json_group_array(json_object('id',id,'message_id',message_id,'chat_id',chat_id,'sub_chat_id',sub_chat_id,'state',state,'content',content,'created_at',created_at,'accepted_at',accepted_at)) FROM agent_turn_inputs WHERE chat_id=${chat} AND sub_chat_id=${sub}),'messages',(SELECT json_group_array(json_object('message_id',message_id,'role',role,'parts',parts,'metadata',metadata,'created_at',created_at,'updated_at',updated_at)) FROM messages WHERE chat_id=${chat} AND sub_chat_id=${sub})) AS payload;`;
  const h=await querySnapshot(sessionDatabase,hostQuery,{consistentOnlineBackup:true,captureEvidence:true});
  require(h.rows.length===1,'HOST_ROW_COUNT_INVALID');const host=json(h.rows[0].payload);require(host.record,'HOST_RECORD_MISSING');
  const binding=json(host.record.sub_chat_ext).engineSessionBindingV1;
  require(binding?.engineId==='opencode' && isAbsolute(binding.storageNamespace||''),'ENGINE_ROUTE_UNSUPPORTED');
  const database=await realpath(binding.storageNamespace);
  require(database===resolve(process.env.HOME,'.qwenworkcn/.harness/flash-cli/qwenwork/qwenwork.db'), 'DATABASE_PATH_UNSUPPORTED');
  const info=await lstat(binding.storageNamespace);require(info.isFile()&&!info.isSymbolicLink(),'DATABASE_UNSAFE');
  const nativeId=sqlId(binding.nativeSessionId);
  // Only the bound session subtree is exported. Credential/account tables are never selected.
  const query=`WITH RECURSIVE scope(id) AS (SELECT id FROM session WHERE id=${nativeId} UNION ALL SELECT s.id FROM session s JOIN scope x ON s.parent_id=x.id) SELECT json_object('sessions',(SELECT json_group_array(json_object('id',id,'parent_id',parent_id,'directory',directory,'version',version,'model',model,'time_created',time_created,'time_updated',time_updated)) FROM session WHERE id IN scope),'messages',(SELECT json_group_array(json_object('id',id,'session_id',session_id,'time_created',time_created,'time_updated',time_updated,'data',data)) FROM (SELECT * FROM message WHERE session_id IN scope ORDER BY time_created,id)),'parts',(SELECT json_group_array(json_object('id',id,'message_id',message_id,'session_id',session_id,'time_created',time_created,'time_updated',time_updated,'data',data)) FROM (SELECT * FROM part WHERE session_id IN scope ORDER BY time_created,id))) AS payload;`;
  const n=await querySnapshot(database,query,{consistentOnlineBackup:true,captureEvidence:true});
  require(n.rows.length===1,'NATIVE_ROW_COUNT_INVALID');const native=json(n.rows[0].payload);
  const evidence={profile:QWEN_ENGINE_PROFILE,host:{...host,snapshot:h.snapshot},native:{...native,snapshot:n.snapshot}};
  verifyQwenEngineEvidence(evidence,{session,prompt,terminal});return evidence;
}
