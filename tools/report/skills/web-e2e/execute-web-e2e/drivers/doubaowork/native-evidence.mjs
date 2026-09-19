import { createHash } from "node:crypto";
import { link, lstat, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, normalize } from "node:path";
import { homedir } from "node:os";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

import {
  DRIVER_VERSION,
  NATIVE_EVIDENCE_SCHEMA,
  unavailableUsage,
  validateSessionId,
} from "./lib.mjs";
import { defaultNativeRoots, discoverNativeSources } from "./platform.mjs";

const MAX_TRAJECTORY_BYTES = 16 * 1024 * 1024;
const MAX_TRAJECTORY_LINES = 50_000;
const TERMINAL_FIELD_CANDIDATES = new Set([
  "status",
  "state",
  "terminal_status",
  "event",
  "event_type",
  "finish_reason",
  "completed_at",
  "ended_at",
]);
const WORKSPACE_FIELD_CANDIDATES = new Set([
  "cwd",
  "workspace",
  "workspace_path",
  "working_directory",
  "project_path",
  "root_path",
]);

function sha256Buffer(value) {
  return createHash("sha256").update(value).digest("hex");
}

function countStringReferences(value, needle) {
  if (!needle) return 0;
  if (typeof value === "string") return value.includes(needle) ? 1 : 0;
  if (Array.isArray(value)) {
    return value.reduce((total, item) => total + countStringReferences(item, needle), 0);
  }
  if (value && typeof value === "object") {
    return Object.values(value).reduce((total, item) => total + countStringReferences(item, needle), 0);
  }
  return 0;
}

export function inspectTrajectoryNativeSignals(entries, { requestedWorkspace = null } = {}) {
  const topLevelFields = new Set();
  const terminalCandidateFields = new Map();
  const workspaceCandidateFields = new Map();
  let requestedWorkspaceReferenceCount = 0;
  let structuredToolPathReferenceCount = 0;
  let toolResultPathReferenceCount = 0;
  let terminalLikeToolResultCount = 0;
  for (const entry of entries) {
    for (const field of Object.keys(entry)) {
      topLevelFields.add(field);
      if (TERMINAL_FIELD_CANDIDATES.has(field)) {
        terminalCandidateFields.set(field, (terminalCandidateFields.get(field) || 0) + 1);
      }
      if (WORKSPACE_FIELD_CANDIDATES.has(field)) {
        workspaceCandidateFields.set(field, (workspaceCandidateFields.get(field) || 0) + 1);
      }
    }
    requestedWorkspaceReferenceCount += countStringReferences(entry, requestedWorkspace);
    if (Array.isArray(entry.tool_calls)) {
      for (const call of entry.tool_calls) {
        const filePath = call?.function?.arguments?.file_path;
        if (typeof filePath === "string" && requestedWorkspace && filePath.includes(requestedWorkspace)) {
          structuredToolPathReferenceCount += 1;
        }
      }
    }
    if (entry.role === "tool" && typeof entry.content === "string") {
      if (requestedWorkspace && entry.content.includes(requestedWorkspace)) toolResultPathReferenceCount += 1;
      if (/\b(?:completed|finished|succeeded|failed|interrupted|ended)\b/iu.test(entry.content)) {
        terminalLikeToolResultCount += 1;
      }
    }
  }
  const terminalCandidateCount = [...terminalCandidateFields.values()]
    .reduce((total, count) => total + count, 0);
  const workspaceCandidateCount = [...workspaceCandidateFields.values()]
    .reduce((total, count) => total + count, 0);
  return {
    observed_top_level_fields: [...topLevelFields].sort(),
    terminal: {
      status: terminalCandidateCount > 0 ? "unverified" : "unavailable",
      authoritative_source: null,
      candidate_top_level_fields: Object.fromEntries([...terminalCandidateFields].sort()),
      candidate_event_count: terminalCandidateCount,
      terminal_like_tool_result_count: terminalLikeToolResultCount,
      tool_result_text_is_sufficient: false,
      reason: terminalCandidateCount > 0
        ? "trajectory 存在未经语义验证的终态候选字段，不能直接映射为 Agent 终态"
        : "trajectory 顶层没有已知 session/turn 终态字段或结束事件",
    },
    workspace_binding: {
      status: "unverified",
      native_cwd: null,
      authoritative_source: null,
      candidate_top_level_fields: Object.fromEntries([...workspaceCandidateFields].sort()),
      candidate_field_count: workspaceCandidateCount,
      requested_workspace_reference_count: requestedWorkspaceReferenceCount,
      structured_tool_path_reference_count: structuredToolPathReferenceCount,
      tool_result_path_reference_count: toolResultPathReferenceCount,
      tool_activity_is_sufficient: false,
      reason: workspaceCandidateCount > 0
        ? "trajectory 存在未经语义验证的路径候选字段，尚不能作为 session 原生 cwd"
        : "工具参数或输出中的路径仅证明工具活动，trajectory 没有 session 原生 cwd 字段",
    },
  };
}

