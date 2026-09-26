import { readFile, stat } from "node:fs/promises";

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

async function readAdmissionLogs(logPath, cache) {
  const paths = [`${logPath}.2`, `${logPath}.1`, logPath];
  const metadata = async (path) => {
    try { return await stat(path); }
    catch (error) {
      if (error?.code === "ENOENT" && path !== logPath) return null;
      throw error;
    }
  };
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const before = await Promise.all(paths.map(metadata));
      const contents = await Promise.all(paths.map(async (path, index) => {
        if (!before[index]) return null;
        const key = `${before[index].dev}:${before[index].ino}:${before[index].size}:${before[index].mtimeMs}`;
        if (path !== logPath && cache.get(path)?.key === key) return cache.get(path).content;
        const content = await readFile(path);
        if (path !== logPath) cache.set(path, { key, content });
        return content;
      }));
      const after = await Promise.all(paths.map(metadata));
      const stable = before.every((initial, index) => {
        const current = after[index];
        return initial === null ? current === null : current !== null
          && initial.dev === current.dev && initial.ino === current.ino
          && current.size >= initial.size && contents[index]?.length >= initial.size;
      });
      if (stable) return contents.filter(Boolean).map((content) => content.toString("utf8")).join("\n");
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  return null;
}

export async function waitForThreadStreamLease({
  logPath,
  threadId,
  sinceEpochMs,
  timeoutMs = 120000,
  minStableMs = 1500,
  readLog = null,
  now = () => Date.now(),
  sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
}) {
  if (!logPath || !threadId || !Number.isFinite(sinceEpochMs)) {
    throw new Error("AstronStudio target stream identity is incomplete");
  }
  const deadline = now() + timeoutMs;
  const rotatedCache = new Map();
  while (now() <= deadline) {
    const logText = readLog ? await readLog(logPath, "utf8")
      : await readAdmissionLogs(logPath, rotatedCache);
    if (logText === null) {
      await sleep(500);
      continue;
    }
    const leases = threadStreamLeases(logText, threadId, sinceEpochMs);
    const ready = leases.active.find((lease) => now() - lease.admittedAt >= minStableMs);
    if (ready) return { threadId, leaseId: ready.leaseId, admittedAt: ready.admittedAt };
    await sleep(500);
  }
  throw new Error("AstronStudio target thread stream admission remained unavailable before Prompt send");
}
