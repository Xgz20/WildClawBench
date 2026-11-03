#!/usr/bin/env node
// Apply one explicit human decision to one still-live native permission.
import { createHash, randomUUID } from "node:crypto";
import { mkdir, open, readFile, realpath, lstat, writeFile, rename, unlink } from "node:fs/promises";
import { hostname } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveWorkBuddyBatchInvocation, verifyWorkBuddyQueueRepairs } from "./batch.mjs";
import { getWorkBuddyRuntimeConversation } from "./runtime-binding.mjs";
import { discoverWorkBuddyMainTarget, WorkBuddyCdpClient } from "./ui.mjs";
const sha = value => createHash("sha256").update(value).digest("hex");
const json = value => Buffer.from(JSON.stringify(value, null, 2) + "\n");
const requireOk = (condition, code) => { if (!condition) throw new Error("WORKBUDDY_PENDING_" + code); };
async function plain(path) {
  requireOk(await realpath(path) === resolve(path) && (await lstat(path)).isFile(), "UNSAFE_PATH");
  return readFile(path);
}
export function validateNativePermission(manifest, journal, loaded, pending) {
  const r = loaded.requestEntries?.requests?.find(r => r.id === manifest.request_id);
  requireOk(manifest.option_id === "allow" && typeof manifest.user_authorization === "string"
    && manifest.user_authorization.trim(), "EXPLICIT_ONCE_AUTHORIZATION_REQUIRED");
  requireOk(journal.send?.dispatch_attempt_count === 1 && journal.prompt?.send_status === "sent"
    && journal.identity?.attempt_id === manifest.attempt_id && journal.identity?.task_id === manifest.task_id
    && journal.native?.conversation_id === manifest.conversation_id && journal.native?.request_id === manifest.request_id,
    "JOURNAL_IDENTITY_MISMATCH");
  requireOk(loaded.conversation?.id === manifest.conversation_id
    && loaded.conversation.space?.cwd === journal.candidate_workspace
    && loaded.requestEntries.historyReady === true && loaded.requestEntries.hasOlder !== true
    && loaded.requestEntries.requests.length === 1 && r && ["streaming", "running", "pending"].includes(r.state), "STALE_NATIVE_REQUEST");
  const text = (r.userMessage?.content || []).filter(c => c.type === "text").map(c => c.text || "").join("");
  requireOk(sha(text) === journal.prompt.sha256, "PROMPT_MISMATCH");
  const tools = (r.assistantMessage?.content || []).filter(t => t.toolCallId === manifest.tool_call_id
    && t.kind === "permission" && ["in_progress", "pending"].includes(t.status));
  requireOk(tools.length === 1 && pending?.id === manifest.tool_call_id && pending.category === manifest.category
    && pending.toolName === manifest.tool_name && pending.options?.some(o => o.optionId === "allow" && o.kind === "allow_once"), "PENDING_MISMATCH");
  const tool = tools[0];
  requireOk(sha(JSON.stringify(tool.rawInput)) === manifest.raw_input_sha256
    && tool._meta?.["codebuddy.ai/conversationRequestId"] === manifest.request_id, "PARAMETERS_CHANGED");
  requireOk((manifest.category === "highCredit" && manifest.tool_name === "ImageGen")
    || (manifest.category === "sandbox" && manifest.tool_name === "Read"
      && tool.metadata?.sandbox?.interceptType === "tool-call-loop"), "UNSUPPORTED_PERMISSION");
  return { tool, pending };
}
export async function respondPending(manifestPath) {
  const manifestBytes = await plain(resolve(manifestPath)), m = JSON.parse(manifestBytes);
  requireOk(m.schema_version === "wildclawbench.workbuddy-native-once-authorization/v1", "MANIFEST_INVALID");
  const cfg = await resolveWorkBuddyBatchInvocation(m.original_argv.slice(2));
  const config = cfg.configs.find(c => c.task.task_id === m.task_id); requireOk(config, "TASK_UNKNOWN");
  const queuePath = join(cfg.root, ".general-e2e/queues/workbuddy", cfg.batch.queueId + ".json");
  const qb = await plain(queuePath), q = JSON.parse(qb); requireOk(sha(qb) === m.queue_sha256, "QUEUE_CHANGED");
  await verifyWorkBuddyQueueRepairs(cfg.root, q);
  const row = q.tasks.find(t => t.task_id === m.task_id);
  requireOk(row?.attempt_id === m.attempt_id && row.dispatch_attempt_count === 1, "QUEUE_IDENTITY_MISMATCH");
  const owner = q.last_owner;
  requireOk(owner?.host === hostname() && Number.isSafeInteger(owner.pid), "OWNER_UNKNOWN");
  try { process.kill(owner.pid, 0); throw new Error("WORKBUDDY_PENDING_OWNER_ACTIVE"); }
  catch(e) { if (e.code !== "ESRCH") throw e; }
  const output = resolve(m.output_root), rel = relative(cfg.root, output);
  requireOk(rel.startsWith(".general-e2e/mechanical-interventions/") && !rel.split("/").includes(".."), "OUTPUT_INVALID");
  await mkdir(dirname(output), { recursive: true }); requireOk(await realpath(dirname(output)) === dirname(output), "OUTPUT_ALIAS");
  await mkdir(output);
  const held = []; let client;
  try {
    for (const path of [join(cfg.root, ".general-e2e/queues/workbuddy/owner-lock.json"), config.uiLockFile, config.lockFile]) {
      const f = await open(path, "wx", 0o600), st = await f.stat(); held.push({f,path,st});
      await f.writeFile(json({pid:process.pid,host:hostname(),kind:"explicit-native-permission-once",task_id:m.task_id}));
    }
    const original = await plain(config.journalFile), journal = JSON.parse(original);
    const target = await discoverWorkBuddyMainTarget(config.endpoint, 10000);
    client = await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl, 10000);
    const loaded = await getWorkBuddyRuntimeConversation(client, m.conversation_id);
    const pending = await client.evaluate(`(async()=>{const c=await window.wb.conversations.get(${JSON.stringify(m.conversation_id)});return c.getPendingInfo()||null})()`);
    validateNativePermission(m, journal, loaded, pending);
    for (const [name,bytes] of [["authorization.json",manifestBytes],["original-journal.json",original],["native-before.json",json({loaded,pending})]])
      await writeFile(join(output,name),bytes,{flag:"wx",mode:0o444});
    const intent = {status:"RESPONSE_INTENT_DO_NOT_REPEAT",at:new Date().toISOString(),task_id:m.task_id,
      attempt_id:m.attempt_id,conversation_id:m.conversation_id,request_id:m.request_id,tool_call_id:m.tool_call_id,
      option_id:"allow",raw_input_sha256:m.raw_input_sha256,new_prompts_sent:0,semantic_intervention_count:0};
    await writeFile(join(output,"intent.json"),json(intent),{flag:"wx",mode:0o444});
    // Revalidate the active pending ID immediately before the single response.
    const result = await client.evaluate(`(async(__m)=>{const c=await window.wb.conversations.get(__m.conversation_id);const p=c.getPendingInfo();if(p?.id!==__m.tool_call_id||p.category!==__m.category||!p.options?.some(o=>o.optionId==='allow'&&o.kind==='allow_once'))throw Error('PENDING_CHANGED_BEFORE_RESPONSE');c.resolvePending(p.id,{optionId:'allow'});return {response_invoked:true,at:new Date().toISOString()};})(${JSON.stringify(m)})`);
    let after = null;
    for(let i=0;i<50;i++) {
      await new Promise(r=>setTimeout(r,100));
      after=await client.evaluate(`(async()=>{const c=await window.wb.conversations.get(${JSON.stringify(m.conversation_id)});return {pending:c.getPendingInfo()||null,info:c.info}})()`);
      if(after.pending?.id!==m.tool_call_id)break;
    }
    const receipt={...intent,...result,status:after?.pending?.id!==m.tool_call_id?"RESPONDED_NATIVE_PENDING_CLEARED":"RESPONSE_UNCONFIRMED_DO_NOT_REPEAT",after};
    const receiptPath=join(output,"receipt.json");await writeFile(receiptPath,json(receipt),{flag:"wx",mode:0o444});
    requireOk(sha(await plain(config.journalFile))===sha(original),"JOURNAL_CHANGED_AFTER_RESPONSE");
    journal.human_assistance={mode:"human_assisted",operation_count:(journal.human_assistance?.operation_count||0)+1,
      semantic_intervention_count:journal.human_assistance?.semantic_intervention_count||0};
    journal.mechanical_interventions=[...(journal.mechanical_interventions||[]),{path:relative(cfg.root,receiptPath),sha256:sha(json(receipt)),size:json(receipt).length}];
    journal.history.push({event:"EXPLICIT_NATIVE_PERMISSION_RESPONSE",at:result.at,tool_call_id:m.tool_call_id,option_id:"allow",receipt:relative(cfg.root,receiptPath)});
    const temporary=config.journalFile+"."+randomUUID()+".tmp";await writeFile(temporary,json(journal),{flag:"wx",mode:0o600});await rename(temporary,config.journalFile);
    return receipt;
  } finally {
    await client?.close();
    for(const {f,path,st} of held.reverse()){await f.close();const current=await lstat(path).catch(()=>null);if(current?.ino===st.ino&&current.dev===st.dev)await unlink(path);}
  }
}
if(process.argv[1]&&await realpath(resolve(process.argv[1])).catch(()=>null)===await realpath(fileURLToPath(import.meta.url))){
  const i=process.argv.indexOf("--manifest");if(i<0)throw Error("usage: respond-pending.mjs --manifest ABS");
  respondPending(process.argv[i+1]).then(r=>console.log(JSON.stringify(r,null,2))).catch(e=>{console.error(e.stack);process.exitCode=1});
}