export function parseTrajectoryJsonl(text, source = "trajectory.jsonl", options = {}) {
  const events = [];
  const warnings = [];
  const entries = [];
  const lines = text.split(/\r?\n/);
  if (lines.at(-1) === "") lines.pop();
  if (lines.length > MAX_TRAJECTORY_LINES) {
    throw new Error(`${source} 超过 ${MAX_TRAJECTORY_LINES} 行上限`);
  }
  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index];
    if (!raw.trim()) continue;
    let entry;
    try {
      entry = JSON.parse(raw);
    } catch {
      warnings.push({ code: "INVALID_JSON_LINE", source, line: index + 1 });
      continue;
    }
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      warnings.push({
        code: "INVALID_JSON_LINE",
        source,
        line: index + 1,
        reason: "trajectory JSON 必须是对象",
      });
      continue;
    }
    entries.push(entry);
    const role = typeof entry.role === "string" ? entry.role : "unknown";
    if (Array.isArray(entry.tool_calls)) {
      for (const call of entry.tool_calls) {
        const callId = typeof call?.id === "string" ? call.id : null;
        const name = typeof call?.function?.name === "string" ? call.function.name : null;
        const args = call?.function?.arguments ?? null;
        events.push({
          kind: "assistant_tool_call",
          role,
          call_id: callId,
          tool_name: name,
          arguments: args,
          source: { file: source, line: index + 1 },
        });
      }
    } else if (role === "tool") {
      events.push({
        kind: "tool_result",
        role,
        call_id: typeof entry.tool_call_id === "string" ? entry.tool_call_id : null,
        content: typeof entry.content === "string" ? entry.content : null,
        outcome: entry.is_error === true ? "error" : "unknown",
        source: { file: source, line: index + 1 },
      });
    } else if (role === "user" || role === "assistant") {
      events.push({
        kind: role === "user" ? "user_message" : "assistant_message",
        role,
        content: typeof entry.content === "string" ? entry.content : null,
        source: { file: source, line: index + 1 },
      });
    } else {
      warnings.push({ code: "UNSUPPORTED_TRAJECTORY_EVENT", source, line: index + 1, role });
    }
  }
  return {
    events,
    warnings,
    line_count: lines.length,
    native_signals: inspectTrajectoryNativeSignals(entries, options),
  };
}

