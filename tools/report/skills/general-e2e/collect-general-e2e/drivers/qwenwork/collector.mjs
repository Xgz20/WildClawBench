#!/usr/bin/env node

import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import {
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { basename, dirname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildQwenCallIndex,
  buildQwenStrictResourceMetrics,
  normalizeQwenNativeTrace,
  QWENWORK_COLLECTOR_ADAPTER_ID,
  QWENWORK_COLLECTOR_VERSION,
} from "./native-normalizer.mjs";

const JOURNAL_SCHEMA = "wildclawbench.general-e2e-qwenwork-attempt-journal/v1";
const EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-execution-state/v1";
const TRACE_INDEX_SCHEMA = "urn:wildclawbench:schema:general-e2e:trace-index:v2";
const BINDING_SCHEMA = "wildclawbench.general-e2e-qwenwork-session-binding/v1";
const TERMINAL_PHASES = new Set(["COMPLETED", "FAILED"]);
const MAX_INPUT_BYTES = 64 * 1024 * 1024;

function usage() {
  return `QwenWork General E2E 原生证据采集器

用法：
  node collector.mjs \\
    --unit-root /absolute/unit-root \\
    --journal-file /absolute/qwenwork-attempt-journal.json \\
    --client-trace-root /absolute/.qwenworkcn \\
    --output-root /absolute/unit-root/.general-e2e/collection/<attempt>

只读原生 transcript/segments 和 attempt journal，输出 CB-A state、trace-index v2、
多 raw、binding copies 与严格 resource metrics；不操作或停止 QwenWork。`;
}

function parseArgs(argv) {
  const result = { unitRoot: "", journalFile: "", clientTraceRoot: "", outputRoot: "", redacted: false, help: false };
  const valued = new Map([
    ["--unit-root", "unitRoot"],
    ["--journal-file", "journalFile"],
    ["--client-trace-root", "clientTraceRoot"],
    ["--output-root", "outputRoot"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "-h" || argument === "--help") result.help = true;
    else if (argument === "--redacted") result.redacted = true;
    else if (valued.has(argument)) {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${argument} 缺少值`);
      result[valued.get(argument)] = value;
      index += 1;
    } else throw new Error(`未知选项：${argument}`);
  }
  if (!result.help) {
    for (const field of ["unitRoot", "journalFile", "clientTraceRoot", "outputRoot"]) {
      if (!result[field]) throw new Error(`缺少参数：${field}`);
    }
  }
  return result;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function jsonBytes(value) {
  return Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function jsonlBytes(rows) {
  return Buffer.from(`${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
}

function artifact(path, bytes, extra = {}) {
  return { path, sha256: sha256(bytes), size: bytes.length, ...extra };
}

function isWithin(root, candidate) {
  const value = relative(root, candidate);
  return value === "" || (value !== ".." && !value.startsWith(`..${sep}`) && !isAbsolute(value));
}

function unitRelative(root, candidate, label) {
  const value = relative(root, candidate);
  if (!value || value === ".." || value.startsWith(`..${sep}`) || isAbsolute(value)) {
    throw new Error(`QWENWORK_${label}_OUTSIDE_UNIT`);
  }
  return value.split(sep).join("/");
}

async function assertNoSymlinkPath(path, { requireLeaf = true } = {}) {
  const target = resolve(path);
  const parsed = parse(target);
  const parts = target.slice(parsed.root.length).split(/[\\/]+/u).filter(Boolean);
  let current = parsed.root;
  for (let index = 0; index < parts.length; index += 1) {
    current = resolve(current, parts[index]);
    try {
      const info = await lstat(current);
      if (info.isSymbolicLink()) throw new Error(`QWENWORK_COLLECTOR_SYMLINK_REJECTED: ${current}`);
      if (index < parts.length - 1 && !info.isDirectory()) {
        throw new Error(`QWENWORK_COLLECTOR_ANCESTOR_NOT_DIRECTORY: ${current}`);
      }
      if (index === parts.length - 1 && requireLeaf && !info.isFile() && !info.isDirectory()) {
        throw new Error(`QWENWORK_COLLECTOR_SPECIAL_FILE_REJECTED: ${current}`);
      }
    } catch (error) {
      if (error?.code === "ENOENT" && !requireLeaf) return;
      throw error;
    }
  }
}

async function readRegularFile(path, { nonempty = false } = {}) {
  await assertNoSymlinkPath(path);
  const absolute = await realpath(path);
  const info = await lstat(absolute);
  if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_INPUT_BYTES) {
    throw new Error(`QWENWORK_COLLECTOR_INPUT_NOT_REGULAR: ${absolute}`);
  }
  const bytes = await readFile(absolute);
  if (bytes.length > MAX_INPUT_BYTES || (nonempty && bytes.length === 0)) {
    throw new Error(`QWENWORK_COLLECTOR_INPUT_SIZE_INVALID: ${absolute}`);
  }
  return { absolute, bytes, sha256: sha256(bytes), size: bytes.length, info };
}

async function readJson(path) {
  const source = await readRegularFile(path, { nonempty: true });
  try {
    return { ...source, value: JSON.parse(source.bytes.toString("utf8")) };
  } catch (error) {
    throw new Error(`QWENWORK_COLLECTOR_JSON_INVALID: ${source.absolute}: ${error.message}`);
  }
}

function parseJsonLines(source, rawPath) {
  const text = source.bytes.toString("utf8");
  const lines = text.split(/\r?\n/u);
  if (lines.at(-1) === "") lines.pop();
  if (!lines.length || lines.some((line) => !line.trim())) {
    throw new Error(`QWENWORK_COLLECTOR_JSONL_EMPTY_LINE: ${source.absolute}`);
  }
  return lines.map((line, index) => {
    try {
      return { ...JSON.parse(line), __raw_path: rawPath, __raw_line: index + 1 };
    } catch (error) {
      throw new Error(`QWENWORK_COLLECTOR_JSONL_INVALID: ${source.absolute}#L${index + 1}: ${error.message}`);
    }
  });
}

function requireString(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`QWENWORK_COLLECTOR_FIELD_MISSING: ${label}`);
  return value;
}

function sameIdentity(left, right) {
  return ["batch_id", "unit_id", "task_id", "attempt_id"].every((field) => (
    typeof left?.[field] === "string" && left[field] === right?.[field]
  ));
}

function requireSha256(value, label) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/u.test(value)) {
    throw new Error(`QWENWORK_COLLECTOR_PROVENANCE_INVALID: ${label}`);
  }
  return value;
}

function assertOptionalSqliteSnapshot(value, label) {
  if (value === undefined) return;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`QWENWORK_COLLECTOR_SQLITE_PROVENANCE_INVALID: ${label}`);
  }
  if (value.quick_check !== "ok") {
    throw new Error(`QWENWORK_COLLECTOR_SQLITE_QUICK_CHECK_FAILED: ${label}`);
  }
  if (!new Set(["sqlite3-readonly-snapshot", "sqlite3-readonly"]).has(value.backend)) {
    throw new Error(`QWENWORK_COLLECTOR_SQLITE_BACKEND_UNTRUSTED: ${label}`);
  }
  if (value.sidecars_present === true && value.read_mode === "immutable") {
    throw new Error(`QWENWORK_COLLECTOR_SQLITE_IMMUTABLE_WITH_SIDECARS: ${label}`);
  }
  if (!new Set(["readonly-snapshot", "readonly", "immutable"]).has(value.read_mode)) {
    throw new Error(`QWENWORK_COLLECTOR_SQLITE_READ_MODE_INVALID: ${label}`);
  }
  for (const field of ["main", "wal", "shm"]) {
    const digest = value[field];
    if (digest == null) continue;
    if (!digest || typeof digest !== "object") {
      throw new Error(`QWENWORK_COLLECTOR_SQLITE_DIGEST_INVALID: ${label}.${field}`);
    }
    requireSha256(digest.sha256, `${label}.${field}.sha256`);
    if (!Number.isSafeInteger(digest.size) || digest.size < 0) {
      throw new Error(`QWENWORK_COLLECTOR_SQLITE_DIGEST_INVALID: ${label}.${field}.size`);
    }
  }
}

