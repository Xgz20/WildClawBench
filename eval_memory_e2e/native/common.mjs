import { createHash, randomUUID } from "node:crypto";
import { readFile, writeFile, mkdir, lstat, open, rename, unlink } from "node:fs/promises";
import { dirname, resolve, basename, join } from "node:path";
import { hostname } from "node:os";
import { inspectMacGuiSession, assertMacGuiReady } from "../../tools/report/e2e-shared/desktop-gui/macos.mjs";

export const sha = value => createHash("sha256").update(value).digest("hex");
export const MEMORY_UI_LOCK='/Users/gzx/debug-workspace/e2e-evaluate/memory-e2e/.memory-native-ui.lock';
export function memoryUiLockPath(root,profile) {
  if(profile.ui_lock_path!==undefined&&profile.ui_lock_path!==MEMORY_UI_LOCK)throw Error('NATIVE_UI_LOCK_POLICY');
  return profile.ui_lock_path??join(dirname(root),'.memory-native-ui.lock');
}
export function sorted(value) {
  if (Array.isArray(value)) return value.map(sorted);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map(key => [key, sorted(value[key])]));
  return value;
}
export const requestHash = request => sha(JSON.stringify(sorted(Object.fromEntries(Object.entries(request).filter(([key]) => key !== "transport_action")))));
export const readJson = async path => JSON.parse(await readFile(path, "utf8"));

export async function assertNoLinks(path) {
  for (let current = resolve(path);; current = dirname(current)) {
    try { if ((await lstat(current)).isSymbolicLink()) throw Error(`NATIVE_SYMLINK_REJECTED: ${current}`); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
    if (dirname(current) === current) break;
  }
}

export async function context(request, harness) {
  if (request.mode !== "native" || request.harness !== harness || request.contract !== "wildclawbench.memory-e2e/v1"
      || !["dispatch", "observe", "retry_pre_send"].includes(request.transport_action)) throw Error("NATIVE_REQUEST_SCOPE");
  if (!/^op-[a-f0-9]{64}$/.test(request.operation_id)) throw Error("NATIVE_OPERATION_ID");
  const workspace = resolve(request.workspace);
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(request.scope??'') || basename(workspace)!==request.scope || basename(dirname(workspace)) !== request.episode_id
      || basename(resolve(workspace, "../..")) !== "candidate") throw Error("NATIVE_WORKSPACE_LAYOUT");
  await assertNoLinks(workspace);
  const root = resolve(workspace, "../../..");
  const manifest = await readJson(join(root, "manifest.json"));
  const episode = manifest.episodes.find(row => row.id === request.episode_id);
  if (!episode || episode.harness !== harness || episode.namespace !== request.namespace
      || episode.workspaces[request.scope] !== workspace || manifest.experiment_id !== request.experiment_id
      || manifest.mode !== "native") throw Error("NATIVE_MANIFEST_BINDING");
  const expectedOperation = "op-" + sha(JSON.stringify(sorted({ experiment_id: request.experiment_id,
    episode_id: request.episode_id, step_id: request.step_id, execution_attempt_id: request.execution_attempt_id })) + "\n");
  if (expectedOperation !== request.operation_id) throw Error("NATIVE_OPERATION_ID_BINDING");
  if (request.action === "execute_step") {
    const plan = await readJson(join(root, episode.plan_path));
    const step = plan.steps.find(item => item.id === request.step_id);
    if (!step || step.prompt !== request.prompt || sha(step.prompt) !== request.prompt_sha256
        || step.scope !== request.scope || step.session !== request.session_action) throw Error("NATIVE_FROZEN_STEP_MISMATCH");
  } else if (request.action !== "prepare_namespace" || request.step_id !== "prepare" || request.prompt !== null) throw Error("NATIVE_ACTION_SCOPE");
  const journal = (await readFile(join(root, "events.jsonl"), "utf8")).trim().split("\n").map(line => JSON.parse(line));
  const intent = journal.find(event => event.kind === "INTENT" && event.payload?.operation_id === request.operation_id);
  if (!intent || requestHash(intent.payload.request) !== requestHash(request)) throw Error("NATIVE_DURABLE_INTENT_REQUIRED");
  if(request.transport_action==='retry_pre_send'){
    if(!['QwenWork','DoubaoWork'].includes(harness)||manifest.profiles[harness].pre_send_retry!==true
      ||!journal.some(e=>e.kind==='PRE_SEND_RETRY_INTENT'&&e.payload?.operation_id===request.operation_id
        &&e.payload?.request&&requestHash(e.payload.request)===requestHash(request)))throw Error('NATIVE_EXPLICIT_RETRY_INTENT_REQUIRED');
  }
  const control = join(root, ".native", harness, request.operation_id);
  await mkdir(control, { recursive: true });
  await assertNoLinks(control);
  return { root, workspace, control, manifest, stateFile: join(control, "state.json"),
    uiLock: memoryUiLockPath(root,manifest.profiles[harness]) };
}

export async function saveState(ctx, state) {
  const temp = join(ctx.control, `.state-${randomUUID()}.json`);
  const handle = await open(temp, "wx");
  try { await handle.writeFile(JSON.stringify(state, null, 2) + "\n"); await handle.sync(); }
  finally { await handle.close(); }
  await rename(temp, ctx.stateFile);
}