export function summarizeNormalizedEvents(events) {
  const calls = events.filter((event) => event.kind === "assistant_tool_call");
  const results = events.filter((event) => event.kind === "tool_result");
  const diagnostics = [];
  const scopedKey = (event) => {
    const agentId = typeof event.agent_id === "string" && event.agent_id.trim()
      ? event.agent_id
      : null;
    const callId = typeof event.call_id === "string" && event.call_id.trim()
      ? event.call_id
      : null;
    return agentId && callId ? `${agentId}\u0000${callId}` : null;
  };
  const groupByScopedId = (items, kind) => {
    const groups = new Map();
    let unscopedCount = 0;
    for (const event of items) {
      const key = scopedKey(event);
      if (!key) {
        unscopedCount += 1;
        diagnostics.push({
          code: kind === "call" ? "TOOL_CALL_SCOPE_MISSING" : "TOOL_RESULT_SCOPE_MISSING",
          detail: "工具事件缺少 agent_id 或 call_id，不能纳入已知小计或结果匹配",
          source: event.source ?? null,
        });
        continue;
      }
      const group = groups.get(key) ?? [];
      group.push(event);
      groups.set(key, group);
    }
    for (const [key, group] of groups) {
      if (group.length < 2) continue;
      const fingerprints = new Set(group.map((event) => JSON.stringify(kind === "call"
        ? { tool_name: event.tool_name ?? null, arguments: event.arguments ?? null }
        : { content: event.content ?? null, outcome: event.outcome ?? null })));
      diagnostics.push({
        code: fingerprints.size > 1
          ? `CONFLICTING_SCOPED_TOOL_${kind.toUpperCase()}_ID`
          : `DUPLICATE_SCOPED_TOOL_${kind.toUpperCase()}_ID`,
        detail: "同一 session + agent_id + call_id 出现重复来源，已按一个已知 ID 计数",
        scoped_id_sha256: sha256Buffer(Buffer.from(key)),
        source_count: group.length,
        sources: group.map((event) => event.source ?? null),
      });
    }
    return { groups, unscopedCount };
  };
  const callIndex = groupByScopedId(calls, "call");
  const resultIndex = groupByScopedId(results, "result");
  const matchedResults = [...callIndex.groups.keys()]
    .filter((key) => resultIndex.groups.has(key)).length;
  const finalAssistant = [...events].reverse().find((event) => event.kind === "assistant_message") ?? null;
  return {
    event_count: events.length,
    user_message_count: events.filter((event) => event.kind === "user_message").length,
    assistant_message_count: events.filter((event) => event.kind === "assistant_message").length,
    tool_call_event_count: calls.length,
    tool_result_event_count: results.length,
    tool_call_known_subtotal: callIndex.groups.size,
    tool_result_known_subtotal: resultIndex.groups.size,
    matched_tool_result_count: matchedResults,
    identifier_scope: "session+agent_id+call_id",
    identifier_coverage: {
      status: callIndex.unscopedCount === 0 && resultIndex.unscopedCount === 0
        ? "complete-for-observed-events"
        : "incomplete",
      unscoped_tool_call_event_count: callIndex.unscopedCount,
      unscoped_tool_result_event_count: resultIndex.unscopedCount,
    },
    diagnostics,
    final_assistant_in_trajectory: Boolean(finalAssistant?.content),
  };
}

async function validateTrajectoryPath(trajectory, sessionId) {
  const expectedRelative = join(
    sessionId,
    "agents",
    trajectory.agent_id,
    "system",
    "trajectory.jsonl",
  );
  if (normalize(trajectory.relative_path) !== normalize(expectedRelative)) {
    throw new Error(`trajectory 相对路径不符合显式 session/agent 布局：${trajectory.relative_path}`);
  }
  const pathChain = [
    { path: trajectory.path, kind: "file", label: "trajectory.jsonl" },
    { path: dirname(trajectory.path), kind: "directory", label: "system" },
    { path: dirname(dirname(trajectory.path)), kind: "directory", label: "agent" },
    { path: dirname(dirname(dirname(trajectory.path))), kind: "directory", label: "agents" },
    { path: dirname(dirname(dirname(dirname(trajectory.path)))), kind: "directory", label: "session" },
  ];
  if (basename(pathChain[1].path) !== "system"
      || basename(pathChain[2].path) !== trajectory.agent_id
      || basename(pathChain[3].path) !== "agents"
      || basename(pathChain[4].path) !== sessionId) {
    throw new Error(`trajectory 绝对路径不符合显式 session/agent 布局：${trajectory.relative_path}`);
  }
  for (const item of pathChain) {
    const info = await lstat(item.path);
    const typeMatches = item.kind === "file" ? info.isFile() : info.isDirectory();
    if (info.isSymbolicLink() || !typeMatches) {
      throw new Error(`${item.label} 不是普通${item.kind === "file" ? "文件" : "目录"}或包含符号链接`);
    }
  }
  return lstat(trajectory.path);
}