function assertBindingProvenance(source, state, index) {
  let value;
  try {
    value = JSON.parse(source.bytes.toString("utf8"));
  } catch (error) {
    throw new Error(`QWENWORK_COLLECTOR_BINDING_JSON_INVALID: ${index}: ${error.message}`);
  }
  if (value?.schema_version !== BINDING_SCHEMA) {
    throw new Error(`QWENWORK_COLLECTOR_BINDING_SCHEMA_INVALID: ${index}`);
  }
  if (!sameIdentity(value.identity, state.identity)) {
    throw new Error(`QWENWORK_COLLECTOR_BINDING_IDENTITY_MISMATCH: ${index}`);
  }
  if (value.prompt_sha256 !== state.prompt.sha256
      || resolve(value.workspace || "/") !== resolve(state.candidate_workspace || "/")) {
    throw new Error(`QWENWORK_COLLECTOR_BINDING_WORKSPACE_MISMATCH: ${index}`);
  }
  if (value.session_id !== state.session.session_id
      || value.conversation_id == null || value.sub_chat_id == null) {
    throw new Error(`QWENWORK_COLLECTOR_BINDING_SESSION_MISMATCH: ${index}`);
  }
  const localProjectId = state.extensions?.qwenwork?.local_project_id;
  if (localProjectId && value.local_project_id !== localProjectId) {
    throw new Error(`QWENWORK_COLLECTOR_BINDING_PROJECT_MISMATCH: ${index}`);
  }
  const observation = value.terminal_observation;
  if (!observation || observation.trusted_terminal !== true
      || observation.target_session_verified !== true
      || observation.active_stream !== false
      || observation.stop_confirmed !== true
      || (Array.isArray(observation.conflicts) && observation.conflicts.length)) {
    throw new Error(`QWENWORK_COLLECTOR_BINDING_TERMINAL_UNTRUSTED: ${index}`);
  }
  assertOptionalSqliteSnapshot(value.sqlite_snapshot, `binding[${index}]`);
}

