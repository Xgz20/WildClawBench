import { execFile as execFileCallback } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  lstat,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { homedir, hostname } from "node:os";
import { basename, dirname, isAbsolute, join, parse as parsePath, resolve, sep } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { chromium } from "playwright-core";

import {
  DEFAULT_APP_PATH,
  DEFAULT_ENDPOINT,
  classifyDomObservation,
  normalizePromptReadback,
  parseConversationId,
  parseLoopbackEndpoint,
  selectUniqueChatTarget,
  sha256Text,
  summarizePromptReadback,
  workspaceReadbackMatches,
} from "./lib.mjs";
import {
  defaultNativeRoots,
  discoverNativeSources,
  inspectEndpointListener,
  listSessionDirectoryIds,
  readDoubaoWorkAppIdentity,
} from "./platform.mjs";
import {
  assertAttemptState,
  atomicWriteAttemptState,
  bindConversation,
  confirmConversationPromptReadback,
  confirmModel,
  confirmPermission,
  confirmWorkspaceReadback,
  createAttemptState,
  decideResume,
  findNewConversationCandidate,
  persistBeforeDispatch,
  readAttemptState,
  recordPreSendBaselines,
  recordPromptAccepted,
  recordSendIntent,
  transitionAttempt,
} from "./state.mjs";
import {
  atomicWriteJson,
  buildNativeEvidence,
} from "./native-evidence.mjs";
import { assessDoubaoWebFinalization } from "./finalizer.mjs";

const execFile = promisify(execFileCallback);
const DRIVER_DIR = dirname(fileURLToPath(import.meta.url));
const STATE_FILE = "automation_state.json";
const LOCK_FILE = ".doubaowork-driver.lock";
const FORBIDDEN_WORKSPACE_NAMES = new Set([".git", "eval", "gt", "private-scoring"]);