export async function buildNativeEvidence({ sessionId, workspace, discovery }) {
  validateSessionId(sessionId);
  if (!isAbsolute(workspace)) throw new Error("--workspace 必须是绝对路径");
  if (!discovery.session?.exists) throw new Error(`未找到显式 DoubaoWork session：${sessionId}`);
  if (discovery.session.trajectories.length === 0) {
    throw new Error(`DoubaoWork session ${sessionId} 没有可读取的 trajectory.jsonl`);
  }

  const sources = [];
  const events = [];
  const warnings = [];
  const nativeSignalSources = [];
  for (const trajectory of discovery.session.trajectories) {
    const info = await validateTrajectoryPath(trajectory, sessionId);
    if (info.size > MAX_TRAJECTORY_BYTES) {
      throw new Error(`${trajectory.relative_path} 超过大小上限`);
    }
    const buffer = await readFile(trajectory.path);
    const parsed = parseTrajectoryJsonl(buffer.toString("utf8"), trajectory.relative_path, {
      requestedWorkspace: workspace,
    });
    events.push(...parsed.events.map((event) => ({ ...event, agent_id: trajectory.agent_id })));
    warnings.push(...parsed.warnings);
    nativeSignalSources.push({
      source: trajectory.relative_path,
      agent_id: trajectory.agent_id,
      ...parsed.native_signals,
    });
    sources.push({
      kind: "doubaowork-session-trajectory",
      relative_path: trajectory.relative_path,
      agent_id: trajectory.agent_id,
      size_bytes: buffer.length,
      sha256: sha256Buffer(buffer),
      line_count: parsed.line_count,
      raw_copied: false,
    });
  }

  const summary = summarizeNormalizedEvents(events);
  const terminalCandidateEventCount = nativeSignalSources
    .reduce((total, item) => total + item.terminal.candidate_event_count, 0);
  const nativeCapabilities = {
    terminal: {
      status: terminalCandidateEventCount > 0 ? "unverified" : "unavailable",
      authoritative_source: null,
      candidate_event_count: terminalCandidateEventCount,
      tool_result_text_is_sufficient: false,
      reason: terminalCandidateEventCount > 0
        ? "发现未经语义验证的终态候选字段；没有已知 DoubaoWork session/turn 完成事件映射"
        : "已绑定 trajectory 没有 session/turn 终态字段或结束事件；工具子任务文本与 UI idle 均不足以提升终态",
    },
    workspace_binding: {
      status: "unverified",
      native_cwd: null,
      authoritative_source: null,
      requested_workspace_reference_count: nativeSignalSources
        .reduce((total, item) => total + item.workspace_binding.requested_workspace_reference_count, 0),
      structured_tool_path_reference_count: nativeSignalSources
        .reduce((total, item) => total + item.workspace_binding.structured_tool_path_reference_count, 0),
      tool_result_path_reference_count: nativeSignalSources
        .reduce((total, item) => total + item.workspace_binding.tool_result_path_reference_count, 0),
      tool_activity_is_sufficient: false,
      reason: "工具参数、pwd 输出和写文件路径仅为活动旁证；没有 session 原生 cwd 字段",
    },
    sources: nativeSignalSources,
  };
  const usage = unavailableUsage("trajectory.jsonl 未暴露可验证的模型 usage 或请求事件");
  const traceWarnings = [
    ...warnings,
    ...summary.diagnostics,
    {
      code: "NATIVE_CWD_UNAVAILABLE",
      detail: "session 目录和 trajectory 未提供 cwd，不能把调用者 workspace 写成原生 cwd",
    },
    {
      code: "NATIVE_TERMINAL_UNAVAILABLE",
      detail: "trajectory 未提供可信 turn/session 终态，UI 完成候选不能提升为原生成功终态",
    },
  ];
  if (!summary.final_assistant_in_trajectory) {
    traceWarnings.push({
      code: "FINAL_ASSISTANT_MISSING_FROM_TRAJECTORY",
      detail: "最终回复仅能另从 UI 保存；当前原生 trajectory 不完整",
    });
  }

  return {
    schema: NATIVE_EVIDENCE_SCHEMA,
    adapter: { harness: "doubaowork", platform: "darwin", version: DRIVER_VERSION },
    collected_at: new Date().toISOString(),
    identity: {
      conversation_id: sessionId,
      session_directory_id: sessionId,
      turn_id: null,
      native_cwd: null,
      requested_workspace: workspace,
      workspace_binding: {
        status: "unverified",
        requested_path: workspace,
        native_path: null,
        reason: "当前原生 session/trajectory 不含 cwd；必须依赖客户端完整路径回读并等待公共可信映射",
      },
    },
    terminal: {
      status: "unverified",
      raw_status: null,
      source: null,
      ui_completion_is_sufficient: false,
    },
    native_capabilities: nativeCapabilities,
    trace: {
      completeness: "partial",
      summary,
      events,
      sources,
      warnings: traceWarnings,
    },
    resources: {
      usage,
      tools: {
        call_count: summary.tool_call_known_subtotal,
        status: summary.tool_call_event_count > 0 ? "partial" : "unavailable",
        basis: "trajectory.jsonl 中按 session + agent_id + call_id 去重的已知小计；空 ID、重复/冲突与完整 turn 覆盖均单列诊断",
        known_subtotal: summary.tool_call_known_subtotal,
        coverage: { numerator: summary.matched_tool_result_count, denominator: null },
      },
      execution: {
        duration_seconds: null,
        agent_duration_seconds: null,
        status: "unavailable",
        basis: "trajectory.jsonl 事件没有可信时间戳和终态边界",
      },
      native_credit: {
        value: null,
        unit: null,
        status: "unavailable",
        basis: "未发现绑定本 session/attempt 的结算来源；不能从 UI 消耗或 Token 反推",
      },
    },
  };
}