async function normalizeFormalState(journal, unitRoot) {
  if (journal?.schema_version !== JOURNAL_SCHEMA || !TERMINAL_PHASES.has(journal.phase)) {
    throw new Error(`QWENWORK_COLLECTOR_JOURNAL_NOT_TERMINAL: ${journal?.phase || "missing"}`);
  }
  const state = structuredClone(journal.execution_state);
  if (state?.schema_version !== EXECUTION_STATE_SCHEMA || !TERMINAL_PHASES.has(state.phase)
      || state.phase !== journal.phase || !sameIdentity(state.identity, journal.identity)) {
    throw new Error("QWENWORK_COLLECTOR_EXECUTION_STATE_INVALID");
  }
  if (state.send?.dispatch_attempt_count !== 1 || journal.send?.dispatch_attempt_count !== 1
      || state.prompt?.send_status !== "sent" || state.session?.verified !== true) {
    throw new Error("QWENWORK_COLLECTOR_DISPATCH_OR_SESSION_UNVERIFIED");
  }
  const observation = state.extensions?.qwenwork?.terminal_observation;
  if (observation?.trusted_terminal !== true || observation?.target_session_verified !== true
      || observation?.active_stream !== false || observation?.stop_confirmed !== true
      || observation?.conflicts?.length) {
    throw new Error("QWENWORK_COLLECTOR_TERMINAL_OBSERVATION_UNTRUSTED");
  }
  if (state.session.thread_id !== null || state.session.turn_id !== null) {
    throw new Error("QWENWORK_COLLECTOR_SYNTHETIC_NATIVE_ID_REJECTED");
  }
  if (state.session.session_id !== journal.session?.session_id
      || resolve(state.session.cwd || "/") !== resolve(journal.session?.cwd || "/")
      || resolve(state.session.cwd || "/") !== resolve(state.candidate_workspace || "/")) {
    throw new Error("QWENWORK_COLLECTOR_SESSION_BINDING_MISMATCH");
  }
  const bindingRows = state.session.binding_evidence;
  if (!Array.isArray(bindingRows) || !bindingRows.length) throw new Error("QWENWORK_COLLECTOR_BINDING_EVIDENCE_MISSING");
  const sources = [];
  const sourceKeys = new Set();
  for (let index = 0; index < bindingRows.length; index += 1) {
    const row = bindingRows[index];
    const rawPath = requireString(row?.path, `session.binding_evidence[${index}].path`);
    const absolute = isAbsolute(rawPath) ? resolve(rawPath) : resolve(unitRoot, rawPath);
    if (!isWithin(unitRoot, absolute)) throw new Error("QWENWORK_COLLECTOR_BINDING_OUTSIDE_UNIT");
    const source = await readRegularFile(absolute, { nonempty: true });
    if (source.sha256 !== row.sha256 || source.size !== row.size) {
      throw new Error(`QWENWORK_COLLECTOR_BINDING_DIGEST_MISMATCH: ${index}`);
    }
    const key = `${source.sha256}:${source.size}`;
    if (sourceKeys.has(key)) throw new Error("QWENWORK_COLLECTOR_BINDING_DUPLICATE");
    sourceKeys.add(key);
    assertBindingProvenance(source, state, index);
    const relativePath = unitRelative(unitRoot, source.absolute, "BINDING");
    state.session.binding_evidence[index] = { path: relativePath, sha256: source.sha256, size: source.size };
    sources.push(source);
  }
  for (const field of ["task_root", "candidate_workspace"]) {
    const actual = await realpath(state[field]);
    if (!isWithin(unitRoot, actual)) throw new Error(`QWENWORK_COLLECTOR_${field.toUpperCase()}_OUTSIDE_UNIT`);
    state[field] = actual;
  }
  const prompt = await realpath(state.prompt.path);
  if (!isWithin(unitRoot, prompt)) throw new Error("QWENWORK_COLLECTOR_PROMPT_OUTSIDE_UNIT");
  state.prompt.path = prompt;
  return { state, bindingSources: sources };
}

