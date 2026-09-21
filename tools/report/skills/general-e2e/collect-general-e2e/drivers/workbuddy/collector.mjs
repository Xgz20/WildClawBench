#!/usr/bin/env node

import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import {
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { discoverJsonl, parseBoundJsonl, applyJsonlMetrics, withoutModelResponseCount } from "../../vendor/e2e-shared/workbuddy-jsonl-metrics/index.mjs";

import {
  collectWorkBuddyGeneralEvidence,
  loadWorkBuddyRuntimeBinding,
  loadWorkBuddyConversation,
  normalizeWorkBuddyConversation,
} from "../../vendor/e2e-shared/workbuddy-evidence/native-history.mjs";

const JOURNAL_SCHEMA = "wildclawbench.general-e2e-workbuddy-dispatch-journal/v1";
const STATE_SCHEMA = "wildclawbench.general-e2e-execution-state/v1";
const TERMINAL_PHASES = new Set(["COMPLETED", "FAILED"]);
const MAX_INPUT_BYTES = 64 * 1024 * 1024;

function usage() {
  return `WorkBuddy General E2E 原生证据采集器

用法：
  node collector.mjs \\
    --unit-root /absolute/unit-root \\
    --journal-file /absolute/unit-root/.general-e2e/execution/<task>/workbuddy/dispatch-journal.json \\
    --state-file /absolute/unit-root/.general-e2e/execution/<task>/workbuddy/execution-state.json \\
    --history-root /absolute/WorkBuddyExtension/Data (legacy history；runtime API 证据可省略) \\
    --output-root /absolute/unit-root/.general-e2e/collection/<attempt>

只读取已终态的 WorkBuddy journal、execution state 和原生 history，输出 CB-B
trace-index v2 与 resource-metrics v1；不会启动、停止、重启或通过 CDP 操作客户端。
输出之后由通用 finalizer 使用 WorkBuddy cleanup hook 完成正式收口。`;
}

function requireString(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`WORKBUDDY_COLLECTOR_FIELD_MISSING: ${label}`);
  return value;
}

function isWithin(root, candidate) {
  const value = relative(root, candidate);
  return value === "" || (value !== ".." && !value.startsWith(`..${sep}`) && !isAbsolute(value));
}

