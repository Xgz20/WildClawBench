#!/usr/bin/env node

import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { lstat, readFile, realpath } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024;
const MAX_PAGE_SIZE = 200;

function usage() {
  return `General E2E 标准轨迹只读检索

用法：
  node scripts/query_trace.mjs --trace-index /absolute/trace-index.json [过滤条件]

过滤条件按 AND 组合：
  --from-sequence <n>   标准事件起始 sequence（包含）
  --to-sequence <n>     标准事件结束 sequence（包含）
  --call-id <id>        精确匹配工具 call ID
  --path <path>         精确匹配原始或 /tmp_workspace 规范路径
  --text <substring>    在消息、工具参数和结果中不区分大小写检索
  --page <n>            页码，默认 1
  --page-size <n>       每页条数，默认 50，最大 200
  -h, --help            显示帮助`;
}

function positiveInteger(value, name, maximum = Number.MAX_SAFE_INTEGER) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0 || parsed > maximum) {
    throw new Error(`${name} 必须是 1–${maximum} 的整数`);
  }
  return parsed;
}

function nonNegativeInteger(value, name) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`${name} 必须是非负整数`);
  return parsed;
}

export function parseArgs(argv) {
  const values = {
    traceIndex: "",
    fromSequence: null,
    toSequence: null,
    callId: "",
    path: "",
    text: "",
    page: 1,
    pageSize: 50,
    help: false,
  };
  const valued = new Map([
    ["--trace-index", "traceIndex"],
    ["--from-sequence", "fromSequence"],
    ["--to-sequence", "toSequence"],
    ["--call-id", "callId"],
    ["--path", "path"],
    ["--text", "text"],
    ["--page", "page"],
    ["--page-size", "pageSize"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else {
      const key = valued.get(arg);
      if (!key) throw new Error(`未知选项：${arg}`);
      const value = argv[index + 1];
      if (value === undefined || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      if (key === "page") values.page = positiveInteger(value, arg);
      else if (key === "pageSize") values.pageSize = positiveInteger(value, arg, MAX_PAGE_SIZE);
      else if (key === "fromSequence" || key === "toSequence") {
        values[key] = nonNegativeInteger(value, arg);
      } else values[key] = value;
      index += 1;
    }
  }
  if (!values.help && !values.traceIndex) throw new Error("必须指定 --trace-index");
  if (
    values.fromSequence !== null
    && values.toSequence !== null
    && values.fromSequence > values.toSequence
  ) throw new Error("--from-sequence 不能大于 --to-sequence");
  return values;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function readSafeArtifact(indexPath, artifact) {
  if (
    !artifact
    || typeof artifact.path !== "string"
    || !artifact.path
    || isAbsolute(artifact.path)
    || artifact.path.includes("\\")
    || artifact.path.split("/").some((part) => !part || part === "." || part === "..")
  ) throw new Error("TRANSCRIPT_PATH_INVALID");
  const root = await realpath(dirname(indexPath));
  const path = resolve(root, artifact.path);
  const leaf = await lstat(path);
  if (leaf.isSymbolicLink()) throw new Error("TRANSCRIPT_UNSAFE_OR_OVERSIZED");
  const resolved = await realpath(path);
  const rel = relative(root, resolved);
  if (!rel || rel === ".." || rel.startsWith("../") || isAbsolute(rel)) {
    throw new Error("TRANSCRIPT_OUTSIDE_TRACE_ROOT");
  }
  const info = await lstat(resolved);
  if (!info.isFile() || info.size > MAX_TRANSCRIPT_BYTES) {
    throw new Error("TRANSCRIPT_UNSAFE_OR_OVERSIZED");
  }
  const bytes = await readFile(resolved);
  if (bytes.length !== artifact.size || sha256(bytes) !== artifact.sha256) {
    throw new Error("TRANSCRIPT_ARTIFACT_MISMATCH");
  }
  return { path: resolved, bytes };
}

function eventCallId(event) {
  return typeof event?.tool?.call_id === "string" ? event.tool.call_id : null;
}

function eventPaths(event) {
  if (!Array.isArray(event?.path_mappings)) return [];
  return event.path_mappings.flatMap((mapping) => (
    mapping && typeof mapping === "object"
      ? [mapping.raw, mapping.normalized].filter((value) => typeof value === "string")
      : []
  ));
}

function searchableText(event) {
  return JSON.stringify({
    role: event?.role ?? null,
    content: event?.content ?? null,
    tool: event?.tool ?? null,
    message: event?.message ?? null,
  }).toLowerCase();
}

function matchEvent(event, filters) {
  const matchedFields = [];
  if (filters.fromSequence !== null) {
    if (event.sequence < filters.fromSequence) return null;
    matchedFields.push("sequence");
  }
  if (filters.toSequence !== null) {
    if (event.sequence > filters.toSequence) return null;
    if (!matchedFields.includes("sequence")) matchedFields.push("sequence");
  }
  if (filters.callId) {
    if (eventCallId(event) !== filters.callId) return null;
    matchedFields.push("call_id");
  }
  if (filters.path) {
    if (!eventPaths(event).includes(filters.path)) return null;
    matchedFields.push("path");
  }
  if (filters.text) {
    if (!searchableText(event).includes(filters.text.toLowerCase())) return null;
    matchedFields.push("text");
  }
  return matchedFields;
}

export async function queryTrace(options) {
  const indexPath = resolve(options.traceIndex);
  const index = JSON.parse(await readFile(indexPath, "utf8"));
  const expectedVersion = new Map([
    ["urn:wildclawbench:schema:general-e2e:trace-index:v1", 1],
    ["urn:wildclawbench:schema:general-e2e:trace-index:v2", 2],
  ]).get(index?.schema_id);
  if (!expectedVersion || index.schema_version !== expectedVersion) {
    throw new Error("TRACE_INDEX_UNSUPPORTED");
  }
  const transcript = await readSafeArtifact(indexPath, index.transcript);
  const lines = transcript.bytes.toString("utf8").split(/\r?\n/u).filter((line) => line.trim());
  const events = lines.map((line, offset) => {
    try {
      return JSON.parse(line);
    } catch (error) {
      throw new Error(`TRANSCRIPT_JSON_INVALID: line=${offset + 1}: ${error.message}`);
    }
  });
  if (events.length !== index.transcript.event_count) throw new Error("TRANSCRIPT_EVENT_COUNT_MISMATCH");
  const filters = {
    fromSequence: options.fromSequence ?? null,
    toSequence: options.toSequence ?? null,
    callId: options.callId || null,
    path: options.path || null,
    text: options.text || null,
  };
  const matches = [];
  events.forEach((event, offset) => {
    const matchedFields = matchEvent(event, filters);
    if (matchedFields === null) return;
    matches.push({
      sequence: event.sequence,
      event_id: event.event_id,
      type: event.type,
      role: event.role ?? null,
      call_id: eventCallId(event),
      tool_name: event?.tool?.name ?? null,
      matched_fields: matchedFields,
      location: {
        transcript_line: offset + 1,
        raw_ref: event?.source?.raw_ref ?? null,
      },
      event,
    });
  });
  const page = options.page || 1;
  const pageSize = options.pageSize || 50;
  const totalMatches = matches.length;
  const totalPages = totalMatches === 0 ? 0 : Math.ceil(totalMatches / pageSize);
  const start = (page - 1) * pageSize;
  const pageMatches = start >= totalMatches ? [] : matches.slice(start, start + pageSize);
  return {
    schema_version: "wildclawbench.general-e2e-trace-query/v1",
    status: "PASS",
    source: {
      trace_index: indexPath,
      transcript: transcript.path,
      transcript_sha256: index.transcript.sha256,
      event_count: events.length,
      completeness: index.completeness,
    },
    filters,
    pagination: {
      page,
      page_size: pageSize,
      total_matches: totalMatches,
      total_pages: totalPages,
      has_previous: page > 1 && totalMatches > 0,
      has_next: page < totalPages,
    },
    matches: pageMatches,
  };
}

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  if (parsed.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  process.stdout.write(`${JSON.stringify(await queryTrace(parsed), null, 2)}\n`);
}

const isEntrypoint = process.argv[1]
  && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
