import assert from "node:assert/strict";
import test from "node:test";
import {createHash} from "node:crypto";
import {validateNativePermission} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/respond-pending.mjs";
const sha=s=>createHash("sha256").update(s).digest("hex");
function fixture(){
  const input={params:{"{output_dir":"/task/results/assets"},toolName:"ImageGen"};
  const m={option_id:"allow",user_authorization:"保持原参数，允许本次 ImageGen 并留证",task_id:"task",attempt_id:"attempt",conversation_id:"conversation",request_id:"request",tool_call_id:"call",category:"highCredit",tool_name:"ImageGen",raw_input_sha256:sha(JSON.stringify(input))};
  const j={identity:{task_id:"task",attempt_id:"attempt"},send:{dispatch_attempt_count:1},prompt:{send_status:"sent",sha256:sha("prompt")},native:{conversation_id:"conversation",request_id:"request"},candidate_workspace:"/task"};
  const l={conversation:{id:"conversation",space:{cwd:"/task"}},requestEntries:{historyReady:true,hasOlder:false,requests:[{id:"request",state:"streaming",userMessage:{content:[{type:"text",text:"prompt"}]},assistantMessage:{content:[{toolCallId:"call",kind:"permission",status:"in_progress",rawInput:input,_meta:{"codebuddy.ai/conversationRequestId":"request"}}]}}]}};
  const p={id:"call",category:"highCredit",toolName:"ImageGen",options:[{optionId:"allow",kind:"allow_once"}]};return {m,j,l,p};
}
test("explicit native response preserves even malformed model arguments",()=>{const {m,j,l,p}=fixture();const x=validateNativePermission(m,j,l,p);assert.equal(x.tool.rawInput.params['{output_dir'],"/task/results/assets");});
test("a cancelled native request cannot consume an old authorization",()=>{const {m,j,l,p}=fixture();l.requestEntries.requests[0].state="cancelled";assert.throws(()=>validateNativePermission(m,j,l,p),/STALE_NATIVE_REQUEST/);});
test("global allow and missing human authorization are refused",()=>{for(const change of [{option_id:"allow_always"},{user_authorization:""}]){const {m,j,l,p}=fixture();Object.assign(m,change);assert.throws(()=>validateNativePermission(m,j,l,p),/AUTHORIZATION_REQUIRED/);}});
test("changed pending identity and changed model parameters fail closed",()=>{const {m,j,l,p}=fixture();p.id="another-call";assert.throws(()=>validateNativePermission(m,j,l,p),/PENDING_MISMATCH/);p.id="call";l.requestEntries.requests[0].assistantMessage.content[0].rawInput.params={output_dir:"/elsewhere"};assert.throws(()=>validateNativePermission(m,j,l,p),/PARAMETERS_CHANGED/);});
test("extra native turns and an uncertain Prompt cannot be approved",()=>{const {m,j,l,p}=fixture();l.requestEntries.requests.push({id:"other"});assert.throws(()=>validateNativePermission(m,j,l,p),/STALE_NATIVE_REQUEST/);l.requestEntries.requests.pop();j.prompt.send_status="uncertain";assert.throws(()=>validateNativePermission(m,j,l,p),/JOURNAL_IDENTITY_MISMATCH/);});
