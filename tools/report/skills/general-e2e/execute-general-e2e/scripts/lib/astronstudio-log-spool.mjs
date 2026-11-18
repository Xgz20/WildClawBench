import { fork } from "node:child_process";
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { mkdir, open, rename, rm, writeFile } from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const names = ["desktop-main.log", "server-child.log", "server.log", "provider/events.log"];
const sources = names.flatMap(name => [name + ".2", name + ".1", name]);
const incident = /server\.shutdown\.stage\.started|APP SESSION END[^\n]*signal=SIG|backend exited unexpectedly/iu;
const tailBytes = 32 * 1024;
const chunkBytes = 1024 * 1024;
const maxRetainedBytes = 64 * 1024 * 1024;
const windowMs = 75_000;
const maxSegments = 256;

// Raw bytes stay in the local, private queue directory. They are excluded from
// automatic task evidence delivery.
export async function createNativeLogSpool(logRoot, output, clock = Date.now) {
  await mkdir(output, { mode: 0o700 });
  const cursors = new Map();
  const segments = [];
  const gaps = [];
  let omittedGaps = 0;
  let next = 0;
  let initialized = false;
  let incidentUntil = 0;
  let recentIncident = null;
  let evictedSegments = 0;
  let retainedBytes = 0;
  const startedAt = new Date(clock()).toISOString();

  function recordGap(value) {
    if (gaps.length === 128) {
      gaps.shift();
      omittedGaps++;
    }
    gaps.push(value);
  }

  return async function sample() {
    const now = clock();
    const at = new Date(now).toISOString();
    for (const source of sources) {
      let file;
      try {
        file = await open(join(logRoot, source), constants.O_RDONLY | constants.O_NOFOLLOW);
        const info = await file.stat();
        if (!info.isFile()) continue;
        const identity = `${info.dev}:${info.ino}:${info.birthtimeMs}`;
        let start = cursors.get(identity);
        if (start === undefined) {
          start = initialized ? 0 : names.includes(source) ? Math.max(0, info.size - tailBytes) : info.size;
        } else if (info.size < start) {
          recordGap({ at, source, identity, reason: "truncated", previous_offset: start, size: info.size });
          start = 0;
        }
        if (info.size - start > chunkBytes) {
          recordGap({ at, source, identity, reason: "sample_byte_limit", from: start, to: info.size - chunkBytes });
          start = info.size - chunkBytes;
        }
        const buffer = Buffer.alloc(info.size - start);
        const { bytesRead } = buffer.length ? await file.read(buffer, 0, buffer.length, start) : { bytesRead: 0 };
        cursors.set(identity, start + bytesRead);
        if (!bytesRead) continue;
        const bytes = buffer.subarray(0, bytesRead);
        const name = `${String(++next).padStart(8, "0")}-${basename(source)}.bin`;
        await writeFile(join(output, name), bytes, { flag: "wx", mode: 0o600 });
        const segment = {
          name, captured_at: at, source, identity, offset: start, size: bytesRead,
          sha256: createHash("sha256").update(bytes).digest("hex"),
          observed_ms: now, pinned: now < incidentUntil,
        };
        segments.push(segment);
        retainedBytes += bytesRead;
        if (initialized && incident.test(bytes.toString("utf8"))) {
          recentIncident = at;
          incidentUntil = now + windowMs;
          for (const prior of segments) {
            if (now - prior.observed_ms <= windowMs) prior.pinned = true;
          }
        }
      } catch (error) {
        if (error.code !== "ENOENT" || names.includes(source)) {
          recordGap({ at, source, reason: error.code || "log_read_failed" });
        }
      } finally {
        await file?.close();
      }
    }
    initialized = true;
    const evicted = [];
    while (segments.length > maxSegments || retainedBytes > maxRetainedBytes) {
      const unpinned = segments.findIndex(segment => !segment.pinned);
      const [removed] = segments.splice(Math.max(0, unpinned), 1);
      evicted.push(removed);
      retainedBytes -= removed.size;
    }
    evictedSegments += evicted.length;
    const index = {
      schema_version: "wildclawbench.astudio-native-log-spool/v1",
      started_at: startedAt, sampled_at: at, recent_incident_at: recentIncident,
      retained_bytes: retainedBytes, retained_byte_limit: maxRetainedBytes,
      evicted_segments: evictedSegments, omitted_gap_records: omittedGaps, gaps, segments,
    };
    await writeFile(join(output, ".index.tmp"), JSON.stringify(index, null, 2) + "\n", { mode: 0o600 });
    await rename(join(output, ".index.tmp"), join(output, "index.json"));
    await Promise.all(evicted.map(segment => rm(join(output, segment.name), { force: true })));
    return index;
  };
}

export async function startNativeLogSpool(database, output) {
  const worker = fork(fileURLToPath(import.meta.url), [join(dirname(database), "logs"), output], {
    stdio: ["ignore", "ignore", "inherit", "ipc"],
  });
  const done = new Promise(resolveExit => {
    worker.once("exit", resolveExit);
    worker.once("error", () => resolveExit(1));
  });
  await new Promise((ready, reject) => {
    worker.once("error", reject);
    worker.once("message", message => message === "ready" ? ready() : reject(Error("ASTUDIO_NATIVE_LOG_SPOOL_START_FAILED")));
    done.then(() => reject(Error("ASTUDIO_NATIVE_LOG_SPOOL_EXITED_BEFORE_READY")));
  });
  return async () => {
    let timer;
    const deadline = new Promise(resolveTimeout => {
      timer = setTimeout(() => {
        if (worker.connected) worker.disconnect();
        worker.unref();
        resolveTimeout(1);
      }, 10_000);
    });
    try {
      if (worker.connected) {
        worker.channel?.ref();
        worker.send("stop", error => {
          if (error && worker.connected) worker.disconnect();
        });
      }
      return await Promise.race([done, deadline]);
    } finally {
      clearTimeout(timer);
    }
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const sample = await createNativeLogSpool(process.argv[2], process.argv[3]);
    await sample();
    let busy;
    const timer = setInterval(() => {
      if (busy) return;
      busy = sample().catch(error => {
        console.error("ASTUDIO_NATIVE_LOG_SPOOL_FAILED", error.code || error.name);
        process.exitCode = 1;
        clearInterval(timer);
        if (process.connected) process.disconnect();
      }).finally(() => { busy = null; });
    }, 2_000);
    let stopping;
    const stop = () => stopping ??= (async () => {
      clearInterval(timer);
      await busy;
      await sample();
    })().catch(() => { process.exitCode = 1; });
    if (process.connected) {
      process.on("message", message => {
        if (message === "stop") {
          stop().then(() => { if (process.connected) process.disconnect(); });
        }
      });
      process.once("disconnect", stop);
      process.send("ready");
    } else {
      await stop();
    }
  } catch (error) {
    console.error("ASTUDIO_NATIVE_LOG_SPOOL_FAILED", error.code || error.name);
    process.exitCode = 1;
    if (process.connected) process.disconnect();
  }
}