async function discoverTranscript(journal, clientTraceRoot, sessionId) {
  if (!/^[A-Za-z0-9._:-]+$/u.test(sessionId)) throw new Error("QWENWORK_COLLECTOR_SESSION_ID_UNSAFE");
  const path = requireString(journal.session?.prompt_evidence?.transcript_path, "journal.session.prompt_evidence.transcript_path");
  const source = await readRegularFile(path, { nonempty: true });
  const projectsRoot = await realpath(join(clientTraceRoot, "projects"));
  if (!isWithin(projectsRoot, source.absolute) || basename(source.absolute) !== `${sessionId}.jsonl`) {
    throw new Error("QWENWORK_COLLECTOR_TRANSCRIPT_PATH_MISMATCH");
  }
  if (journal.session.prompt_evidence.transcript_sha256 !== source.sha256
      || journal.session.prompt_evidence.transcript_size !== source.size) {
    throw new Error("QWENWORK_COLLECTOR_TRANSCRIPT_DIGEST_MISMATCH");
  }
  return source;
}

async function discoverSegments(clientTraceRoot, sessionId) {
  const sessionsRoot = await realpath(join(clientTraceRoot, "logs", "sessions"));
  await assertNoSymlinkPath(sessionsRoot);
  const matches = [];
  for (const workspaceEntry of await readdir(sessionsRoot, { withFileTypes: true })) {
    const workspacePath = join(sessionsRoot, workspaceEntry.name);
    if (workspaceEntry.isSymbolicLink()) throw new Error(`QWENWORK_COLLECTOR_SEGMENT_SYMLINK_REJECTED: ${workspacePath}`);
    if (!workspaceEntry.isDirectory()) continue;
    const candidate = join(workspacePath, sessionId);
    try {
      const info = await lstat(candidate);
      if (info.isSymbolicLink()) throw new Error(`QWENWORK_COLLECTOR_SEGMENT_SYMLINK_REJECTED: ${candidate}`);
      if (info.isDirectory()) matches.push(await realpath(candidate));
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  if (matches.length !== 1) throw new Error(`QWENWORK_COLLECTOR_SEGMENT_SESSION_COUNT: ${matches.length}`);
  const directory = join(matches[0], "segments");
  await assertNoSymlinkPath(directory);
  const entries = await readdir(directory, { withFileTypes: true });
  const sources = [];
  const identities = new Set();
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name, "en"))) {
    const path = join(directory, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`QWENWORK_COLLECTOR_SEGMENT_SYMLINK_REJECTED: ${path}`);
    if (!entry.isFile() || !entry.name.endsWith(".jsonl")) {
      throw new Error(`QWENWORK_COLLECTOR_SEGMENT_ENTRY_UNSUPPORTED: ${path}`);
    }
    const source = await readRegularFile(path, { nonempty: true });
    const identity = `${source.info.dev}:${source.info.ino}`;
    if (identities.has(identity)) throw new Error("QWENWORK_COLLECTOR_SEGMENT_DUPLICATE_FILE");
    identities.add(identity);
    sources.push(source);
  }
  if (!sources.length) throw new Error("QWENWORK_COLLECTOR_SEGMENTS_EMPTY");
  return sources;
}

