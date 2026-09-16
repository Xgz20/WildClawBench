import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { empty } from "./parsers.mjs";

export function captureResourceMetrics(config, state, harness, overrides = {}) {
  if ((overrides.environment || process.env).WEB_E2E_RESOURCE_METRICS === "off") return Promise.resolve(empty("DISABLED"));
  const run = overrides.spawn || spawn;
  return new Promise(resolve => {
    let child;
    try {
      child = run(process.execPath, [fileURLToPath(new URL("./worker.mjs", import.meta.url))], {
        stdio: ["pipe", "pipe", "ignore"], windowsHide: true,
      });
    } catch { resolve(empty("COLLECTOR_START_FAILED")); return; }
    let stdout = "", settled = false;
    const finish = (value) => { if (!settled) { settled = true; clearTimeout(timer); resolve(value); } };
    // 数据库锁、损坏日志和慢磁盘不能阻塞执行终态或触发重发 Prompt。
    const timer = setTimeout(() => { child.kill("SIGKILL"); finish(empty("COLLECTION_TIMEOUT")); }, overrides.timeoutMilliseconds || 25000);
    child.stdout.on("data", chunk => {
      stdout += chunk;
      if (stdout.length > 262144) { child.kill("SIGKILL"); finish(empty("OUTPUT_LIMIT")); }
    });
    child.once("error", () => finish(empty("COLLECTOR_START_FAILED")));
    child.stdin.on("error", () => {});
    // close 在 stdout 排空之后触发；exit 可能早于末块 JSON。
    child.once("close", code => {
      try {
        const result = code === 0 ? JSON.parse(stdout) : empty("COLLECTOR_FAILED");
        if (!result?.usage || !result?.tools || !result?.execution || !result?.collection?.metrics) throw new Error("INVALID");
        finish(result);
      }
      catch { finish(empty("COLLECTOR_INVALID_OUTPUT")); }
    });
    child.stdin.end(JSON.stringify({ harness, workspace: config.workspace, sessionDb: config.sessionDb,
      state: { session: state.session, timing: state.timing, attempt_id: state.attempt_id } }));
  });
}
