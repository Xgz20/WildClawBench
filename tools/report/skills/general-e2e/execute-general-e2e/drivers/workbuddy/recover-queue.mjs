#!/usr/bin/env node
// Explicit, audited recovery of a dead owner's zero-send preparation failures.
// It never sends a Prompt, edits a Workspace, or retries an accepted attempt.
import { createHash, randomUUID } from "node:crypto";
import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import { link, lstat, mkdir, open, readFile, realpath, rename, unlink, writeFile } from "node:fs/promises";
import { hostname } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveWorkBuddyBatchInvocation, synchronizeRow, verifyWorkBuddyQueueRepairs, WORKBUDDY_QUEUE_VERSION } from "./batch.mjs";
import { assertWorkBuddyExecutionReadiness, assertWorkBuddyNativeIdle } from "./execute.mjs";
import { inspectWorkBuddyMacos, parseArgs as parseProbeArgs } from "./probe.mjs";
import { assertWorkBuddyUiIdle, discoverWorkBuddyMainTarget, readWorkBuddyUi, WorkBuddyCdpClient } from "./ui.mjs";

const SCHEMA = "wildclawbench.workbuddy-zero-send-queue-repair/v1";
const execFile = promisify(execFileCallback);
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const json = value => Buffer.from(JSON.stringify(value, null, 2) + "\n");
const readJson = async path => JSON.parse(await readFile(path, "utf8"));
function requireOk(value, code) { if (!value) throw new Error(`WORKBUDDY_RECOVERY_${code}`); }
async function optional(path) { try { return await lstat(path); } catch (e) { if (e.code === "ENOENT") return null; throw e; } }
async function plain(path) {
  requireOk(isAbsolute(path) && await realpath(path) === resolve(path), "UNSAFE_PATH");
  const st = await lstat(path); requireOk(st.isFile() && !st.isSymbolicLink(), "UNSAFE_FILE");
  const bytes = await readFile(path); const after = await lstat(path);
  requireOk(st.ino === after.ino && st.dev === after.dev && st.size === after.size && st.mtimeMs === after.mtimeMs, "SOURCE_CHANGED");
  return { bytes, dev: st.dev, ino: st.ino, sha256: sha(bytes), size: bytes.length };
}
async function deadOwner(owner) {
  requireOk(owner.host === hostname() && Number.isSafeInteger(owner.pid) && owner.pid > 0, "OWNER_IDENTITY_INVALID");
  try { process.kill(owner.pid, 0); } catch (e) { if (e.code === "ESRCH") return { exited: true, pid: owner.pid }; throw e; }
  throw new Error("WORKBUDDY_RECOVERY_OWNER_STILL_ACTIVE");
}
async function persist(path, value) {
  const temporary = path + "." + randomUUID() + ".tmp";
  await writeFile(temporary, json(value), { flag: "wx", mode: 0o600 });
  await rename(temporary, path);
}
async function moveVerified(source, destination, expected) {
  await mkdir(dirname(destination), { recursive: true });
  const src = await optional(source), dst = await optional(destination);
  requireOk(src || dst, "ARCHIVE_SOURCE_MISSING");
  if (src) {
    const current = await plain(source);
    requireOk(current.sha256 === expected.sha256 && current.dev === expected.dev && current.ino === expected.ino, "ARCHIVE_SOURCE_DRIFT");
    if (!dst) await link(source, destination);
  }
  const saved = await plain(destination);
  requireOk(saved.sha256 === expected.sha256 && saved.dev === expected.dev && saved.ino === expected.ino, "ARCHIVE_CONFLICT");
  if (src) {
    const current = await plain(source);
    requireOk(current.dev === saved.dev && current.ino === saved.ino && current.sha256 === saved.sha256, "ARCHIVE_SOURCE_DRIFT");
    await unlink(source);
  }
}
async function initialWorkspace(config, variants = []) {
  const expected = new Map(config.task.workspace.entries.map(e => [e.path.normalize("NFC"), e]));
  const found = new Set();
  async function walk(directory, prefix = "") {
    const { readdir } = await import("node:fs/promises");
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const name = prefix + entry.name, key = name.normalize("NFC"), want = expected.get(key);
      requireOk(want && !found.has(key), "INITIAL_WORKSPACE_MEMBER_DRIFT"); found.add(key);
      const path = join(directory, entry.name), st = await lstat(path);
      requireOk(!st.isSymbolicLink() && (st.mode & 0o777) === Number.parseInt(want.mode, 8), "INITIAL_WORKSPACE_TYPE_OR_MODE_DRIFT");
      if (entry.isDirectory()) { requireOk(want.kind === "directory", "INITIAL_WORKSPACE_TYPE_DRIFT"); await walk(path, name + "/"); }
      else {
        requireOk(want.kind === "file" && entry.isFile(), "INITIAL_WORKSPACE_TYPE_DRIFT");
        const value = await plain(path);
        const same = value.sha256 === want.sha256 && value.size === want.size;
        const variant = variants.find(v => v.path.normalize("NFC") === key);
        requireOk(same || (variant && variant.expected_sha256 === want.sha256 && variant.expected_size === want.size
          && variant.actual_sha256 === value.sha256 && variant.actual_size === value.size
          && variant.office_delta?.business_members_unchanged === true), "INITIAL_WORKSPACE_BYTES_DRIFT");
      }
    }
  }
  await walk(config.candidateWorkspace);
  requireOk(found.size === expected.size, "INITIAL_WORKSPACE_MISSING");
}
async function verifyIdle(config, zeroWorkspaces) {
  const report = await inspectWorkBuddyMacos({ ...parseProbeArgs([]), appPath: config.appPath, sessionDb: config.sessionDb,
    extensionDataRoot: config.dataRoot, endpoint: config.endpoint, timeoutMs: 10000 });
  assertWorkBuddyExecutionReadiness(report, config.endpoint);
  requireOk(!config.manifest.unit.harness.version || report.application.version === config.manifest.unit.harness.version, "APPLICATION_VERSION_DRIFT");
  const idle = assertWorkBuddyNativeIdle(report);
  requireOk(!report.native_sources.session_index.sessions.some(s => zeroWorkspaces.has(s.cwd)), "ZERO_WORKSPACE_NATIVE_SESSION_EXISTS");
  const target = await discoverWorkBuddyMainTarget(config.endpoint, 10000);
  const client = await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl, 10000);
  let ui;
  try { ui = await readWorkBuddyUi(client); assertWorkBuddyUiIdle(ui); } finally { client.close(); }
  requireOk(ui.editor_count === 1 && ui.model_count === 1 && ui.model === config.expectedModel
    && ui.permission_count === 1 && ui.permission === config.expectedPermission, "UI_NOT_READY");
  return { verified: true, captured_at: new Date().toISOString(), idle,
    application: { path: report.application.path, version: report.application.version, identity_verified: report.application.identity_verified },
    process: { pid: report.process.pid, started_at: report.process.started_at, command_sha256: sha(report.process.command) },
    session_index: { backend: report.native_sources.session_index.backend, sessions: report.native_sources.session_index.sessions }, ui };
}