function assertTranscriptBinding(rows, state) {
  const expectedWorkspace = resolve(state.session.cwd);
  for (const [index, row] of rows.entries()) {
    if (row.sessionId !== state.session.session_id) {
      throw new Error(`QWENWORK_COLLECTOR_TRANSCRIPT_SESSION_MISMATCH: line=${row.__raw_line || index + 1}`);
    }
    if (!isAbsolute(row.cwd || "") || resolve(row.cwd) !== expectedWorkspace) {
      throw new Error(`QWENWORK_COLLECTOR_TRANSCRIPT_WORKSPACE_MISMATCH: line=${row.__raw_line || index + 1}`);
    }
  }
  const userTexts = rows.flatMap((row) => row.type === "user" && Array.isArray(row?.message?.content)
    ? row.message.content.filter((part) => part?.type === "text" && typeof part.text === "string").map((part) => part.text)
    : []);
  const exact = userTexts.filter((text) => sha256(Buffer.from(text, "utf8")) === state.prompt.sha256);
  if (exact.length !== 1) throw new Error(`QWENWORK_COLLECTOR_PROMPT_MATCH_COUNT: ${exact.length}`);
}

function assertSegmentBinding(rows, state) {
  const expectedWorkspace = resolve(state.session.cwd);
  let workspaceEvidence = 0;
  for (const [index, row] of rows.entries()) {
    if (row.session_id !== undefined && row.session_id !== state.session.session_id) {
      throw new Error(`QWENWORK_COLLECTOR_SEGMENT_SESSION_MISMATCH: line=${row.__raw_line || index + 1}`);
    }
    const candidates = [
      row.cwd,
      row.data?.cwd,
      row.data?.project_root,
      row.data?.target_dir,
      row.data?.workspace,
    ].filter((value) => value !== undefined && value !== null);
    for (const candidate of candidates) {
      if (typeof candidate !== "string" || !isAbsolute(candidate) || resolve(candidate) !== expectedWorkspace) {
        throw new Error(`QWENWORK_COLLECTOR_SEGMENT_WORKSPACE_MISMATCH: line=${row.__raw_line || index + 1}`);
      }
      workspaceEvidence += 1;
    }
  }
  if (workspaceEvidence === 0) throw new Error("QWENWORK_COLLECTOR_SEGMENT_WORKSPACE_UNVERIFIED");
}

