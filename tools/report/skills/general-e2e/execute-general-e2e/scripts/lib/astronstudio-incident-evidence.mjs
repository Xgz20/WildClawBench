import { createHash, randomUUID } from "node:crypto";
import { constants } from "node:fs";
import { link, mkdir, open, readFile, readdir, rename } from "node:fs/promises";
import { join } from "node:path";
import { readEvidenceJson, syncEvidenceDirectory, writeEvidenceBytes, writeEvidenceJson } from "./astronstudio-evidence-files.mjs";

const maxIncidentBytes = 128 * 1024 * 1024;
const maxIncidents = 32;
const nativeMarker = /server\.shutdown\.stage\.started|APP SESSION END[^\r\n]*signal=SIG[A-Z]+|backend exited unexpectedly|abandoning stalled acode turn|transport connection closed|(?:app.server|sdk|desktop server|acode)[^\r\n]{0,100}(?:transport|pipe|IPC)[^\r\n]{0,60}(?:closed|disconnected|EPIPE|ECONNRESET)/giu;
const terminalFailure = /interrupt|abort|cancel|disconnect/i;
const identityKey = row => `${row.role}:${row.pid}:${row.started_at}`;

export function nativeLogTriggers(bytes, previous, segment) {
  if (!/^(desktop-main|server-child|server)\.log(?:\.[12])?$/u.test(segment.source)) return [];
  const input = Buffer.concat([previous, bytes]).toString("latin1");
  return Array.from(input.matchAll(nativeMarker))
    .filter(match => match.index + match[0].length > previous.length)
    .slice(0, 32)
    .map(match => {
      const offset = segment.offset - previous.length + match.index;
      const line = input.slice(match.index, match.index + 240).split("\n", 1)[0];
      const pid = /\bpid[=: ]+(\d+)/iu.exec(line)?.[1];
      return { key: `${segment.identity}:${offset}`, kind: "native-log", marker: match[0].slice(0, 160),
        source: segment.source, offset, ...(pid ? { pid: Number(pid) } : {}) };
    });
}

export function processTriggers(before, after) {
  if (!before || !after || [before, after].some(row => row.observations_unavailable.includes("native_process_table"))) {
    return [];
  }
  const current = new Set(after.processes.map(identityKey));
  return before.processes
    .filter(row => ["astudio-backend", "shared-acode-app-server"].includes(row.role) && !current.has(identityKey(row)))
    .map(row => ({ key: `${identityKey(row)}:${after.at}`, kind: "process-exit-observed", pid: row.pid,
      role: row.role, started_at: row.started_at, prior_sample_at: before.at, observed_at: after.at }));
}

export async function readJournal(path, from, until, accept, maxBytes = 4 * 1024 * 1024) {
  if (!path) return { availability: "not_configured", rows: [] };
  let file;
  try {
    file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
    const info = await file.stat();
    if (!info.isFile()) return { availability: "not_regular_file", rows: [] };
    const offset = Math.max(0, info.size - maxBytes);
    const buffer = Buffer.alloc(info.size - offset);
    const { bytesRead } = await file.read(buffer, 0, buffer.length, offset);
    const lines = buffer.subarray(0, bytesRead).toString("utf8").split("\n");
    if (offset) lines.shift();
    let malformed = 0;
    const rows = [];
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const row = JSON.parse(line);
        const time = Date.parse(row.at);
        if (!Number.isFinite(time)) { malformed++; continue; }
        if (time >= from && time <= until && accept(row)) rows.push(row);
      } catch {
        malformed++;
      }
    }
    return {
      availability: rows.length ? "matched" : "no_matching_events",
      file_size: info.size, byte_offset: offset, bytes_read: bytesRead, malformed_lines: malformed,
      omitted_matching_rows: Math.max(0, rows.length - 1_000),
      rows: rows.slice(-1_000),
    };
  } catch (error) {
    return { availability: error.code === "ENOENT" ? "missing" : "unreadable", error: error.code || error.name, rows: [] };
  } finally {
    await file?.close();
  }
}

