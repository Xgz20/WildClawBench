#!/usr/bin/env node
// Recover only the native error boundary, after every local session is idle.
import { createHash } from "node:crypto";
import { lstat, mkdir, open, readFile, realpath, unlink, writeFile } from "node:fs/promises";
import { hostname } from "node:os";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveWorkBuddyBatchInvocation } from "./batch.mjs";
import { assertWorkBuddyExecutionReadiness, assertWorkBuddyNativeIdle } from "./execute.mjs";
import { inspectWorkBuddyMacos, parseArgs as parseProbeArgs } from "./probe.mjs";
import { discoverWorkBuddyMainTarget, readWorkBuddyUi, WorkBuddyCdpClient } from "./ui.mjs";

const hash = value => createHash("sha256").update(value).digest("hex");
const json = value => JSON.stringify(value, null, 2) + "\n";
const fail = message => { throw new Error(`WORKBUDDY_UI_RECOVERY_${message}`); };
async function nativeIdle(config) {
  const report = await inspectWorkBuddyMacos({ ...parseProbeArgs([]), appPath: config.appPath, sessionDb: config.sessionDb,
    extensionDataRoot: config.dataRoot, endpoint: config.endpoint, timeoutMs: 10000 });
  assertWorkBuddyExecutionReadiness(report, config.endpoint); const idle = assertWorkBuddyNativeIdle(report);
  if (config.manifest.unit.harness.version && report.application.version !== config.manifest.unit.harness.version) fail("VERSION_DRIFT");
  return { idle, captured_at: new Date().toISOString(), application: { path: report.application.path, version: report.application.version },
    process: { pid: report.process.pid, started_at: report.process.started_at, command_sha256: hash(report.process.command) },
    sessions: report.native_sources.session_index.sessions };
}
async function connect(config) {
  const target = await discoverWorkBuddyMainTarget(config.endpoint, 10000);
  return WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl, 10000);
}
export async function recoverWorkBuddyUi({ invocationPath, auditRoot, expectedOwnerPid }) {
  const invocationBytes = await readFile(invocationPath), invocation = JSON.parse(invocationBytes);
  const cfg = await resolveWorkBuddyBatchInvocation(invocation.argv.slice(2)), config = cfg.configs[0];
  const audit = resolve(auditRoot), auditRelative = relative(cfg.root, audit);
  if (!auditRelative.startsWith(".general-e2e/ui-recoveries/") || auditRelative.split("/").includes("..")) fail("AUDIT_OUTSIDE_UNIT");
  let directory = cfg.root;
  const parts = auditRelative.split("/");
  for (let i = 0; i < parts.length; i++) {
    directory = join(directory, parts[i]);
    if (i === parts.length - 1) { await mkdir(directory); break; }
    const st = await lstat(directory).catch(e => { if (e.code === "ENOENT") return null; throw e; });
    if (st && (!st.isDirectory() || st.isSymbolicLink())) fail("AUDIT_SYMLINK");
    if (!st) await mkdir(directory);
  }
  if (await realpath(audit) !== audit) fail("AUDIT_SYMLINK");
  const statePath = join(audit, "recovery.json");
  const state = { schema_version: "wildclawbench.workbuddy-native-ui-recovery/v1", status: "PREFLIGHT",
    invocation_sha256: hash(invocationBytes), captured_at: new Date().toISOString(), prompt_send_count: 0 };
  const save = () => writeFile(statePath, json(state), { mode: 0o600 });
  await save();
  const uiLockPath = join(cfg.root, ".general-e2e/workbuddy-ui.lock");
  let lock, lockInfo, client;
  try {
    const ownerPath = join(cfg.root, ".general-e2e/queues/workbuddy/owner-lock.json");
    let owner;
    try { owner = JSON.parse(await readFile(ownerPath)); state.owner_source = "original-owner-lock"; }
    catch (e) {
      if (e.code !== "ENOENT") throw e;
      const queueBytes = await readFile(join(cfg.root, ".general-e2e/queues/workbuddy", cfg.batch.queueId + ".json"));
      owner = JSON.parse(queueBytes).last_owner;
      state.owner_source = "persisted-queue-owner"; state.owner_queue_sha256 = hash(queueBytes);
    }
    if (!owner) fail("OWNER_UNKNOWN");
    if (owner.host !== hostname() || owner.pid !== expectedOwnerPid || owner.queue_id !== cfg.batch.queueId) fail("OWNER_UNKNOWN");
    let dead = false;
    try { process.kill(owner.pid, 0); } catch (e) { if (e.code === "ESRCH") dead = true; else throw e; }
    if (!dead) fail("OWNER_ACTIVE");
    for (const task of cfg.configs) {
      try { await lstat(task.lockFile); fail("ATTEMPT_LOCK_EXISTS"); } catch (e) { if (e.code !== "ENOENT") throw e; }
    }
    lock = await open(uiLockPath, "wx", 0o600); lockInfo = await lock.stat();
    await lock.writeFile(json({ host: hostname(), pid: process.pid, type: "native-ui-idle-recovery", audit_root: audit }));
    state.first_native_idle = await nativeIdle(config);
    client = await connect(config); const before = await readWorkBuddyUi(client);
    if (!before.app_error_boundary) fail("NOT_RECOGNIZED_ERROR_BOUNDARY");
    state.before_ui = before;
    state.error_text = await client.evaluate("document.body.innerText.slice(0,50000)");
    const second = await nativeIdle(config);
    if (JSON.stringify(second.process) !== JSON.stringify(state.first_native_idle.process)) fail("PROCESS_CHANGED");
    state.status = "REFRESH_ARMED"; state.refresh_attempt_count = 1; await save();
    try {
      const clicked = await client.evaluate(`(() => {
        const visible = e => { const r=e.getBoundingClientRect(),s=getComputedStyle(e); return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'; };
        const buttons=[...document.querySelectorAll('button')].filter(e=>visible(e)&&e.innerText.trim()==='刷新页面');
        const details=[...document.querySelectorAll('summary')].filter(e=>visible(e)&&e.innerText.trim()==='点击查看错误详情');
        if(buttons.length!==1||details.length!==1||!document.body.innerText.includes('出错了'))throw new Error('ERROR_BOUNDARY_CHANGED');
        buttons[0].click(); return { clicked:true };
      })()`, { userGesture: true });
      state.refresh_returned = clicked;
    } catch (e) {
      // A destroyed execution context is expected during this one reload.
      state.refresh_transport_error = String(e.message);
      if (!/context|closed|WebSocket|timeout|超时/iu.test(state.refresh_transport_error)) throw e;
    }
    state.status = "OBSERVING_ORIGINAL_REFRESH"; await save(); client.close(); client = null;
    const deadline = Date.now() + 30000; let last = null, verified = false;
    while (Date.now() < deadline) {
      try {
        client = await connect(config); last = await readWorkBuddyUi(client);
        const controls = await client.evaluate(`(() => [...document.querySelectorAll('button')].filter(e=>{
          const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&/^(新建任务|New task)$/i.test((e.innerText||e.textContent||'').trim());}).length)()`);
        if (!last.app_error_boundary && last.editor_count === 1 && last.editor_nonempty_count === 0
            && last.busy_control_count === 0 && last.model_count === 1 && last.model === config.expectedModel
            && last.permission_count === 1 && last.permission === config.expectedPermission && controls === 1) { verified = true; break; }
      } catch (e) { state.last_observation_error = String(e.message); }
      client?.close(); client = null; await new Promise(r => setTimeout(r, 250));
    }
    if (!verified || !client || !last || last.app_error_boundary || last.editor_count !== 1 || last.editor_nonempty_count
        || last.model !== config.expectedModel || last.permission !== config.expectedPermission) fail("REFRESH_NOT_VERIFIED_DO_NOT_REPEAT");
    state.after_ui = last; state.final_native_idle = await nativeIdle(config);
    if (JSON.stringify(state.final_native_idle.process) !== JSON.stringify(state.first_native_idle.process)) fail("PROCESS_CHANGED");
    const identities = p => JSON.stringify(p.sessions.map(s => [s.conversation_id, s.cwd]).sort((a,b) => String(a).localeCompare(String(b))));
    if (identities(state.final_native_idle) !== identities(state.first_native_idle)) fail("NATIVE_SESSION_SET_CHANGED");
    state.status = "PASS_UI_RECOVERED_WITHOUT_PROMPT"; state.completed_at = new Date().toISOString(); await save();
    return { status: state.status, receipt: statePath, prompt_send_count: 0 };
  } catch (error) {
    state.status = "NEEDS_ATTENTION"; state.error = String(error.message); await save(); throw error;
  } finally {
    client?.close();
    if (lock) {
      await lock.close(); const st = await lstat(uiLockPath).catch(() => null);
      if (st?.ino === lockInfo.ino && st.dev === lockInfo.dev) await unlink(uiLockPath);
    }
  }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), get = flag => args[args.indexOf(flag) + 1];
  if (!["--invocation", "--audit-root", "--expected-owner-pid"].every(f => args.includes(f))) throw new Error("usage: recover-ui.mjs --invocation ABS --audit-root NEW_ABS --expected-owner-pid PID");
  recoverWorkBuddyUi({ invocationPath: get("--invocation"), auditRoot: get("--audit-root"), expectedOwnerPid: Number(get("--expected-owner-pid")) })
    .then(result => console.log(json(result))).catch(error => { console.error(error.message); process.exitCode = 1; });
}
