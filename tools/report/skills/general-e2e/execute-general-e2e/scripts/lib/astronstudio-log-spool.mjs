import { createHash, randomUUID } from "node:crypto";
import { constants } from "node:fs";
import { mkdir, open, readdir, rm } from "node:fs/promises";
import { basename, join } from "node:path";
import { evidenceClock, readEvidenceJson, syncEvidenceDirectory, writeEvidenceBytes, writeEvidenceJson }
  from "./astronstudio-evidence-files.mjs";
import { createIncidentSealer, journalTriggers, nativeLogTriggers, processTriggers, readJournal }
  from "./astronstudio-incident-evidence.mjs";
import { sampleNativeHost } from "./astronstudio-host-evidence.mjs";

const names = ["desktop-main.log", "server-child.log", "server.log", "provider/events.log"];
const sources = names.flatMap(name => [name + ".2", name + ".1", name]);
const tailBytes = 32 * 1024;
const chunkBytes = 1024 * 1024;
const retainedByteLimit = 64 * 1024 * 1024;
const schema = "wildclawbench.astudio-native-log-spool/v2";

function taskIdentities(tasks) {
  return tasks.map(task => ({
    task_id: task.task_id, phase: task.phase, selected_attempt_id: task.selected_attempt_id,
    thread_id: task.session?.thread_id ?? null, turn_id: task.session?.turn_id ?? null,
    session_id: task.session?.session_id ?? null,
  }));
}

