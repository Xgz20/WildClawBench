import { createHash } from "node:crypto";
import { readFile, rename, stat, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join } from "node:path";
import { mkdir } from "node:fs/promises";
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

function sha256Buffer(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function parseTrajectoryJsonl(text, source = "trajectory.jsonl") {
  const events = [];
  const warnings = [];
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
  return { events, warnings, line_count: lines.length };
}

export function summarizeNormalizedEvents(events) {
  const calls = events.filter((event) => event.kind === "assistant_tool_call");
  const results = events.filter((event) => event.kind === "tool_result");
  const resultIds = new Set(results.map((event) => event.call_id).filter(Boolean));
  const matchedResults = calls.filter((event) => event.call_id && resultIds.has(event.call_id)).length;
  const finalAssistant = [...events].reverse().find((event) => event.kind === "assistant_message") ?? null;
  return {
    event_count: events.length,
    user_message_count: events.filter((event) => event.kind === "user_message").length,
    assistant_message_count: events.filter((event) => event.kind === "assistant_message").length,
    tool_call_known_subtotal: calls.length,
    tool_result_known_subtotal: results.length,
    matched_tool_result_count: matchedResults,
    final_assistant_in_trajectory: Boolean(finalAssistant?.content),
  };
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
  for (const trajectory of discovery.session.trajectories) {
    const info = await stat(trajectory.path);
    if (!info.isFile() || info.size > MAX_TRAJECTORY_BYTES) {
      throw new Error(`${trajectory.relative_path} 不是普通文件或超过大小上限`);
    }
    const buffer = await readFile(trajectory.path);
    const parsed = parseTrajectoryJsonl(buffer.toString("utf8"), trajectory.relative_path);
    events.push(...parsed.events.map((event) => ({ ...event, agent_id: trajectory.agent_id })));
    warnings.push(...parsed.warnings);
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
  const usage = unavailableUsage("trajectory.jsonl 未暴露可验证的模型 usage 或请求事件");
  const traceWarnings = [
    ...warnings,
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
        status: summary.tool_call_known_subtotal > 0 ? "partial" : "unavailable",
        basis: "trajectory.jsonl 中已解析的唯一 call_id 已知小计；无法证明覆盖完整 turn",
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

async function atomicWriteJson(outputPath, value) {
  await mkdir(dirname(outputPath), { recursive: true });
  const temporary = `${outputPath}.tmp-${process.pid}`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  await rename(temporary, outputPath);
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

