#!/usr/bin/env node
import { parseArgs } from "node:util";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { startDevelopmentRun, resumeDevelopmentRun, retryPreSendDevelopmentRun, dispatchPreparedRun } from "../../vendor/e2e-shared/doubaowork/controller.mjs";
import { DEFAULT_ENDPOINT, DEFAULT_APP_PATH } from "../../vendor/e2e-shared/doubaowork/lib.mjs";
import { validateGeneralTask, validateGeneralResume } from "./prepared-task.mjs";
import { managedPeerConversations } from "./managed-queue.mjs";

export async function main(argv = process.argv.slice(2)) {
  const { values: v } = parseArgs({ args: argv, options: {
    "unit-root": { type: "string" }, "task-id": { type: "string" },
    "project-name": { type: "string" }, "expected-permission": { type: "string", default: "current" },
    "managed-queue-id": { type: "string" },
    "prepare-only": { type: "boolean" }, "dispatch-prepared": { type: "boolean" },
    "app-path": { type: "string", default: DEFAULT_APP_PATH }, endpoint: { type: "string", default: DEFAULT_ENDPOINT },
    resume: { type: "boolean" }, "retry-pre-send-failure": { type: "boolean" }, "observe-seconds": { type: "string", default: "30" }, help: { type: "boolean" },
  } });
  if (v.help) {
    console.log("DoubaoWork General: --unit-root ABS --task-id ID --project-name NAME [--resume --observe-seconds 30]. Native terminal/cwd unavailable => NEEDS_ATTENTION; no formal receipt.");
    return;
  }
  const config = await validateGeneralTask({ unitRoot: v["unit-root"], taskId: v["task-id"], expectedPermission: v["expected-permission"] });
  if (v["managed-queue-id"]) {
    config.frozenIdentity.managed_queue_id = v["managed-queue-id"];
    const peers = await managedPeerConversations(config, v["managed-queue-id"]);
    config.allowedActiveConversationIds = peers.conversationIds;
    config.allowedActiveSessionIds = peers.sessionIds;
  }
  const observeSeconds = Number(v["observe-seconds"]);
  if (!Number.isFinite(observeSeconds) || observeSeconds <= 0 || observeSeconds > 900) throw new Error("Invalid observation window");
  const options = {
    scene: "general", taskRoot: config.taskRoot,
    outputDir: join(config.unitRoot, ".general-e2e", "execution", config.taskId, "doubaowork"),
    projectName: v["project-name"], endpoint: v.endpoint, appPath: v["app-path"], observeSeconds,
    prepareOnly: v["prepare-only"],
    validateTask: async () => config, validateResume: state => validateGeneralResume(state, config),
    connect: (...args) => chromium.connectOverCDP(...args),
  };
  if (v["retry-pre-send-failure"] && !v.resume) throw new Error("Retry requires --resume");
  if (v["prepare-only"] && (v.resume || v["dispatch-prepared"])) throw new Error("Prepare-only cannot resume or dispatch");
  if (v["dispatch-prepared"] && (!v.resume || v["retry-pre-send-failure"])) throw new Error("Prepared dispatch requires a separate --resume");
  const result = v["dispatch-prepared"] ? await dispatchPreparedRun(options)
    : v["retry-pre-send-failure"] ? await retryPreSendDevelopmentRun(options)
    : v.resume ? await resumeDevelopmentRun(options) : await startDevelopmentRun(options);
  console.log(JSON.stringify({ state: result.state, formal_execution_record_created: false }, null, 2));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
