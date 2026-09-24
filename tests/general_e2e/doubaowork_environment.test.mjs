import { test } from "node:test";
import assert from "node:assert/strict";
import { inspectEndpointListener, verifyExecutionEnvironment } from "../../tools/report/e2e-shared/doubaowork/platform.mjs";

const app = { browser_executable: "/Applications/DoubaoWork.app/Contents/Helpers/DoubaoWork Browser.app/Contents/MacOS/DoubaoWork Browser" };
const processIdentity = { pid: 123, process_start_identity: "Thu Sep 24 10:00:00 2026", command_sha256: "a".repeat(64) };
const listener = { unique_expected_listener: true, listeners: [processIdentity] };
const client = { app, endpoint: "http://127.0.0.1:9260", listener };

test("Doubao listener requires a stable process birth identity across command inspection", async () => {
  for (const changed of [false, true]) {
    let reads = 0;
    const run = async (command, args) => ({ stdout: command.endsWith("lsof")
      ? "p123\ncDoubaoWork Browser\nn127.0.0.1:9260\n"
      : args.includes("command=") ? `${app.browser_executable} --remote-debugging-port=9260`
        : (++reads === 2 && changed ? "another-start" : processIdentity.process_start_identity) });
    const result = inspectEndpointListener(client.endpoint, app, { run });
    if (changed) await assert.rejects(result, /LISTENER_PROCESS_CHANGED/);
    else { const value = await result; assert.equal(value.unique_expected_listener, true); assert.equal(value.listeners[0].process_start_identity, processIdentity.process_start_identity); }
  }
});

test("Doubao final environment gate rejects a late lock and replacement listener", async () => {
  let checkedListener = false;
  await assert.rejects(verifyExecutionEnvironment(client, {
    inspectGui: async () => ({ unlocked: false }), inspectListener: async () => { checkedListener = true; return listener; },
  }), /GUI_LOCKED_OR_UNKNOWN/);
  assert.equal(checkedListener, false);
  for (const change of [{ pid: 124 }, { process_start_identity: "reused-pid" }, { command_sha256: "b".repeat(64) }]) {
    await assert.rejects(verifyExecutionEnvironment(client, { inspectGui: async () => ({ unlocked: true }),
      inspectListener: async () => ({ ...listener, listeners: [{ ...processIdentity, ...change }] }),
    }), /EXECUTION_ENVIRONMENT_CHANGED/);
  }
  assert.equal((await verifyExecutionEnvironment(client, {
    inspectGui: async () => ({ unlocked: true }), inspectListener: async () => listener,
  })).listener, listener);
});
