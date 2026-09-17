#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { realpathSync } from "node:fs";
import {
  copyFile,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const TRACE_ADAPTER_ID = "astronstudio-provider-runtime-events";
export const TRACE_ADAPTER_VERSION = "0.1.0";
export const TRACE_EVENT_SCHEMA = "urn:wildclawbench:schema:general-e2e:transcript-event:v1";
export const TRACE_INDEX_SCHEMA = "urn:wildclawbench:schema:general-e2e:trace-index:v1";
const EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-astronstudio-execution-state/v1";
const MAX_EVENT_BYTES = 2 * 1024 * 1024;
const TOOL_ITEM_TYPES = new Set(["commandExecution", "fileChange", "mcpToolCall"]);
const NON_TRANSCRIPT_ITEM_TYPES = new Set(["reasoning"]);

function usage() {
  return `AstronStudio General E2E 轨迹归档器

用法：
  node scripts/archive_astronstudio_trace.mjs \\
    --state-file /absolute/automation-state.json [选项]

选项：
  --state-db /absolute/state.sqlite  覆盖运行配置中的状态库路径
  --output-dir /absolute/evidence   默认为执行状态目录下的 trace/
  --replace                         原子覆盖已有的三个轨迹产物
  -h, --help                        显示帮助

本工具只读 AstronStudio SQLite 快照，只归档执行状态精确绑定的
thread/turn/provider session/cwd。它不冻结候选、不生成资源指标或正式执行回执。`;
}

export function parseArgs(argv) {
  const values = {
    stateFile: "",
    stateDb: "",
    outputDir: "",
    replace: false,
    help: false,
  };
  const valued = new Map([
    ["--state-file", "stateFile"],
    ["--state-db", "stateDb"],
    ["--output-dir", "outputDir"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else if (arg === "--replace") values.replace = true;
    else {
      const key = valued.get(arg);
      if (!key) throw new Error(`未知选项：${arg}`);
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      values[key] = value;
      index += 1;
    }
  }
  if (!values.help && !values.stateFile) throw new Error("必须指定 --state-file");
  return values;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sqlString(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

function jsonLineBytes(rows) {
  return Buffer.from(`${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
}

function prettyJsonBytes(value) {
  return Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function copyIfPresent(source, destination) {
  try {
    await copyFile(source, destination);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

async function loadNodeSqlite() {
  const sqlite = await import("node:sqlite").catch(() => null);
  if (typeof sqlite?.DatabaseSync !== "function") {
    throw new Error("NODE_SQLITE_UNAVAILABLE: 需要支持 node:sqlite 的 Node.js 运行时");
  }
  return sqlite;
}

export async function withStateSnapshot(stateDatabase, operation, overrides = {}) {
  const source = resolve(stateDatabase);
  const attempts = overrides.attempts || 3;
  const wait = overrides.sleep || ((milliseconds) => new Promise((done) => setTimeout(done, milliseconds)));
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const root = await mkdtemp(join(tmpdir(), "general-e2e-astudio-trace-"));
    const snapshot = join(root, "state.sqlite");
    try {
      await copyFile(source, snapshot);
      await copyIfPresent(`${source}-wal`, `${snapshot}-wal`);
      await copyIfPresent(`${source}-shm`, `${snapshot}-shm`);
      const sqlite = await (overrides.loadNodeSqlite || loadNodeSqlite)();
      const database = new sqlite.DatabaseSync(snapshot, { readOnly: true });
      try {
        const integrity = String(Object.values(database.prepare("PRAGMA quick_check;").get() || {})[0] || "");
        if (integrity !== "ok") throw new Error(`状态库快照 quick_check=${integrity || "empty"}`);
        return await operation(database, snapshot);
      } finally {
        database.close();
      }
    } catch (error) {
      lastError = error;
    } finally {
      await rm(root, { recursive: true, force: true }).catch(() => {});
    }
    if (attempt < attempts) await wait(100 * attempt);
  }
  throw new Error(
    `读取 AstronStudio 状态库快照失败：${lastError instanceof Error ? lastError.message : String(lastError)}`,
  );
}

function assertExecutionState(state) {
  if (state?.schema_version !== EXECUTION_STATE_SCHEMA) {
    throw new Error(`EXECUTION_STATE_UNSUPPORTED: ${state?.schema_version || "missing"}`);
  }
  if (!new Set(["COMPLETED", "FAILED"]).has(state.phase)) {
    throw new Error(`EXECUTION_NOT_TERMINAL: ${state.phase || "missing"}`);
  }
  if (state.prompt?.send_status !== "sent" || state.send?.dispatch_attempt_count !== 1) {
    throw new Error("PROMPT_IDENTITY_UNVERIFIED: 轨迹归档需要唯一且已确认的 Prompt 发送");
  }
  const session = state.session || {};
  for (const field of ["thread_id", "turn_id", "session_id", "cwd"]) {
    if (typeof session[field] !== "string" || !session[field].trim()) {
      throw new Error(`SESSION_IDENTITY_MISSING: ${field}`);
    }
  }
  if (session.verified !== true) throw new Error("SESSION_IDENTITY_UNVERIFIED");
  for (const field of ["batch_id", "unit_id", "task_id", "attempt_id"]) {
    if (typeof state.identity?.[field] !== "string" || !state.identity[field].trim()) {
      throw new Error(`TASK_IDENTITY_MISSING: ${field}`);
    }
  }
}

function samePath(left, right, platform = process.platform) {
  const first = resolve(String(left || ""));
  const second = resolve(String(right || ""));
  return platform === "win32" ? first.toLowerCase() === second.toLowerCase() : first === second;
}

function parseNativeEvent(row) {
  if (Buffer.byteLength(String(row.event_json || ""), "utf8") > MAX_EVENT_BYTES) {
    throw new Error(`NATIVE_EVENT_OVERSIZED: sequence=${row.sequence}`);
  }
  let event;
  try {
    event = JSON.parse(row.event_json);
  } catch (error) {
    throw new Error(`NATIVE_EVENT_JSON_INVALID: sequence=${row.sequence}: ${error.message}`);
  }
  return {
    sequence: Number(row.sequence),
    event_id: String(row.event_id),
    thread_id: String(row.thread_id),
    turn_id: row.turn_id === null ? null : String(row.turn_id),
    lifecycle_generation: row.lifecycle_generation === null
      ? null
      : String(row.lifecycle_generation),
    event_type: String(row.event_type),
    persisted_at: String(row.persisted_at),
    event,
  };
}

export async function queryBoundNativeTrace(database, state) {
  const { thread_id: threadId, turn_id: turnId, session_id: sessionId, cwd } = state.session;
  const bindingRows = database.prepare(`
SELECT
  turns.state AS turn_state,
  turns.requested_at AS requested_at,
  turns.started_at AS started_at,
  turns.completed_at AS completed_at,
  projects.workspace_root AS cwd
FROM projection_turns AS turns
INNER JOIN projection_threads AS threads ON threads.thread_id = turns.thread_id
INNER JOIN projection_projects AS projects ON projects.project_id = threads.project_id
WHERE turns.thread_id = ${sqlString(threadId)}
  AND turns.turn_id = ${sqlString(turnId)};
`).all();
  if (bindingRows.length !== 1) {
    throw new Error(`TURN_BINDING_AMBIGUOUS: expected=1 actual=${bindingRows.length}`);
  }
  const binding = bindingRows[0];
  if (!samePath(binding.cwd, cwd)) {
    throw new Error(`TRACE_CWD_MISMATCH: expected=${cwd} actual=${binding.cwd}`);
  }
  const rows = database.prepare(`
SELECT sequence, event_id, thread_id, turn_id, lifecycle_generation,
       event_type, event_json, persisted_at
FROM provider_runtime_events
WHERE thread_id = ${sqlString(threadId)}
  AND turn_id = ${sqlString(turnId)}
ORDER BY sequence ASC;
`).all().map(parseNativeEvent);
  if (!rows.length) throw new Error("NATIVE_TRACE_UNAVAILABLE: bound turn has no provider events");

  const seenSequences = new Set();
  const seenEventIds = new Set();
  const lifecycleGenerations = new Set();
  const providerSessionIds = new Set();
  let previousSequence = -1;
  for (const row of rows) {
    if (row.thread_id !== threadId || row.turn_id !== turnId) {
      throw new Error(`CROSS_SESSION_EVENT: sequence=${row.sequence}`);
    }
    if (row.sequence <= previousSequence || seenSequences.has(row.sequence)) {
      throw new Error(`NATIVE_SEQUENCE_INVALID: sequence=${row.sequence}`);
    }
    if (seenEventIds.has(row.event_id)) {
      throw new Error(`NATIVE_EVENT_ID_DUPLICATE: ${row.event_id}`);
    }
    if (row.event?.threadId && row.event.threadId !== threadId) {
      throw new Error(`NATIVE_EVENT_THREAD_MISMATCH: sequence=${row.sequence}`);
    }
    if (row.event?.turnId && row.event.turnId !== turnId) {
      throw new Error(`NATIVE_EVENT_TURN_MISMATCH: sequence=${row.sequence}`);
    }
    const providerThreadId = row.event?.providerRefs?.providerThreadId;
    if (typeof providerThreadId === "string" && providerThreadId.trim()) {
      providerSessionIds.add(providerThreadId);
    }
    if (row.lifecycle_generation) lifecycleGenerations.add(row.lifecycle_generation);
    seenSequences.add(row.sequence);
    seenEventIds.add(row.event_id);
    previousSequence = row.sequence;
  }
  if (providerSessionIds.size !== 1 || !providerSessionIds.has(sessionId)) {
    throw new Error(
      `PROVIDER_SESSION_MISMATCH: expected=${sessionId} actual=${[...providerSessionIds].join(",") || "missing"}`,
    );
  }
  if (lifecycleGenerations.size !== 1) {
    throw new Error(`LIFECYCLE_GENERATION_AMBIGUOUS: ${[...lifecycleGenerations].join(",")}`);
  }
  return {
    binding: {
      ...binding,
      lifecycle_generation: [...lifecycleGenerations][0],
    },
    rows,
  };
}

function itemFrom(row) {
  const item = row.event?.payload?.data?.item;
  return item && typeof item === "object" ? item : null;
}

function itemTypeFrom(row, item) {
  return String(item?.type || row.event?.payload?.itemType || "");
}

function textFromContent(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((block) => {
    if (typeof block === "string") return block;
    if (!block || typeof block !== "object") return "";
    if (typeof block.text === "string") return block.text;
    if (typeof block.content === "string") return block.content;
    if (typeof block.content?.value === "string") return block.content.value;
    return "";
  }).filter(Boolean).join("\n");
}

function normalizeWorkspacePath(rawPath, workspace, platform = process.platform) {
  if (typeof rawPath !== "string" || !rawPath.trim()) return null;
  if (!isAbsolute(rawPath)) return null;
  const absolute = resolve(rawPath);
  const workspaceAbsolute = resolve(workspace);
  const pathValue = platform === "win32" ? absolute.toLowerCase() : absolute;
  const workspaceValue = platform === "win32" ? workspaceAbsolute.toLowerCase() : workspaceAbsolute;
  if (pathValue === workspaceValue) return "/tmp_workspace";
  const rel = relative(workspaceAbsolute, absolute);
  if (!rel || rel === ".." || rel.startsWith("../") || rel.startsWith("..\\") || isAbsolute(rel)) {
    return null;
  }
  return `/tmp_workspace/${rel.split("\\").join("/")}`;
}

function createPathMapping(rawPath, workspace, kind) {
  if (typeof rawPath !== "string" || !rawPath.trim()) return null;
  return {
    kind,
    raw: rawPath,
    normalized: normalizeWorkspacePath(rawPath, workspace),
  };
}

function normalizeChanges(changes, workspace, mappings) {
  if (!Array.isArray(changes)) return [];
  return changes.map((change) => {
    if (!change || typeof change !== "object") return change;
    const mapping = createPathMapping(change.path, workspace, "file");
    if (mapping) mappings.push(mapping);
    const moveMapping = createPathMapping(change.kind?.move_path, workspace, "move_path");
    if (moveMapping) mappings.push(moveMapping);
    return {
      ...change,
      raw_path: typeof change.path === "string" ? change.path : null,
      normalized_path: mapping?.normalized || null,
      kind: change.kind && typeof change.kind === "object"
        ? {
          ...change.kind,
          raw_move_path: typeof change.kind.move_path === "string" ? change.kind.move_path : null,
          normalized_move_path: moveMapping?.normalized || null,
        }
        : change.kind,
    };
  });
}

function normalizeTool(item, workspace) {
  const mappings = [];
  if (item.type === "commandExecution") {
    const cwd = createPathMapping(item.cwd, workspace, "cwd");
    if (cwd) mappings.push(cwd);
    return {
      name: "command",
      arguments: {
        command: item.command ?? null,
        cwd: item.cwd ?? null,
        normalized_cwd: cwd?.normalized || null,
        command_actions: item.commandActions ?? [],
      },
      result: {
        output: item.aggregatedOutput ?? null,
        exit_code: item.exitCode ?? null,
        duration_ms: item.durationMs ?? null,
        status: item.status ?? null,
      },
      path_mappings: mappings,
    };
  }
  if (item.type === "fileChange") {
    const changes = normalizeChanges(item.changes, workspace, mappings);
    return {
      name: "file_change",
      arguments: { changes },
      result: { changes, duration_ms: item.durationMs ?? null, status: item.status ?? null },
      path_mappings: mappings,
    };
  }
  return {
    name: String(item.tool || item.name || "mcp_tool"),
    arguments: item.arguments ?? {},
    result: {
      result: item.result ?? null,
      error: item.error ?? null,
      duration_ms: item.durationMs ?? null,
      status: item.status ?? null,
      server: item.server ?? null,
      plugin_id: item.pluginId ?? null,
    },
    path_mappings: mappings,
  };
}

function resultStatus(item) {
  const status = String(item?.status || "").toLowerCase();
  if (new Set(["completed", "success", "succeeded"]).has(status)) return "success";
  if (new Set(["failed", "error", "cancelled", "canceled"]).has(status)) return "error";
  return "unknown";
}

function sourceFor(row, rawLine) {
  return {
    adapter: `${TRACE_ADAPTER_ID}@${TRACE_ADAPTER_VERSION}`,
    raw_ref: `raw/astronstudio-provider-events.jsonl#L${rawLine}`,
    redacted: false,
  };
}

function baseEvent(identity, row, rawLine, suffix = "") {
  return {
    schema_id: TRACE_EVENT_SCHEMA,
    schema_version: 1,
    identity,
    event_id: `${row.event_id}${suffix}`,
    sequence: -1,
    occurred_at: typeof row.event?.createdAt === "string" ? row.event.createdAt : row.persisted_at,
    type: "status",
    source: sourceFor(row, rawLine),
    native: {
      sequence: row.sequence,
      event_id: row.event_id,
      event_type: row.event_type,
      item_id: typeof row.event?.itemId === "string" ? row.event.itemId : null,
      lifecycle_generation: row.lifecycle_generation,
    },
  };
}

function callCompatibility(callId, name, args) {
  return {
    role: "assistant",
    content: [{
      type: "tool_use",
      id: callId,
      name,
      input: args,
      arguments: args,
    }],
  };
}

function resultCompatibility(callId, result) {
  return {
    role: "tool",
    content: [{
      type: "tool_result",
      tool_use_id: callId,
      content: result,
    }],
  };
}

export function normalizeTraceRows(rows, state) {
  const identity = { ...state.identity };
  const workspace = state.session.cwd;
  const completedAssistantRows = rows.filter((row) => {
    const item = itemFrom(row);
    return row.event_type === "item.completed" && item?.type === "agentMessage";
  });
  const finalAssistantEventId = completedAssistantRows.at(-1)?.event_id || null;
  const events = [];
  const missing = [];
  const calls = new Map();
  const unsupportedItems = new Set();
  let userMessageCount = 0;
  let assistantMessageCount = 0;
  let filteredNativeEventCount = 0;

  function append(event) {
    event.sequence = events.length;
    events.push(event);
  }

  rows.forEach((row, rowIndex) => {
    const rawLine = rowIndex + 1;
    const item = itemFrom(row);
    const itemType = itemTypeFrom(row, item);
    if (row.event_type === "turn.started" || row.event_type === "turn.completed") {
      const event = baseEvent(identity, row, rawLine);
      event.type = "status";
      event.content = row.event_type;
      event.status = row.event?.payload ?? null;
      append(event);
      return;
    }
    if (row.event_type === "thread.token-usage.updated") {
      const event = baseEvent(identity, row, rawLine);
      event.type = "usage";
      event.usage = row.event?.payload ?? null;
      append(event);
      return;
    }
    if (row.event_type === "item.completed" && itemType === "userMessage") {
      const content = textFromContent(item?.content);
      const event = baseEvent(identity, row, rawLine);
      event.type = "user_message";
      event.role = "user";
      event.content = content;
      append(event);
      userMessageCount += 1;
      return;
    }
    if (row.event_type === "item.completed" && itemType === "agentMessage") {
      const content = typeof item?.text === "string" ? item.text : textFromContent(item?.content);
      const event = baseEvent(identity, row, rawLine);
      event.type = "assistant_message";
      event.role = "assistant";
      event.content = content;
      event.final = row.event_id === finalAssistantEventId;
      append(event);
      assistantMessageCount += 1;
      return;
    }
    if (TOOL_ITEM_TYPES.has(itemType) && row.event_type === "item.started") {
      const callId = String(item?.id || row.event?.itemId || "");
      if (!callId) {
        missing.push(`tool_call_id:${row.event_id}`);
        return;
      }
      if (calls.has(callId)) throw new Error(`TOOL_CALL_DUPLICATE: ${callId}`);
      const normalized = normalizeTool(item, workspace);
      const event = baseEvent(identity, row, rawLine, ":call");
      event.type = "tool_call";
      event.role = "assistant";
      event.content = null;
      event.tool = {
        call_id: callId,
        name: normalized.name,
        arguments: normalized.arguments,
        status: "unknown",
      };
      event.path_mappings = normalized.path_mappings;
      event.message = callCompatibility(callId, normalized.name, normalized.arguments);
      append(event);
      calls.set(callId, { call_sequence: event.sequence, result_sequence: null });
      return;
    }
    if (TOOL_ITEM_TYPES.has(itemType) && row.event_type === "item.completed") {
      const callId = String(item?.id || row.event?.itemId || "");
      if (!callId) {
        missing.push(`tool_result_call_id:${row.event_id}`);
        return;
      }
      const normalized = normalizeTool(item, workspace);
      const event = baseEvent(identity, row, rawLine, ":result");
      event.type = "tool_result";
      event.role = null;
      event.content = null;
      event.tool = {
        call_id: callId,
        name: normalized.name,
        result: normalized.result,
        status: resultStatus(item),
      };
      event.path_mappings = normalized.path_mappings;
      event.message = resultCompatibility(callId, normalized.result);
      append(event);
      const call = calls.get(callId);
      if (!call) missing.push(`tool_call:${callId}`);
      else if (call.result_sequence !== null) throw new Error(`TOOL_RESULT_DUPLICATE: ${callId}`);
      else call.result_sequence = event.sequence;
      return;
    }
    if (
      row.event_type.startsWith("item.")
      && itemType
      && !TOOL_ITEM_TYPES.has(itemType)
      && !NON_TRANSCRIPT_ITEM_TYPES.has(itemType)
      && !new Set(["userMessage", "agentMessage", "unknown"]).has(itemType)
    ) {
      unsupportedItems.add(itemType);
    }
    if (/error|failed/iu.test(row.event_type)) {
      const event = baseEvent(identity, row, rawLine);
      event.type = "error";
      event.content = JSON.stringify(row.event?.payload ?? row.event);
      append(event);
      return;
    }
    filteredNativeEventCount += 1;
  });

  const eventTypes = new Set(rows.map((row) => row.event_type));
  if (!eventTypes.has("turn.started")) missing.push("turn.started");
  if (!eventTypes.has("turn.completed")) missing.push("turn.completed");
  if (userMessageCount !== 1) missing.push(`user_message_count:${userMessageCount}`);
  if (assistantMessageCount < 1) missing.push("assistant_message");
  for (const [callId, call] of calls) {
    if (call.result_sequence === null) missing.push(`tool_result:${callId}`);
  }
  for (const itemType of unsupportedItems) missing.push(`unsupported_item_type:${itemType}`);

  return {
    events,
    calls: [...calls.entries()].map(([call_id, value]) => ({ call_id, ...value })),
    completeness: {
      status: missing.length ? "partial" : "complete",
      omitted_event_count: 0,
      missing: [...new Set(missing)].sort(),
    },
    normalization: {
      native_event_count: rows.length,
      normalized_event_count: events.length,
      filtered_native_event_count: filteredNativeEventCount,
      compatibility_profiles: [
        "general-e2e-transcript-event-v1",
        "wildclawbench-grading-transcript-v2",
      ],
    },
  };
}

function promptFromEvents(events) {
  const messages = events.filter((event) => event.type === "user_message");
  return messages.length === 1 ? messages[0].content : null;
}

function finalResponseFromEvents(events) {
  const messages = events.filter((event) => event.type === "assistant_message" && event.final);
  return messages.length === 1 ? messages[0].content : null;
}

async function assertPromptAndFinalResponse(state, events) {
  const prompt = await readFile(resolve(state.prompt.path));
  if (sha256(prompt) !== state.prompt.sha256) throw new Error("PROMPT_FILE_DIGEST_MISMATCH");
  const archivedPrompt = promptFromEvents(events);
  if (archivedPrompt === null || sha256(Buffer.from(archivedPrompt, "utf8")) !== state.prompt.sha256) {
    throw new Error("ARCHIVED_PROMPT_DIGEST_MISMATCH");
  }
  if (!state.evidence?.final_response_path || !state.evidence?.final_response_sha256) return;
  const taskRoot = resolve(state.task_root);
  const unitRoot = resolve(taskRoot, "../../..");
  const finalPath = resolve(unitRoot, state.evidence.final_response_path);
  const finalBytes = await readFile(finalPath);
  if (sha256(finalBytes) !== state.evidence.final_response_sha256) {
    throw new Error("FINAL_RESPONSE_FILE_DIGEST_MISMATCH");
  }
  const archivedFinal = finalResponseFromEvents(events);
  if (archivedFinal === null || archivedFinal.trim() !== finalBytes.toString("utf8").trim()) {
    throw new Error("ARCHIVED_FINAL_RESPONSE_MISMATCH");
  }
}

async function atomicWrite(path, bytes) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  await writeFile(temporary, bytes);
  try {
    await rename(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

async function assertWritableTargets(paths, replace) {
  for (const path of paths) {
    try {
      const info = await lstat(path);
      if (!info.isFile() || info.isSymbolicLink()) throw new Error(`UNSAFE_OUTPUT_TARGET: ${path}`);
      if (!replace) throw new Error(`OUTPUT_EXISTS: ${path}`);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
}

function artifact(path, bytes, extra = {}) {
  return {
    path,
    sha256: sha256(bytes),
    size: bytes.length,
    ...extra,
  };
}

function rawArchiveRows(rows) {
  return rows.map((row) => ({
    sequence: row.sequence,
    event_id: row.event_id,
    thread_id: row.thread_id,
    turn_id: row.turn_id,
    lifecycle_generation: row.lifecycle_generation,
    event_type: row.event_type,
    persisted_at: row.persisted_at,
    event: row.event,
  }));
}

export async function archiveAstronStudioTrace(options, overrides = {}) {
  const stateFile = resolve(options.stateFile);
  const stateInfo = await stat(stateFile);
  if (!stateInfo.isFile()) throw new Error(`STATE_FILE_INVALID: ${stateFile}`);
  const state = await readJson(stateFile);
  assertExecutionState(state);
  let stateDatabase = options.stateDb ? resolve(options.stateDb) : "";
  if (!stateDatabase) {
    const runConfig = await readJson(resolve(state.run_config.path));
    const configuredPath = runConfig?.state_database?.path;
    if (typeof configuredPath === "string" && configuredPath.trim()) {
      stateDatabase = resolve(configuredPath);
    }
  }
  if (!stateDatabase) throw new Error("STATE_DATABASE_MISSING");
  const outputDir = resolve(options.outputDir || join(dirname(stateFile), "trace"));
  const rawPath = join(outputDir, "raw", "astronstudio-provider-events.jsonl");
  const transcriptPath = join(outputDir, "transcript.jsonl");
  const indexPath = join(outputDir, "trace-index.json");
  await assertWritableTargets([rawPath, transcriptPath, indexPath], Boolean(options.replace));

  const native = await withStateSnapshot(
    stateDatabase,
    (database) => queryBoundNativeTrace(database, state),
    overrides,
  );
  const normalized = normalizeTraceRows(native.rows, state);
  await assertPromptAndFinalResponse(state, normalized.events);

  const rawBytes = jsonLineBytes(rawArchiveRows(native.rows));
  const transcriptBytes = jsonLineBytes(normalized.events);
  const index = {
    schema_id: TRACE_INDEX_SCHEMA,
    schema_version: 1,
    identity: { ...state.identity },
    adapter: {
      id: TRACE_ADAPTER_ID,
      version: TRACE_ADAPTER_VERSION,
      source: "provider_runtime_events",
    },
    session: {
      thread_id: state.session.thread_id,
      turn_id: state.session.turn_id,
      session_id: state.session.session_id,
      cwd: state.session.cwd,
      lifecycle_generation: native.binding.lifecycle_generation,
    },
    transcript: artifact("transcript.jsonl", transcriptBytes, {
      event_count: normalized.events.length,
    }),
    raw_trace: [artifact("raw/astronstudio-provider-events.jsonl", rawBytes)],
    raw_event_range: {
      first_sequence: native.rows[0].sequence,
      last_sequence: native.rows.at(-1).sequence,
      event_count: native.rows.length,
    },
    normalization: normalized.normalization,
    completeness: normalized.completeness,
    calls: normalized.calls,
  };
  const indexBytes = prettyJsonBytes(index);
  await mkdir(join(outputDir, "raw"), { recursive: true });
  await atomicWrite(rawPath, rawBytes);
  await atomicWrite(transcriptPath, transcriptBytes);
  await atomicWrite(indexPath, indexBytes);
  return {
    status: "PASS",
    output_dir: outputDir,
    trace_index: index,
    artifacts: {
      raw_trace: {
        ...artifact("raw/astronstudio-provider-events.jsonl", rawBytes),
        absolute_path: rawPath,
      },
      transcript: { ...artifact("transcript.jsonl", transcriptBytes), absolute_path: transcriptPath },
      trace_index: { absolute_path: indexPath, sha256: sha256(indexBytes), size: indexBytes.length },
    },
  };
}

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  if (parsed.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  const result = await archiveAstronStudioTrace(parsed);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

const isEntrypoint = process.argv[1]
  && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
