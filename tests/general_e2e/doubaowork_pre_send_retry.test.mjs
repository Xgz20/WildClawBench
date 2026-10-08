import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import vm from "node:vm";
import { assertPreSendRetryEligible } from "../../tools/report/e2e-shared/doubaowork/controller.mjs";
import { createAttemptState, transitionAttempt } from "../../tools/report/e2e-shared/doubaowork/state.mjs";

test("a failed pre-send reconnect preserves the active journal and idempotent archive", async t => {
  const root = await mkdtemp(join(tmpdir(), "doubao-zero-send-retry-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = await readFile(new URL("../../tools/report/e2e-shared/doubaowork/controller.mjs", import.meta.url), "utf8");
  const STATE_FILE = /const STATE_FILE = "([^"]+)"/.exec(source)[1];
  const previous = createAttemptState({ attemptId: "fixture", batchId: "batch", taskId: "task", workspace: join(root, "workspace"),
    promptFile: join(root, "prompt.md"), prompt: "fixture" });
  previous.scene = "general"; previous.client.project_name = "fixture"; previous.client.manifest_sha256 = "a".repeat(64);
  transitionAttempt(previous, "CLIENT_READY"); transitionAttempt(previous, "INFRA_FAILED");
  previous.error = { code: "DEVELOPMENT_PRE_SEND_FAILED" };
  assertPreSendRetryEligible(previous);
  const stateFile = join(root, STATE_FILE), bytes = Buffer.from(JSON.stringify(previous));
  await writeFile(stateFile, bytes);
  // Execute the production function bodies; only connection and lock adapters
  // are replaced. This fixture never connects to a client or dispatches a task.
  const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end));
  const release = async () => {}; release.owner = {};
  const context = vm.createContext({ isAbsolute, resolve, dirname, join, STATE_FILE, readFile, writeFile, mkdir, rm,
    acquireExclusiveWorkerLock: async () => release,
    readAttemptState: async path => JSON.parse(await readFile(path)), assertPreSendRetryEligible,
    preflightDoubaoPaths: async () => ({}), releaseUnsentObserver: async () => {},
    connectClient: async () => { throw new Error("fixture connection failed"); },
  });
  vm.runInContext(section("async function archiveAttemptState(", "async function dispatchFromSelectedProject(")
    + section("async function markFailure(", "export function assertPreSendRetryEligible(")
    + section("async function retryPreSendDevelopmentRunUnlocked(", "async function navigateToConversation("), context);
  const options = { outputDir: root, scene: "general", validateTask: async () => ({ batchId: "batch", taskId: "task",
    workspace: previous.workspace, promptFile: previous.prompt.file, promptSha256: previous.prompt.sha256, manifestSha256: previous.client.manifest_sha256 }) };
  for (let attempt = 0; attempt < 2; attempt++) {
    await assert.rejects(context.retryPreSendDevelopmentRunUnlocked(options), /fixture connection failed/);
    assert.deepEqual(await readFile(stateFile), bytes);
    await access(join(root, ".attempts", previous.attempt_id, STATE_FILE));
  }
});