function sha256Buffer(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function pathExists(pathValue) {
  try {
    await lstat(pathValue);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function assertNoSymlinkDirectoryChain(pathValue, overrides = {}) {
  if (!isAbsolute(pathValue)) throw new Error(`目录链必须是绝对路径：${pathValue}`);
  const inspect = overrides.lstat ?? lstat;
  const absolute = resolve(pathValue);
  const root = parsePath(absolute).root;
  let current = root;
  for (const segment of absolute.slice(root.length).split(sep).filter(Boolean)) {
    current = join(current, segment);
    let info;
    try {
      info = await inspect(current);
    } catch (error) {
      if (error?.code === "ENOENT") return;
      throw error;
    }
    if (info.isSymbolicLink()) throw new Error(`Driver 输出目录链禁止符号链接：${current}`);
    if (!info.isDirectory()) throw new Error(`Driver 输出目录链包含非目录：${current}`);
  }
}

async function requireOrdinary(pathValue, type, label) {
  const info = await lstat(pathValue);
  const matches = type === "file" ? info.isFile() : info.isDirectory();
  if (!matches || info.isSymbolicLink()) {
    throw new Error(`${label} 不是普通${type === "file" ? "文件" : "目录"}：${pathValue}`);
  }
  return info;
}

async function inspectWorkspaceTree(root, relative = "") {
  const current = relative ? join(root, relative) : root;
  const entries = await readdir(current, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isSymbolicLink()) throw new Error(`workspace 禁止符号链接：${join(relative, entry.name)}`);
    if (FORBIDDEN_WORKSPACE_NAMES.has(entry.name)) {
      throw new Error(`workspace 包含禁止目录：${join(relative, entry.name)}`);
    }
    if (entry.isDirectory()) await inspectWorkspaceTree(root, join(relative, entry.name));
  }
}

export async function validatePreparedTaskRoot(taskRootValue) {
  if (typeof taskRootValue !== "string" || !taskRootValue.trim()) {
    throw new Error("--task-root 必填，且必须是 prepared execution 单题根目录的绝对路径");
  }
  if (!isAbsolute(taskRootValue)) throw new Error("task root 必须是绝对路径");
  const taskRoot = resolve(taskRootValue);
  await requireOrdinary(taskRoot, "directory", "单题根目录");
  const promptFile = join(taskRoot, "PROMPT.md");
  const candidateWorkspace = join(taskRoot, "workspace");
  await requireOrdinary(promptFile, "file", "PROMPT.md");
  await requireOrdinary(candidateWorkspace, "directory", "workspace");
  await inspectWorkspaceTree(candidateWorkspace);
  const prompt = await readFile(promptFile, "utf8");
  if (!prompt.trim()) throw new Error("PROMPT.md 不能为空");

  const harnessRoot = dirname(dirname(dirname(taskRoot)));
  const manifestPath = join(harnessRoot, "manifest.json");
  await requireOrdinary(manifestPath, "file", "Harness manifest");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  if (manifest.schema_version !== "wildclawbench.web-e2e-batch/v3") {
    throw new Error(`manifest schema_version 不受支持：${manifest.schema_version ?? "<missing>"}`);
  }
  if (manifest.harness?.id !== "doubaowork") {
    throw new Error(`manifest harness 必须是 doubaowork，实际为 ${manifest.harness?.id ?? "<missing>"}`);
  }
  const taskId = basename(taskRoot);
  const task = manifest.tasks?.find((item) => item.task_id === taskId);
  if (!task) throw new Error(`manifest 未声明当前 task：${taskId}`);
  if (resolve(harnessRoot, task.execution_dir) !== taskRoot
      || resolve(harnessRoot, task.prompt_file) !== promptFile) {
    throw new Error("manifest 中 execution_dir 或 prompt_file 与当前单题不一致");
  }
  return {
    taskRoot,
    workspace: taskRoot,
    candidateWorkspace,
    promptFile,
    prompt,
    promptSha256: sha256Text(prompt),
    promptBytes: Buffer.byteLength(prompt),
    manifestPath,
    manifestSha256: sha256Buffer(await readFile(manifestPath)),
    batchId: manifest.batch_id,
    taskId,
    taskName: task.task_name ?? null,
    taskSha256: task.task_sha256 ?? null,
  };
}

async function readProcessStartIdentity(pid, overrides = {}) {
  if (overrides.readProcessStartIdentity) return overrides.readProcessStartIdentity(pid);
  const { stdout } = await execFile(
    "/bin/ps",
    ["-p", String(pid), "-o", "lstart="],
    { encoding: "utf8", timeout: 5_000, maxBuffer: 64 * 1024 },
  );
  const identity = stdout.trim().replace(/\s+/g, " ");
  if (!identity) throw new Error(`无法读取 PID ${pid} 的进程启动身份`);
  return identity;
}

function assertWorkerLockRecord(record, lockPath) {
  if (record?.schema !== "wildclawbench.doubaowork-worker-lock/v1"
      || typeof record.host !== "string"
      || !Number.isSafeInteger(record.pid)
      || record.pid <= 0
      || typeof record.process_start_identity !== "string"
      || !record.process_start_identity
      || typeof record.instance_id !== "string"
      || !record.instance_id) {
    throw new Error(`Driver lock 已存在且身份记录无效，拒绝接管：${lockPath}`);
  }
  return record;
}

async function readWorkerLock(lockPath, overrides = {}) {
  const inspect = overrides.lstat ?? lstat;
  const read = overrides.readFile ?? readFile;
  await assertNoSymlinkDirectoryChain(dirname(lockPath), overrides);
  const info = await inspect(lockPath);
  if (!info.isFile() || info.isSymbolicLink()) {
    throw new Error(`Driver lock 不是普通文件，拒绝接管：${lockPath}`);
  }
  let record;
  try {
    record = JSON.parse(await read(lockPath, "utf8"));
  } catch {
    throw new Error(`Driver lock 已存在且不可解析，拒绝接管：${lockPath}`);
  }
  return assertWorkerLockRecord(record, lockPath);
}

export async function acquireExclusiveWorkerLock(outputDir, overrides = {}) {
  const makeDirectory = overrides.mkdir ?? mkdir;
  const write = overrides.writeFile ?? writeFile;
  const remove = overrides.rm ?? rm;
  const pid = overrides.pid ?? process.pid;
  const host = overrides.host ?? hostname();
  const now = overrides.now ?? new Date();
  const instanceId = overrides.instanceId ?? randomUUID();
  const processStartIdentity = await readProcessStartIdentity(pid, overrides);
  await assertNoSymlinkDirectoryChain(outputDir, overrides);
  await makeDirectory(outputDir, { recursive: true });
  await assertNoSymlinkDirectoryChain(outputDir, overrides);
  const lockPath = join(outputDir, LOCK_FILE);
  const record = {
    schema: "wildclawbench.doubaowork-worker-lock/v1",
    host,
    pid,
    process_start_identity: processStartIdentity,
    instance_id: instanceId,
    acquired_at: now.toISOString(),
  };
  try {
    await write(lockPath, `${JSON.stringify(record, null, 2)}\n`, {
      encoding: "utf8",
      flag: "wx",
      mode: 0o600,
    });
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    const existing = await readWorkerLock(lockPath, overrides);
    let currentStartIdentity = null;
    try {
      if (existing.host === host) {
        currentStartIdentity = await readProcessStartIdentity(existing.pid, overrides);
      }
    } catch {
      currentStartIdentity = null;
    }
    if (existing.host === host
        && currentStartIdentity === existing.process_start_identity) {
      throw new Error(
        `已有 DoubaoWork Driver 仍存活：host=${existing.host} PID=${existing.pid} start=${existing.process_start_identity}`,
      );
    }
    throw new Error(
      `检测到 foreign、stale 或身份不可验证的 Driver lock，失败关闭且不自动删除：${lockPath}`,
    );
  }
  return async () => {
    const existing = await readWorkerLock(lockPath, overrides);
    if (existing.instance_id !== instanceId
        || existing.host !== host
        || existing.pid !== pid
        || existing.process_start_identity !== processStartIdentity) {
      throw new Error(`Driver lock 所有权已变化，拒绝删除：${lockPath}`);
    }
    await remove(lockPath);
  };
}

export function validateOutputDirectory(taskRoot, outputDirValue) {
  if (typeof outputDirValue !== "string" || !outputDirValue.trim()) {
    throw new Error("--output-dir 必填，且必须位于单题目录外");
  }
  if (!isAbsolute(outputDirValue)) throw new Error("自动化输出目录必须是绝对路径");
  const outputDir = resolve(outputDirValue);
  if (outputDir === taskRoot || outputDir.startsWith(`${taskRoot}${sep}`)) {
    throw new Error("自动化输出目录必须是单题目录外的绝对路径");
  }
  return outputDir;
}

async function connectClient(endpointValue = DEFAULT_ENDPOINT, appPath = DEFAULT_APP_PATH) {
  const endpoint = parseLoopbackEndpoint(endpointValue);
  const app = await readDoubaoWorkAppIdentity(appPath);
  const listener = await inspectEndpointListener(endpoint.origin, app);
  if (!listener.unique_expected_listener) {
    throw new Error("CDP 端口监听者不是唯一且可核验的 DoubaoWork Browser 进程");
  }
  const browser = await chromium.connectOverCDP(endpoint.origin, { timeout: 10_000 });
  const pages = browser.contexts().flatMap((context) => context.pages());
  const page = selectUniqueChatTarget(pages.map((item) => ({ url: item.url(), page: item }))).page;
  page.setDefaultTimeout(10_000);
  return { browser, page, endpoint: endpoint.origin, app, listener };
}

export function classifyDevelopmentObservation(snapshot) {
  return classifyDomObservation({
    visibleError: snapshot.visible_error_count > 0,
    userQuestion: snapshot.user_question_count > 0
      || snapshot.visible_dialog_count > 0
      || snapshot.approval_count > 0,
    stopControlVisible: snapshot.stop_control_count > 0,
    running: snapshot.stop_control_count > 0
      || (snapshot.bound_conversation_busy_count ?? snapshot.busy_conversation_count) > 0,
    finalAssistantVisible: snapshot.final_assistant_bytes > 0,
    replyActionsVisible: snapshot.positive_completion_marker_count > 0,
  });
}

async function inspectPage(page, { projectName = null } = {}) {
  const raw = await page.evaluate(({ expectedProjectName }) => {
    const visible = (element) => Boolean(element?.getClientRects().length);
    const stopControls = [...document.querySelectorAll(
      'button[data-testid*="stop" i],button[aria-label*="停止"],button[title*="停止"],button[aria-label*="stop" i]',
    )].filter(visible);
    const dialogs = [...document.querySelectorAll('[role="dialog"],[data-slot="dialog-content"]')]
      .filter(visible);
    const questions = [...document.querySelectorAll(
      '[data-slot="user-question"],[data-testid*="question" i],[data-testid*="clarif" i]',
    )].filter(visible);
    const approvals = [...document.querySelectorAll(
      '[data-testid*="approval" i],[data-testid*="permission-request" i]',
    )].filter(visible);
    const errors = [...document.querySelectorAll(
      '[data-testid*="error" i],[role="alert"]',
    )].filter(visible);
    const conversationItems = [...document.querySelectorAll(
      '[data-testid="conversation-list-v2-item"][data-conversation-id]',
    )];
    const conversationFacts = conversationItems.map((element) => ({
      id: element.getAttribute("data-conversation-id"),
      busy: element.getAttribute("aria-busy") === "true"
        || element.querySelectorAll('[class*="animate-spin"],[class*="animate-pulse"],[data-loading="true"]').length > 0,
      project_id: element.closest("section[data-project-id]")?.getAttribute("data-project-id") ?? null,
    }));
    const busyConversationCount = conversationFacts.filter((item) => item.busy).length;
    const replies = [...document.querySelectorAll('[data-testid="receive_message"]')].filter(visible);
    const finalReply = replies.at(-1) ?? null;
    const replyContainer = finalReply?.closest('[data-testid="union_message"]') ?? finalReply?.parentElement;
    const replyActions = replyContainer
      ? [...replyContainer.querySelectorAll('[data-testid^="message_action_"]')].filter(visible)
      : [];
    const finalText = (finalReply?.innerText || finalReply?.textContent || "").trim();
    const userMessages = [...new Set([
      ...document.querySelectorAll('[data-testid="send_message"]'),
      ...document.querySelectorAll('[data-message-role="user"]'),
    ])].filter(visible);
    const latestUser = userMessages.at(-1) ?? null;
    const latestUserText = latestUser?.innerText || latestUser?.textContent || "";
    const chatInput = document.querySelector('[data-testid="chat_input"]');
    const exactProjectControls = expectedProjectName && chatInput
      ? [...chatInput.querySelectorAll("button")].filter((element) => (
        visible(element)
        && element.getAttribute("title") === expectedProjectName
        && element.getAttribute("aria-label") === expectedProjectName
      ))
      : [];
    return {
      visible_dialog_count: dialogs.length,
      user_question_count: questions.length,
      approval_count: approvals.length,
      visible_error_count: errors.length,
      stop_control_count: stopControls.length,
      busy_conversation_count: busyConversationCount,
      conversation_facts: conversationFacts,
      visible_conversation_ids: conversationFacts
        .map((item) => item.id)
        .filter((value) => /^[0-9]{1,64}$/.test(value)),
      final_reply_action_count: replyActions.length,
      final_text: finalText,
      user_message_count: userMessages.length,
      latest_user_text: latestUserText,
      exact_project_control_count: exactProjectControls.length,
      current_url: location.href,
    };
  }, { expectedProjectName: projectName });
  const finalText = raw.final_text;
  const latestUserText = normalizePromptReadback(raw.latest_user_text);
  const currentConversationId = parseConversationId(raw.current_url);
  const currentConversation = raw.conversation_facts
    .find((item) => item.id === currentConversationId) ?? null;
  return {
    snapshot: {
      observed_at: new Date().toISOString(),
      visible_dialog_count: raw.visible_dialog_count,
      user_question_count: raw.user_question_count,
      approval_count: raw.approval_count,
      visible_error_count: raw.visible_error_count,
      stop_control_count: raw.stop_control_count,
      busy_conversation_count: raw.busy_conversation_count,
      bound_conversation_busy_count: currentConversation?.busy ? 1 : 0,
      visible_conversation_count: new Set(raw.visible_conversation_ids).size,
      final_reply_action_count: raw.final_reply_action_count,
      positive_completion_marker_count: finalText && raw.final_reply_action_count > 0 ? 1 : 0,
      final_assistant_bytes: Buffer.byteLength(finalText),
      final_assistant_sha256: finalText ? sha256Text(finalText) : null,
      current_conversation_id: currentConversationId,
      conversation_project_id_sha256: currentConversation?.project_id
        ? sha256Text(currentConversation.project_id)
        : null,
      current_project_name: raw.exact_project_control_count === 1 ? projectName : null,
      current_project_control_count: raw.exact_project_control_count,
      user_message_count: raw.user_message_count,
      latest_user_message_normalization: summarizePromptReadback(latestUserText).normalization,
      latest_user_message_sha256: raw.user_message_count > 0 ? sha256Text(latestUserText) : null,
      latest_user_message_bytes: raw.user_message_count > 0 ? Buffer.byteLength(latestUserText) : null,
    },
    visibleConversationIds: [...new Set(raw.visible_conversation_ids)].sort(),
    finalText,
    latestUserText,
  };
}

export function validateObservationBinding(state, snapshot) {
  assertAttemptState(state);
  if (!state.session.conversation_id) throw new Error("观察绑定缺少已持久化 conversation ID");
  if (snapshot.current_conversation_id !== state.session.conversation_id) {
    throw new Error("当前页面 conversation 与已绑定 ID 不一致");
  }
  if (!/^[0-9a-f]{64}$/.test(state.client.project_id_sha256 ?? "")
      || snapshot.conversation_project_id_sha256 !== state.client.project_id_sha256) {
    throw new Error("当前 conversation 不属于已绑定 project ID");
  }
  if (!state.client.project_name
      || snapshot.current_project_control_count !== 1
      || snapshot.current_project_name !== state.client.project_name) {
    throw new Error("当前页面未唯一回读已绑定 project 名称");
  }
  if (!state.workspace_selection.confirmed
      || state.workspace_selection.actual_path !== state.workspace
      || state.workspace_selection.source !== "project-folder-tooltip"
      || state.workspace_selection.project_id_sha256 !== state.client.project_id_sha256) {
    throw new Error("project 与完整 tooltip workspace 的归属证据不完整");
  }
  if (!state.prompt.readback_sha256
      || snapshot.latest_user_message_normalization !== state.prompt.readback_normalization
      || snapshot.latest_user_message_sha256 !== state.prompt.readback_sha256
      || snapshot.latest_user_message_bytes !== state.prompt.readback_bytes) {
    throw new Error("绑定 conversation 的最新 user message 与发送前 Prompt 不一致");
  }
  return {
    status: "verified",
    observed_at: snapshot.observed_at,
    conversation_id_sha256: sha256Text(state.session.conversation_id),
    project_id_sha256: state.client.project_id_sha256,
    project_name: state.client.project_name,
    workspace_path_sha256: sha256Text(state.workspace),
    workspace_readback_sha256: state.workspace_selection.display_sha256,
    workspace_source: state.workspace_selection.source,
    prompt_sha256: snapshot.latest_user_message_sha256,
    prompt_bytes: snapshot.latest_user_message_bytes,
    prompt_normalization: snapshot.latest_user_message_normalization,
  };
}

export function confirmResumePromptReadback(state, snapshot, bindingEvidence) {
  if (bindingEvidence?.status !== "verified") {
    throw new Error("恢复 Prompt 回读必须先通过当前 conversation 绑定校验");
  }
  if (state.session.prompt_readback?.status === "verified") return false;
  confirmConversationPromptReadback(state, {
    sha256: snapshot.latest_user_message_sha256,
    bytes: snapshot.latest_user_message_bytes,
    normalization: snapshot.latest_user_message_normalization,
    source: "resume-bound-conversation-user-message",
  }, snapshot.observed_at ? new Date(snapshot.observed_at) : new Date());
  return true;
}

function assertNoConflictingActivity(snapshot) {
  if (snapshot.stop_control_count > 0
      || snapshot.busy_conversation_count > 0
      || snapshot.visible_dialog_count > 0
      || snapshot.user_question_count > 0
      || snapshot.approval_count > 0) {
    throw new Error("DoubaoWork 存在运行、pending 或可见交互，拒绝创建开发 canary");
  }
}

async function captureScreenshot(page, pathValue) {
  const cdp = await page.context().newCDPSession(page);
  try {
    const capture = await cdp.send("Page.captureScreenshot", { format: "png" });
    const buffer = Buffer.from(capture.data, "base64");
    await writeFile(pathValue, buffer, { flag: "wx", mode: 0o600 });
    return { path: pathValue, size_bytes: buffer.length, sha256: sha256Buffer(buffer) };
  } finally {
    await cdp.detach();
  }
}

async function revealAndOpenProjectDialog(page) {
  const trigger = page.getByTestId("conversation-list-v2-project-create-menu-trigger");
  if (await trigger.count() !== 1) throw new Error("新建项目入口不唯一");
  const box = await trigger.boundingBox();
  if (!box) throw new Error("新建项目入口没有可交互坐标");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  if (!(await trigger.isVisible())) throw new Error("新建项目入口悬停后仍不可见");
  await trigger.click();
  const dialog = page.getByTestId("project-shared-create-project-dialog");
  await dialog.waitFor({ state: "visible" });
  if (await dialog.count() !== 1) throw new Error("创建项目对话框不唯一");
  return dialog;
}

async function runFolderHelper(workspace) {
  const helper = join(DRIVER_DIR, "select-folder.swift");
  const result = await execFile(
    "/usr/bin/swift",
    [helper, "com.work.pc.doubao", workspace, "30"],
    { encoding: "utf8", timeout: 60_000, maxBuffer: 1024 * 1024 },
  );
  const parsed = JSON.parse(result.stdout);
  if (parsed.status !== "selected" || resolve(parsed.folder) !== workspace) {
    throw new Error("原生目录 helper 未确认请求目录");
  }
  return parsed;
}

export function selectWorkspaceReadbackCandidate(candidates, workspace, userHome = homedir()) {
  for (const value of candidates) {
    const candidate = String(value ?? "").trim();
    if (!candidate) continue;
    try {
      if (workspaceReadbackMatches(candidate, workspace, userHome)) return candidate;
    } catch {
      // Ignore non-path UI labels; only a strict full-path readback can pass.
    }
  }
  return null;
}

async function readWorkspaceTooltip(page, dialog, workspace) {
  const item = dialog.getByTestId("project-shared-project-folder-item");
  await item.waitFor({ state: "visible" });
  if (await item.count() !== 1) throw new Error("项目目录项不唯一");
  const attributes = await item.evaluate((element) => ({
    title: element.getAttribute("title"),
    aria_label: element.getAttribute("aria-label"),
    data_path: element.getAttribute("data-path"),
    text: (element.innerText || element.textContent || "").trim(),
  }));
  await item.hover();
  const deadline = Date.now() + 3_000;
  do {
    const tooltipValues = await page.locator('[role="tooltip"]').allTextContents();
    const exact = selectWorkspaceReadbackCandidate([
      attributes.title,
      attributes.aria_label,
      attributes.data_path,
      attributes.text,
      ...tooltipValues,
    ], workspace);
    if (exact) return exact;
    await page.waitForTimeout(250);
  } while (Date.now() < deadline);
  throw new Error("项目目录 tooltip 未在 3 秒内回读匹配的完整绝对路径");
}

async function openProjectConversation(page, projectName) {
  const grouped = page.getByTestId("project-grouped-section");
  const projectTitle = grouped.getByTitle(projectName, { exact: true });
  const section = projectTitle.locator("xpath=ancestor::section[@data-project-id]");
  if (await section.count() !== 1) throw new Error("新建项目在侧栏中不唯一");
  const projectId = await section.getAttribute("data-project-id");
  if (!/^[0-9]{1,64}$/.test(projectId ?? "")) throw new Error("新建项目缺少稳定数字 project ID");

  const chatInput = page.getByTestId("chat_input");
  const currentProject = chatInput.getByRole("button", { name: projectName, exact: true });
  if (await currentProject.count() !== 1 || !(await currentProject.isVisible())) {
    const row = section.locator('[role="button"]').first();
    await row.hover();
    const newConversation = section.getByRole("button", { name: "新对话", exact: true });
    if (await newConversation.count() !== 1) throw new Error("项目新对话入口不唯一");
    await newConversation.waitFor({ state: "visible" });
    await newConversation.click();
    await currentProject.waitFor({ state: "visible" });
  }
  if (await currentProject.getAttribute("title") !== projectName) {
    throw new Error("当前项目工具栏未精确回读新建项目名称");
  }
  return { projectIdSha256: sha256Text(projectId) };
}

async function createProject(page, state, stateFile, config) {
  const dialog = await revealAndOpenProjectDialog(page);
  await dialog.getByTestId("project-shared-create-project-name-input").fill(config.projectName);
  await dialog.getByRole("button", { name: "添加本地文件夹", exact: true }).click();
  await runFolderHelper(config.workspace);
  const readback = await readWorkspaceTooltip(page, dialog, config.workspace);
  confirmWorkspaceReadback(state, readback, homedir());
  await atomicWriteAttemptState(stateFile, state);
  const confirm = dialog.getByTestId("project-shared-create-project-confirm");
  if (await confirm.isDisabled()) throw new Error("完整路径回读后创建项目按钮仍不可用");
  await confirm.click();
  await dialog.waitFor({ state: "hidden" });
  await page.getByTestId("chat_input").waitFor({ state: "visible" });
  const project = await openProjectConversation(page, config.projectName);
  state.client.project_id_sha256 = project.projectIdSha256;
  state.workspace_selection.project_id_sha256 = project.projectIdSha256;
  state.history.push({
    phase: state.phase,
    event: "PROJECT_WORKSPACE_BINDING_RECORDED",
    project_id_sha256: project.projectIdSha256,
    workspace_path_sha256: sha256Text(state.workspace),
    workspace_readback_sha256: state.workspace_selection.display_sha256,
    at: new Date().toISOString(),
  });
  await atomicWriteAttemptState(stateFile, state);
}

export function selectConfigurationReadback(controls, projectName) {
  const visible = controls.filter((item) => item.visible !== false);
  const localComputer = visible.filter((item) => item.text === "本地电脑");
  if (localComputer.length !== 1) throw new Error("必须唯一回读本地电脑模式");
  const project = visible.filter((item) => item.title === projectName && item.aria_label === projectName);
  if (project.length !== 1) throw new Error("必须唯一回读当前项目名称");
  const permission = visible.filter((item) => item.title
    && item.title === item.aria_label
    && item.title !== projectName);
  if (permission.length !== 1) throw new Error("必须唯一回读当前权限");
  const ignoredTexts = new Set(["", "本地电脑", "技能", "连接器"]);
  const model = visible.filter((item) => !item.title
    && !item.aria_label
    && !item.testid
    && !ignoredTexts.has(item.text));
  if (model.length !== 1) throw new Error("必须唯一回读当前非空模型");
  return { permission: permission[0].title, model: model[0].text };
}

async function readConfiguration(page, projectName) {
  const controls = await page.getByTestId("chat_input").evaluate((root) => (
    [...root.querySelectorAll("button")].map((element) => ({
      visible: Boolean(element.getClientRects().length),
      testid: element.getAttribute("data-testid"),
      aria_label: element.getAttribute("aria-label"),
      title: element.getAttribute("title"),
      text: (element.innerText || element.textContent || "").trim().replace(/\s+/g, " "),
    }))
  ));
  return selectConfigurationReadback(controls, projectName);
}

export function canonicalEditorBlockText(blockTexts) {
  const blocks = blockTexts.map((value) => String(value).replace(/\r\n/g, "\n"));
  while (blocks.length > 0 && blocks.at(-1) === "") blocks.pop();
  return blocks.join("\n");
}

async function fillPrompt(page, prompt) {
  const editor = page.getByTestId("chat_input_input").getByRole("textbox");
  if (await editor.count() !== 1) throw new Error("Prompt 编辑器不唯一");
  await editor.fill(prompt);
  const blocks = await editor.evaluate((element) => (
    element.childNodes.length > 0
      ? [...element.childNodes].map((node) => node.textContent || "")
      : [element.textContent || ""]
  ));
  const current = canonicalEditorBlockText(blocks);
  const expected = String(prompt).replace(/\r\n/g, "\n").replace(/\n+$/u, "");
  if (current !== expected) throw new Error("Prompt 编辑器按块回读与 PROMPT.md 不一致");
  const send = page.getByTestId("chat_input_send_button");
  await send.waitFor({ state: "visible" });
  if (await send.count() !== 1 || await send.isDisabled()) throw new Error("发送按钮不唯一或不可用");
  return send;
}

async function waitForSessionBinding(page, state, roots, projectName, promptReadback, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const pageObservation = await inspectPage(page, { projectName });
    const sessionDirectoryIds = await listSessionDirectoryIds({ roots });
    const candidate = findNewConversationCandidate(
      state,
      pageObservation.visibleConversationIds,
      sessionDirectoryIds,
    );
    if (candidate.status === "unique") {
      if (pageObservation.snapshot.current_conversation_id !== candidate.conversation_id) {
        throw new Error("发送后新 conversation 未成为当前页面，拒绝跨会话绑定");
      }
      if (pageObservation.snapshot.conversation_project_id_sha256 !== state.client.project_id_sha256) {
        throw new Error("发送后 conversation 不属于已确认 project，拒绝绑定");
      }
      if (pageObservation.snapshot.current_project_control_count !== 1
          || pageObservation.snapshot.current_project_name !== projectName) {
        throw new Error("发送后当前 project 未唯一回读");
      }
      if (pageObservation.snapshot.latest_user_message_normalization === promptReadback.normalization
          && pageObservation.snapshot.latest_user_message_sha256 === promptReadback.sha256
          && pageObservation.snapshot.latest_user_message_bytes === promptReadback.bytes) {
      return {
        conversationId: candidate.conversation_id,
        visibleConversationIds: pageObservation.visibleConversationIds,
        sessionDirectoryIds,
        pageObservation,
      };
      }
    }
    if (candidate.status === "ambiguous" || candidate.status === "mismatch") {
      throw new Error(`发送后 session 绑定失败关闭：${candidate.status}`);
    }
    await page.waitForTimeout(1_000);
  }
  throw new Error("发送后未在有界时间内发现唯一的新 UI conversation/native session");
}

function sanitizedStateSummary(state) {
  return {
    attempt_id: state.attempt_id,
    phase: state.phase,
    batch_id: state.identity.batch_id,
    task_id: state.identity.task_id,
    dispatch_attempt_count: state.send.dispatch_attempt_count,
    prompt_sha256: state.prompt.sha256,
    prompt_readback_sha256: state.prompt.readback_sha256,
    prompt_readback_bytes: state.prompt.readback_bytes,
    prompt_readback_normalization: state.prompt.readback_normalization,
    actual_model: state.actual.model,
    actual_permission_mode: state.actual.permission_mode,
    conversation_id_sha256: state.session.conversation_id
      ? sha256Text(state.session.conversation_id)
      : null,
    session_directory_id_sha256: state.session.session_directory_id
      ? sha256Text(state.session.session_directory_id)
      : null,
    turn_id: state.session.turn_id,
    native_cwd: state.session.native_cwd,
    prompt_readback_status: state.session.prompt_readback?.status ?? "unverified",
  };
}

async function markFailure(stateFile, state, error) {
  if (!state) return;
  state.error = {
    code: state.send.dispatch_attempt_count === 1
      ? "DEVELOPMENT_DISPATCH_UNCERTAIN"
      : "DEVELOPMENT_PRE_SEND_FAILED",
    message: error instanceof Error ? error.message : String(error),
    at: new Date().toISOString(),
  };
  try {
    if (state.send.dispatch_attempt_count === 1
        || new Set(["READY_TO_SEND", "PROMPT_SENT", "RUNNING", "NEEDS_ATTENTION"]).has(state.phase)) {
      if (state.phase !== "NEEDS_ATTENTION") {
        transitionAttempt(state, "NEEDS_ATTENTION", { reason: state.error.code });
      }
    } else if (!state.terminal) {
      transitionAttempt(state, "INFRA_FAILED", { reason: state.error.code });
    }
    await atomicWriteAttemptState(stateFile, state);
  } catch {
    // Preserve the original error; a partially persisted state remains fail-closed.
  }
}

export function assertPreSendRetryEligible(state) {
  assertAttemptState(state);
  if (state.phase !== "INFRA_FAILED"
      || state.error?.code !== "DEVELOPMENT_PRE_SEND_FAILED"
      || state.send.dispatch_attempt_count !== 0
      || state.send.intent_persisted_at
      || state.send.dispatch_started_at
      || state.send.accepted_at
      || state.timing.sent_at
      || state.session.conversation_id
      || state.session.session_directory_id
      || !state.workspace_selection.confirmed
      || state.workspace_selection.actual_path !== state.workspace
      || !/^[0-9a-f]{64}$/.test(state.client.project_id_sha256 ?? "")) {
    throw new Error("发送前重试只允许 workspace 已确认且从未进入发送临界区的 INFRA_FAILED attempt");
  }
  return state;
}

async function archiveAttemptState(outputDir, stateFile, state) {
  const archivePath = join(outputDir, ".attempts", state.attempt_id, STATE_FILE);
  const contents = await readFile(stateFile);
  await mkdir(dirname(archivePath), { recursive: true });
  try {
    await writeFile(archivePath, contents, { flag: "wx", mode: 0o600 });
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    const existing = await readFile(archivePath);
    if (!existing.equals(contents)) throw new Error("旧 attempt 归档已存在但内容不一致");
  }
  return archivePath;
}

async function dispatchFromSelectedProject({ client, state, stateFile, config, roots }) {
  const actual = await readConfiguration(client.page, config.projectName);
  confirmPermission(state, actual.permission);
  await atomicWriteAttemptState(stateFile, state);
  confirmModel(state, actual.model);
  const beforeSend = await inspectPage(client.page, { projectName: config.projectName });
  assertNoConflictingActivity(beforeSend.snapshot);
  const beforeSendSessionIds = await listSessionDirectoryIds({ roots });
  recordPreSendBaselines(state, {
    conversationIds: beforeSend.visibleConversationIds,
    sessionDirectoryIds: beforeSendSessionIds,
  });
  await atomicWriteAttemptState(stateFile, state);

  const sendButton = await fillPrompt(client.page, config.prompt);
  const promptReadback = summarizePromptReadback(config.prompt);
  recordSendIntent(state);
  await atomicWriteAttemptState(stateFile, state);
  const readyScreenshot = await captureScreenshot(client.page, join(config.outputDir, "ready-to-send.png"));
  await persistBeforeDispatch(stateFile, state);
  await sendButton.click();
  recordPromptAccepted(state);
  await atomicWriteAttemptState(stateFile, state);
  const sentScreenshot = await captureScreenshot(client.page, join(config.outputDir, "prompt-sent.png"));

  const binding = await waitForSessionBinding(
    client.page,
    state,
    roots,
    config.projectName,
    promptReadback,
  );
  bindConversation(state, {
    conversationId: binding.conversationId,
    sessionDirectoryId: binding.conversationId,
    evidence: [
      {
        kind: "ui-conversation-id",
        sha256: sha256Text(binding.conversationId),
        source: "sidebar-data-conversation-id",
      },
      {
        kind: "native-session-directory",
        sha256: sha256Text(binding.conversationId),
        source: "agent-mode-workspace-sessions",
      },
    ],
  });
  const bindingEvidence = validateObservationBinding(state, binding.pageObservation.snapshot);
  state.session.binding_evidence.push(bindingEvidence);
  confirmConversationPromptReadback(state, {
    sha256: binding.pageObservation.snapshot.latest_user_message_sha256,
    bytes: binding.pageObservation.snapshot.latest_user_message_bytes,
    normalization: binding.pageObservation.snapshot.latest_user_message_normalization,
  });
  await atomicWriteAttemptState(stateFile, state);
  transitionAttempt(state, "RUNNING", { reason: "tentative-session-bound" });
  await atomicWriteAttemptState(stateFile, state);

  const dispatchRecord = {
    schema: "wildclawbench.doubaowork-development-dispatch/v1",
    development_only: true,
    created_at: new Date().toISOString(),
    source: {
      manifest_sha256: config.manifestSha256,
      task_sha256: config.taskSha256,
      prompt_sha256: config.promptSha256,
      prompt_bytes: config.promptBytes,
    },
    state: sanitizedStateSummary(state),
    binding: state.session.binding_evidence,
    screenshots: [readyScreenshot, sentScreenshot].map((item) => ({
      file: basename(item.path),
      size_bytes: item.size_bytes,
      sha256: item.sha256,
    })),
    formal_execution_record_created: false,
  };
  await atomicWriteJson(join(config.outputDir, "development-dispatch.json"), dispatchRecord);
  return dispatchRecord;
}

async function startDevelopmentRun(options) {
  const config = await validatePreparedTaskRoot(options.taskRoot);
  const outputDir = validateOutputDirectory(config.taskRoot, options.outputDir);
  if (!options.projectName?.trim()) throw new Error("--project-name 必填");
  config.projectName = options.projectName.trim();
  config.outputDir = outputDir;
  const stateFile = join(outputDir, STATE_FILE);
  const releaseLock = await acquireExclusiveWorkerLock(outputDir);
  let client;
  let state;
  let primaryError = null;
  try {
    if (await pathExists(stateFile)) throw new Error("新执行拒绝复用已有 automation_state.json；请使用 --resume");
    client = await connectClient(options.endpoint, options.appPath);
    const preflight = await inspectPage(client.page);
    assertNoConflictingActivity(preflight.snapshot);
    const roots = defaultNativeRoots(homedir());
    const initialSessionIds = await listSessionDirectoryIds({ roots });
    state = createAttemptState({
      attemptId: randomUUID(),
      batchId: config.batchId,
      taskId: config.taskId,
      workspace: config.workspace,
      promptFile: config.promptFile,
      prompt: config.prompt,
      requestedModel: null,
      requestedPermissionMode: "current",
      appPath: client.app.app_path,
      endpoint: client.endpoint,
      baselineConversationIds: preflight.visibleConversationIds,
      baselineSessionDirectoryIds: initialSessionIds,
    });
    state.client.version = client.app.version;
    state.client.process = { listener_pid: client.listener.listeners[0].pid };
    state.client.project_name = config.projectName;
    state.client.manifest_sha256 = config.manifestSha256;
    await atomicWriteAttemptState(stateFile, state);

    transitionAttempt(state, "CLIENT_READY", {
      preflight: {
        visible_conversation_count: preflight.snapshot.visible_conversation_count,
        native_session_directory_count: initialSessionIds.length,
        conflicting_activity: false,
      },
    });
    await atomicWriteAttemptState(stateFile, state);
    await createProject(client.page, state, stateFile, config);
    return await dispatchFromSelectedProject({ client, state, stateFile, config, roots });
  } catch (error) {
    primaryError = error;
    if (client?.page) await client.page.keyboard.press("Escape").catch(() => {});
    await markFailure(stateFile, state, error);
    throw error;
  } finally {
    try {
      if (client?.browser) await client.browser.close();
    } catch (error) {
      if (!primaryError) throw error;
    } finally {
      try {
        await releaseLock();
      } catch (error) {
        if (!primaryError) throw error;
      }
    }
  }
}

async function retryPreSendDevelopmentRun(options) {
  if (!isAbsolute(options.outputDir)) throw new Error("--output-dir 必须是绝对路径");
  const outputDir = resolve(options.outputDir);
  const stateFile = join(outputDir, STATE_FILE);
  const releaseLock = await acquireExclusiveWorkerLock(outputDir);
  let client;
  let state = null;
  let primaryError = null;
  try {
    const previous = assertPreSendRetryEligible(await readAttemptState(stateFile));
    const config = await validatePreparedTaskRoot(dirname(previous.prompt.file));
    if (config.batchId !== previous.identity.batch_id
        || config.taskId !== previous.identity.task_id
        || config.taskRoot !== previous.workspace
        || config.promptSha256 !== previous.prompt.sha256
        || config.manifestSha256 !== previous.client.manifest_sha256) {
      throw new Error("发送前重试时 prepared task 身份、Prompt 或 manifest 已漂移");
    }
    if (typeof previous.client.project_name !== "string" || !previous.client.project_name.trim()) {
      throw new Error("发送前重试缺少已创建项目名称");
    }
    config.projectName = previous.client.project_name;
    config.outputDir = outputDir;

    client = await connectClient(previous.client.endpoint, previous.client.app_path);
    const preflight = await inspectPage(client.page);
    assertNoConflictingActivity(preflight.snapshot);
    const roots = defaultNativeRoots(homedir());
    const sessionDirectoryIds = await listSessionDirectoryIds({ roots });
    const project = await openProjectConversation(client.page, config.projectName);
    if (project.projectIdSha256 !== previous.client.project_id_sha256) {
      throw new Error("发送前重试的当前 project ID 与上次已确认项目不一致");
    }

    await archiveAttemptState(outputDir, stateFile, previous);
    state = createAttemptState({
      attemptId: randomUUID(),
      batchId: config.batchId,
      taskId: config.taskId,
      workspace: config.workspace,
      promptFile: config.promptFile,
      prompt: config.prompt,
      requestedModel: null,
      requestedPermissionMode: "current",
      appPath: client.app.app_path,
      endpoint: client.endpoint,
      baselineConversationIds: preflight.visibleConversationIds,
      baselineSessionDirectoryIds: sessionDirectoryIds,
    });
    state.client.version = client.app.version;
    state.client.process = { listener_pid: client.listener.listeners[0].pid };
    state.client.project_name = config.projectName;
    state.client.project_id_sha256 = project.projectIdSha256;
    state.workspace_selection.project_id_sha256 = project.projectIdSha256;
    state.client.manifest_sha256 = config.manifestSha256;
    transitionAttempt(state, "CLIENT_READY", {
      preflight: {
        visible_conversation_count: preflight.snapshot.visible_conversation_count,
        native_session_directory_count: sessionDirectoryIds.length,
        conflicting_activity: false,
      },
      retry_of_attempt_sha256: sha256Text(previous.attempt_id),
    });
    confirmWorkspaceReadback(
      state,
      previous.workspace_selection.display_value,
      homedir(),
    );
    state.history.push({
      phase: state.phase,
      event: "PRE_SEND_RETRY_EXISTING_PROJECT_RECONFIRMED",
      previous_attempt_sha256: sha256Text(previous.attempt_id),
      at: new Date().toISOString(),
    });
    await atomicWriteAttemptState(stateFile, state);
    return await dispatchFromSelectedProject({ client, state, stateFile, config, roots });
  } catch (error) {
    primaryError = error;
    await markFailure(stateFile, state, error);
    throw error;
  } finally {
    try {
      if (client?.browser) await client.browser.close();
    } catch (error) {
      if (!primaryError) throw error;
    } finally {
      try {
        await releaseLock();
      } catch (error) {
        if (!primaryError) throw error;
      }
    }
  }
}

async function navigateToConversation(page, conversationId) {
  if (parseConversationId(page.url()) === conversationId) return;
  const item = page.locator(
    `[data-testid="conversation-list-v2-item"][data-conversation-id="${conversationId}"]`,
  );
  if (await item.count() !== 1 || !(await item.isVisible())) {
    throw new Error("已绑定 conversation 不在可见侧栏，拒绝按标题或时间猜测");
  }
  await item.click();
  await page.waitForURL((url) => parseConversationId(url.toString()) === conversationId);
}

async function collectNativeEvidenceSnapshot(outputDir, state, observationId) {
  const pathValue = join(outputDir, `native-evidence-${observationId}.json`);
  const discovery = await discoverNativeSources({ sessionId: state.session.session_directory_id });
  if (!discovery.session?.trajectories?.length) return null;
  const evidence = await buildNativeEvidence({
    sessionId: state.session.session_directory_id,
    workspace: state.workspace,
    discovery,
  });
  await atomicWriteJson(pathValue, evidence);
  const buffer = await readFile(pathValue);
  return {
    file: basename(pathValue),
    size_bytes: buffer.length,
    sha256: sha256Buffer(buffer),
    collected_at: evidence.collected_at,
  };
}

async function resumeDevelopmentRun(options) {
  if (!isAbsolute(options.outputDir)) throw new Error("--output-dir 必须是绝对路径");
  const outputDir = resolve(options.outputDir);
  const stateFile = join(outputDir, STATE_FILE);
  const releaseLock = await acquireExclusiveWorkerLock(outputDir);
  let client;
  let state;
  let primaryError = null;
  try {
    state = await readAttemptState(stateFile);
    assertAttemptState(state);
    if (state.send.dispatch_attempt_count !== 1) {
      throw new Error("开发恢复入口只观察已登记一次发送的 attempt，不在恢复中发送 Prompt");
    }
    state.runtime.driver_pid = process.pid;
    state.runtime.heartbeat_at = new Date().toISOString();
    state.history.push({ phase: state.phase, event: "DRIVER_RESUMED_READ_ONLY", at: state.runtime.heartbeat_at });
    await atomicWriteAttemptState(stateFile, state);
    client = await connectClient(state.client.endpoint, state.client.app_path);
    const roots = defaultNativeRoots(homedir());
    let pageObservation = await inspectPage(client.page);
    let sessionDirectoryIds = await listSessionDirectoryIds({ roots });
    const decision = decideResume(state, {
      visibleConversationIds: pageObservation.visibleConversationIds,
      sessionDirectoryIds,
    });
    if (decision.action === "bind-and-observe") {
      bindConversation(state, {
        conversationId: decision.conversation_id,
        sessionDirectoryId: decision.conversation_id,
        evidence: [{ kind: "resume-binding", source: decision.reason }],
      });
      await atomicWriteAttemptState(stateFile, state);
    } else if (decision.action !== "observe-only") {
      if (state.phase !== "NEEDS_ATTENTION") {
        transitionAttempt(state, "NEEDS_ATTENTION", { reason: decision.reason });
        await atomicWriteAttemptState(stateFile, state);
      }
      throw new Error(`只读恢复拒绝继续：${decision.reason}`);
    }

    await navigateToConversation(client.page, state.session.conversation_id);
    const deadline = Date.now() + options.observeSeconds * 1000;
    let stableCompletionHash = null;
    let stableCompletionCount = 0;
    let classification = { kind: "unknown", trusted: false };
    let bindingEvidence = null;
    while (Date.now() < deadline) {
      pageObservation = await inspectPage(client.page, { projectName: state.client.project_name });
      bindingEvidence = validateObservationBinding(state, pageObservation.snapshot);
      if (confirmResumePromptReadback(state, pageObservation.snapshot, bindingEvidence)) {
        await atomicWriteAttemptState(stateFile, state);
      }
      classification = classifyDevelopmentObservation(pageObservation.snapshot);
      if (classification.kind === "needs-attention" || classification.kind === "failure-candidate") break;
      if (classification.kind === "ui-completion-candidate") {
        if (stableCompletionHash === pageObservation.snapshot.final_assistant_sha256) {
          stableCompletionCount += 1;
        } else {
          stableCompletionHash = pageObservation.snapshot.final_assistant_sha256;
          stableCompletionCount = 1;
        }
        if (stableCompletionCount >= 3) break;
      } else {
        stableCompletionHash = null;
        stableCompletionCount = 0;
      }
      await client.page.waitForTimeout(2_000);
    }

    bindingEvidence = validateObservationBinding(state, pageObservation.snapshot);
    if (confirmResumePromptReadback(state, pageObservation.snapshot, bindingEvidence)) {
      await atomicWriteAttemptState(stateFile, state);
    }
    const running = pageObservation.snapshot.stop_control_count > 0
      || pageObservation.snapshot.bound_conversation_busy_count > 0;
    const pending = pageObservation.snapshot.visible_dialog_count > 0
      || pageObservation.snapshot.user_question_count > 0
      || pageObservation.snapshot.approval_count > 0
      || pageObservation.snapshot.visible_error_count > 0;
    const uiCompletion = classification.kind === "ui-completion-candidate"
      && stableCompletionCount >= 3
      && !running
      && !pending
      && pageObservation.snapshot.positive_completion_marker_count > 0;
    const observationId = Date.now();
    let finalReply = null;
    let screenshot = null;
    let nativeEvidence = null;
    if (uiCompletion) {
      const replyPath = join(outputDir, `ui-final-reply-${observationId}.txt`);
      await writeFile(replyPath, pageObservation.finalText, { encoding: "utf8", flag: "wx", mode: 0o600 });
      const replyBuffer = await readFile(replyPath);
      const replySha256 = sha256Buffer(replyBuffer);
      if (replySha256 !== pageObservation.snapshot.final_assistant_sha256
          || replyBuffer.length !== pageObservation.snapshot.final_assistant_bytes) {
        throw new Error("同次 observation 的最终回复文件与 DOM 哈希或字节数不一致");
      }
      finalReply = {
        file: basename(replyPath),
        size_bytes: replyBuffer.length,
        sha256: replySha256,
        dom_sha256_matches: true,
      };
      const screenshotPath = join(outputDir, `ui-completion-candidate-${observationId}.png`);
      screenshot = await captureScreenshot(client.page, screenshotPath);
      nativeEvidence = await collectNativeEvidenceSnapshot(outputDir, state, observationId);
      if (state.phase !== "NEEDS_ATTENTION") {
        transitionAttempt(state, "NEEDS_ATTENTION", {
          reason: "ui-equivalent-binding-without-public-finalizer-or-process-cleanup",
        });
      }
      state.error = {
        code: "DEVELOPMENT_UI_COMPLETION_UNVERIFIED",
        message: "UI 等价完成证据已稳定，但公共 finalizer/任务进程清理尚未接入",
        at: new Date().toISOString(),
      };
    } else if (pending || classification.kind === "failure-candidate") {
      if (state.phase !== "NEEDS_ATTENTION") {
        transitionAttempt(state, "NEEDS_ATTENTION", { reason: "visible-pending-or-error" });
      }
      state.error = {
        code: "DEVELOPMENT_NEEDS_ATTENTION",
        message: "观察到 pending、用户问题、授权或可见错误；控制端未作答",
        at: new Date().toISOString(),
      };
    }
    const cleanupEvidence = state.terminal_process_cleanup ?? {
      supported: false,
      success: false,
      error_code: "CLEANUP_NOT_RUN",
      tracked_residue: null,
      after: null,
    };
    const finalizerAssessment = assessDoubaoWebFinalization({
      state,
      observation: {
        ui: pageObservation.snapshot,
        binding: bindingEvidence,
        classification,
        stable_completion_observations: stableCompletionCount,
        terminal_process_cleanup: cleanupEvidence,
      },
      nativeEvidence: nativeEvidence
        ? JSON.parse(await readFile(join(outputDir, nativeEvidence.file), "utf8"))
        : null,
      cleanup: cleanupEvidence,
      candidate: null,
    });
    state.session.binding_evidence.push(bindingEvidence);
    await atomicWriteAttemptState(stateFile, state);

    sessionDirectoryIds = await listSessionDirectoryIds({ roots });
    const finalDecision = decideResume(state, {
      visibleConversationIds: pageObservation.visibleConversationIds,
      sessionDirectoryIds,
    });
    const record = {
      schema: "wildclawbench.doubaowork-development-observation/v1",
      development_only: true,
      observation_id: String(observationId),
      observed_at: new Date().toISOString(),
      state: sanitizedStateSummary(state),
      resume: {
        action: finalDecision.action,
        allow_send: false,
        reason: finalDecision.reason,
      },
      ui: pageObservation.snapshot,
      binding: bindingEvidence,
      classification,
      stable_completion_observations: stableCompletionCount,
      artifacts: {
        final_reply: finalReply,
        screenshot: screenshot ? {
          file: basename(screenshot.path),
          size_bytes: screenshot.size_bytes,
          sha256: screenshot.sha256,
        } : null,
        native_evidence: nativeEvidence,
      },
      finalizer: finalizerAssessment,
      terminal: {
        status: "unverified",
        trusted_native_terminal: false,
      },
      terminal_process_cleanup: {
        supported: false,
        success: false,
        blocks_formal_completion: true,
      },
      formal_execution_record_created: false,
      slot_status: running || pending ? "SLOT_HELD" : "SLOT_RELEASED",
    };
    const observationPath = join(outputDir, `development-observation-${observationId}.json`);
    await atomicWriteJson(observationPath, record);
    return record;
  } catch (error) {
    primaryError = error;
    await markFailure(stateFile, state, error);
    throw error;
  } finally {
    try {
      if (client?.browser) await client.browser.close();
    } catch (error) {
      if (!primaryError) throw error;
    } finally {
      try {
        await releaseLock();
      } catch (error) {
        if (!primaryError) throw error;
      }
    }
  }
}

export async function main(argv = process.argv.slice(2)) {
  const { values } = parseArgs({
    args: argv,
    options: {
      "task-root": { type: "string" },
      "output-dir": { type: "string" },
      "project-name": { type: "string" },
      endpoint: { type: "string", default: DEFAULT_ENDPOINT },
      "app-path": { type: "string", default: DEFAULT_APP_PATH },
      resume: { type: "boolean", default: false },
      "retry-pre-send-failure": { type: "boolean", default: false },
      "observe-seconds": { type: "string", default: "900" },
    },
  });
  if (!values["output-dir"]) throw new Error("--output-dir 必填，且必须位于单题目录外");
  if (!values.resume && !values["task-root"]) {
    throw new Error("--task-root 必填，且必须是 prepared execution 单题根目录的绝对路径");
  }
  if (values["retry-pre-send-failure"] && !values.resume) {
    throw new Error("--retry-pre-send-failure 必须与 --resume 同时使用");
  }
  const observeSeconds = Number(values["observe-seconds"]);
  if (!Number.isFinite(observeSeconds) || observeSeconds <= 0 || observeSeconds > 900) {
    throw new Error("--observe-seconds 必须是 1–900 秒");
  }
  const result = values.resume && values["retry-pre-send-failure"]
    ? await retryPreSendDevelopmentRun({ outputDir: values["output-dir"] })
    : values.resume
      ? await resumeDevelopmentRun({ outputDir: values["output-dir"], observeSeconds })
    : await startDevelopmentRun({
      taskRoot: values["task-root"],
      outputDir: values["output-dir"],
      projectName: values["project-name"],
      endpoint: values.endpoint,
      appPath: values["app-path"],
    });
  process.stdout.write(`${JSON.stringify({
    status: "ok",
    development_only: true,
    state: result.state,
    slot_status: result.slot_status ?? "SLOT_HELD",
  }, null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