// Source files are read-only. Persist raw bytes before checkpointing offsets and
// keep sealed hard links independently of circular buffer eviction.
export async function createNativeLogSpool(logRoot, output, clock = Date.now, options = {}) {
  await mkdir(output, { mode: 0o700, recursive: true });
  const indexPath = join(output, "index.json");
  const index = await readEvidenceJson(indexPath) ?? {
    schema_version: schema, started_at: new Date(clock()).toISOString(), sampled_at: null,
    boot_id: options.bootId ?? null, cursors: {}, recent_incident_at: null, pending_triggers: [],
    seen_journal_keys: [], host_samples: [], retained_bytes: 0, retained_byte_limit: retainedByteLimit,
    evicted_segments: 0, omitted_gap_records: 0, gaps: [], segments: [],
  };
  if (index.schema_version !== schema) throw Error("ASTUDIO_NATIVE_LOG_SPOOL_SCHEMA");
  const priorBootId = index.boot_id;
  const keep = new Set(index.segments.map(segment => segment.name));
  for (const file of await readdir(output)) {
    if (/^[0-9a-f-]{36}-[a-z.-]+\.bin$/u.test(file) && !keep.has(file)) await rm(join(output, file));
  }
  const seal = await createIncidentSealer(output, {
    bootId: options.bootId ?? null, beforeMs: options.beforeMs ?? 120_000, afterMs: options.afterMs ?? 75_000,
    journal: options.journal,
  });
  let bootChanged = Boolean(priorBootId && options.bootId && priorBootId !== options.bootId);
  if (bootChanged) index.host_samples = [];
  index.boot_id = options.bootId ?? null;
  const contextGap = { last: new Map() };
  const writeRaw = options.writeRaw || writeEvidenceBytes;
  const segmentLimit = options.segmentLimit ?? 256;

  function gap(value) {
    if (index.gaps.length === 128) {
      index.gaps.shift();
      index.omitted_gap_records++;
    }
    index.gaps.push(value);
  }

  async function capture(source, now, seen, triggers) {
    const at = new Date(now).toISOString();
    let file;
    let location = { at, source };
    try {
      file = await open(join(logRoot, source), constants.O_RDONLY | constants.O_NOFOLLOW);
      const info = await file.stat();
      if (!info.isFile()) return;
      const identity = `${info.dev}:${info.ino}:${info.birthtimeMs}`;
      if (seen.has(identity)) return;
      seen.add(identity);
      const old = index.cursors[identity];
      let offset = old?.offset ?? (index.sampled_at ? 0
        : names.includes(source) ? Math.max(0, info.size - tailBytes) : info.size);
      if (!old && offset) gap({ at, source, identity, reason: "before_initial_tail", from: 0, to: offset });
      if (old && info.size < old.size) {
        gap({ at, source, identity, reason: "source_shrank", from: Math.min(offset, info.size), to: old.size });
        offset = 0;
      }
      const cursor = { source, offset, size: info.size, last_seen: at };
      index.cursors[identity] = cursor;
      const previousLength = Math.min(512, offset);
      const readFrom = offset - previousLength;
      const length = Math.min(info.size - offset, chunkBytes);
      if (!length) return;
      location = { at, source, identity, from: offset, to: offset + length };
      const buffer = Buffer.alloc(previousLength + length);
      const { bytesRead } = await file.read(buffer, 0, buffer.length, readFrom);
      const bytes = buffer.subarray(previousLength, bytesRead);
      if (!bytes.length) return;
      const name = randomUUID() + "-" + basename(source).replace(/\.[12]$/u, "") + ".bin";
      try {
        await writeRaw(join(output, name), bytes);
        await syncEvidenceDirectory(output);
      } catch (error) {
        gap({ ...location, reason: "raw_write_failed", error: error.code || error.name });
        await rm(join(output, name), { force: true }).catch(() => {});
        return;
      }
      const segment = {
        name, captured_at: at, observed_ms: now, source, identity, offset, size: bytes.length,
        sha256: createHash("sha256").update(bytes).digest("hex"),
      };
      index.segments.push(segment);
      index.retained_bytes += segment.size;
      cursor.offset += bytes.length;
      if (index.sampled_at) triggers.push(...nativeLogTriggers(bytes, buffer.subarray(0, previousLength), segment));
      contextGap.last.delete(source);
    } catch (error) {
      if (error.code === "ENOENT" && !names.includes(source)) return;
      const reason = error.code === "ENOENT" ? "source_missing" : "source_unreadable";
      if (now - (contextGap.last.get(source) ?? -Infinity) >= 60_000) {
        contextGap.last.set(source, now);
        gap({ ...location, reason, error: error.code || error.name });
      }
    } finally {
      await file?.close();
    }
  }

  return async function sample({ finalReason, outage } = {}) {
    const started = performance.now();
    const now = clock();
    const stamp = evidenceClock(now);
    if (outage) gap({ at: stamp.at, source: "collector", ...outage });
    if (bootChanged) {
      gap({ at: stamp.at, source: "collector", reason: "host_reboot", previous_boot_id: priorBootId, boot_id: index.boot_id });
      bootChanged = false;
    }
    if (index.sampled_at && now - Date.parse(index.sampled_at) > (options.maximumIntervalMs ?? 10_000)) {
      gap({ at: stamp.at, source: "collector", reason: "sampling_time_gap", from_at: index.sampled_at, to_at: stamp.at });
    }
    if (index.sampled_at && now < Date.parse(index.sampled_at)) {
      gap({ at: stamp.at, source: "collector", reason: "clock_moved_backwards", from_at: index.sampled_at, to_at: stamp.at });
    }
    const queue = await readEvidenceJson(options.queueState || join(output, "unconfigured-queue-state.json")).catch(error => {
      gap({ at: stamp.at, source: "queue_state", reason: error.code || error.name });
      return null;
    });
    const tasks = taskIdentities(queue?.tasks || []);
    const seen = new Set();
    const triggers = [...index.pending_triggers];
    for (const source of sources) await capture(source, now, seen, triggers);
    for (const [identity, cursor] of Object.entries(index.cursors)) {
      if (seen.has(identity)) continue;
      if (cursor.size > cursor.offset) {
        gap({ at: stamp.at, source: cursor.source, identity, reason: "rotated_before_drain",
          from: cursor.offset, to: cursor.size, last_seen: cursor.last_seen });
      }
      // Missing generations also leave their unobserved suffix unknowable.
      gap({ at: stamp.at, source: cursor.source, identity, reason: "source_generation_disappeared",
        from: cursor.size, to: null, last_seen: cursor.last_seen });
      delete index.cursors[identity];
    }
    const lastHost = index.host_samples.at(-1);
    if (options.appPath && (!lastHost || now - Date.parse(lastHost.at) >= 5_000 || finalReason)) {
      const host = await (options.sampleHost || sampleNativeHost)(options.appPath, lastHost?.processes);
      host.boot_id = index.boot_id;
      host.collector_sample_before_seal_ms = performance.now() - started;
      triggers.push(...processTriggers(lastHost, host));
      index.host_samples.push(host);
      index.host_samples = index.host_samples.slice(-96);
    }
    if (options.journal && tasks.length) {
      const journal = await readJournal(options.journal, now - 20_000, now,
        row => row.event === "execution.native-terminal", 256 * 1024);
      const seenKeys = new Set(index.seen_journal_keys);
      const added = journalTriggers(journal.rows, tasks).filter(row => !seenKeys.has(row.key));
      triggers.push(...added);
      index.seen_journal_keys = [...index.seen_journal_keys, ...added.map(row => row.key)].slice(-256);
    }
    const evicted = [];
    if (triggers.length) index.recent_incident_at = stamp.at;
    index.pending_triggers = triggers.slice(0, 128);
    index.sampled_at = stamp.at;
    index.sampled_monotonic_ns = stamp.monotonic_ns;
    // Checkpoint the trigger references before sealing or evicting their bytes.
    if (index.pending_triggers.length) await writeEvidenceJson(indexPath, index);
    const omission = await seal(index, index.pending_triggers, {
      now, monotonicNs: stamp.monotonic_ns, tasks, queueIdentity: queue?.identity ?? null,
      activeTaskIds: queue?.active_task_ids ?? [],
    }, finalReason);
    if (omission) gap({ at: stamp.at, source: "incidents", reason: omission });
    index.pending_triggers = [];
    while (index.segments.length > segmentLimit || index.retained_bytes > retainedByteLimit) {
      const removed = index.segments.shift();
      evicted.push(removed);
      index.retained_bytes -= removed.size;
    }
    index.evicted_segments += evicted.length;
    await writeEvidenceJson(indexPath, index);
    await Promise.all(evicted.map(segment => rm(join(output, segment.name), { force: true })));
    return index;
  };
}