function traceCompleteness(events, calls, segmentRows) {
  const missing = [];
  if (events.filter((event) => event.type === "user_message").length !== 1) missing.push("user_message_count");
  if (!events.some((event) => event.type === "assistant_message")) missing.push("assistant_message");
  const mainTurnIds = new Set(segmentRows
    .filter((row) => row.type === "turn.started" && !row.data?.is_subagent)
    .map((row) => row.turn_id)
    .filter(Boolean));
  if (mainTurnIds.size !== 1) {
    missing.push("main_turn_started");
  }
  if (segmentRows.filter((row) => row.type === "turn.finished" && mainTurnIds.has(row.turn_id)).length !== 1) {
    missing.push("main_turn_finished");
  }
  for (const call of calls) if (call.result_sequence == null) missing.push(`tool_result:${call.call_id}`);
  return {
    status: missing.length ? "partial" : "complete",
    omitted_event_count: 0,
    missing: [...new Set(missing)].sort(),
  };
}

async function ensureNewOutput(unitRoot, outputRoot) {
  const absolute = resolve(outputRoot);
  if (!isWithin(unitRoot, absolute) || absolute === unitRoot) throw new Error("QWENWORK_COLLECTOR_OUTPUT_OUTSIDE_UNIT");
  await mkdir(dirname(absolute), { recursive: true });
  await assertNoSymlinkPath(dirname(absolute));
  try {
    await lstat(absolute);
    throw new Error("QWENWORK_COLLECTOR_OUTPUT_EXISTS");
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  return absolute;
}

export async function collectQwenWorkEvidence(options) {
  const unitRoot = await realpath(resolve(requireString(options?.unitRoot, "unitRoot")));
  const clientTraceRoot = await realpath(resolve(requireString(options?.clientTraceRoot, "clientTraceRoot")));
  const outputRoot = await ensureNewOutput(unitRoot, requireString(options?.outputRoot, "outputRoot"));
  const journalSource = await readJson(requireString(options?.journalFile, "journalFile"));
  const { state, bindingSources } = await normalizeFormalState(journalSource.value, unitRoot);
  const sessionId = requireString(state.session.session_id, "state.session.session_id");
  const transcriptSource = await discoverTranscript(journalSource.value, clientTraceRoot, sessionId);
  const segmentSources = await discoverSegments(clientTraceRoot, sessionId);

  const transcriptRows = parseJsonLines(transcriptSource, "raw/transcript.jsonl");
  const segmentRows = segmentSources.flatMap((source) => parseJsonLines(
    source,
    `raw/segments/${basename(source.absolute)}`,
  ));
  assertTranscriptBinding(transcriptRows, state);
  assertSegmentBinding(segmentRows, state);
  const normalized = normalizeQwenNativeTrace({
    identity: state.identity,
    transcriptRows,
    segmentRows,
    redacted: options.redacted === true,
  });
  if (!normalized.events.length) throw new Error("QWENWORK_COLLECTOR_NORMALIZED_TRACE_EMPTY");
  const calls = buildQwenCallIndex(normalized.events);
  const transcriptBytes = jsonlBytes(normalized.events);
  const rawArtifacts = [artifact("raw/transcript.jsonl", transcriptSource.bytes)];
  for (const source of segmentSources) {
    rawArtifacts.push(artifact(`raw/segments/${basename(source.absolute)}`, source.bytes));
  }
  const bindingArtifacts = bindingSources.map((source, index) => artifact(
    `bindings/${String(index + 1).padStart(2, "0")}-${basename(source.absolute)}`,
    source.bytes,
  ));
  const stateBytes = jsonBytes(state);
  const index = {
    schema_id: TRACE_INDEX_SCHEMA,
    schema_version: 2,
    identity: { ...state.identity },
    adapter: {
      id: QWENWORK_COLLECTOR_ADAPTER_ID,
      version: QWENWORK_COLLECTOR_VERSION,
      source: options.redacted === true ? "redacted-fixture" : "qwenwork-native-session-files",
    },
    session: {
      thread_id: null,
      turn_id: null,
      session_id: state.session.session_id,
      cwd: state.session.cwd,
      lifecycle_generation: null,
    },
    transcript: artifact("transcript.jsonl", transcriptBytes, { event_count: normalized.events.length }),
    raw_trace: rawArtifacts,
    binding_evidence: bindingArtifacts,
    normalization: {
      native_event_count: normalized.native_event_count,
      normalized_event_count: normalized.normalized_event_count,
      filtered_native_event_count: normalized.filtered_native_event_count,
      compatibility_profiles: ["general-e2e-transcript-event-v1", "qwenwork-native-1.0.6-unverified-token-semantics"],
    },
    completeness: traceCompleteness(normalized.events, calls, segmentRows),
    calls,
  };
  const indexBytes = jsonBytes(index);
  const resourceSources = [
    artifact("execution/automation-state.json", stateBytes),
    artifact("trace/trace-index.json", indexBytes),
    ...rawArtifacts.slice(1).map((item) => ({ ...item, path: `trace/${item.path}` })),
  ];
  const resource = buildQwenStrictResourceMetrics({
    state,
    segmentRows,
    sources: resourceSources,
    traceCalls: calls,
    collectedAt: options.collectedAt || new Date().toISOString(),
  });
  const resourceBytes = jsonBytes(resource);

  const stage = await mkdtemp(join(dirname(outputRoot), ".qwenwork-collector-stage-"));
  try {
    await mkdir(join(stage, "execution"), { recursive: true });
    await mkdir(join(stage, "trace", "raw", "segments"), { recursive: true });
    await mkdir(join(stage, "trace", "bindings"), { recursive: true });
    await writeFile(join(stage, "execution", "automation-state.json"), stateBytes, { flag: "wx", mode: 0o600 });
    await writeFile(join(stage, "trace", "raw", "transcript.jsonl"), transcriptSource.bytes, { flag: "wx", mode: 0o600 });
    for (const source of segmentSources) {
      await writeFile(join(stage, "trace", "raw", "segments", basename(source.absolute)), source.bytes, { flag: "wx", mode: 0o600 });
    }
    for (let indexValue = 0; indexValue < bindingSources.length; indexValue += 1) {
      await writeFile(
        join(stage, "trace", bindingArtifacts[indexValue].path),
        bindingSources[indexValue].bytes,
        { flag: "wx", mode: 0o600 },
      );
    }
    await writeFile(join(stage, "trace", "transcript.jsonl"), transcriptBytes, { flag: "wx", mode: 0o600 });
    await writeFile(join(stage, "trace", "trace-index.json"), indexBytes, { flag: "wx", mode: 0o600 });
    await writeFile(join(stage, "resource-metrics.json"), resourceBytes, { flag: "wx", mode: 0o600 });
    await rename(stage, outputRoot);
  } catch (error) {
    await rm(stage, { recursive: true, force: true }).catch(() => {});
    throw error;
  }
  return {
    status: "PASS",
    output_root: outputRoot,
    state_file: join(outputRoot, "execution", "automation-state.json"),
    trace_index: join(outputRoot, "trace", "trace-index.json"),
    resource_metrics: join(outputRoot, "resource-metrics.json"),
    identity: state.identity,
    trace: index,
    resource,
  };
}

async function main(argv = process.argv.slice(2)) {
  const parsed = parseArgs(argv);
  if (parsed.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  process.stdout.write(`${JSON.stringify(await collectQwenWorkEvidence(parsed), null, 2)}\n`);
}

if (process.argv[1] && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url))) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