export function journalTriggers(rows, activeTasks) {
  const taskIds = new Set(activeTasks.map(task => task.task_id));
  return rows.filter(row => row.event === "execution.native-terminal"
      && taskIds.has(row.identity?.task_id)
      && terminalFailure.test(`${row.native_status || ""} ${row.turn_state || ""}`))
    .map(row => ({
      key: `${row.actor_instance_id}:${row.actor_sequence}:${row.identity.attempt_id}:${row.at}`,
      kind: "native-terminal", at: row.at, task_id: row.identity.task_id, attempt_id: row.identity.attempt_id,
      native_status: row.native_status, turn_state: row.turn_state,
    }));
}

const externalKeys = new Set([
  "at", "monotonic_ns", "boot_id", "event", "pid", "parent_pid", "process_start", "source_pid", "target_pid",
  "source_start", "target_start", "signal", "exit_code", "exit_status_raw", "seq_num", "global_seq_num",
  "request_id", "reason_code", "role", "thread_id", "turn_id", "dropped_count",
]);

async function externalEvidence(root, name, incident, pids) {
  if (!incident.boot_id) return { availability: "boot_id_unavailable", rows: [] };
  const result = await readJournal(join(root, "external", name + ".jsonl"), incident.from_ms, incident.until_ms,
    row => row.boot_id === incident.boot_id
      && (row.event === "coverage" || [row.pid, row.source_pid, row.target_pid].some(pid => Number.isInteger(pid) && pids.has(pid))));
  result.rows = result.rows.map(row => Object.fromEntries(Object.entries(row)
    .filter(([key, value]) => externalKeys.has(key)
      && (typeof value === "number" || typeof value === "string" && value.length <= 160))));
  return result;
}