export async function artifact(ctx, name, value) {
  const bytes = typeof value === "string" ? value : JSON.stringify(value, null, 2) + "\n";
  const path = join(ctx.control, `${name}-${sha(bytes).slice(0, 20)}.${name === "response" ? "txt" : "json"}`);
  try { await writeFile(path, bytes, { flag: "wx" }); }
  catch (error) { if (error.code !== "EEXIST" || (await readFile(path, "utf8")) !== bytes) throw error; }
  return path;
}

export async function withUiLock(ctx, request, action) {
  const handle = await open(ctx.uiLock, "wx").catch(error => {
    if (error.code === "EEXIST") throw Error("NATIVE_UI_LOCK_BUSY: keep the owner record; do not delete an unknown lock");
    throw error;
  });
  const owner = { id: randomUUID(), host: hostname(), pid: process.pid, created_at: new Date().toISOString(), operation_id: request.operation_id };
  try {
    await handle.writeFile(JSON.stringify(owner)); await handle.sync();
    assertMacGuiReady(await inspectMacGuiSession());
    return await action();
  } finally {
    await handle.close();
    if ((await readJson(ctx.uiLock)).id !== owner.id) throw Error("NATIVE_UI_LOCK_OWNER_CHANGED");
    await unlink(ctx.uiLock);
  }
}

export async function requireGui() { assertMacGuiReady(await inspectMacGuiSession()); }

export async function readQwenMemoryOperationUi({transportAction,frozen,terminal=false},read) {
  if(transportAction==='observe'&&frozen&&!terminal)return {ui:null,basis:'frozen_pre_send_pending_terminal_readback'};
  try{return {ui:await read(),basis:'live_ui'};}
  catch(error){if(terminal||!frozen)throw error;return {ui:null,basis:'frozen_after_unavailable_ui'};}
}

export function baseReply(request, actualConfig) {
  return { ...Object.fromEntries(["contract", "mode", "experiment_id", "execution_attempt_id", "operation_id", "episode_id", "profile_id", "namespace", "step_id", "prompt_sha256"].map(key => [key, request[key]])),
    actual_config: actualConfig, background_settled: null };
}

export async function bindReply(ctx, request, reply, raw = {}) {
  const binding = { source_kind: "native_memory_binding", operation_id: request.operation_id,
    profile_id: request.profile_id, namespace: request.namespace, prompt_sha256: request.prompt_sha256,
    actual_config: reply.actual_config, native: reply.native ?? null, ...raw };
  reply.binding_evidence = await artifact(ctx, "binding", binding);
  return reply;
}

export function verifyConfig(actual, expected) {
  if (expected && JSON.stringify(sorted(actual)) !== JSON.stringify(sorted(expected))) throw Error("NATIVE_CONFIG_DRIFT");
  for (const field of ["app_version", "model_display", "permissions", "account_fingerprint"]) {
    if (typeof actual[field] !== "string" || !actual[field].trim()) throw Error(`NATIVE_CONFIG_MISSING: ${field}`);
  }
}

export async function stdinRequest() {
  let value = "";
  for await (const chunk of process.stdin) value += chunk;
  return JSON.parse(value);
}

export function assertMemoryPreSendRetry(harness, journal) {
  const send=journal?.send,session=journal?.session;
  if(!journal||send?.dispatch_attempt_count!==0||session?.conversation_id||session?.session_id||session?.session_directory_id
    ||session?.verified===true)throw Error('NATIVE_PRE_SEND_RETRY_REJECTED');
  if(harness==='QwenWork'){
    if(send.state!=='not_reserved'||send.reservation_id||send.invoking_at||send.returned_at
      ||journal.prompt?.send_status!=='not_sent'
      ||!(journal.phase==='PREPARING'||journal.phase==='NEEDS_ATTENTION'
        &&['QWENWORK_PRE_SEND_PREPARATION_FAILED','QWENWORK_EXECUTION_ENVIRONMENT_BLOCKED'].includes(journal.attention?.code)))throw Error('NATIVE_PRE_SEND_RETRY_REJECTED');
  }else if(harness==='DoubaoWork'){
    if(journal.phase!=='INFRA_FAILED'||journal.error?.code!=='DEVELOPMENT_PRE_SEND_FAILED'
      ||send.intent_persisted_at||send.dispatch_started_at||send.click_returned_at||send.accepted_at||journal.timing?.sent_at)throw Error('NATIVE_PRE_SEND_RETRY_REJECTED');
  }else throw Error('NATIVE_PRE_SEND_RETRY_NOT_SUPPORTED');
  return true;
}

/** Select only the inspected local-runtime menu item; never send a prompt. */
export async function ensureLocalRuntimeMode(page, recordIntent) {
  const mode = page.getByTestId('chat_input_action_mode');
  if (await mode.count() !== 1) throw Error('DOUBAO_RUNTIME_MODE_AMBIGUOUS');
  const original = (await mode.innerText()).trim();
  if (original === '本地电脑') return original;
  if (original !== '云电脑') throw Error('DOUBAO_RUNTIME_MODE_UNKNOWN');
  await recordIntent({before: original, desired: '本地电脑', prompt_sent: false});
  const local = page.getByRole('menuitem', {name: '工作任务 本地电脑', exact: true});
  if (await local.count() !== 1 || !await local.isVisible()) await mode.click();
  await local.waitFor({state: 'visible', timeout: 10000});
  if (await local.count() !== 1) throw Error('DOUBAO_LOCAL_MODE_AMBIGUOUS');
  await local.click();
  await page.waitForFunction(() => {
    const modes = document.querySelectorAll('[data-testid="chat_input_action_mode"]');
    return modes.length === 1 && modes[0].innerText.trim() === '本地电脑';
  }, null, {timeout: 10000});
  return original;
}
