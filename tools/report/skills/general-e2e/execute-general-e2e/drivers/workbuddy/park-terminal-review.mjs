#!/usr/bin/env node
// Park a proven native terminal cancellation for review without declaring a
// completed execution, a human-intervention count, a score, or a retry.
import { createHash, randomUUID } from "node:crypto";
import { readFile, writeFile, mkdir, open, lstat, realpath, rename, unlink } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { hostname } from "node:os";
import { fileURLToPath } from "node:url";
import { resolveWorkBuddyBatchInvocation, verifyWorkBuddyQueueRepairs } from "./batch.mjs";
import { parseArgs as probeArgs, inspectWorkBuddyMacos } from "./probe.mjs";
import { assertWorkBuddyExecutionReadiness } from "./execute.mjs";
import { discoverWorkBuddyMainTarget, WorkBuddyCdpClient } from "./ui.mjs";
import { getWorkBuddyRuntimeConversation } from "./runtime-binding.mjs";
import { discoverJsonl } from "../../vendor/e2e-shared/workbuddy-jsonl-metrics/index.mjs";
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const json = value => Buffer.from(JSON.stringify(value, null, 2) + "\n");
function requireOk(value, code) { if (!value) throw new Error("WORKBUDDY_TERMINAL_REVIEW_" + code); }
const textOf = content => typeof content === "string" ? content : (content || []).filter(c => ["text", "input_text", "output_text"].includes(c.type)).map(c => c.text || "").join("");
async function plain(path) {
  requireOk(await realpath(path) === resolve(path), "PATH_ALIAS");
  const st = await lstat(path); requireOk(st.isFile() && !st.isSymbolicLink(), "UNSAFE_FILE");
  return readFile(path);
}
export function validateCancelledReview({ row, journal, state, loaded, sdkRows, promptSha256 }) {
  requireOk(row.phase === "NEEDS_ATTENTION" && row.dispatch_attempt_count === 1
    && journal.phase === "NEEDS_ATTENTION" && state.phase === "NEEDS_ATTENTION"
    && journal.identity?.attempt_id === row.attempt_id && state.identity?.attempt_id === row.attempt_id
    && journal.identity?.task_id === row.task_id && state.identity?.task_id === row.task_id
    && journal.send?.dispatch_attempt_count === 1 && journal.prompt?.send_status === "sent"
    && journal.prompt?.sha256 === promptSha256 && !journal.cancellation, "ORIGINAL_ATTEMPT_INVALID");
  const c = loaded.conversation, requests = loaded.requestEntries?.requests;
  requireOk(c?.id === row.conversation_id && c.space?.cwd === row.cwd && c.state === "idle"
    && Array.isArray(requests) && requests.length === 1, "RUNTIME_SCOPE_INVALID");
  const r = requests[0];
  requireOk(r.id === row.request_id && r.state === "cancelled" && r.userMessage?.state === "completed"
    && r.assistantMessage?.state === "completed" && sha(textOf(r.userMessage.content)) === promptSha256, "RUNTIME_NOT_CANCELLED");
  const events = sdkRows.filter(e => ["message", "function_call", "function_call_result"].includes(e.type));
  requireOk(events.length && events.every(e => e.sessionId === row.conversation_id && e.cwd === row.cwd), "SDK_IDENTITY_INVALID");
  const users = events.filter(e => e.type === "message" && e.role === "user" && !e.providerData?.isMeta && !e.providerData?.isCompactInternal);
  requireOk(users.length === 1, "SDK_USER_SCOPE_INVALID");
  const expected = textOf(r.userMessage.content), actual = textOf(users[0].content);
  requireOk(actual === expected || ([`<user_query>${expected}</user_query>`, `<user_query>\n${expected}\n</user_query>`].some(s => actual.endsWith(s))
    && actual.split("<user_query>").length === 2), "SDK_PROMPT_INVALID");
  const last = events.at(-1), pd = last.providerData || {};
  requireOk(last.type === "message" && last.role === "assistant" && pd.skipRun === true
    && pd.conversationRequestId === row.request_id && pd.error?.message === "Interrupted by user"
    && textOf(last.content) === "Interrupted by user" && Number.isFinite(r.finishTimestamp)
    && Number.isFinite(last.timestamp) && Math.abs(last.timestamp - r.finishTimestamp) <= 1000, "SDK_CANCELLED_BOUNDARY_INVALID");
  return { profile: "workbuddy-native-cancelled-terminal-review/v1", native_terminal_observed: true,
    cancellation_origin: "unresolved", execution_completed: false, score_admitted: false, prompt_replayed: false,
    identity: { task_id: row.task_id, attempt_id: row.attempt_id, conversation_id: row.conversation_id, request_id: row.request_id },
    sdk_terminal_message_id: last.id, native_finish_timestamp: r.finishTimestamp };
}
export async function parkTerminalReview(manifestPath) {
  const manifestBytes = await plain(resolve(manifestPath)), manifest = JSON.parse(manifestBytes);
  requireOk(manifest.schema_version === "wildclawbench.workbuddy-terminal-review-request/v1", "MANIFEST_INVALID");
  const cfg = await resolveWorkBuddyBatchInvocation(manifest.original_argv.slice(2));
  const root = cfg.root, queueRoot = join(root, ".general-e2e/queues/workbuddy"), queuePath = join(queueRoot, cfg.batch.queueId + ".json");
  const originalBytes = await plain(queuePath), queue = JSON.parse(originalBytes);
  requireOk(sha(originalBytes) === manifest.queue_sha256 && queue.phase === "NEEDS_ATTENTION", "QUEUE_CHANGED");
  await verifyWorkBuddyQueueRepairs(root, queue);
  const oldScope = { ...queue.frozen }, newScope = { ...cfg.frozen };
  for (const k of ["driver_sha256", "batch_sha256", "ui_sha256"]) { delete oldScope[k]; delete newScope[k]; }
  requireOk(JSON.stringify(oldScope) === JSON.stringify(newScope), "FROZEN_SCOPE_CHANGED");
  const owner = queue.last_owner;
  requireOk(owner?.pid === manifest.expected_owner_pid && owner.host === hostname(), "OWNER_UNKNOWN");
  let dead = false; try { process.kill(owner.pid, 0); } catch (e) { if (e.code === "ESRCH") dead = true; else throw e; }
  requireOk(dead, "OWNER_ACTIVE");
  const lockPath = join(queueRoot, "owner-lock.json"), lock = await open(lockPath, "wx", 0o600), lockInfo = await lock.stat();
  try {
    await lock.writeFile(json({ pid: process.pid, host: hostname(), queue_id: cfg.batch.queueId, type: "terminal-review-registration" }));
    const row = queue.tasks.find(r => r.task_id === manifest.task_id), config = cfg.configs.find(c => c.task.task_id === manifest.task_id);
    requireOk(row && config && row.cwd === config.candidateWorkspace
      && row.error?.code === "WORKBUDDY_CANCELLATION_UNCONFIRMED", "NOT_REGISTERED_ATTENTION");
    const report = await inspectWorkBuddyMacos({ ...probeArgs([]), appPath: config.appPath, sessionDb: config.sessionDb,
      extensionDataRoot: config.dataRoot, endpoint: config.endpoint, timeoutMs: 10000 });
    assertWorkBuddyExecutionReadiness(report, config.endpoint);
    const sqlRow = report.native_sources.session_index.sessions.find(s => s.conversation_id === row.conversation_id && s.cwd === row.cwd);
    requireOk(sqlRow && ["completed", "cancelled"].includes(sqlRow.status), "SQL_TERMINAL_MISSING");
    const target = await discoverWorkBuddyMainTarget(config.endpoint, 10000), client = await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl, 10000);
    let loaded; try { loaded = await getWorkBuddyRuntimeConversation(client, row.conversation_id); } finally { client.close(); }
    const journalBytes = await plain(config.journalFile), stateBytes = await plain(config.stateFile), native = await discoverJsonl(manifest.native_projects_root, row.conversation_id);
    requireOk(native, "SDK_MISSING");
    for (const value of [JSON.parse(journalBytes), JSON.parse(stateBytes)]) requireOk(
      value.identity?.batch_id === cfg.manifest.batch_id && value.identity?.unit_id === cfg.manifest.unit_id
      && value.dataset?.id === cfg.manifest.dataset.id && value.dataset?.digest === cfg.manifest.dataset.digest,
      "ORIGINAL_DATASET_IDENTITY_INVALID");
    const proof = validateCancelledReview({ row, journal: JSON.parse(journalBytes), state: JSON.parse(stateBytes), loaded,
      sdkRows: native.bytes.toString("utf8").trim().split(/\r?\n/u).map(JSON.parse), promptSha256: config.promptSha256 });
    proof.sql_session_projection_status = sqlRow.status;
    proof.note = "Session completed is only an idle projection; Runtime request cancellation and SDK interruption establish terminality, not successful task completion.";
    const output = resolve(manifest.output_root), outputRelative = relative(root, output);
    requireOk(outputRelative.startsWith(".general-e2e/terminal-reviews/") && !outputRelative.split("/").includes(".."), "OUTPUT_INVALID");
    let directory = root;
    const parts = outputRelative.split("/");
    for (let i = 0; i < parts.length; i++) {
      directory = join(directory, parts[i]);
      if (i === parts.length - 1) { await mkdir(directory); break; }
      const st = await lstat(directory).catch(e => { if (e.code === "ENOENT") return null; throw e; });
      requireOk(!st || (st.isDirectory() && !st.isSymbolicLink()), "OUTPUT_ALIAS");
      if (!st) await mkdir(directory);
    }
    requireOk(await realpath(output) === output, "OUTPUT_ALIAS");
    const artifacts = [];
    for (const [name, bytes] of [["original-queue.json", originalBytes], ["original-journal.json", journalBytes],
      ["original-state.json", stateBytes], ["runtime-snapshot.json", json(loaded)], ["native.jsonl", native.bytes],
      ["review.json", json(proof)], ["request.json", manifestBytes]]) {
      const path = join(output, name); await writeFile(path, bytes, { flag: "wx", mode: 0o444 });
      artifacts.push({ path: relative(root, path).split("\\").join("/"), sha256: sha(bytes), size: bytes.length });
    }
    requireOk(sha(await plain(queuePath)) === manifest.queue_sha256, "QUEUE_CHANGED_BEFORE_COMMIT");
    queue.frozen = cfg.frozen; queue.frozen_sha256 = cfg.digest;
    queue.terminal_reviews = [...(queue.terminal_reviews || []), { task_id: row.task_id, attempt_id: row.attempt_id,
      profile: proof.profile, artifacts, native_terminal_observed: true, origin_unresolved: true }];
    queue.phase = "PENDING";
    queue.events.push({ event: "NATIVE_TERMINAL_PARKED_FOR_REVIEW", at: new Date().toISOString(), task_id: row.task_id,
      attempt_id: row.attempt_id, native_status: "cancelled", score_admitted: false, prompt_replayed: false });
    const temporary = queuePath + "." + randomUUID() + ".tmp";
    await writeFile(temporary, json(queue), { flag: "wx", mode: 0o600 }); await rename(temporary, queuePath);
    return { status: "PARKED_FOR_REVIEW_OTHER_TASKS_MAY_CONTINUE", task_id: row.task_id, proof_root: output,
      new_prompts_sent: 0, original_attempt_retained: true, score_admitted: false };
  } finally {
    await lock.close(); const current = await lstat(lockPath).catch(() => null);
    if (current?.ino === lockInfo.ino && current.dev === lockInfo.dev) await unlink(lockPath);
  }
}
if (process.argv[1] && await realpath(resolve(process.argv[1])).catch(() => null) === await realpath(fileURLToPath(import.meta.url))) {
  const index = process.argv.indexOf("--manifest"); if (index < 0) throw new Error("usage: park-terminal-review.mjs --manifest ABS");
  parkTerminalReview(process.argv[index + 1]).then(r => console.log(JSON.stringify(r, null, 2)))
    .catch(e => { console.error(e.message); process.exitCode = 1; });
}