export async function createIncidentSealer(output, options) {
  const root = join(output, "incidents");
  await mkdir(root, { mode: 0o700, recursive: true });
  const entries = await readdir(root);
  const sealedNames = entries.filter(name => /^incident-[0-9a-f-]{36}$/u.test(name));
  let sealed = sealedNames.length;
  const processed = new Set();
  const openIncidents = [];
  for (const name of entries) {
    if (/^\.pending-[0-9a-f-]{36}$/u.test(name)) {
      const pending = await readEvidenceJson(join(root, name, "incident.json"));
      if (pending) openIncidents.push(pending);
    }
    if (sealedNames.includes(name)) {
      const integrity = await readEvidenceJson(join(root, name, "integrity.json"));
      for (const key of integrity?.trigger_keys || []) processed.add(key);
    }
  }
  openIncidents.sort((left, right) => Date.parse(left.triggered_at) - Date.parse(right.triggered_at));

  async function begin(context, triggers) {
    const now = context.now;
    const id = randomUUID();
    const incident = {
      schema_version: "wildclawbench.astudio-incident/v1", id, boot_id: options.bootId,
      triggered_at: new Date(now).toISOString(), trigger_monotonic_ns: context.monotonicNs,
      from_ms: now - options.beforeMs, until_ms: now + options.afterMs,
      active_at_trigger: context.tasks.filter(task =>
        context.activeTaskIds.includes(task.task_id) || triggers.some(trigger => trigger.task_id === task.task_id)),
      triggers: [], raw_segments: [], bytes: 0, omissions: [],
    };
    await mkdir(join(root, ".pending-" + id, "raw"), { mode: 0o700, recursive: true });
    return incident;
  }

  async function update(current, index, context, finalReason) {
    const now = context.now;
    const pending = join(root, ".pending-" + current.id);
    const raw = join(pending, "raw");
    const linked = new Set(current.raw_segments.map(segment => segment.name));
    for (const segment of index.segments) {
      if (linked.has(segment.name) || segment.observed_ms < current.from_ms || segment.observed_ms > current.until_ms) continue;
      if (current.bytes + segment.size > maxIncidentBytes || current.raw_segments.length >= 4096) {
        if (!current.omissions.includes("incident_raw_budget")) current.omissions.push("incident_raw_budget");
        continue;
      }
      await link(join(output, segment.name), join(raw, segment.name)).catch(error => {
        if (error.code !== "EEXIST") throw error;
      });
      current.raw_segments.push(segment);
      current.bytes += segment.size;
    }
    await syncEvidenceDirectory(raw);

    const recent = at => Date.parse(at) >= current.from_ms && Date.parse(at) <= current.until_ms;
    current.capture_gaps = index.gaps.filter(row => recent(row.at));
    current.previous_ring_evictions = index.evicted_segments;
    current.unlisted_capture_gaps = index.omitted_gap_records;
    current.collector_started_at = index.started_at;
    current.oldest_raw_sample_at = current.raw_segments[0]?.captured_at ?? null;
    current.latest_raw_sample_at = current.raw_segments.at(-1)?.captured_at ?? null;
    current.host_samples = [...new Map([...(current.host_samples ?? []), ...index.host_samples]
      .filter(row => recent(row.at) && row.boot_id === current.boot_id)
      .map(row => [row.monotonic_ns, row])).values()];
    current.latest_tasks = context.tasks;
    current.queue_identity = context.queueIdentity;
    current.sealed_at = null;
    const reason = current.boot_id && index.boot_id && current.boot_id !== index.boot_id ? "host_reboot" : finalReason;
    if (!reason && now < current.until_ms) {
      await writeEvidenceJson(join(pending, "incident.json"), current);
      return false;
    }

    const pids = new Set(current.host_samples.flatMap(sample => sample.processes.map(row => row.pid))
      .concat(current.triggers.map(row => row.pid)).filter(Number.isInteger));
    const relevant = row => row.queue_identity?.queue_id === context.queueIdentity?.queue_id && Boolean(context.queueIdentity?.queue_id)
      || context.tasks.some(task => Boolean(task.selected_attempt_id) && row.identity?.attempt_id === task.selected_attempt_id)
      || current.active_at_trigger.some(task => Boolean(task.selected_attempt_id) && row.identity?.attempt_id === task.selected_attempt_id);
    [current.framework_events, current.endpoint_security, current.astudio_lifecycle] = await Promise.all([
      readJournal(options.journal, current.from_ms, current.until_ms, relevant),
      externalEvidence(output, "endpoint-security", current, pids),
      externalEvidence(output, "astudio-lifecycle", current, pids),
    ]);
    current.sealed_at = new Date(now).toISOString();
    current.window_closed_early = now < current.until_ms;
    current.close_reason = reason || "post_window_complete";
    current.correlated_pids = [...pids];
    const receipt = join(pending, "incident.json");
    await writeEvidenceJson(receipt, current);
    const sha = createHash("sha256").update(await readFile(receipt)).digest("hex");
    await writeEvidenceJson(join(pending, "integrity.json"), {
      incident_json_sha256: sha, trigger_keys: current.triggers.map(trigger => trigger.key),
    });
    await rename(pending, join(root, "incident-" + current.id));
    await syncEvidenceDirectory(root);
    sealed++;
    for (const trigger of current.triggers) processed.add(trigger.key);
    return true;
  }

  return async function seal(index, triggers, context, finalReason) {
    const activeKeys = new Set(openIncidents.flatMap(incident => incident.triggers.map(trigger => trigger.key)));
    const newTriggers = triggers.filter(row => !processed.has(row.key) && !activeKeys.has(row.key));
    const now = context.now;
    let target = openIncidents.at(-1);
    let omission;
    if (newTriggers.length) {
      const differentGeneration = newTriggers.some(trigger => trigger.kind === "process-exit-observed"
        && target?.triggers.some(prior => prior.kind === trigger.kind && prior.role === trigger.role
          && (prior.pid !== trigger.pid || prior.started_at !== trigger.started_at)));
      if (!target || differentGeneration || now > target.until_ms) {
        if (sealed + openIncidents.length >= maxIncidents) {
          target = null;
          omission = "incident_count_limit";
        } else {
          target = await begin(context, newTriggers);
          openIncidents.push(target);
        }
      }
      if (target) {
        const available = 128 - target.triggers.length;
        if (newTriggers.length > available && !target.omissions.includes("incident_trigger_budget")) {
          target.omissions.push("incident_trigger_budget");
        }
        target.triggers.push(...newTriggers.slice(0, available));
        target.until_ms = Math.max(target.until_ms, Math.min(now + options.afterMs,
          Date.parse(target.triggered_at) + 180_000));
      }
    }
    for (const pending of [...openIncidents]) {
      if (await update(pending, index, context, finalReason)) {
        openIncidents.splice(openIncidents.indexOf(pending), 1);
      }
    }
    return omission;
  };
}
