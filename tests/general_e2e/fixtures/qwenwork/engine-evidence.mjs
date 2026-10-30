import {createHash} from 'node:crypto';
const sha=x=>createHash('sha256').update(x).digest('hex');
const QWEN_ENGINE_PROFILE='qwenwork-opencode-sqlite-v1';
export function fixture(){
 const session={session_id:'host',conversation_id:'chat',sub_chat_id:'sub',local_project_id:'project',cwd:'/work'};
 const binding={version:1,engineId:'opencode',hostSessionId:'host',subChatId:'sub',workingDirectory:'/work',executionLocationKey:'local',storageNamespace:'/native.db',nativeSessionId:'root'};
 const snapshot={method:'readonly-source-sqlite-online-backup',quick_check:'ok',snapshot_sha256:'a'.repeat(64),query_sha256:'b'.repeat(64),database_path:'/native.db'};
 const evidence={profile:QWEN_ENGINE_PROFILE,host:{record:{...session,stream_id:null,native_status:'ready',sub_chat_ext:JSON.stringify({engineSessionBindingV1:binding,modelExecutionRouteV2:{version:2,engineId:'opencode',modelId:'flash',modeKey:'flash'}})},inputs:[{chat_id:'chat',sub_chat_id:'sub',state:'consumed',message_id:'input',content:JSON.stringify({params:{chatId:'chat',subChatId:'sub',userMessageId:'input',prompt:''}})}],messages:[{role:'user',message_id:'input',parts:JSON.stringify([{type:'text',text:'prompt'}])}],snapshot},native:{snapshot,sessions:[{id:'root',parent_id:null,directory:'/work',version:'1.18.18-26102004'}],messages:[{id:'user',session_id:'root',time_created:1,data:JSON.stringify({role:'user'})},{id:'assistant',session_id:'root',time_created:2,data:JSON.stringify({role:'assistant',finish:'stop',time:{completed:3}})}],parts:[{id:'part',message_id:'user',session_id:'root',data:JSON.stringify({type:'text',text:'<workspace_context>\n/work\n</workspace_context>\nprompt'})}]}};
 return {evidence,options:{session,prompt:{sha256:sha('prompt')},terminal:true}};
}
