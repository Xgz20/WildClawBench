import assert from "node:assert/strict";
import test from "node:test";

import {
  threadStreamLeases,
  waitForThreadStreamLease,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-stream.mjs";

const THREAD = "thread-target";
const BASE = Date.parse("2026-09-25T19:16:30.000Z");

function event(at, phase, threadId, leaseId, extra = {}) {
  const label = `Streaming RPC admission ${phase}.`;
  const payload = { phase, subscriptionKey: `orchestration.thread:${threadId}`, leaseId, ...extra };
  return `timestamp=${new Date(at).toISOString()} level=Info fiber=#1 message=${JSON.stringify(JSON.stringify(label))} message=${JSON.stringify(JSON.stringify(payload))}`;
}

test("stream gate accepts only a live lease for the exact target thread", () => {
  const log = [
    event(BASE - 1000, "admitted", THREAD, "old"),
    event(BASE, "rejected", THREAD, null, { reason: "thread-capacity" }),
    event(BASE + 500, "admitted", "other", "other-lease", {
      activeLeaseDetails: [{ subscriptionKey: `orchestration.thread:${THREAD}` }],
    }),
    event(BASE + 1000, "admitted", THREAD, "short"),
    event(BASE + 1200, "released", THREAD, "short"),
    event(BASE + 2000, "admitted", THREAD, "live"),
  ].join("\n");
  assert.deepEqual(threadStreamLeases(log, THREAD, BASE), {
    active: [{ leaseId: "live", admittedAt: BASE + 2000 }],
    rejected: 1,
  });
});

test("stream gate waits for an admitted lease to remain stable", async () => {
  let clock = BASE;
  const admitted = event(BASE + 1000, "admitted", THREAD, "lease-1");
  const result = await waitForThreadStreamLease({
    logPath: "/unused/server.log",
    threadId: THREAD,
    sinceEpochMs: BASE,
    timeoutMs: 5000,
    minStableMs: 1500,
    readLog: async () => clock >= BASE + 1000 ? admitted : "",
    now: () => clock,
    sleep: async (milliseconds) => { clock += milliseconds; },
  });
  assert.equal(result.leaseId, "lease-1");
  assert.ok(clock >= BASE + 2500);
});

test("a lease released before stability does not admit a send", async () => {
  let clock = BASE;
  const admitted = event(BASE + 500, "admitted", THREAD, "short");
  const released = event(BASE + 900, "released", THREAD, "short");
  await assert.rejects(
    waitForThreadStreamLease({
      logPath: "/unused/server.log",
      threadId: THREAD,
      sinceEpochMs: BASE,
      timeoutMs: 2000,
      minStableMs: 1500,
      readLog: async () => clock >= BASE + 900 ? `${admitted}\n${released}` : clock >= BASE + 500 ? admitted : "",
      now: () => clock,
      sleep: async (milliseconds) => { clock += milliseconds; },
    }),
    /remained unavailable/u,
  );
});
