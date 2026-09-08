import { createHash, randomUUID } from "node:crypto";
import {
  access,
  lstat,
  mkdir,
  readFile,
  readdir,
  readlink,
  realpath,
  rename,
  stat,
  writeFile,
} from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";

export const AUTOMATION_SCHEMA = "wildclawbench.web-e2e-automation-state/v1";
export const EXECUTION_SCHEMA = "wildclawbench.web-e2e-execution/v1";
export const DRIVER_VERSION = "1.7.0";
export const DEFAULT_APP_PATH = "/Applications/WorkBuddy.app";
export const DEFAULT_BUNDLE_ID = "com.tencent.workbuddy.mac";
export const DEFAULT_ENDPOINT = "http://127.0.0.1:9229";
export const DEFAULT_MODEL = "";
export const DEFAULT_PERMISSION_MODE = "current";
export const PERMISSION_MODES = new Set(["current", "full-access"]);
export const TERMINAL_PHASES = new Set(["SUCCEEDED", "INFRA_FAILED", "TIMEOUT"]);
export const RESUMABLE_PHASES = new Set([
  "READY_TO_SEND",
  "PROMPT_SENT",
  "RUNNING",
  "NEEDS_ATTENTION",
]);
const EXCLUDED_TREE_DIRS = new Set([".git", ".cache", ".vite", "node_modules"]);

function numberOption(value, name, { minimum = 0, integer = false } = {}) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= minimum || (integer && !Number.isInteger(parsed))) {
    throw new Error(`${name} 必须是大于 ${minimum} 的${integer ? "整数" : "数字"}`);
  }
  return parsed;
}