export async function atomicWriteJson(outputPath, value) {
  await mkdir(dirname(outputPath), { recursive: true });
  const temporary = `${outputPath}.tmp-${process.pid}`;
  try {
    await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
    await link(temporary, outputPath);
  } catch (error) {
    if (error?.code === "EEXIST") {
      throw new Error(`输出证据已存在，拒绝覆盖：${outputPath}`);
    }
    throw error;
  } finally {
    await rm(temporary, { force: true }).catch(() => {});
  }
}

export async function main(argv = process.argv.slice(2)) {
  const { values } = parseArgs({
    args: argv,
    options: {
      "session-id": { type: "string" },
      workspace: { type: "string" },
      "sessions-root": { type: "string" },
      "logs-root": { type: "string" },
      output: { type: "string" },
    },
  });
  if (!values["session-id"] || !values.workspace || !values.output) {
    throw new Error("用法：node native-evidence.mjs --session-id <原生数字ID> --workspace <绝对路径> --output <新JSON路径>");
  }
  validateSessionId(values["session-id"]);
  const defaults = defaultNativeRoots(homedir());
  const roots = {
    ...defaults,
    sessions_root: values["sessions-root"] || defaults.sessions_root,
    logs_root: values["logs-root"] || defaults.logs_root,
  };
  const discovery = await discoverNativeSources({ sessionId: values["session-id"], roots });
  const evidence = await buildNativeEvidence({
    sessionId: values["session-id"],
    workspace: values.workspace,
    discovery,
  });
  await atomicWriteJson(values.output, evidence);
  process.stdout.write(`${JSON.stringify({ status: "written", output: values.output, schema: evidence.schema })}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
