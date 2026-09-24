// Web input/finalization policy; UI, dispatch and evidence live in one shared component.
import { chromium } from "playwright-core";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { DEFAULT_ENDPOINT, DEFAULT_APP_PATH } from "./lib.mjs";
import { validatePreparedTaskRoot } from "./prepared-task.mjs";
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
  const result = values.resume && values["retry-pre-send-failure"]
    ? await retryPreSendDevelopmentRun({ ...adapter, outputDir: values["output-dir"] })
    : values.resume
      ? await resumeDevelopmentRun({ ...adapter, outputDir: values["output-dir"], observeSeconds })
    : await startDevelopmentRun({
      ...adapter,
      taskRoot: values["task-root"],
      outputDir: values["output-dir"],
      projectName: values["project-name"],
      endpoint: values.endpoint,
      appPath: values["app-path"],
    });
  process.stdout.write(`${JSON.stringify({
    status: "ok",
    development_only: true,
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