function sameIdentity(left, right) {
  return ["batch_id", "unit_id", "task_id", "attempt_id"].every((field) => (
    typeof left?.[field] === "string" && left[field] === right?.[field]
  ));
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function jsonBytes(value) {
  return Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function artifact(path, bytes, extra = {}) {
  return { path, sha256: sha256(bytes), size: bytes.length, ...extra };
}

async function assertRegularFile(path, label) {
  const absolute = resolve(path);
  const info = await lstat(absolute);
  if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_INPUT_BYTES) {
    throw new Error(`WORKBUDDY_COLLECTOR_INPUT_INVALID: ${label}`);
  }
  const bytes = await readFile(absolute);
  if (bytes.length > MAX_INPUT_BYTES) throw new Error(`WORKBUDDY_COLLECTOR_INPUT_OVERSIZED: ${label}`);
  return { absolute, bytes, sha256: sha256(bytes), size: bytes.length };
}

async function readJson(path, label) {
  const source = await assertRegularFile(path, label);
  try {
    return { ...source, value: JSON.parse(source.bytes.toString("utf8")) };
  } catch (error) {
    throw new Error(`WORKBUDDY_COLLECTOR_JSON_INVALID: ${label}: ${error.message}`);
  }
}

async function ensureNewOutput(unitRoot, outputRoot) {
  const absolute = resolve(outputRoot);
  if (!isWithin(unitRoot, absolute) || absolute === unitRoot) {
    throw new Error("WORKBUDDY_COLLECTOR_OUTPUT_OUTSIDE_UNIT");
  }
  await mkdir(dirname(absolute), { recursive: true });
  try {
    await lstat(absolute);
    throw new Error("WORKBUDDY_COLLECTOR_OUTPUT_EXISTS");
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  return absolute;
}

function parseArgs(argv) {
  const result = {
    unitRoot: "",
    journalFile: "",
    stateFile: "",
    historyRoot: "",
    outputRoot: "",
    redacted: false,
    help: false,
  };
  const valued = new Map([
    ["--unit-root", "unitRoot"],
    ["--journal-file", "journalFile"],
    ["--state-file", "stateFile"],
    ["--history-root", "historyRoot"],
    ["--native-projects-root", "nativeProjectsRoot"],
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
    for (const field of ["unitRoot", "journalFile", "stateFile", "outputRoot"]) {
      if (!result[field]) throw new Error(`缺少参数：${field}`);
    }
  }
  return result;
}

async function assertFormalState(journal, state, unitRoot) {
  if (journal?.schema_version !== JOURNAL_SCHEMA) {
    throw new Error("WORKBUDDY_COLLECTOR_JOURNAL_SCHEMA_UNSUPPORTED");
  }
  if (state?.schema_version !== STATE_SCHEMA) {
    throw new Error("WORKBUDDY_COLLECTOR_STATE_SCHEMA_UNSUPPORTED");
  }
  if (!TERMINAL_PHASES.has(journal.phase) || !TERMINAL_PHASES.has(state.phase) || journal.phase !== state.phase) {
    throw new Error(`WORKBUDDY_COLLECTOR_NOT_TERMINAL: journal=${journal?.phase}; state=${state?.phase}`);
  }
  if (!sameIdentity(journal.identity, state.identity)) {
    throw new Error("WORKBUDDY_COLLECTOR_IDENTITY_MISMATCH");
  }
  if (journal.dataset?.id !== state.dataset?.id || journal.dataset?.digest !== state.dataset?.digest) {
    throw new Error("WORKBUDDY_COLLECTOR_DATASET_MISMATCH");
  }
  if (journal.prompt?.sha256 !== state.prompt?.sha256
      || journal.prompt?.send_status !== state.prompt?.send_status) {
    throw new Error("WORKBUDDY_COLLECTOR_PROMPT_MISMATCH");
  }
  if (journal.send?.dispatch_attempt_count !== state.send?.dispatch_attempt_count) {
    throw new Error("WORKBUDDY_COLLECTOR_SEND_MISMATCH");
  }
  const journalWorkspace = await realpath(resolve(journal.candidate_workspace || ""));
  const stateWorkspace = await realpath(resolve(state.candidate_workspace || ""));
  if (journalWorkspace !== stateWorkspace) {
    throw new Error("WORKBUDDY_COLLECTOR_WORKSPACE_MISMATCH");
  }
  const taskRoot = await realpath(resolve(state.task_root || ""));
  const candidateWorkspace = await realpath(resolve(state.candidate_workspace || ""));
  if (!isWithin(unitRoot, taskRoot) || !isWithin(unitRoot, candidateWorkspace)) {
    throw new Error("WORKBUDDY_COLLECTOR_STATE_PATH_OUTSIDE_UNIT");
  }
  if (state.driver?.harness !== "workbuddy" || !/^macos(?:-[a-z0-9-]+)?$/u.test(state.driver?.platform || "")) {
    throw new Error("WORKBUDDY_COLLECTOR_DRIVER_MISMATCH");
  }
  if (state.session?.verified !== true || state.session?.thread_id !== null
      || !state.session?.session_id || !state.session?.turn_id || !state.session?.cwd) {
    throw new Error("WORKBUDDY_COLLECTOR_NATIVE_BINDING_UNVERIFIED");
  }
  const sessionCwd = await realpath(resolve(state.session.cwd));
  if (sessionCwd !== candidateWorkspace) {
    throw new Error("WORKBUDDY_COLLECTOR_SESSION_WORKSPACE_MISMATCH");
  }
  if (journal.native?.conversation_id !== state.session.session_id
      || journal.native?.request_id !== state.session.turn_id
      || await realpath(resolve(journal.native?.cwd || "")) !== sessionCwd) {
    throw new Error("WORKBUDDY_COLLECTOR_JOURNAL_NATIVE_BINDING_MISMATCH");
  }
  if (state.prompt?.send_status !== "sent" || state.send?.dispatch_attempt_count !== 1) {
    throw new Error("WORKBUDDY_COLLECTOR_SEND_NOT_RECONCILED");
  }
  if (!Array.isArray(state.session.binding_evidence) || state.session.binding_evidence.length === 0) {
    throw new Error("WORKBUDDY_COLLECTOR_BINDING_EVIDENCE_MISSING");
  }
  const mapping = state.extensions?.workbuddy?.identity_mapping;
  const runtimeSource = mapping?.binding_source === "workbuddy-runtime-api";
  const expectedMapping = runtimeSource ? {
    turn_id_source: "runtime.conversations.current.requestEntries().requests[].id",
    session_id_source: "runtime.conversations.current.info.id",
    cwd_source: "runtime.conversations.current.info.space.cwd",
    terminal_status_source: "runtime.conversations.current.info.state/lifecycle + requestEntries().requests[].state + message.state",
  } : {
    turn_id_source: "conversation-index.requests[].id",
    session_id_source: "codebuddy-sessions.vscdb.session:*.conversationId",
    cwd_source: "codebuddy-sessions.vscdb.session:*.cwd",
    terminal_status_source: "codebuddy-sessions.vscdb.session:*.status + conversation-index.requests[].state",
  };
  for (const [field, expected] of Object.entries(expectedMapping)) {
    if (mapping?.[field] !== expected) throw new Error(`WORKBUDDY_COLLECTOR_NATIVE_SOURCE_UNVERIFIED: ${field}`);
  }
}

async function loadBindingSources(unitRoot, state) {
  return Promise.all(state.session.binding_evidence.map(async (item, index) => {
    const relativePath = requireString(item.path, `binding_evidence[${index}].path`);
    if (relativePath.includes("\\") || relativePath.split("/").some((part) => !part || part === "." || part === "..")) {
      throw new Error(`WORKBUDDY_COLLECTOR_BINDING_PATH_INVALID: ${relativePath}`);
    }
    const sourcePath = resolve(unitRoot, relativePath);
    if (!isWithin(unitRoot, sourcePath)) throw new Error("WORKBUDDY_COLLECTOR_BINDING_OUTSIDE_UNIT");
    const source = await assertRegularFile(sourcePath, `binding_evidence[${index}]`);
    if (source.sha256 !== item.sha256 || source.size !== item.size) {
      throw new Error(`WORKBUDDY_COLLECTOR_BINDING_DIGEST_MISMATCH: ${relativePath}`);
    }
    let value = null;
    try {
      value = JSON.parse(source.bytes.toString("utf8"));
    } catch {
      // The digest check above remains authoritative; native binding evidence
      // is opaque JSON to the legacy collector.
    }
    return {
      source: { path: source.absolute, sha256: source.sha256, size: source.size },
      target: `bindings/${String(index + 1).padStart(2, "0")}-${basename(relativePath)}`,
      value,
    };
  }));
}

function rebaseResourceMetrics(resource, stateSource, evidence) {
  const traceSources = [
    evidence.trace_index_artifact,
    ...evidence.raw_trace,
    ...evidence.binding_evidence,
  ].map((item) => ({ ...item, path: `trace/${item.path}` }));
  const sources = [
    artifact("execution/automation-state.json", stateSource.bytes),
    ...traceSources,
  ];
  const metricSources = Object.fromEntries(Object.entries(resource.collection.metric_sources || {}).map(([field, refs]) => [
    field,
    refs.map((ref) => ref.startsWith("trace/") ? ref : `trace/${ref}`),
  ]));
  return {
    ...resource,
    collection: {
      ...resource.collection,
      sources,
      metric_sources: metricSources,
    },
  };
}

export async function collectWorkBuddyEvidence(options) {
  const unitRootInput = resolve(requireString(options?.unitRoot, "unitRoot"));
  const unitRoot = await realpath(unitRootInput);
  const journalSource = await readJson(requireString(options?.journalFile, "journalFile"), "journal");
  const stateSource = await readJson(requireString(options?.stateFile, "stateFile"), "execution state");
  const requestedOutputRoot = resolve(requireString(options?.outputRoot, "outputRoot"));
  const outputRelative = relative(unitRootInput, requestedOutputRoot);
  if (!outputRelative || outputRelative === ".." || outputRelative.startsWith(`..${sep}`) || isAbsolute(outputRelative)) {
    throw new Error("WORKBUDDY_COLLECTOR_OUTPUT_OUTSIDE_UNIT");
  }
  const outputRoot = await ensureNewOutput(unitRoot, join(unitRoot, outputRelative));
  const journal = journalSource.value;
  const state = stateSource.value;
  await assertFormalState(journal, state, unitRoot);
  const bindingSources = await loadBindingSources(unitRoot, state);
  const runtimeEvidence = bindingSources.find((item) => (
    item.value?.source_kind === "workbuddy-runtime-api"
      && item.value?.runtime_snapshot
  ));
  let loaded;
  if (runtimeEvidence) {
    loaded = loadWorkBuddyRuntimeBinding({
      value: runtimeEvidence.value,
      sourceArtifact: runtimeEvidence.source,
    });
  } else {
    const historyRoot = await realpath(resolve(requireString(options?.historyRoot, "historyRoot")));
    loaded = await loadWorkBuddyConversation({
      dataRoot: historyRoot,
      workspace: state.session.cwd,
      conversationId: state.session.session_id,
      requestId: state.session.turn_id,
    });
  }
  if (resolve(loaded.workspace) !== resolve(state.session.cwd)
      || loaded.conversation_id !== state.session.session_id
      || loaded.request_id !== state.session.turn_id) {
    throw new Error("WORKBUDDY_COLLECTOR_NATIVE_BINDING_MISMATCH");
  }
  const normalized = normalizeWorkBuddyConversation(loaded, {
    identity: state.identity,
    redacted: options.redacted === true,
  });
  if (normalized.prompt.sha256 !== state.prompt.sha256) {
    throw new Error("WORKBUDDY_COLLECTOR_PROMPT_DIGEST_MISMATCH");
  }
  const stage = await mkdtemp(join(dirname(outputRoot), ".workbuddy-collector-stage-"));
  try {
    await mkdir(join(stage, "execution"), { recursive: true });
    const responseBytes = Buffer.from(normalized.final_response, "utf8");
    await writeFile(join(stage, "final-response.md"), responseBytes, { flag: "wx", mode: 0o600 });
    const collectedState = {
      ...state,
      extensions: {
        ...state.extensions,
        evidence: {
          ...state.extensions?.evidence,
          final_response_path: relative(unitRoot, join(outputRoot, "final-response.md")).split(sep).join("/"),
          final_response_sha256: sha256(responseBytes),
        },
      },
    };
    const collectedStateBytes = jsonBytes(collectedState);
    await writeFile(join(stage, "execution", "automation-state.json"), collectedStateBytes, { flag: "wx", mode: 0o600 });
    const evidence = await collectWorkBuddyGeneralEvidence({
      identity: state.identity,
      loaded,
      normalized,
      outputRoot: join(stage, "trace"),
      bindingSources,
      lifecycleGeneration: null,
      writeResourceMetrics: false,
      collectedAt: options.collectedAt || new Date().toISOString(),
    });
    let resource = rebaseResourceMetrics(evidence.resource_metrics, { bytes: collectedStateBytes }, evidence);
    resource = withoutModelResponseCount(resource);
    if (runtimeEvidence) {
      const native = await discoverJsonl(options.nativeProjectsRoot || join(homedir(), ".workbuddy/projects"), state.session.session_id);
      if (native) {
        const parsed = parseBoundJsonl(native.bytes, {
          snapshot: runtimeEvidence.value.runtime_snapshot, session: state.session, promptSha256: state.prompt.sha256,
        });
        const name = "raw/workbuddy-session.jsonl";
        await writeFile(join(stage, "trace", name), native.bytes, { flag: "wx", mode: 0o600 });
        evidence.trace_index.raw_trace.push(artifact(name, native.bytes));
        const indexBytes = jsonBytes(evidence.trace_index);
        await writeFile(join(stage, "trace/trace-index.json"), indexBytes);
        evidence.trace_index_artifact = artifact("trace-index.json", indexBytes);
        resource = rebaseResourceMetrics(resource, { bytes: collectedStateBytes }, evidence);
        resource = applyJsonlMetrics(resource, parsed, artifact(`trace/${name}`, native.bytes));
      }
    }
    await writeFile(join(stage, "resource-metrics.json"), jsonBytes(resource), { flag: "wx", mode: 0o600 });
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
  };
}

async function main(argv = process.argv.slice(2)) {
  const parsed = parseArgs(argv);
  if (parsed.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  process.stdout.write(`${JSON.stringify(await collectWorkBuddyEvidence(parsed), null, 2)}\n`);
}

if (process.argv[1] && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url))) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
