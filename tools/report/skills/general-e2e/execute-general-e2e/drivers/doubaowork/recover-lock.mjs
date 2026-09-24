#!/usr/bin/env node
import { randomUUID } from "node:crypto";
import { realpath, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { chromium } from "playwright-core";
import { validateGeneralTask, validateGeneralResume } from "./prepared-task.mjs";
import { readAttemptState } from "../../vendor/e2e-shared/doubaowork/state.mjs";
import { recoverStaleAttemptLock } from "../../vendor/e2e-shared/doubaowork/lock-recovery.mjs";
import { readWorkerLock, inspectPage, assertNoConflictingActivity } from "../../vendor/e2e-shared/doubaowork/controller.mjs";
import { readNativeActivity, assertNativeActivityAllowed } from "../../vendor/e2e-shared/doubaowork/runtime-activity.mjs";
import { selectUniqueChatTarget } from "../../vendor/e2e-shared/doubaowork/lib.mjs";
import { listSessionDirectoryIds } from "../../vendor/e2e-shared/doubaowork/platform.mjs";
import { collectNativeToolObserver, readNativeToolActivity, assertNativeToolActivityAllowed } from "../../vendor/e2e-shared/doubaowork/runtime-tools.mjs";
import { collectNativeLifecycleObserver } from "../../vendor/e2e-shared/doubaowork/runtime-lifecycle.mjs";
import { runProbe } from "./probe.mjs";

export async function recoverGeneralAttempt({ unitRoot, taskId, expectedOwnerId }) {
  const initial = await validateGeneralTask({ unitRoot, taskId });
  const attemptRoot = join(initial.unitRoot, ".general-e2e/execution", taskId, "doubaowork");
  if (await realpath(attemptRoot) !== resolve(attemptRoot)) throw new Error("DOUBAOWORK_RECOVERY_PATH_UNSAFE");
  const stateFile = join(attemptRoot, "automation_state.json"), state = await readAttemptState(stateFile);
  if (state.prepared?.managed_queue_id) throw new Error("DOUBAOWORK_RECOVERY_MANAGED_QUEUE_NOT_SUPPORTED");
  const config = await validateGeneralTask({ unitRoot, taskId, expectedPermission: state.requested.permission_mode });
  await validateGeneralResume(state, config);
  const owner = await readWorkerLock(join(attemptRoot, ".doubaowork-driver.lock"));
  if (owner.pid !== state.runtime.driver_pid || owner.instance_id !== expectedOwnerId
      || JSON.stringify(owner) !== JSON.stringify(state.runtime.lock_owner)) throw new Error("DOUBAOWORK_RECOVERY_JOURNAL_OWNER_MISMATCH");
  const output = join(attemptRoot, `lock-recovery-${randomUUID()}.json`);
  await writeFile(output, JSON.stringify({ status: "STARTED", attempt_id: state.attempt_id }) + "\n", { flag: "wx", mode: 0o600 });
  try {
    const result = await recoverStaleAttemptLock({ attemptRoot, uiRoot: join(homedir(), ".wildclawbench/locks/doubaowork-ui"),
      expectedOwnerId, protectedFiles: [stateFile, config.manifestPath, config.promptFile], verifyIdle: async () => {
        const probe = await runProbe({ appPath: state.client.app_path, endpoint: state.client.endpoint });
        if (probe.status !== "passed" || probe.app.version !== state.client.version) throw new Error("DOUBAOWORK_RECOVERY_FRESH_PROBE_FAILED");
        const browser = await chromium.connectOverCDP(state.client.endpoint, { timeout: 10000 });
        try {
          const pages = browser.contexts().flatMap(c => c.pages());
          const page = selectUniqueChatTarget(pages.map(page => ({ url: page.url(), page }))).page;
          const activity = await readNativeActivity(page), observation = await inspectPage(page);
          assertNativeActivityAllowed(activity); assertNoConflictingActivity(observation.snapshot);
          const background = await readNativeToolActivity(browser); assertNativeToolActivityAllowed(background, [], activity);
          return { verified: true, checked_at: new Date().toISOString(), probe, native_activity: activity, background_activity: background,
            ui: { current_path: observation.snapshot.current_path, visible_dialog_count: observation.snapshot.visible_dialog_count,
              user_question_count: observation.snapshot.user_question_count, approval_count: observation.snapshot.approval_count } };
        } finally { await browser.close(); }
      }, beforeRelease: async () => {
        if (state.send.dispatch_attempt_count !== 0) return { status: "retained-for-original-dispatch-observation" };
        const browser = await chromium.connectOverCDP(state.client.endpoint, { timeout: 10000 });
        try {
          const page = selectUniqueChatTarget(browser.contexts().flatMap(c => c.pages()).map(page => ({ url: page.url(), page }))).page;
          assertNativeActivityAllowed(await readNativeActivity(page));
          const ui = (await inspectPage(page)).snapshot; assertNoConflictingActivity(ui);
          const directories = await listSessionDirectoryIds();
          if (state.session.conversation_id || ui.current_conversation_id || ui.user_message_count !== 0
              || JSON.stringify(directories.sort()) !== JSON.stringify([...state.session.baseline_session_directory_ids].sort())) {
            throw new Error("DOUBAOWORK_RECOVERY_ZERO_SEND_SCOPE_UNVERIFIED");
          }
          const input = { attemptId: state.attempt_id, workspace: state.workspace };
          const tools = await collectNativeToolObserver(browser, { ...input, unsent: true });
          const lifecycle = await collectNativeLifecycleObserver(page, input);
          if (tools.status !== "unavailable" && (tools.events.length || tools.errors.length || tools.unknown_context_events || tools.overflow)
              || lifecycle.status !== "unavailable" && (lifecycle.samples.length || lifecycle.errors.length || lifecycle.native_request_session_id)) {
            throw new Error("DOUBAOWORK_RECOVERY_UNSENT_OBSERVER_HAS_EVENTS");
          }
          const toolResult = await collectNativeToolObserver(browser, { ...input, unsent: true, restore: true });
          const lifecycleResult = await collectNativeLifecycleObserver(page, { ...input, restore: true });
          return { status: "empty-unsent-observers-restored", native_session_directories_unchanged: true,
            ui_user_message_count: 0, tools, lifecycle, tools_restored: toolResult.observer_restored ?? null,
            lifecycle_restored: lifecycleResult.observer_restored ?? null };
        } finally { await browser.close(); }
      } });
    const receipt = { ...result, identity: state.identity, attempt_id: state.attempt_id, output };
    await writeFile(output, JSON.stringify(receipt, null, 2) + "\n");
    return receipt;
  } catch (error) {
    await writeFile(output, JSON.stringify({ status: "NEEDS_ATTENTION", attempt_id: state.attempt_id, error: error.message }, null, 2) + "\n");
    throw error;
  }
}

export async function main(args = process.argv.slice(2)) {
  const { values: v } = parseArgs({ args, options: { "unit-root": { type: "string" }, "task-id": { type: "string" },
    "expected-owner-id": { type: "string" }, help: { type: "boolean" } } });
  if (v.help) { console.log("--unit-root ABS --task-id ID --expected-owner-id EXACT_INSTANCE_ID; requires dead same-host single-attempt owner and fresh native/UI idle proof; does not send or change journals."); return; }
  const r = await recoverGeneralAttempt({ unitRoot: v["unit-root"], taskId: v["task-id"], expectedOwnerId: v["expected-owner-id"] });
  console.log(JSON.stringify({ status: r.status, attempt_id: r.attempt_id, journal_unchanged: r.journal_unchanged, output: r.output }, null, 2));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(e => { console.error(e.message); process.exitCode = 1; });