export function parseArgs(argv) {
  const values = {
    workspace: "",
    promptFile: "",
    model: DEFAULT_MODEL,
    permissionMode: DEFAULT_PERMISSION_MODE,
    modelId: "",
    modelDisplayName: "",
    batchId: "",
    taskId: "",
    endpoint: DEFAULT_ENDPOINT,
    appPath: DEFAULT_APP_PATH,
    outputDir: "",
    stateFile: "",
    executionRecord: "",
    sessionDb: join(homedir(), "Library", "Application Support", "WorkBuddy", "codebuddy-sessions.vscdb"),
    timeoutSeconds: 30,
    runTimeoutSeconds: 3600,
    pollIntervalSeconds: 2,
    postCancelQuiescenceSeconds: 5,
    restartApp: false,
    resume: false,
    retryPreSendFailure: false,
    detachAfterSubmit: false,
    observeOnce: false,
    quiet: false,
    dryRun: false,
    probe: false,
    help: false,
  };

  const needsValue = new Map([
    ["--workspace", "workspace"],
    ["--prompt-file", "promptFile"],
    ["--model", "model"],
    ["--permission-mode", "permissionMode"],
    ["--model-id", "modelId"],
    ["--model-display-name", "modelDisplayName"],
    ["--batch-id", "batchId"],
    ["--task-id", "taskId"],
    ["--endpoint", "endpoint"],
    ["--app-path", "appPath"],
    ["--output-dir", "outputDir"],
    ["--state-file", "stateFile"],
    ["--execution-record", "executionRecord"],
    ["--session-db", "sessionDb"],
    ["--timeout-seconds", "timeoutSeconds"],
    ["--run-timeout-seconds", "runTimeoutSeconds"],
    ["--poll-interval-seconds", "pollIntervalSeconds"],
    ["--post-cancel-quiescence-seconds", "postCancelQuiescenceSeconds"],
  ]);

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else if (arg === "--restart-app") values.restartApp = true;
    else if (arg === "--resume") values.resume = true;
    else if (arg === "--retry-pre-send-failure") values.retryPreSendFailure = true;
    else if (arg === "--detach-after-submit") values.detachAfterSubmit = true;
    else if (arg === "--observe-once") values.observeOnce = true;
    else if (arg === "--quiet") values.quiet = true;
    else if (arg === "--dry-run") values.dryRun = true;
    else if (arg === "--probe") values.probe = true;
    else {
      const key = needsValue.get(arg);
      if (!key) throw new Error(`未知参数：${arg}`);
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少参数值`);
      values[key] = value;
      index += 1;
    }
  }

  values.timeoutSeconds = numberOption(values.timeoutSeconds, "timeoutSeconds");
  values.runTimeoutSeconds = numberOption(values.runTimeoutSeconds, "runTimeoutSeconds");
  values.pollIntervalSeconds = numberOption(values.pollIntervalSeconds, "pollIntervalSeconds");
  values.postCancelQuiescenceSeconds = numberOption(values.postCancelQuiescenceSeconds, "postCancelQuiescenceSeconds");
  if (!PERMISSION_MODES.has(values.permissionMode)) {
    throw new Error("--permission-mode 仅支持 current 或 full-access");
  }
  if (values.retryPreSendFailure && !values.resume) {
    throw new Error("--retry-pre-send-failure 必须与 --resume 一起使用");
  }
  if (values.observeOnce && !values.resume) {
    throw new Error("--observe-once 必须与 --resume 一起使用");
  }
  if (values.detachAfterSubmit && values.observeOnce) {
    throw new Error("--detach-after-submit 与 --observe-once 不能同时使用");
  }
  return values;
}

function isInside(parent, child) {
  const rel = relative(parent, child);
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
}

async function canonicalizePotentialPath(path) {
  let current = resolve(path);
  const suffix = [];
  for (;;) {
    try {
      return join(await realpath(current), ...suffix.reverse());
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
      const parent = dirname(current);
      if (parent === current) throw error;
      suffix.push(basename(current));
      current = parent;
    }
  }
}

export async function resolveConfig(parsed) {
  const endpoint = new URL(parsed.endpoint);
  if (!new Set(["127.0.0.1", "localhost", "::1"]).has(endpoint.hostname)) {
    throw new Error("--endpoint 仅允许连接本机地址");
  }
  const appPath = await realpath(resolve(parsed.appPath));
  await access(join(appPath, "Contents", "Resources", "app.asar"));
  const sessionDb = resolve(parsed.sessionDb);

  if (parsed.probe) {
    return { ...parsed, appPath, endpoint: endpoint.origin, sessionDb };
  }
  if (!parsed.workspace) throw new Error("必须指定 --workspace，或使用 --probe");
  const workspace = await realpath(resolve(parsed.workspace));
  if (!(await stat(workspace)).isDirectory()) throw new Error(`任务工作空间不是目录：${workspace}`);

  const promptFile = await realpath(parsed.promptFile ? resolve(parsed.promptFile) : join(workspace, "PROMPT.md"));
  if (!isInside(workspace, promptFile)) throw new Error("Prompt 文件必须位于当前单题目录内");
  const prompt = await readFile(promptFile, "utf8");
  if (!prompt.trim()) throw new Error(`Prompt 文件为空：${promptFile}`);
  const candidateWorkspace = await realpath(join(workspace, "workspace"));
  if (!(await stat(candidateWorkspace)).isDirectory()) {
    throw new Error(`候选产物目录不是目录：${candidateWorkspace}`);
  }

  const outputDir = await canonicalizePotentialPath(parsed.outputDir || join(dirname(workspace), ".execute-web-e2e", basename(workspace)));
  if (isInside(workspace, outputDir)) {
    throw new Error("自动化输出目录必须位于所选单题目录之外，避免污染候选上下文");
  }
  const stateFile = await canonicalizePotentialPath(parsed.stateFile || join(outputDir, "automation_state.json"));
  if (!isInside(outputDir, stateFile)) throw new Error("状态文件必须位于自动化输出目录内");
  const executionRecord = await canonicalizePotentialPath(parsed.executionRecord || join(workspace, "execution_record.json"));
  if (!isInside(workspace, executionRecord)) throw new Error("execution_record.json 必须位于当前单题目录内");

  return {
    ...parsed,
    workspace,
    candidateWorkspace,
    promptFile,
    prompt,
    promptSha256: sha256Text(prompt),
    promptBytes: Buffer.byteLength(prompt, "utf8"),
    appPath,
    endpoint: endpoint.origin,
    outputDir,
    stateFile,
    resultFile: join(outputDir, "result.json"),
    executionRecord,
    sessionDb,
  };
}

export function sha256Text(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function sha256File(path) {
  const content = await readFile(path);
  return createHash("sha256").update(content).digest("hex");
}

function compareUnicodeCodePoints(left, right) {
  const leftPoints = Array.from(left, (character) => character.codePointAt(0));
  const rightPoints = Array.from(right, (character) => character.codePointAt(0));
  const length = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < length; index += 1) {
    if (leftPoints[index] !== rightPoints[index]) return leftPoints[index] - rightPoints[index];
  }
  return leftPoints.length - rightPoints.length;
}

export async function atomicWriteJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temporary, path);
}

export async function readJsonIfExists(path) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

export async function snapshotTree(root, { maximumFiles = 20000 } = {}) {
  const rootInfo = await lstat(root);
  if (rootInfo.isSymbolicLink() || !rootInfo.isDirectory()) {
    throw new Error(`候选 workspace 缺失或为符号链接：${root}`);
  }
  const entries = [];
  const excludedRuntimeDirectories = [];
  async function walk(current, prefix = "") {
    const children = await readdir(current, { withFileTypes: true });
    children.sort((left, right) => compareUnicodeCodePoints(left.name, right.name));
    for (const child of children) {
      const rel = prefix ? `${prefix}/${child.name}` : child.name;
      if (child.isDirectory()) {
        if (EXCLUDED_TREE_DIRS.has(child.name)) excludedRuntimeDirectories.push(rel);
        else await walk(join(current, child.name), rel);
        continue;
      }
      if (entries.length >= maximumFiles) throw new Error(`候选目录文件数超过上限 ${maximumFiles}`);
      const path = join(current, child.name);
      const info = await lstat(path);
      if (info.isSymbolicLink()) {
        const target = await readlink(path);
        entries.push({ path: rel, type: "symlink", target, sha256: sha256Text(target), size: target.length });
      } else if (info.isFile()) {
        entries.push({ path: rel, type: "file", size: info.size, sha256: await sha256File(path) });
      }
    }
  }
  await walk(root);
  const digest = createHash("sha256");
  for (const entry of entries) {
    digest.update(entry.path);
    digest.update("\0");
    digest.update(entry.type);
    digest.update("\0");
    digest.update(entry.sha256);
    digest.update("\n");
  }
  return {
    root,
    sha256: digest.digest("hex"),
    file_count: entries.length,
    total_bytes: entries.reduce((sum, entry) => sum + entry.size, 0),
    excluded_directories: [...EXCLUDED_TREE_DIRS].sort(),
    excluded_runtime_directories: excludedRuntimeDirectories.sort(compareUnicodeCodePoints),
    entries,
  };
}

export function diffSnapshots(before, after) {
  const oldEntries = new Map(before.entries.map((entry) => [entry.path, entry]));
  const newEntries = new Map(after.entries.map((entry) => [entry.path, entry]));
  const added = [];
  const modified = [];
  const removed = [];
  for (const [path, entry] of newEntries) {
    const previous = oldEntries.get(path);
    if (!previous) added.push(path);
    else if (previous.sha256 !== entry.sha256 || previous.type !== entry.type) modified.push(path);
  }
  for (const path of oldEntries.keys()) if (!newEntries.has(path)) removed.push(path);
  return { added: added.sort(), modified: modified.sort(), removed: removed.sort() };
}

export function classifySessionStatus(rawStatus) {
  const status = String(rawStatus || "").trim();
  const normalized = status.toLowerCase().replace(/[\s_-]+/g, "");
  if (new Set(["completed", "complete", "succeeded", "success", "finished", "done"]).has(normalized)) {
    return { kind: "success", status };
  }
  if (new Set(["failed", "failure", "error", "errored", "cancelled", "canceled", "aborted", "terminated"]).has(normalized)) {
    return { kind: "failure", status };
  }
  if (new Set(["running", "inprogress", "pending", "active", "streaming", "processing", "executing", "started", "created", "initializing", "queued"]).has(normalized)) {
    return { kind: "running", status };
  }
  return { kind: status ? "unknown" : "missing", status };
}

export function classifyDomStatus({ running = false, agentText = "", rawStatus = "" } = {}) {
  const text = String(agentText || "").trim();
  const statusHeader = text.slice(0, 240);
  if (running || /(?:^|\n)\s*(?:思考中|处理中|正在执行|正在连接(?:\s*MCP\s*服务)?[.…]*|等待模型响应[.…|]*|Running|Processing|Waiting for model)\s*$/im.test(statusHeader)) {
    return { kind: "running", status: "visible-running" };
  }
  if (/(?:^|\n)\s*当前服务异常，请稍后再试或新建任务、切换模型后重试[。！!]?\s*(?=\n|$)/i.test(text)) {
    return { kind: "failure", status: "visible-service-error" };
  }
  const structured = classifySessionStatus(rawStatus);
  if (structured.kind === "success") return { kind: "success", status: `dom-data-status:${structured.status}` };
  if (structured.kind === "failure") return { kind: "failure", status: `dom-data-status:${structured.status}` };
  if (structured.kind === "running") return { kind: "running", status: `dom-data-status:${structured.status}` };
  if (structured.kind === "unknown") return { kind: "unknown", status: `dom-data-status:${structured.status}` };
  if (/(?:^|\n)\s*(?:已完成|Completed)(?:\s|\d|$)/i.test(text)) {
    return { kind: "success", status: "visible-completed" };
  }
  if (/(?:^|\n)\s*(?:已失败|执行失败|发生错误|已取消|已中断|Failed|Cancelled|Canceled|Error)(?:\s|：|:|$)/i.test(text)) {
    return { kind: "failure", status: "visible-failure" };
  }
  return { kind: text ? "unknown" : "missing", status: text ? "visible-unknown" : "" };
}

export function isSubstantiveFinalResponse(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  return !/^(?:正在连接(?:\s*MCP\s*服务)?|等待模型响应|思考中|处理中|正在执行)[.…|]*$/i.test(text);
}

export function classifyApprovalCommand(command, candidateWorkspace) {
  const value = String(command || "").trim();
  const root = resolve(candidateWorkspace);
  const file = join(root, ".DS_Store");
  const candidates = new Set([
    `rm -f ${file} && find ${root} -name '.DS_Store' -delete`,
    `rm -f '${file}' && find '${root}' -name '.DS_Store' -delete`,
    `rm -f "${file}" && find "${root}" -name '.DS_Store' -delete`,
  ]);
  if (candidates.has(value)) {
    return { allow: true, rule: "candidate-workspace-ds-store-cleanup" };
  }
  return { allow: false, rule: null };
}

export function chooseSession(sessions, workspace, { conversationId = "", notBeforeMs = 0 } = {}) {
  const exact = sessions.filter((session) => session.cwd && resolve(String(session.cwd)) === resolve(workspace));
  if (conversationId) return exact.find((session) => session.conversationId === conversationId) || null;
  return exact
    .filter((session) => Number(session.updatedAt || session.createdAt || 0) >= notBeforeMs)
    .sort((left, right) => Number(right.updatedAt || 0) - Number(left.updatedAt || 0))[0] || null;
}

export function chooseAttemptSession(sessions, state, workspace) {
  if (state.session?.conversation_id) {
    return chooseSession(sessions, workspace, { conversationId: state.session.conversation_id });
  }
  const exact = sessions.filter((session) => session.cwd && resolve(String(session.cwd)) === resolve(workspace));
  const baseline = new Map((state.session?.baseline || []).map((item) => [item.conversation_id, Number(item.updated_at_ms || 0)]));
  const sentAt = state.timing?.sent_at ? Date.parse(state.timing.sent_at) : 0;
  const preparedAt = Date.parse(state.timing?.prepared_at || 0);
  return exact
    .filter((session) => {
      const updatedAt = Number(session.updatedAt || session.createdAt || 0);
      if (sentAt) return updatedAt >= sentAt;
      if (baseline.size) {
        return !baseline.has(session.conversationId) || updatedAt > baseline.get(session.conversationId);
      }
      return updatedAt >= preparedAt;
    })
    .sort((left, right) => Number(right.updatedAt || 0) - Number(left.updatedAt || 0))[0] || null;
}

export async function resolveExecutionIdentity(config) {
  const existing = await readJsonIfExists(config.executionRecord);
  const manifestPath = join(config.workspace, "..", "..", "..", "manifest.json");
  const manifest = await readJsonIfExists(manifestPath);
  let fromManifest = null;
  if (manifest) {
    const expectedRoot = await realpath(dirname(manifestPath));
    const matches = [];
    for (const task of manifest.tasks || []) {
      if (!task.execution_dir) continue;
      const target = await realpath(join(expectedRoot, task.execution_dir)).catch(() => null);
      if (target === config.workspace) matches.push(task);
    }
    if (matches.length !== 1) throw new Error("manifest.json 无法按 execution_dir 唯一匹配当前单题目录");
    fromManifest = {
      batchId: String(manifest.batch_id || ""),
      taskId: String(matches[0].task_id || ""),
      harness: manifest.harness || {},
      model: manifest.model || {},
    };
  }

  const identity = existing ? {
    batchId: String(existing.batch_id || ""),
    taskId: String(existing.task_id || ""),
    harness: existing.harness || {},
    model: existing.model || {},
  } : fromManifest ? {
    ...fromManifest,
    model: {
      id: config.modelId || fromManifest.model?.id || "",
      display_name: config.modelDisplayName || fromManifest.model?.display_name || config.modelId || "",
    },
  } : {
    batchId: config.batchId,
    taskId: config.taskId,
    harness: { id: "workbuddy", display_name: "WorkBuddy", version: "" },
    model: { id: config.modelId, display_name: config.modelDisplayName || config.modelId },
  };

  if (!identity.batchId || !identity.taskId) {
    throw new Error("缺少执行身份：需要有效 manifest/execution_record，或显式传入 --batch-id 和 --task-id");
  }
  if (identity.harness?.id !== "workbuddy") throw new Error(`当前 Driver 不能执行 Harness：${identity.harness?.id || "未声明"}`);
  if (fromManifest && (identity.batchId !== fromManifest.batchId || identity.taskId !== fromManifest.taskId || identity.harness?.id !== fromManifest.harness?.id)) {
    throw new Error("execution_record.json 与 manifest.json 的批次、任务或 Harness 身份不一致");
  }
  if (config.batchId && config.batchId !== identity.batchId) throw new Error("--batch-id 与执行身份不一致");
  if (config.taskId && config.taskId !== identity.taskId) throw new Error("--task-id 与执行身份不一致");
  if (config.modelId && identity.model?.id && config.modelId !== identity.model.id) throw new Error("--model-id 与 execution_record.json 不一致");
  return { existing, manifestPath: manifest ? manifestPath : null, identity };
}

export function createExecutionRecord(identity) {
  return {
    schema_version: EXECUTION_SCHEMA,
    batch_id: identity.batchId,
    task_id: identity.taskId,
    model: {
      id: identity.model?.id || "",
      display_name: identity.model?.display_name || identity.model?.id || "",
    },
    harness: {
      id: "workbuddy",
      display_name: identity.harness?.display_name || "WorkBuddy",
      version: identity.harness?.version || "",
    },
    execution: { status: "pending", started_at: null, finished_at: null, duration_seconds: null, error: null },
    usage: { input_tokens: null, output_tokens: null, total_tokens: null, request_count: null, cost_usd: null },
    tools: { call_count: null, format_accuracy: null },
    artifacts: { harness_transcript: null },
  };
}

export async function updateExecutionRecord(config, identityInfo, update) {
  const record = identityInfo.existing || createExecutionRecord(identityInfo.identity);
  if (record.schema_version !== EXECUTION_SCHEMA) throw new Error(`不支持的 execution_record schema：${record.schema_version}`);
  record.harness.version = update.clientVersion || record.harness.version || "";
  const actualUiModel = String(update.modelSelection?.actual_model || "").trim();
  if (actualUiModel) {
    if (config.model && actualUiModel !== config.model) {
      throw new Error(`WorkBuddy 实际模型与请求不一致：${actualUiModel} vs ${config.model}`);
    }
    const declaredModelId = String(record.model?.id || identityInfo.identity.model?.id || "").trim();
    if (declaredModelId && declaredModelId !== actualUiModel && !config.modelId) {
      throw new Error(`execution_record.model.id 与 WorkBuddy 实际模型不一致：${declaredModelId} vs ${actualUiModel}`);
    }
    record.model = {
      id: declaredModelId || actualUiModel,
      display_name: config.modelDisplayName || actualUiModel,
    };
  }
  record.execution = { ...record.execution, ...update.execution };
  if (update.transcriptPath) record.artifacts.harness_transcript = relative(config.workspace, update.transcriptPath).split("\\").join("/");
  await atomicWriteJson(config.executionRecord, record);
  identityInfo.existing = record;
  return record;
}

export function createInitialState(config, identity, initialSnapshot) {
  const now = new Date().toISOString();
  return {
    schema_version: AUTOMATION_SCHEMA,
    driver: {
      id: "workbuddy",
      version: DRIVER_VERSION,
      control_backend: "electron-cdp+workbuddy-workspace-provider+macos-accessibility-fallback",
    },
    attempt_id: randomUUID(),
    phase: "PREPARED",
    terminal: false,
    identity: {
      batch_id: identity.batchId,
      task_id: identity.taskId,
      harness_id: identity.harness.id,
      model_id: identity.model?.id || "",
    },
    workspace: config.workspace,
    candidate_workspace: config.candidateWorkspace,
    prompt_file: config.promptFile,
    prompt_sha256: config.promptSha256,
    prompt_bytes: config.promptBytes,
    requested_ui_model: config.model || null,
    requested_permission_mode: config.permissionMode,
    client: { app_path: config.appPath, endpoint: config.endpoint, version: "", process: null, launch: null },
    session: {
      database: config.sessionDb,
      conversation_id: null,
      dom_conversation_id: null,
      dom_baseline_conversation_id: null,
      cwd: null,
      raw_status: null,
      updated_at_ms: null,
      baseline: [],
    },
    timing: { prepared_at: now, started_at: null, sent_at: null, finished_at: null, duration_seconds: null },
    runtime: {
      driver_pid: process.pid,
      driver_started_at: now,
      heartbeat_at: now,
      interruption: null,
    },
    timeout: null,
    evidence: { terminal_source: null, screenshots: [], approvals: [], final_response: null, transcript_path: null },
    artifacts: { initial: initialSnapshot, final: null, changes: null },
    error: null,
    history: [{ phase: "PREPARED", at: now }],
  };
}

export function assertStateMatches(state, config, identity) {
  if (state.schema_version !== AUTOMATION_SCHEMA) throw new Error(`不支持的自动化状态 schema：${state.schema_version}`);
  const mismatches = [];
  if (state.workspace !== config.workspace) mismatches.push("workspace");
  if (state.prompt_sha256 !== config.promptSha256) mismatches.push("prompt_sha256");
  if ((state.requested_ui_model || "") !== config.model) mismatches.push("requested_ui_model");
  if (state.requested_permission_mode && state.requested_permission_mode !== config.permissionMode) {
    mismatches.push("requested_permission_mode");
  }
  if (state.identity?.batch_id !== identity.batchId) mismatches.push("batch_id");
  if (state.identity?.task_id !== identity.taskId) mismatches.push("task_id");
  if (mismatches.length) throw new Error(`已有 automation_state 与本次调用不一致：${mismatches.join(", ")}`);
}

export function transitionState(state, phase, detail = {}) {
  const at = new Date().toISOString();
  state.phase = phase;
  state.terminal = TERMINAL_PHASES.has(phase);
  state.history.push({ phase, at, ...detail });
  return state;
}