export async function recoverWorkBuddyQueue(manifestPath, { resume = false, ...dependencies } = {}) {
  const source = await plain(resolve(manifestPath)), manifest = JSON.parse(source.bytes);
  requireOk(manifest.schema_version === SCHEMA && typeof manifest.reason === "string" && manifest.reason.trim(), "MANIFEST_INVALID");
  requireOk(Array.isArray(manifest.original_argv) && manifest.original_argv.length > 2, "INVOCATION_INVALID");
  const originalEntry = await plain(manifest.original_argv[1]);
  requireOk(originalEntry.sha256 === manifest.original_batch_sha256, "ORIGINAL_BATCH_DRIFT");
  const originalDriver = await plain(join(dirname(manifest.original_argv[1]), "execute.mjs"));
  const cfg = await resolveWorkBuddyBatchInvocation(manifest.original_argv.slice(2));
  const { root, frozen, digest, configs, batch } = cfg;
  requireOk(manifest.replacement_sources?.driver_sha256 === frozen.driver_sha256
    && manifest.replacement_sources?.batch_sha256 === frozen.batch_sha256
    && manifest.replacement_sources?.ui_sha256 === frozen.ui_sha256, "REPLACEMENT_SOURCE_DRIFT");
  requireOk(!batch.status && !batch.resume, "ORIGINAL_INVOCATION_MODE_INVALID");
  const queueRoot = join(root, ".general-e2e/queues/workbuddy"), queuePath = join(queueRoot, `${batch.queueId}.json`);
  const output = resolve(manifest.output_root), outputRel = relative(root, output);
  requireOk(outputRel.startsWith(".general-e2e/queue-repairs/") && !outputRel.split("/").includes(".."), "OUTPUT_OUTSIDE_REPAIR_NAMESPACE");
  // Refuse symlink ancestors, including partially created recovery directories.
  let directory = root;
  for (const part of outputRel.split("/")) {
    directory = join(directory, part); const st = await optional(directory);
    if (st) requireOk(st.isDirectory() && !st.isSymbolicLink(), "OUTPUT_UNSAFE");
    else await mkdir(directory);
  }
  const transactionPath = join(output, "transaction.json"), ownerPath = join(queueRoot, "owner-lock.json");
  const guardPath = join(queueRoot, "recovery-owner-lock.json");
  const inspectOwner = dependencies.inspectOwner || deadOwner;
  let transaction = await optional(transactionPath) ? await readJson(transactionPath) : null;
  if (transaction) requireOk(resume && transaction.manifest_sha256 === source.sha256, "RESUME_MANIFEST_MISMATCH");
  if (transaction?.status === "RECOVERED") {
    const queue = await plain(queuePath); requireOk(queue.sha256 === transaction.result_queue_sha256, "RECOVERED_QUEUE_CHANGED");
    return { status: "RECOVERED", idempotent: true, receipt: join(output, "recovery-receipt.json") };
  }
  if (await optional(guardPath)) {
    requireOk(resume && transaction, "RECOVERY_GUARD_EXISTS");
    const guard = await plain(guardPath), owner = JSON.parse(guard.bytes);
    requireOk(owner.operation_id === transaction.operation_id, "RECOVERY_GUARD_OWNER_UNKNOWN");
      requireOk((await inspectOwner(owner))?.exited === true, "OWNER_EXIT_UNVERIFIED");
    await moveVerified(guardPath, join(output, `recovery-guard-${owner.pid}.json`), guard);
  }
  const guard = await open(guardPath, "wx", 0o600), guardStat = await guard.stat();
  let ownedQueueLock = null;
  try {
    const operationId = transaction?.operation_id || randomUUID();
    await guard.writeFile(json({ host: hostname(), pid: process.pid, operation_id: operationId, started_at: new Date().toISOString() }));
    if (!transaction) {
      const queueSource = await plain(queuePath), state = JSON.parse(queueSource.bytes);
      requireOk(queueSource.sha256 === manifest.queue_sha256 && state.frozen_sha256 === sha(JSON.stringify(state.frozen)), "ORIGINAL_QUEUE_DRIFT");
      requireOk(JSON.stringify(state.tasks.map(t => t.task_id)) === JSON.stringify(cfg.taskIds)
        && new Set(state.tasks.map(t => t.attempt_id)).size === state.tasks.length, "TASK_SCOPE_OR_ATTEMPT_DRIFT");
      await verifyWorkBuddyQueueRepairs(root, state);
      const oldScope = { ...state.frozen }, newScope = { ...frozen };
      for (const key of ["driver_sha256", "batch_sha256", "ui_sha256"]) { delete oldScope[key]; delete newScope[key]; }
      requireOk(JSON.stringify(oldScope) === JSON.stringify(newScope) && state.frozen.driver_sha256 === originalDriver.sha256, "FROZEN_SCOPE_OR_DRIVER_DRIFT");
      const ownerFileExists = Boolean(await optional(ownerPath));
      requireOk(ownerFileExists || (state.last_owner && typeof state.last_owner === "object"), "PERSISTED_OWNER_MISSING");
      const ownerBytes = ownerFileExists ? (await plain(ownerPath)).bytes : json(state.last_owner);
      const ownerSource = ownerFileExists ? await plain(ownerPath)
        : { bytes: ownerBytes, sha256: sha(ownerBytes), size: ownerBytes.length };
      const owner = JSON.parse(ownerSource.bytes);
      requireOk(owner.pid === manifest.expected_owner_pid && owner.queue_id === batch.queueId, "OWNER_MISMATCH");
      requireOk((await inspectOwner(owner))?.exited === true, "OWNER_EXIT_UNVERIFIED");
      requireOk(!await optional(join(root, ".general-e2e/workbuddy-ui.lock")), "UI_LOCK_EXISTS");
      const retries = [], byId = new Map(configs.map(c => [c.task.task_id, c]));
      for (const row of state.tasks) {
        const config = byId.get(row.task_id);
        requireOk(config && !await optional(config.lockFile), "ATTEMPT_LOCK_OR_SCOPE_INVALID");
        if (row.phase === "PENDING") {
          requireOk(row.dispatch_attempt_count === 0 && !row.conversation_id && !row.request_id, "PENDING_SEND_UNKNOWN");
          requireOk(!await optional(config.journalFile) && !await optional(config.stateFile) && !await optional(config.bindingFile), "PENDING_ATTEMPT_ALREADY_EXISTS");
          // Recovery does not change unrelated, never-started workspaces.
          // Re-reading all of them also provokes host Office watermarks.
          continue;
        }
        if (row.phase === "FAILED" && row.dispatch_attempt_count === 0) {
          const journalSource = await plain(config.journalFile), journal = JSON.parse(journalSource.bytes);
          requireOk(journal.phase === "FAILED" && journal.identity?.attempt_id === row.attempt_id
            && journal.identity?.task_id === row.task_id && journal.identity?.batch_id === frozen.batch_id
            && journal.identity?.unit_id === frozen.unit_id && journal.prompt?.sha256 === config.promptSha256
            && journal.dataset?.id === cfg.manifest.dataset.id && journal.dataset?.digest === cfg.manifest.dataset.digest
            && journal.candidate_workspace === config.candidateWorkspace && journal.task_root === config.taskRoot
            && journal.prompt?.path === config.promptPath && journal.runtime?.endpoint === config.endpoint
            && journal.expected_ui?.workspace === config.candidateWorkspace && journal.expected_ui?.model === config.expectedModel
            && journal.expected_ui?.permission === config.expectedPermission && !row.conversation_id && !row.request_id && !row.cwd
            && journal.prompt?.send_status === "not_sent" && journal.prompt?.sent_at == null
            && journal.send?.dispatch_attempt_count === 0 && journal.send?.dispatch_armed_at == null
            && journal.send?.dispatch_returned_at == null && journal.send?.error == null
            && journal.send?.pre_send_dom_conversation_id == null && journal.send?.post_send_dom_conversation_id == null
            && journal.native?.baseline == null
            && journal.native?.conversation_id == null && journal.native?.request_id == null && journal.native?.cwd == null
            && journal.verified_ui == null && journal.execution?.error?.code === "WORKBUDDY_PRE_SEND_DRIVER_ERROR"
            && ["WorkBuddy 新建任务按钮数量异常：0", "WORKBUDDY_UI_ERROR_BOUNDARY: native error page requires verified idle recovery"].includes(journal.execution.error.message), "NOT_REGISTERED_ZERO_SEND_FAILURE");
          requireOk(!await optional(config.stateFile) && !await optional(config.bindingFile), "UNEXPECTED_ATTEMPT_ARTIFACT");
          let officeAuditSources = [];
          try { await initialWorkspace(config); }
          catch (error) {
            if (error.message !== "WORKBUDDY_RECOVERY_INITIAL_WORKSPACE_BYTES_DRIFT") throw error;
            const script = fileURLToPath(new URL("../../scripts/initial_office_metadata.py", import.meta.url));
            const auditRoot = join(output, "initial-office", row.task_id + "-" + randomUUID());
            const response = await execFile(manifest.initial_office_python || "/usr/bin/python3", [script,
              "--unit-root", root, "--task-id", row.task_id, "--output-root", auditRoot],
              { timeout: 60000, maxBuffer: 4 * 1024 * 1024, env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
            const audit = JSON.parse(response.stdout), proof = await readJson(audit.proof);
            requireOk(audit.status === "PASS_CWM_ONLY" && proof.schema_version === "wildclawbench.workbuddy-initial-office-metadata/v1"
              && proof.identity?.task_id === row.task_id && proof.identity?.batch_id === frozen.batch_id
              && proof.identity?.unit_id === frozen.unit_id && proof.execution_manifest_sha256 === frozen.manifest_sha256
              && proof.validator_sha256 === sha(await readFile(script)) && proof.workspace_modified === false, "INITIAL_OFFICE_AUDIT_INVALID");
            for (const item of audit.artifacts) {
              const path = resolve(root, item.path);
              requireOk(relative(auditRoot, path) && !relative(auditRoot, path).startsWith("..") && !isAbsolute(relative(auditRoot, path)), "INITIAL_OFFICE_AUDIT_PATH_INVALID");
              const saved = await plain(path);
              requireOk(saved.sha256 === item.sha256 && saved.size === item.size, "INITIAL_OFFICE_AUDIT_DRIFT");
            }
            await initialWorkspace(config, proof.variants);
            officeAuditSources = audit.artifacts;
          }
          let priorRecovery = null;
          if (config.zeroSendRecovery) {
            const path = join(config.controlRoot, "zero-send-recovery.json"), original = await plain(path);
            priorRecovery = { path, destination: join(output, "original-case-recovery", row.task_id, "zero-send-recovery.json"),
              ...original, bytes: undefined,
              prior_sources: [config.zeroSendRecovery.proof.original_journal, ...(config.zeroSendRecovery.proof.prior_sources || []),
                ...(config.zeroSendRecovery.proof.audit_sources || [])] };
          }
          retries.push({ task_id: row.task_id, attempt_id: row.attempt_id, path: config.journalFile,
            destination: join(output, "original-attempts", row.task_id, "dispatch-journal.json"),
            ...journalSource, bytes: undefined, prior_recovery: priorRecovery, office_audit_sources: officeAuditSources });
        } else {
          requireOk(row.dispatch_attempt_count === 1 && row.conversation_id && row.request_id, "UNKNOWN_OR_ACCEPTED_FAILURE");
          await synchronizeRow(root, row);
          requireOk(row.phase === "COMPLETED" || row.phase === "FAILED", "BOUND_ATTEMPT_NOT_TERMINAL");
        }
      }
      requireOk(retries.length && JSON.stringify(retries.map(r => r.task_id)) === JSON.stringify(manifest.retry_task_ids), "RETRY_SCOPE_MISMATCH");
      const zeroWorkspaces = new Set(state.tasks.filter(t => t.phase === "PENDING" || retries.some(r => r.task_id === t.task_id)).map(t => byId.get(t.task_id).candidateWorkspace));
      const firstProof = await (dependencies.verifyIdle || verifyIdle)(configs[0], zeroWorkspaces);
      requireOk(firstProof?.verified === true, "FRESH_IDLE_REQUIRED");
      await writeFile(join(output, "manifest.json"), source.bytes, { flag: "wx", mode: 0o600 });
      await writeFile(join(output, "original-queue.json"), queueSource.bytes, { flag: "wx", mode: 0o600 });
      await writeFile(join(output, "first-idle.json"), json(firstProof), { flag: "wx", mode: 0o600 });
      if (!ownerFileExists) await writeFile(join(output, "owner-record.from-queue.json"), ownerSource.bytes, { flag: "wx", mode: 0o600 });
      transaction = { schema_version: SCHEMA, status: "PREPARED", operation_id: operationId, manifest_sha256: source.sha256,
        owner: { kind: ownerFileExists ? "stale-lock-file" : "persisted-queue-owner", path: ownerPath,
          destination: join(output, ownerFileExists ? "owner-lock.original.json" : "owner-record.from-queue.json"),
          ...ownerSource, bytes: undefined },
        queue_sha256: queueSource.sha256, state, retries, zero_workspaces: [...zeroWorkspaces],
        first_idle_sha256: sha(json(firstProof)) };
      await persist(transactionPath, transaction);
    }
    if (await optional(ownerPath)) {
      const currentOwner = await plain(ownerPath);
      if (currentOwner.sha256 !== transaction.owner.sha256) {
        const record = JSON.parse(currentOwner.bytes);
        requireOk(record.operation_id === transaction.operation_id && record.queue_id === batch.queueId, "UNKNOWN_REPLACEMENT_OWNER");
        requireOk((await inspectOwner(record))?.exited === true, "OWNER_EXIT_UNVERIFIED");
        await moveVerified(ownerPath, join(output, `recovery-queue-owner-${record.pid}.json`), currentOwner);
      }
    }
    const currentQueue = await plain(queuePath);
    if (currentQueue.sha256 !== transaction.queue_sha256) {
      const committed = JSON.parse(currentQueue.bytes);
      requireOk(committed.phase === "PENDING" && committed.frozen_sha256 === digest
        && committed.source_repairs?.at(-1)?.operation_id === transaction.operation_id
        && committed.events?.at(-1)?.event === "ZERO_SEND_PREPARATION_RECOVERY", "QUEUE_CHANGED_DURING_RECOVERY");
      await verifyWorkBuddyQueueRepairs(root, committed);
      const idle = await (dependencies.verifyIdle || verifyIdle)(configs[0], new Set(transaction.zero_workspaces));
      requireOk(idle?.verified === true, "FINAL_IDLE_REQUIRED");
      const receipt = { schema_version: SCHEMA, status: "RECOVERED", committed_recovery_completed: true,
        operation_id: transaction.operation_id, result_queue_sha256: currentQueue.sha256,
        retried_preparation_count: transaction.retries.length, new_prompts_sent: 0, final_idle: idle };
      await persist(join(output, "recovery-receipt.json"), receipt);
      transaction.status = "RECOVERED"; transaction.result_queue_sha256 = currentQueue.sha256;
      await persist(transactionPath, transaction);
      return { status: "RECOVERED", receipt: join(output, "recovery-receipt.json"), new_prompts_sent: 0 };
    }
    const owner = JSON.parse((await plain(await optional(ownerPath) ? ownerPath : transaction.owner.destination)).bytes);
    requireOk((await inspectOwner(owner))?.exited === true, "OWNER_EXIT_UNVERIFIED");
    const firstIdleBytes = await plain(join(output, "first-idle.json"));
    requireOk(firstIdleBytes.sha256 === transaction.first_idle_sha256, "INITIAL_IDLE_PROOF_DRIFT");
    const firstIdle = JSON.parse(firstIdleBytes.bytes);
    const finalProof = await (dependencies.verifyIdle || verifyIdle)(configs[0], new Set(transaction.zero_workspaces));
    requireOk(finalProof?.verified === true, "FINAL_IDLE_REQUIRED");
    requireOk(JSON.stringify(finalProof.process) === JSON.stringify(firstIdle.process), "PROCESS_CHANGED_DURING_RECOVERY");
    const artifacts = [], relocations = [];
    const ref = async path => { const value = await plain(path); const item = { path: relative(root, path).split("\\").join("/"), sha256: value.sha256, size: value.size }; artifacts.push(item); return item; };
    const finalIdlePath = join(output, "final-idle-" + randomUUID() + ".json");
    await writeFile(finalIdlePath, json(finalProof), { flag: "wx", mode: 0o600 });
    await ref(join(output, "manifest.json")); await ref(join(output, "original-queue.json"));
    await ref(join(output, "first-idle.json")); await ref(finalIdlePath);
    for (const retry of transaction.retries) {
      await moveVerified(retry.path, retry.destination, retry);
      await dependencies.afterArchive?.({ task_id: retry.task_id, destination: retry.destination });
      const originalJournal = await ref(retry.destination);
      for (const item of retry.office_audit_sources || []) {
        const saved = await ref(join(root, item.path));
        requireOk(saved.sha256 === item.sha256 && saved.size === item.size, "INITIAL_OFFICE_AUDIT_DRIFT");
      }
      const proofPath = join(dirname(retry.path), "zero-send-recovery.json");
      let priorSources = [];
      if (retry.prior_recovery) {
        const prior = retry.prior_recovery;
        // A previous zero-send proof is part of the audit chain, not a file
        // that may be overwritten by the next preparation recovery.
        const current = await optional(prior.path);
        if (current && (await plain(prior.path)).sha256 !== prior.sha256) {
          // Only a partially committed new proof from this exact transaction
          // may occupy the active path on resume.
          const value = await readJson(prior.path);
          requireOk(resume && value.operation_id === transaction.operation_id, "PRIOR_RECOVERY_ACTIVE_PATH_CHANGED");
          requireOk((await plain(prior.destination)).sha256 === prior.sha256, "PRIOR_RECOVERY_ARCHIVE_DRIFT");
        } else await moveVerified(prior.path, prior.destination, prior);
        const archivedProof = await ref(prior.destination);
        const oldPath = relative(root, prior.path).split("\\").join("/");
        relocations.push({ original_path: oldPath, relocated: archivedProof });
        for (const oldRepair of transaction.state.source_repairs || []) {
          oldRepair.artifacts = oldRepair.artifacts.map(item => {
            if (item.path !== oldPath) return item;
            requireOk(item.sha256 === prior.sha256 && item.size === prior.size, "PRIOR_REPAIR_REFERENCE_DRIFT");
            return archivedProof;
          });
        }
        priorSources = [archivedProof, ...prior.prior_sources];
        for (const item of prior.prior_sources) {
          const saved = await plain(join(root, item.path));
          requireOk(saved.sha256 === item.sha256 && saved.size === item.size, "PRIOR_SOURCE_DRIFT");
        }
      }
      const proof = { schema_version: "wildclawbench.workbuddy-zero-send-case-recovery/v1",
        identity: { batch_id: frozen.batch_id, unit_id: frozen.unit_id, task_id: retry.task_id, attempt_id: retry.attempt_id },
        prompt_sha256: configs.find(c => c.task.task_id === retry.task_id).promptSha256,
        original_journal: originalJournal, original_queue_sha256: transaction.queue_sha256,
        recovery_manifest_sha256: transaction.manifest_sha256, operation_id: transaction.operation_id,
        ...(priorSources.length ? { prior_sources: priorSources } : {}),
        ...(retry.office_audit_sources?.length ? { audit_sources: retry.office_audit_sources } : {}) };
      if (await optional(proofPath)) requireOk((await plain(proofPath)).bytes.equals(json(proof)), "CASE_RECOVERY_PROOF_DRIFT");
      else await writeFile(proofPath, json(proof), { flag: "wx", mode: 0o600 });
      const caseProof = await ref(proofPath);
      const row = transaction.state.tasks.find(t => t.task_id === retry.task_id);
      Object.assign(row, { phase: "PENDING", dispatch_attempt_count: 0, conversation_id: null, request_id: null, cwd: null,
        started_at: null, dispatch_started_at: null, finished_at: null, native_started_at: null, native_finished_at: null,
        error: null, exit_code: null, pre_send_recovery: caseProof });
    }
    if (transaction.owner.kind === "stale-lock-file") await moveVerified(ownerPath, transaction.owner.destination, transaction.owner);
    else requireOk(!await optional(ownerPath) && (await plain(transaction.owner.destination)).sha256 === transaction.owner.sha256, "PERSISTED_OWNER_DRIFT");
    await ref(transaction.owner.destination);
    ownedQueueLock = await open(ownerPath, "wx", 0o600);
    await ownedQueueLock.writeFile(json({ pid: process.pid, host: hostname(), started_at: new Date().toISOString(), queue_id: batch.queueId, operation_id: transaction.operation_id }));
    const state = transaction.state;
    state.frozen = frozen; state.frozen_sha256 = digest; state.worker.version = WORKBUDDY_QUEUE_VERSION;
    state.last_owner = owner;
    state.phase = "PENDING"; state.active_task_ids = [];
    state.source_repairs = [...(state.source_repairs || []), { schema_version: SCHEMA, artifacts,
      original_queue_sha256: transaction.queue_sha256, operation_id: transaction.operation_id, relocations }];
    state.events.push({ event: "ZERO_SEND_PREPARATION_RECOVERY", at: new Date().toISOString(),
      operation_id: transaction.operation_id, retry_task_ids: transaction.retries.map(r => r.task_id), reason: manifest.reason });
    requireOk((await plain(queuePath)).sha256 === transaction.queue_sha256, "QUEUE_CHANGED_BEFORE_COMMIT");
    await persist(queuePath, state);
    await dependencies.afterQueueCommit?.();
    const result = { schema_version: SCHEMA, status: "RECOVERED", operation_id: transaction.operation_id,
      queue_id: batch.queueId, retried_preparation_count: transaction.retries.length,
      accepted_attempts_preserved: state.tasks.filter(t => t.dispatch_attempt_count === 1).length,
      new_prompts_sent: 0, original_queue_sha256: transaction.queue_sha256, result_queue_sha256: (await plain(queuePath)).sha256,
      first_idle: join(output, "first-idle.json"), final_idle: finalProof, artifacts };
    await persist(join(output, "recovery-receipt.json"), result);
    transaction.status = "RECOVERED"; transaction.result_queue_sha256 = result.result_queue_sha256;
    await persist(transactionPath, transaction);
    return { status: "RECOVERED", receipt: join(output, "recovery-receipt.json"),
      retried_preparation_count: result.retried_preparation_count, new_prompts_sent: 0 };
  } finally {
    if (ownedQueueLock) {
      const info = await ownedQueueLock.stat(); await ownedQueueLock.close(); const current = await optional(ownerPath);
      if (current?.ino === info.ino && current.dev === info.dev) await unlink(ownerPath);
    }
    await guard.close(); const current = await optional(guardPath);
    if (current?.ino === guardStat.ino && current.dev === guardStat.dev) await unlink(guardPath);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), index = args.indexOf("--manifest");
  if (index < 0 || !args[index + 1]) throw new Error("usage: recover-queue.mjs --manifest ABS [--resume]");
  recoverWorkBuddyQueue(args[index + 1], { resume: args.includes("--resume") })
    .then(result => console.log(JSON.stringify(result, null, 2)))
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
