// Web input/finalization policy; UI, dispatch and evidence live in one shared component.
import { createHash } from "node:crypto";
import { chromium } from "playwright-core";
import { homedir } from "node:os";
import { publishFrozenTransaction } from "./publication.mjs";
import { acquireExclusiveWorkerLock } from "../../vendor/e2e-shared/doubaowork/controller.mjs";
import { lstat } from "node:fs/promises";
import { join, resolve, sep } from "node:path";
import { finalizeWebObservation, validateFormalResume, verifyFormalReceipt } from "./formal.mjs";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { DEFAULT_ENDPOINT, DEFAULT_APP_PATH } from "./lib.mjs";
import { validatePreparedTaskRoot } from "./prepared-task.mjs";
import { managedPeerConversations } from "./managed-peers.mjs";
import { assessDoubaoWebFinalization } from "./finalizer.mjs";
import { startDevelopmentRun, resumeDevelopmentRun, retryPreSendDevelopmentRun } from "../../vendor/e2e-shared/doubaowork/controller.mjs";
export * from "../../vendor/e2e-shared/doubaowork/controller.mjs";
export { validatePreparedTaskRoot } from "./prepared-task.mjs";
const adapter = {
  validateTask: validatePreparedTaskRoot,
  connect: (...args) => chromium.connectOverCDP(...args),
  assessFinalization: assessDoubaoWebFinalization,
};
export async function main(argv = process.argv.slice(2)) {
  const { values } = parseArgs({
    args: argv,
    options: {
      "task-root": { type: "string" },
      "output-dir": { type: "string" },
      "project-name": { type: "string" },
      endpoint: { type: "string", default: DEFAULT_ENDPOINT },
      "app-path": { type: "string", default: DEFAULT_APP_PATH },
      "formal-receipt": { type: "boolean", default: false },
      "managed-run-id": { type: "string" },
      "expected-ui-model": { type: "string" },
      resume: { type: "boolean", default: false },
      "retry-pre-send-failure": { type: "boolean", default: false },
      "observe-seconds": { type: "string", default: "900" },
    },
  });
  if (!values["output-dir"]) throw new Error("--output-dir 必填，且必须位于单题目录外");
  if (!values.resume && !values["task-root"]) {
    throw new Error("--task-root 必填，且必须是 prepared execution 单题根目录的绝对路径");
  }
  if (values["retry-pre-send-failure"] && !values.resume) {
    throw new Error("--retry-pre-send-failure 必须与 --resume 同时使用");
  }
  const observeSeconds = Number(values["observe-seconds"]);
  if (!Number.isFinite(observeSeconds) || observeSeconds <= 0 || observeSeconds > 900) {
    throw new Error("--observe-seconds 必须是 1–900 秒");
  }
  const formal = values["formal-receipt"];
  const runId = values["managed-run-id"] ?? null;
  if (runId && (!formal || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/u.test(runId))) throw new Error("DOUBAOWORK_WEB_BATCH_RUN_ID_INVALID");
  const runAdapter = { ...adapter };
  if (formal) {
    const outputDir = resolve(values["output-dir"]);
    const published = await lstat(join(outputDir, "formal-publication.json")).catch(e => { if (e.code !== "ENOENT") throw e; return null; });
    if (published) {
      if (!values.resume) throw new Error("正式执行已存在，请使用 --resume 复验");
      console.log(JSON.stringify(await verifyFormalReceipt(outputDir), null, 2));
      return 0;
    }
    const transaction = await lstat(join(outputDir, "formal-transaction.json")).catch(e => { if (e.code !== "ENOENT") throw e; return null; });
    if (transaction) {
      if (!values.resume) throw new Error("正式发布事务已存在，请使用 --resume");
      const releaseUI = await acquireExclusiveWorkerLock(join(homedir(), ".wildclawbench/locks/doubaowork-ui"));
      try {
        const release = await acquireExclusiveWorkerLock(outputDir);
        try { await publishFrozenTransaction(outputDir); console.log(JSON.stringify(await verifyFormalReceipt(outputDir), null, 2)); }
        finally { await release(); }
      } finally { await releaseUI(); }
      return 0;
    }
    runAdapter.validateTask = async taskRoot => {
      const config = await validatePreparedTaskRoot(taskRoot, { formal: true, batch: Boolean(runId), runId });
      if (runId) {
        const peers = await managedPeerConversations(config, runId);
        config.allowedActiveConversationIds = peers.conversationIds;
        config.allowedActiveSessionIds = peers.sessionIds;
        config.allowedNativePeers = peers.peers;
        config.frozenIdentity.allowed_peer_identity_hashes = peers.peers.map(peer =>
          createHash("sha256").update(`${peer.conversation_id}:${peer.native_request_session_id}:${peer.workspace}`).digest("hex"));
      }
      config.captureNativeTools = true;
      config.captureNativeLifecycle = true;
      if (values["expected-ui-model"]) config.requestedModel = values["expected-ui-model"];
      if (runId && outputDir !== join(config.harnessRoot, ".execute-web-e2e", "doubaowork-batch", runId, "tasks", config.taskId)) throw new Error("DOUBAOWORK_WEB_BATCH_CONTROL_PATH_INVALID");
      if (!outputDir.startsWith(config.harnessRoot + sep) || outputDir.startsWith(config.taskRoot + sep)) throw new Error("正式控制目录必须位于 Harness 根下、单题目录外");
      return config;
    };
    runAdapter.validateResume = async state => {
      await validateFormalResume(state);
      if ((state.prepared?.run_id ?? null) !== runId) throw new Error("DOUBAOWORK_WEB_BATCH_RUN_ID_DRIFT");
    };
    runAdapter.finalizeObservation = finalizeWebObservation;
  }
  const result = values.resume && values["retry-pre-send-failure"]
    ? await retryPreSendDevelopmentRun({ ...runAdapter, outputDir: values["output-dir"] })
    : values.resume
      ? await resumeDevelopmentRun({ ...runAdapter, outputDir: values["output-dir"], observeSeconds })
    : await startDevelopmentRun({
      ...runAdapter,
      taskRoot: values["task-root"],
      outputDir: values["output-dir"],
      projectName: values["project-name"],
      endpoint: values.endpoint,
      appPath: values["app-path"],
    });
  process.stdout.write(`${JSON.stringify({
    status: "ok",
    development_only: !formal,
    formal_result: result.formal_result ?? null,
    state: result.state,
    slot_status: result.slot_status ?? "SLOT_HELD",
  }, null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
