import { readFile } from "node:fs/promises";

const MESSAGE_FIELD = /message="((?:\\.|[^"])*)"/gu;

export function threadStreamLeases(logText, threadId, sinceEpochMs) {
  if (typeof logText !== "string" || !threadId || !Number.isFinite(sinceEpochMs)) {
    throw new Error("AstronStudio stream lease query identity is incomplete");
  }
  const key = `orchestration.thread:${threadId}`;
  const active = new Map();
  let rejected = 0;
  for (const line of logText.split("\n")) {
    if (!line.includes("Streaming RPC admission") || !line.includes(key)) continue;
    const timestamp = /^timestamp=([^ ]+)/u.exec(line)?.[1];
    const at = Date.parse(timestamp || "");
    if (!Number.isFinite(at) || at < sinceEpochMs) continue;
    const fields = Array.from(line.matchAll(MESSAGE_FIELD));
    if (fields.length < 2) continue;
    let event;
    try {
      event = JSON.parse(JSON.parse(`"${fields[1][1]}"`));
    } catch {
      continue;
    }
    if (event?.subscriptionKey !== key) continue;
    if (event.phase === "admitted" && typeof event.leaseId === "string" && event.leaseId) {
      active.set(event.leaseId, at);
    } else if (event.phase === "released" && typeof event.leaseId === "string") {
      active.delete(event.leaseId);
    } else if (event.phase === "rejected") {
      rejected += 1;
    }
  }
  return { active: Array.from(active, ([leaseId, admittedAt]) => ({ leaseId, admittedAt })), rejected };
}

export async function waitForThreadStreamLease({
  logPath,
  threadId,
  sinceEpochMs,
  timeoutMs = 120000,
  minStableMs = 1500,
  readLog = readFile,
  now = () => Date.now(),
  sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
}) {
  if (!logPath || !threadId || !Number.isFinite(sinceEpochMs)) {
    throw new Error("AstronStudio target stream identity is incomplete");
  }
  const deadline = now() + timeoutMs;
  while (now() <= deadline) {
    const leases = threadStreamLeases(await readLog(logPath, "utf8"), threadId, sinceEpochMs);
    const ready = leases.active.find((lease) => now() - lease.admittedAt >= minStableMs);
    if (ready) return { threadId, leaseId: ready.leaseId, admittedAt: ready.admittedAt };
    await sleep(500);
  }
  throw new Error("AstronStudio target thread stream admission remained unavailable before Prompt send");
}
