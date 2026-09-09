#!/usr/bin/env node
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { realpathSync } from "node:fs";
import { access, copyFile, mkdir, mkdtemp, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_BUNDLE_ID,
  RESUMABLE_PHASES,
  TERMINAL_PHASES,
  assertStateMatches,
  atomicWriteJson,
  classifyApprovalCommand,
  classifyDomStatus,
  classifySessionStatus,
  DRIVER_VERSION,
  createInitialState,
  diffSnapshots,
  parseArgs,
  isSubstantiveFinalResponse,
  readJsonIfExists,
  resolveConfig,
  resolveExecutionIdentity,
  snapshotTree,
  transitionState,
  updateExecutionRecord,
} from "./lib.mjs";

const SCRIPT_DIR = resolve(fileURLToPath(new URL(".", import.meta.url)));
const NATIVE_FOLDER_HELPER = join(SCRIPT_DIR, "select-folder.swift");

function usage() {
  return `QwenWork Web E2E 单题执行 Driver

用法：
  node driver.mjs --probe [选项]
  node driver.mjs --workspace <单题目录> [选项]

核心选项：
  --model <UI名称>                 可选；指定时选择并回读，省略时保持并回读当前模型
  --permission-mode <模式>         current（保持现状）或 full-access（显式开启完全访问）
  --model-id <ID>                  execution_record 模型身份；已有记录时仅校验
  --batch-id <ID> --task-id <ID>   没有 manifest/record 时必须显式提供
  --run-timeout-seconds <秒>       Agent 总执行超时，默认 3600
  --poll-interval-seconds <秒>     终态轮询间隔，默认 2
  --post-cancel-quiescence-seconds <秒> 超时停止后的 workspace 静默观察，默认 5
  --resume                         从已有 automation_state 恢复，禁止重复发送
  --retry-pre-send-failure          仅归档并重试发送前、产物零变化的 INFRA_FAILED
  --detach-after-submit            捕获稳定 conversation ID 后退出，由队列后台观察
  --observe-once                   恢复原 conversation，只执行一次终态观察
  --quiet                          仅输出错误；供批次 Worker 高频观察使用
  --restart-app                    正常退出后以本地 CDP 端口重启 QwenWork
  --dry-run                        校验输入、身份和状态，不操作 QwenWork
  -h, --help                       显示帮助`;
}

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

export async function waitForUniqueVisible(readVisible, timeout, description, pollInterval = 250) {
  const deadline = Date.now() + timeout;
  let lastCount = 0;
  while (Date.now() <= deadline) {
    const matches = await readVisible();
    lastCount = matches.length;
    if (lastCount === 1) return matches[0];
    if (lastCount > 1) throw new Error(`${description}数量异常：${lastCount}`);
    await sleep(Math.min(pollInterval, Math.max(1, deadline - Date.now())));
  }
  throw new Error(`${description}数量异常：${lastCount}`);
}

export function hasTrustedDomCompletion(dom) {
  return dom?.status?.kind === "success"
    && (Boolean(dom.explicitFinished) || isSubstantiveFinalResponse(dom.finalText));
}

function run(command, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const { allowFailure = false, capture = false, ...spawnOptions } = options;
    const child = spawn(command, args, { stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit", ...spawnOptions });
    let stdout = "";
    let stderr = "";
    if (child.stdout) child.stdout.on("data", (chunk) => { stdout += chunk; });
    if (child.stderr) child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", rejectPromise);
    child.once("exit", (code) => {
      if (code === 0 || allowFailure) resolvePromise({ code, stdout, stderr });
      else rejectPromise(new Error(`${command} 执行失败（退出码 ${code}）：${stderr.trim()}`));
    });
  });
}

async function endpointReady(endpoint) {
  try {
    const response = await fetch(`${endpoint}/json/version`, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) return false;
    const value = await response.json();
    return Boolean(value.webSocketDebuggerUrl || value.Browser);
  } catch {
    return false;
  }
}

async function guiSessionStatus() {
  const result = await run(
    "/usr/bin/osascript",
    ["-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
    { capture: true, allowFailure: true },
  );
  const frontmostApplication = result.code === 0 ? result.stdout.trim() : "unknown";
  return {
    frontmost_application: frontmostApplication,
    unlocked: result.code === 0 && frontmostApplication.toLowerCase() !== "loginwindow",
  };
}

async function requireUnlockedGui() {
  const status = await guiSessionStatus();
  if (!status.unlocked) {
    throw new Error(`macOS 图形会话不可交互（当前前台：${status.frontmost_application}）；请解锁桌面后重试`);
  }
  return status;
}

async function appVersion(appPath) {
  const result = await run("/usr/bin/defaults", ["read", join(appPath, "Contents", "Info"), "CFBundleShortVersionString"], { capture: true, allowFailure: true });
  return result.code === 0 ? result.stdout.trim() : "unknown";
}

async function qwenWorkProcessIdentity() {
  const result = await run(
    "/usr/bin/osascript",
    ["-e", `tell application "System Events" to get unix id of first application process whose bundle identifier is "${DEFAULT_BUNDLE_ID}"`],
    { capture: true, allowFailure: true },
  );
  const pid = Number(result.stdout.trim());
  if (result.code !== 0 || !Number.isInteger(pid) || pid <= 0) return null;
  const command = await run("/bin/ps", ["-p", String(pid), "-o", "command="], { capture: true, allowFailure: true });
  return {
    pid,
    bundle_id: DEFAULT_BUNDLE_ID,
    command: command.stdout.trim() || null,
    captured_at: new Date().toISOString(),
  };
}

export async function querySessions(sessionDb) {
  await access(sessionDb);
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotDir = await mkdtemp(join(tmpdir(), "qwenwork-agents-snapshot-"));
    const snapshotDb = join(snapshotDir, "agents.db");
    try {
      await copyFile(sessionDb, snapshotDb);
      await copyFile(`${sessionDb}-wal`, `${snapshotDb}-wal`).catch((error) => {
        if (error?.code !== "ENOENT") throw error;
      });
      await copyFile(`${sessionDb}-shm`, `${snapshotDb}-shm`).catch((error) => {
        if (error?.code !== "ENOENT") throw error;
      });
      const integrity = await run("/usr/bin/sqlite3", ["-readonly", snapshotDb, "PRAGMA quick_check;"], { capture: true });
      if (integrity.stdout.trim() !== "ok") {
        throw new Error(`QwenWork 状态库快照校验失败：${integrity.stdout.trim() || "无结果"}`);
      }
      const query = `
SELECT
  chats.id AS conversationId,
  sub_chats.id AS subChatId,
  sub_chats.session_id AS sessionId,
  chats.local_project_id AS localProjectId,
  local_projects.name AS projectName,
  chats.name AS conversationName,
  COALESCE(
    json_extract(local_projects.root_paths, '$[0]'),
    projects.path,
    chats.worktree_path
  ) AS cwd,
  CASE
    WHEN sub_chats.stream_id IS NOT NULL THEN 'running'
    WHEN json_extract(chats.ext, '$.taskStatus') IS NOT NULL
      THEN json_extract(chats.ext, '$.taskStatus')
    ELSE 'ready'
  END AS status,
  sub_chats.stream_id AS streamId,
  sub_chats.model_level AS modelLevel,
  CASE WHEN sub_chats.updated_at < 100000000000 THEN sub_chats.updated_at * 1000 ELSE sub_chats.updated_at END AS updatedAt,
  CASE WHEN sub_chats.created_at < 100000000000 THEN sub_chats.created_at * 1000 ELSE sub_chats.created_at END AS createdAt,
  (
    SELECT messages.searchable_text
    FROM messages
    WHERE messages.sub_chat_id = sub_chats.id
      AND messages.role = 'assistant'
      AND trim(COALESCE(messages.searchable_text, '')) <> ''
    ORDER BY messages.sequence DESC, messages.updated_at DESC
    LIMIT 1
  ) AS finalText,
  (
    SELECT messages.message_id
    FROM messages
    WHERE messages.sub_chat_id = sub_chats.id
      AND messages.role = 'assistant'
    ORDER BY messages.sequence DESC, messages.updated_at DESC
    LIMIT 1
  ) AS assistantMessageId
FROM sub_chats
INNER JOIN chats ON chats.id = sub_chats.chat_id
LEFT JOIN local_projects ON local_projects.id = chats.local_project_id
LEFT JOIN projects ON projects.id = chats.project_id
WHERE chats.deleted_at IS NULL
ORDER BY sub_chats.updated_at DESC, sub_chats.id ASC;
`;
      const result = await run("/usr/bin/sqlite3", ["-readonly", "-json", snapshotDb, query], { capture: true });
      return result.stdout.trim() ? JSON.parse(result.stdout) : [];
    } catch (error) {
      lastError = error;
    } finally {
      await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`读取 QwenWork 状态库失败：${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

export async function queryProjects(sessionDb) {
  await access(sessionDb);
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotDir = await mkdtemp(join(tmpdir(), "qwenwork-projects-snapshot-"));
    const snapshotDb = join(snapshotDir, "agents.db");
    try {
      await copyFile(sessionDb, snapshotDb);
      await copyFile(`${sessionDb}-wal`, `${snapshotDb}-wal`).catch((error) => {
        if (error?.code !== "ENOENT") throw error;
      });
      await copyFile(`${sessionDb}-shm`, `${snapshotDb}-shm`).catch((error) => {
        if (error?.code !== "ENOENT") throw error;
      });
      const query = `
SELECT
  id AS projectId,
  name,
  json_extract(root_paths, '$[0]') AS cwd,
  CASE WHEN created_at < 100000000000 THEN created_at * 1000 ELSE created_at END AS createdAt,
  CASE WHEN updated_at < 100000000000 THEN updated_at * 1000 ELSE updated_at END AS updatedAt
FROM local_projects
WHERE deleted_at IS NULL
ORDER BY updated_at DESC, id ASC;
`;
      const result = await run("/usr/bin/sqlite3", ["-readonly", "-json", snapshotDb, query], { capture: true });
      return result.stdout.trim() ? JSON.parse(result.stdout) : [];
    } catch (error) {
      lastError = error;
    } finally {
      await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`读取 QwenWork 项目状态失败：${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

export function chooseQwenAttemptSession(sessions, state, workspace) {
  const expectedProjectId = state.session?.local_project_id || state.workspace_selection?.project_id || "";
  const exact = sessions.filter((session) => (
    session.cwd
    && resolve(String(session.cwd)) === resolve(workspace)
    && (!expectedProjectId || session.localProjectId === expectedProjectId)
  ));
  if (state.session?.session_id) {
    return exact.find((session) => session.sessionId === state.session.session_id) || null;
  }
  if (state.session?.sub_chat_id) {
    return exact.find((session) => session.subChatId === state.session.sub_chat_id) || null;
  }
  if (state.session?.conversation_id) {
    return exact.find((session) => session.conversationId === state.session.conversation_id) || null;
  }

  const baseline = state.session?.baseline || [];
  const sentAt = state.timing?.sent_at ? Date.parse(state.timing.sent_at) : 0;
  const preparedAt = Date.parse(state.timing?.prepared_at || 0);
  // QwenWork 1.0.4 stores session timestamps with one-second precision. The
  // session can therefore be created in the same second just before the
  // post-click sent_at value. Compare new sessions against the start of that
  // second, while existing baseline sessions must still advance explicitly.
  const notBefore = Math.floor((sentAt || preparedAt) / 1000) * 1000;
  return exact
    .filter((session) => {
      const updatedAt = Number(session.updatedAt || session.createdAt || 0);
      const previous = session.subChatId
        ? baseline.find((item) => item.sub_chat_id === session.subChatId)
        : baseline.find((item) => item.conversation_id === session.conversationId);
      if (previous) return updatedAt > Number(previous.updated_at_ms || 0);
      return updatedAt >= notBefore;
    })
    .sort((left, right) => Number(right.updatedAt || 0) - Number(left.updatedAt || 0))[0] || null;
}

function rememberSession(state, session) {
  state.session = {
    ...state.session,
    conversation_id: session.conversationId,
    sub_chat_id: session.subChatId || null,
    session_id: session.sessionId || null,
    local_project_id: session.localProjectId || state.session?.local_project_id || null,
    project_name: session.projectName || state.session?.project_name || null,
    conversation_name: session.conversationName || null,
    cwd: session.cwd,
    raw_status: session.status,
    stream_id: session.streamId || null,
    model_level: session.modelLevel || null,
    updated_at_ms: session.updatedAt || null,
  };
  return session;
}

async function waitForEndpoint(endpoint, timeoutSeconds) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    if (await endpointReady(endpoint)) return;
    await sleep(500);
  }
  throw new Error(`等待 QwenWork 调试端口超时：${endpoint}`);
}

async function waitForQwenWorkStopped(config, dependencies, timeoutSeconds = 15) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    const [processIdentity, ready] = await Promise.all([
      dependencies.processIdentity(),
      dependencies.endpointReady(config.endpoint),
    ]);
    if (!processIdentity && !ready) return;
    await dependencies.sleep(500);
  }
  throw new Error(`QwenWork 旧进程或调试端口未在 ${timeoutSeconds} 秒内退出`);
}

export async function restartQwenWork(config, overrides = {}) {
  const dependencies = {
    run,
    sleep,
    endpointReady,
    waitForEndpoint,
    processIdentity: qwenWorkProcessIdentity,
    querySessions,
    launchAttempts: 3,
    retryDelayMilliseconds: 2000,
    ...overrides,
  };
  const quitScript = `
tell application "System Events"
  set matches to every application process whose bundle identifier is "${DEFAULT_BUNDLE_ID}"
  if (count of matches) > 0 then
    tell application id "${DEFAULT_BUNDLE_ID}" to quit
  end if
end tell`;
  const stopCurrentInstance = async () => {
    const before = await dependencies.processIdentity();
    await dependencies.run("/usr/bin/osascript", ["-e", quitScript], { allowFailure: true, capture: true });
    try {
      await waitForQwenWorkStopped(config, dependencies);
      return { method: "application-quit", pid: before?.pid || null };
    } catch (error) {
      const current = await dependencies.processIdentity();
      if (!before || !current || current.pid !== before.pid) throw error;
      const expectedExecutable = join(config.appPath, "Contents", "MacOS");
      if (!String(current.command || "").includes(expectedExecutable)) {
        throw new Error(`QwenWork 退出超时，且 PID ${current.pid} 的命令无法核对为目标应用；拒绝发送信号`);
      }
      const terminated = await dependencies.run("/bin/kill", ["-TERM", String(current.pid)], { allowFailure: true, capture: true });
      if (terminated.code !== 0) {
        throw new Error(`QwenWork 正常退出超时，向已核对 PID ${current.pid} 发送 SIGTERM 失败：${terminated.stderr.trim()}`);
      }
      await waitForQwenWorkStopped(config, dependencies, 10);
      return { method: "verified-pid-sigterm", pid: current.pid };
    }
  };
  const [initialProcess, initialEndpoint, sessions] = await Promise.all([
    dependencies.processIdentity(),
    dependencies.endpointReady(config.endpoint),
    dependencies.querySessions(config.sessionDb),
  ]);
  const activeSessions = sessions.filter((session) => session.streamId || classifySessionStatus(session.status).kind === "running");
  if ((initialProcess || initialEndpoint) && activeSessions.length) {
    throw new Error(`QwenWork 当前有 ${activeSessions.length} 个活动任务；拒绝为自动化重启客户端`);
  }
  const stop = await stopCurrentInstance();
  const port = new URL(config.endpoint).port || "9250";
  const attempts = [];
  for (let attempt = 1; attempt <= dependencies.launchAttempts; attempt += 1) {
    let result;
    try {
      result = await dependencies.run(
        "/usr/bin/open",
        ["-na", config.appPath, "--args", "--remote-debugging-address=127.0.0.1", `--remote-debugging-port=${port}`],
        { allowFailure: true, capture: true },
      );
    } catch (error) {
      result = { code: null, stdout: "", stderr: error instanceof Error ? error.message : String(error) };
    }
    const evidence = {
      attempt,
      open_exit_code: result.code,
      open_stderr: String(result.stderr || "").trim().slice(0, 2000) || null,
      endpoint_ready: false,
    };
    attempts.push(evidence);

    try {
      if (result.code === 0) {
        await dependencies.waitForEndpoint(config.endpoint, 45);
        evidence.endpoint_ready = true;
      } else {
        await dependencies.sleep(1000);
        if (await dependencies.endpointReady(config.endpoint)) {
          evidence.endpoint_ready = true;
        } else if (await dependencies.processIdentity()) {
          await dependencies.waitForEndpoint(config.endpoint, 45);
          evidence.endpoint_ready = true;
        }
      }
    } catch (error) {
      evidence.endpoint_error = error instanceof Error ? error.message : String(error);
    }
    if (evidence.endpoint_ready) {
      return {
        status: "READY",
        recovered_after_retry: attempt > 1,
        stop,
        attempts,
      };
    }
    if (attempt < dependencies.launchAttempts) {
      if (await dependencies.processIdentity() || await dependencies.endpointReady(config.endpoint)) {
        await stopCurrentInstance();
      }
      await dependencies.sleep(dependencies.retryDelayMilliseconds * attempt);
    }
  }
  const detail = attempts
    .map((item) => `#${item.attempt}: open=${item.open_exit_code ?? "spawn-error"}${item.endpoint_error ? `, ${item.endpoint_error}` : ""}`)
    .join("；");
  throw Object.assign(
    new Error(`QwenWork 自动启动 ${dependencies.launchAttempts} 次后仍未开放调试端口 ${config.endpoint}：${detail}`),
    { launchAttempts: attempts },
  );
}

export async function prepareClientForNewAttempt(config, state, overrides = {}) {
  const restart = overrides.restart || restartQwenWork;
  const isEndpointReady = overrides.endpointReady || endpointReady;
  if (config.restartApp) {
    state.client.launch = await restart(config);
    return state.client.launch;
  }
  if (!(await isEndpointReady(config.endpoint))) {
    throw new Error(`QwenWork 未开放调试端口 ${config.endpoint}；请添加 --restart-app，或手工以 --remote-debugging-port 启动`);
  }
  return null;
}

async function visibleLocators(locator) {
  const matches = [];
  const count = await locator.count();
  for (let index = 0; index < count; index += 1) {
    const candidate = locator.nth(index);
    if (await candidate.isVisible().catch(() => false)) matches.push(candidate);
  }
  return matches;
}

async function clickExactText(page, value, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const matches = await visibleLocators(page.getByText(value, { exact: true }));
    if (matches.length) {
      await matches[matches.length - 1].click({ timeout });
      return;
    }
    await sleep(250);
  }
  throw new Error(`找不到可见文本：${value}`);
}

async function selectNativeFolder(folderPath, timeoutSeconds) {
  const { stdout } = await run("/usr/bin/swift", [NATIVE_FOLDER_HELPER, DEFAULT_BUNDLE_ID, folderPath, String(timeoutSeconds)], { capture: true });
  try {
    return JSON.parse(stdout.trim());
  } catch {
    throw new Error(`原生文件夹选择器返回了无法识别的结果：${stdout.trim()}`);
  }
}

function projectNameForAttempt(identityInfo, state) {
  const taskId = String(identityInfo.identity.taskId || basename(state.workspace));
  const suffix = taskId.replace(/^07_Website_Generation_task_/, "").slice(-52);
  return `WCB-${suffix}-${state.attempt_id.slice(0, 8)}`;
}

async function openProjectByName(page, projectName, timeout) {
  const deadline = Date.now() + timeout;
  let projectSelectors = [];
  let navigationMethod = null;
  while (Date.now() < deadline) {
    projectSelectors = [];
    const candidates = await visibleLocators(page.locator('.new-task-chat-input button[aria-haspopup="menu"]'));
    for (const candidate of candidates) {
      const ariaLabel = ((await candidate.getAttribute("aria-label")) || "").trim();
      if (ariaLabel && ariaLabel !== "选择权限模式") projectSelectors.push(candidate);
    }
    if (projectSelectors.length === 1) break;
    if (projectSelectors.length > 1) break;

    if (!navigationMethod) {
      const projectLabels = await visibleLocators(page.getByText(projectName, { exact: true }));
      if (projectLabels.length > 1) {
        throw new Error(`QwenWork 侧栏项目“${projectName}”数量异常：${projectLabels.length}`);
      }
      if (projectLabels.length === 1) {
        const projectGroup = projectLabels[0].locator('xpath=ancestor::div[@data-state][1]');
        if (await projectGroup.count() !== 1) throw new Error(`QwenWork 侧栏项目“${projectName}”结构异常`);
        const createTaskButtons = await visibleLocators(projectGroup.getByRole("button", { name: "在项目中新建任务", exact: true }));
        if (createTaskButtons.length !== 1) {
          throw new Error(`QwenWork 侧栏项目“${projectName}”的新任务按钮数量异常：${createTaskButtons.length}`);
        }
        // QwenWork keeps this icon button in the DOM but visually overlays it
        // with the project label until hover. The exact project-scoped button
        // is already unique, so dispatch its DOM click instead of relying on
        // Playwright pointer hit-testing.
        await createTaskButtons[0].evaluate((element) => element.click());
        navigationMethod = "project-sidebar-new-task";
      }
    }
    await sleep(250);
  }
  if (projectSelectors.length !== 1) throw new Error(`QwenWork 当前项目选择按钮数量异常：${projectSelectors.length}`);
  const selector = projectSelectors[0];
  const currentName = ((await selector.getAttribute("aria-label")) || (await selector.innerText())).trim();
  if (currentName !== projectName) {
    await selector.click({ timeout });
    const menu = await waitForUniqueVisible(
      () => visibleLocators(page.getByRole("menu")),
      timeout,
      "QwenWork 项目菜单",
    );
    const label = await waitForUniqueVisible(
      () => visibleLocators(menu.getByText(projectName, { exact: true })),
      timeout,
      `QwenWork 项目菜单项“${projectName}”`,
    );
    const menuItem = label.locator('xpath=ancestor-or-self::*[@role="menuitem" or @role="menuitemradio"][1]');
    if (await menuItem.count() !== 1) throw new Error(`QwenWork 项目菜单项“${projectName}”结构异常`);
    await menuItem.click({ timeout });
    const selectionDeadline = Date.now() + timeout;
    while (Date.now() < selectionDeadline) {
      const actual = ((await selector.getAttribute("aria-label")) || (await selector.innerText())).trim();
      if (actual === projectName) break;
      await sleep(250);
    }
    const actual = ((await selector.getAttribute("aria-label")) || (await selector.innerText())).trim();
    if (actual !== projectName) throw new Error(`QwenWork 未回读目标项目“${projectName}”`);
    navigationMethod = "project-menu-selection";
  }
  await waitForUniqueVisible(
    () => visibleLocators(page.locator('[data-voice-input-target="chat-input"]')),
    timeout,
    "QwenWork Prompt 输入框",
  );
  return { opened: true, method: navigationMethod || "already-selected", project_name: projectName };
}

async function createQwenProject(page, config, state, identityInfo, timeout) {
  const existing = (await queryProjects(config.sessionDb))
    .filter((project) => project.cwd && resolve(String(project.cwd)) === config.workspace);
  if (existing.length) {
    if (existing.length !== 1 || !state.retry) {
      throw new Error(`QwenWork 已存在 ${existing.length} 个绑定当前工作空间的项目；拒绝覆盖或猜测复用`);
    }
    const opened = await openProjectByName(page, existing[0].name, timeout);
    return {
      requested_path: config.workspace,
      confirmed_path: resolve(String(existing[0].cwd)),
      project_id: existing[0].projectId,
      project_name: existing[0].name,
      method: "existing-project-from-pre-send-retry",
      opened,
    };
  }

  const baselineProjectIds = new Set((await queryProjects(config.sessionDb)).map((project) => project.projectId));
  const newProjectButtons = await visibleLocators(page.locator('button[aria-label="新建项目"]'));
  if (!newProjectButtons.length) throw new Error("QwenWork 找不到“新建项目”入口");
  await newProjectButtons[newProjectButtons.length - 1].evaluate((element) => element.click());
  const dialog = page.getByRole("dialog", { name: "新建个人项目" });
  await dialog.waitFor({ state: "visible", timeout });
  const projectName = projectNameForAttempt(identityInfo, state);
  await dialog.getByRole("textbox", { name: "项目名称" }).fill(projectName, { timeout });

  const pathPicker = dialog.locator('[data-slot="path-picker-trigger"]');
  if (await pathPicker.count() !== 1) throw new Error("QwenWork 新建项目对话框缺少唯一的目录选择器");
  await pathPicker.evaluate((element) => element.click());
  const native = await selectNativeFolder(config.workspace, config.timeoutSeconds);
  const expectedLabel = basename(config.workspace);
  const selectedLabel = (await dialog.locator('[data-slot="path-picker-value"]').innerText()).trim();
  if (selectedLabel !== expectedLabel) {
    throw new Error(`QwenWork 原生目录选择回读不一致：${selectedLabel || "<空>"} vs ${expectedLabel}`);
  }
  await dialog.getByRole("button", { name: "新建项目", exact: true }).click({ timeout });
  await dialog.waitFor({ state: "hidden", timeout });

  const deadline = Date.now() + timeout;
  let matches = [];
  while (Date.now() < deadline) {
    matches = (await queryProjects(config.sessionDb)).filter((project) => (
      !baselineProjectIds.has(project.projectId)
      && project.cwd
      && resolve(String(project.cwd)) === config.workspace
    ));
    if (matches.length === 1) break;
    if (matches.length > 1) throw new Error(`QwenWork 为当前工作空间创建了 ${matches.length} 个新项目`);
    await sleep(250);
  }
  if (matches.length !== 1) throw new Error(`QwenWork 项目数据库未回读目标绝对路径：${config.workspace}`);
  const project = matches[0];
  const opened = await openProjectByName(page, project.name, timeout);
  return {
    requested_path: config.workspace,
    selected_label: selectedLabel,
    confirmed_path: resolve(String(project.cwd)),
    project_id: project.projectId,
    project_name: project.name,
    method: "project-dialog+macos-accessibility+agents-sqlite",
    native,
    opened,
  };
}

export async function ensureModel(page, model, timeout) {
  const trigger = await waitForUniqueVisible(
    () => visibleLocators(page.locator(".new-task-model-selector button")),
    timeout,
    "QwenWork 模型选择按钮",
  );
  const current = ((await trigger.getAttribute("title")) || (await trigger.innerText())).trim();
  if (!current) throw new Error("QwenWork 当前模型显示值为空");
  if (!model) {
    return {
      mode: "current",
      requested_model: null,
      actual_model: current,
      method: "visible-current-value",
    };
  }
  if (current === model) {
    return {
      mode: "explicit",
      requested_model: model,
      actual_model: current,
      method: "visible-current-value",
    };
  }

  if (await trigger.getAttribute("aria-expanded") !== "true") {
    await trigger.click({ timeout });
  }
  const menu = await waitForUniqueVisible(
    () => visibleLocators(page.locator('[role="menu"]')),
    timeout,
    "QwenWork 模型下拉框",
  );
  const label = await waitForUniqueVisible(
    () => visibleLocators(menu.getByText(model, { exact: true })),
    timeout,
    `QwenWork 模型选项“${model}”`,
  );
  const option = label.locator('xpath=ancestor-or-self::*[@role="menuitem"][1]');
  if (await option.count() !== 1) throw new Error(`QwenWork 模型选项“${model}”结构异常`);
  await option.click({ timeout });

  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const actual = ((await trigger.getAttribute("title")) || (await trigger.innerText())).trim();
    if (actual === model) {
      return {
        mode: "explicit",
        requested_model: model,
        actual_model: actual,
        method: "dropdown-selection+trigger-readback",
      };
    }
    await sleep(250);
  }
  throw new Error(`QwenWork 未回读目标模型“${model}”`);
}

async function inspectPermissionMode(page) {
  const triggers = await visibleLocators(page.locator('button[aria-label="选择权限模式"]'));
  if (triggers.length !== 1) {
    return { available: false, reason: `visible-trigger-count:${triggers.length}`, mode: "unknown", label: "" };
  }
  const trigger = triggers[0];
  const label = (await trigger.innerText().catch(() => "")).trim();
  const mode = /完全访问(?:权限)?|Full access/i.test(label) ? "full-access"
    : /默认权限|Default permission/i.test(label) ? "default-sandbox"
      : "unknown";
  return {
    available: true,
    reason: null,
    mode,
    label,
    enabled: await trigger.isEnabled().catch(() => false),
  };
}

async function ensurePermissionMode(page, requestedMode, timeout) {
  let before = await inspectPermissionMode(page);
  if (!before.available) throw new Error(`QwenWork 权限设置不可用：${before.reason}`);
  if (requestedMode === "current") {
    return { requested_mode: requestedMode, confirmed_mode: before.mode, changed: false, method: "visible-current-value" };
  }
  if (before.mode === "full-access") {
    return { requested_mode: requestedMode, confirmed_mode: before.mode, changed: false, method: "visible-current-value" };
  }
  const enableDeadline = Date.now() + timeout;
  while (!before.enabled && Date.now() < enableDeadline) {
    await sleep(250);
    before = await inspectPermissionMode(page);
    if (!before.available) throw new Error(`QwenWork 权限设置不可用：${before.reason}`);
    if (before.mode === "full-access") {
      return { requested_mode: requestedMode, confirmed_mode: before.mode, changed: false, method: "visible-current-value" };
    }
  }
  if (!before.enabled) throw new Error(`等待 QwenWork 权限设置可操作超时（${timeout}ms）`);

  const trigger = (await visibleLocators(page.locator('button[aria-label="选择权限模式"]')))[0];
  await trigger.click({ timeout });
  const menu = page.getByRole("menu");
  await menu.waitFor({ state: "visible", timeout });
  const fullAccess = menu.getByRole("menuitemradio").filter({ hasText: /完全访问权限|Full access/i });
  if (await fullAccess.count() !== 1) throw new Error("QwenWork 权限菜单缺少唯一的“完全访问权限”选项");
  await fullAccess.click({ timeout });

  const dialog = page.getByRole("dialog").filter({ hasText: /启用完全访问权限|Enable full access/i });
  await dialog.waitFor({ state: "visible", timeout });
  await dialog.getByRole("button", { name: /启用完全访问权限|Enable full access/i }).click({ timeout });

  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const current = await inspectPermissionMode(page);
    if (current.available && current.mode === "full-access") {
      return {
        requested_mode: requestedMode,
        confirmed_mode: current.mode,
        changed: true,
        method: "permission-menu+risk-confirmation",
      };
    }
    await sleep(250);
  }
  throw new Error("QwenWork 未回读“允许完全访问”状态");
}

function hasWorkspaceChanges(state) {
  const changes = state.artifacts?.changes;
  return ["added", "modified", "removed"].some((key) => Array.isArray(changes?.[key]) && changes[key].length > 0);
}

async function archiveRetryablePreSendFailure(config, state) {
  if (state.phase !== "INFRA_FAILED" || state.timing?.sent_at || hasWorkspaceChanges(state)) {
    throw new Error("只允许重试 Prompt 发送前且候选 workspace 零变化的 INFRA_FAILED");
  }
  const archiveDir = join(dirname(config.outputDir), ".attempts", basename(config.outputDir), state.attempt_id);
  await access(archiveDir).then(
    () => { throw new Error(`重试归档目录已存在：${archiveDir}`); },
    (error) => { if (error?.code !== "ENOENT") throw error; },
  );
  await mkdir(dirname(archiveDir), { recursive: true });
  await rename(config.outputDir, archiveDir);

  const archivedState = structuredClone(state);
  archivedState.evidence.screenshots = (archivedState.evidence?.screenshots || []).map((path) => (
    path.startsWith(`${config.outputDir}/`) ? `${archiveDir}/${path.slice(config.outputDir.length + 1)}` : path
  ));
  archivedState.archive = { archived_at: new Date().toISOString(), archive_dir: archiveDir };
  await atomicWriteJson(join(archiveDir, "automation_state.json"), archivedState);
  await atomicWriteJson(join(archiveDir, "result.json"), archivedState);
  return archiveDir;
}

async function findPromptEditor(page, timeout) {
  const candidates = [
    page.locator('[data-voice-input-target="chat-input"]'),
    page.getByPlaceholder(/输入你的问题|拖入文件|调用技能与指令/),
    page.locator("textarea:visible"),
    page.locator('[contenteditable="true"]:visible'),
  ];
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    for (const locator of candidates) {
      const matches = await visibleLocators(locator);
      if (matches.length) return matches[matches.length - 1];
    }
    await sleep(250);
  }
  throw new Error("找不到 Prompt 输入框");
}

async function clickSend(page, editor, timeout) {
  const labelled = page.locator('button[aria-label*="发送"]:visible, button[title*="发送"]:visible, [role="button"][aria-label*="发送"]:visible, button[aria-label*="Send"]:visible');
  const labelledMatches = await visibleLocators(labelled);
  if (labelledMatches.length) {
    await labelledMatches[labelledMatches.length - 1].click({ timeout });
    return "accessible-label";
  }
  const editorBox = await editor.boundingBox();
  const nearby = [];
  for (const candidate of await visibleLocators(page.locator('button:visible, [role="button"]:visible'))) {
    const box = await candidate.boundingBox();
    if (!box || !editorBox) continue;
    const centerY = box.y + box.height / 2;
    if (centerY >= editorBox.y - 20 && centerY <= editorBox.y + editorBox.height + 20 && box.x >= editorBox.x + editorBox.width * 0.65) {
      nearby.push({ candidate, x: box.x });
    }
  }
  nearby.sort((left, right) => right.x - left.x);
  for (const { candidate } of nearby) {
    if (await candidate.isEnabled().catch(() => false)) {
      await candidate.click({ timeout });
      return "rightmost-composer-button";
    }
  }
  await editor.press("Enter", { timeout });
  return "enter-key-fallback";
}

async function chooseQwenWorkPage(browser, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const pages = browser.contexts().flatMap((context) => context.pages());
    for (const page of pages) if (/QwenWork/i.test(await page.title().catch(() => ""))) return page;
    if (pages.length === 1) return pages[0];
    await sleep(250);
  }
  throw new Error("调试端口已连接，但找不到 QwenWork 主页面");
}

async function captureAttemptSession(config, state, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const session = chooseQwenAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
    if (session?.sessionId) {
      rememberSession(state, session);
      state.session.captured_at = new Date().toISOString();
      return session;
    }
    await sleep(250);
  }
  return null;
}

export function hasStableConversationId(state) {
  return Boolean(state.session?.session_id && state.session?.conversation_id);
}

async function openAttemptConversation(page, config, state, timeout) {
  if (!hasStableConversationId(state)) return { opened: false, reason: "stable-session-id-unavailable" };
  const session = chooseQwenAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
  if (!session) return { opened: false, reason: "session-not-found", session_id: state.session.session_id };
  rememberSession(state, session);
  const projectName = session.projectName || state.session.project_name || state.workspace_selection?.project_name;
  if (!projectName) return { opened: false, reason: "project-name-unavailable", session_id: session.sessionId };
  const project = await openProjectByName(page, projectName, timeout);
  const projectSessions = (await querySessions(config.sessionDb)).filter((candidate) => (
    candidate.cwd && resolve(String(candidate.cwd)) === config.workspace
  ));
  if (projectSessions.length !== 1) {
    return {
      opened: false,
      reason: `project-session-count:${projectSessions.length}`,
      session_id: session.sessionId,
      project,
    };
  }
  return {
    opened: true,
    conversation_id: session.conversationId,
    session_id: session.sessionId,
    method: "project-selection+unique-project-session+agents-sqlite",
    project,
  };
}

export async function inspectPendingAttention(page) {
  const attentionContainers = page.locator('[data-testid="pending-sandbox-panel"]:visible, [role="dialog"]:visible');
  const attentionButtons = attentionContainers.getByRole("button", { name: /允许|批准|确认执行|始终允许|Allow|Approve|Deny|拒绝/ });
  const attention = [];
  for (const button of await visibleLocators(attentionButtons)) {
    const name = (await button.innerText().catch(() => "")) || (await button.getAttribute("aria-label")) || "";
    if (name.trim()) attention.push(name.trim());
  }
  return [...new Set(attention)];
}

async function inspectDom(page) {
  const stop = page.locator('button[aria-label*="停止"]:visible, button[title*="停止"]:visible, button[aria-label*="Stop"]:visible, button[title*="Stop"]:visible');
  const running = (await visibleLocators(stop)).length > 0;
  const attention = await inspectPendingAttention(page);
  const agentTurns = page.locator('[data-message-author-role="assistant"]:visible, [data-role="assistant"]:visible, [class*="assistant-message"]:visible');
  const agentValues = await agentTurns.allInnerTexts().catch(() => []);
  const agentText = agentValues.map((value) => value.trim()).filter(Boolean).at(-1) || "";
  const explicitFinished = false;
  const emptyConversation = agentValues.length === 0;
  const rawStatus = "";
  const responseSelectors = [
    '.cr-agent__content:visible .cr-markdown:visible',
    '[data-message-author-role="assistant"]:visible',
    '[data-testid*="assistant"]:visible',
    '.assistant-message:visible',
    '[class*="assistant"] [class*="markdown"]:visible',
    '[class*="response"] [class*="markdown"]:visible',
  ];
  let finalText = "";
  for (const selector of responseSelectors) {
    const values = await page.locator(selector).allInnerTexts().catch(() => []);
    const candidate = values.map((value) => value.trim()).filter(Boolean).at(-1) || "";
    if (candidate) {
      finalText = candidate;
      break;
    }
  }
  return {
    running,
    attention,
    emptyConversation,
    explicitFinished,
    agentText: agentText.slice(-50000),
    finalText: finalText.slice(-50000),
    rawStatus,
    status: classifyDomStatus({ running, agentText, rawStatus }),
  };
}

function observationFailureReason(error) {
  const message = error instanceof Error ? error.message : String(error);
  return /target page|browser has been closed|websocket|econnrefused|connection closed|session closed/i.test(message)
    ? "client-disconnected"
    : "post-send-observation-failed";
}

async function persistNeedsAttention(config, state, identityInfo, reason, error, page = null, screenshotName = null) {
  if (page && screenshotName) await takeScreenshot(page, config, state, screenshotName).catch(() => {});
  transitionState(state, "NEEDS_ATTENTION", { reason });
  state.error = error;
  state.runtime ||= {};
  state.runtime.heartbeat_at = new Date().toISOString();
  await saveState(config, state);
  await updateExecutionRecord(config, identityInfo, {
    clientVersion: state.client.version,
    execution: { status: "pending", error },
  });
  return state;
}

async function cancelTimedOutAttempt(page, config, state, identityInfo, lastDom, deadlineAt) {
  state.timeout = {
    deadline_at: new Date(deadlineAt).toISOString(),
    triggered_at: new Date().toISOString(),
    stop_requested_at: null,
    cancellation_confirmed: false,
    cancellation_source: null,
    quiescence: null,
  };
  await takeScreenshot(page, config, state, "10-timeout-before-stop.png");
  const currentDom = await inspectDom(page);
  const session = chooseQwenAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
  if (session) {
    rememberSession(state, session);
    const classification = classifySessionStatus(session.status);
    if (classification.kind === "success") {
      await takeScreenshot(page, config, state, "10-succeeded-at-timeout-boundary.png");
      return finalize(config, state, identityInfo, "SUCCEEDED", {
        terminalSource: "qwenwork-session-db",
        finalText: session.finalText || currentDom.finalText || lastDom.finalText,
      });
    }
    if (classification.kind === "failure") {
      await takeScreenshot(page, config, state, "10-failed-at-timeout-boundary.png");
      return finalize(config, state, identityInfo, "INFRA_FAILED", {
        terminalSource: "qwenwork-session-db",
        error: `QwenWork conversation 终态：${session.status}`,
        finalText: session.finalText || currentDom.finalText || lastDom.finalText,
      });
    }
  }
  if (hasTrustedDomCompletion({
    ...currentDom,
    finalText: currentDom.finalText || lastDom.finalText,
  })) {
    await takeScreenshot(page, config, state, "10-succeeded-at-timeout-boundary.png");
    return finalize(config, state, identityInfo, "SUCCEEDED", {
      terminalSource: "qwenwork-dom-completion",
      finalText: currentDom.finalText || lastDom.finalText,
    });
  }
  if (currentDom.status.kind === "failure") {
    await takeScreenshot(page, config, state, "10-failed-at-timeout-boundary.png");
    return finalize(config, state, identityInfo, "INFRA_FAILED", {
      terminalSource: "qwenwork-dom-completion",
      error: "QwenWork 页面在超时边界显示执行失败终态",
      finalText: currentDom.finalText || lastDom.finalText,
    });
  }

  const stopButtons = await visibleLocators(page.locator('button[aria-label*="停止"]:visible, button[title*="停止"]:visible, button[aria-label*="Stop"]:visible, button[title*="Stop"]:visible'));
  if (!currentDom.running || stopButtons.length !== 1) {
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "timeout-stop-control-unavailable",
      `超过 ${config.runTimeoutSeconds} 秒，但无法唯一确认并停止当前 QwenWork 会话`,
      page,
      "10-timeout-stop-unavailable.png",
    );
  }

  state.timeout.stop_requested_at = new Date().toISOString();
  await stopButtons[0].click({ timeout: config.timeoutSeconds * 1000 });
  await saveState(config, state);
  await takeScreenshot(page, config, state, "10-timeout-stop-requested.png");

  const cancelDeadline = Date.now() + config.timeoutSeconds * 1000;
  let stableNonRunningPolls = 0;
  let cancellationSource = null;
  let finalText = currentDom.finalText || lastDom.finalText;
  while (Date.now() < cancelDeadline) {
    const dom = await inspectDom(page);
    finalText = dom.finalText || finalText;
    const currentSession = chooseQwenAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
    if (currentSession) {
      rememberSession(state, currentSession);
      finalText = currentSession.finalText || finalText;
      const classification = classifySessionStatus(currentSession.status);
      if (classification.kind === "success") {
        cancellationSource = "qwenwork-session-db-terminal-after-stop";
        break;
      }
      if (classification.kind === "failure") {
        cancellationSource = "qwenwork-session-db";
        break;
      }
    }
    if (dom.status.kind === "success") {
      cancellationSource = "qwenwork-dom-terminal-after-stop";
      break;
    }
    if (dom.status.kind === "failure") {
      cancellationSource = "qwenwork-dom-cancelled";
      break;
    }
    if (!dom.running) stableNonRunningPolls += 1;
    else stableNonRunningPolls = 0;
    if (stableNonRunningPolls >= 2) {
      cancellationSource = "qwenwork-dom-non-running";
      break;
    }
    await sleep(config.pollIntervalSeconds * 1000);
  }
  if (!cancellationSource) {
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "timeout-cancellation-unconfirmed",
      `超过 ${config.runTimeoutSeconds} 秒，已请求停止但无法确认 QwenWork 不再运行`,
      page,
      "10-timeout-cancellation-unconfirmed.png",
    );
  }

  state.timeout.cancellation_source = cancellationSource;
  state.timeout.cancellation_observed_at = new Date().toISOString();
  const before = await snapshotTree(config.candidateWorkspace);
  await sleep(config.postCancelQuiescenceSeconds * 1000);
  const after = await snapshotTree(config.candidateWorkspace);
  state.timeout.quiescence = {
    observed_seconds: config.postCancelQuiescenceSeconds,
    before_sha256: before.sha256,
    after_sha256: after.sha256,
    stable: before.sha256 === after.sha256,
  };
  if (!state.timeout.quiescence.stable) {
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "post-timeout-workspace-still-changing",
      "QwenWork 已停止，但候选 workspace 在静默观察窗口内仍发生变化",
      page,
      "10-timeout-workspace-changing.png",
    );
  }
  state.timeout.cancellation_confirmed = true;
  state.timeout.cancellation_confirmed_at = new Date().toISOString();
  await takeScreenshot(page, config, state, "10-timeout-cancelled.png");
  return finalize(config, state, identityInfo, "TIMEOUT", {
    terminalSource: "driver-timeout+cancellation-confirmed",
    error: `超过 ${config.runTimeoutSeconds} 秒，已确认 QwenWork 停止且 workspace 保持静默`,
    finalText,
  });
}

async function inspectApprovalPanels(page, candidateWorkspace) {
  const panels = await visibleLocators(page.locator('[data-testid="pending-sandbox-panel"]'));
  const approvals = [];
  for (const panel of panels) {
    const command = await panel.locator('[class*="commandInline"]').innerText().catch(() => "");
    const buttons = await panel.getByRole("button").allInnerTexts().catch(() => []);
    approvals.push({
      command: command.trim(),
      buttons: buttons.map((value) => value.trim()).filter(Boolean),
      classification: classifyApprovalCommand(command, candidateWorkspace),
    });
  }
  return approvals;
}

async function handleExpectedApprovals(page, config, state) {
  const approvals = await inspectApprovalPanels(page, config.candidateWorkspace);
  if (!approvals.length) return { handled: false, approvals: [] };
  if (approvals.some((approval) => !approval.classification.allow)) {
    return { handled: false, approvals };
  }
  if (!Array.isArray(state.evidence.approvals)) state.evidence.approvals = [];
  await takeScreenshot(page, config, state, `09-approval-before-${state.evidence.approvals.length + 1}.png`);
  const panels = await visibleLocators(page.locator('[data-testid="pending-sandbox-panel"]'));
  if (panels.length !== approvals.length) {
    throw new Error("QwenWork 授权面板数量在检查期间发生变化");
  }
  for (let index = 0; index < approvals.length; index += 1) {
    const allowOnce = panels[index].getByRole("button", { name: /^\s*(?:\d+\s*)?允许\s*$/ });
    const matches = await visibleLocators(allowOnce);
    if (matches.length !== 1) throw new Error("安全授权面板中找不到唯一的单次“允许”按钮");
    await matches[0].click({ timeout: config.timeoutSeconds * 1000 });
    state.evidence.approvals.push({
      at: new Date().toISOString(),
      decision: "allow-once",
      rule: approvals[index].classification.rule,
      command_sha256: createHash("sha256").update(approvals[index].command).digest("hex"),
    });
  }
  await saveState(config, state);
  return { handled: true, approvals };
}

async function saveState(config, state) {
  await atomicWriteJson(config.stateFile, state);
  await atomicWriteJson(config.resultFile, state);
}

async function takeScreenshot(page, config, state, name) {
  const path = join(config.outputDir, name);
  await page.screenshot({ path });
  state.evidence.screenshots.push(path);
  await saveState(config, state);
  return path;
}

async function finalize(config, state, identityInfo, phase, { error = null, terminalSource = null, finalText = "" } = {}) {
  transitionState(state, phase, terminalSource ? { terminal_source: terminalSource } : {});
  const finishedAt = new Date().toISOString();
  state.timing.finished_at = finishedAt;
  state.timing.duration_seconds = state.timing.started_at
    ? Math.max(0, (Date.parse(finishedAt) - Date.parse(state.timing.started_at)) / 1000)
    : null;
  state.error = error;
  state.runtime ||= {};
  state.runtime.heartbeat_at = finishedAt;
  state.evidence.terminal_source = terminalSource;
  const finalSnapshot = await snapshotTree(config.candidateWorkspace);
  state.artifacts.final = finalSnapshot;
  state.artifacts.changes = diffSnapshots(state.artifacts.initial, finalSnapshot);

  const evidenceDir = join(config.workspace, ".web-e2e-evidence", state.attempt_id);
  await mkdir(evidenceDir, { recursive: true });
  const finalScreenshotSource = state.evidence.screenshots.at(-1) || null;
  if (finalScreenshotSource) {
    const finalScreenshot = join(evidenceDir, "final.png");
    await copyFile(finalScreenshotSource, finalScreenshot);
    state.evidence.final_screenshot_path = finalScreenshot;
  }
  let transcriptPath = null;
  if (finalText.trim()) {
    transcriptPath = join(evidenceDir, "final-response.txt");
    await mkdir(dirname(transcriptPath), { recursive: true });
    await writeFile(transcriptPath, `${finalText.trim()}\n`, "utf8");
    state.evidence.final_response = {
      source: "qwenwork-dom",
      sha256: createHash("sha256").update(finalText.trim()).digest("hex"),
      bytes: Buffer.byteLength(finalText.trim(), "utf8"),
    };
    state.evidence.transcript_path = transcriptPath;
  } else {
    state.evidence.final_response = {
      source: "terminal-screenshot",
      text_available: false,
      screenshot_path: state.evidence.final_screenshot_path || null,
    };
  }
  await saveState(config, state);

  const formalStatus = phase === "SUCCEEDED" ? "completed" : phase === "TIMEOUT" ? "timeout" : "execution_error";
  await updateExecutionRecord(config, identityInfo, {
    clientVersion: state.client.version,
    transcriptPath,
    execution: {
      status: formalStatus,
      started_at: state.timing.started_at,
      finished_at: finishedAt,
      duration_seconds: state.timing.duration_seconds,
      error: error,
    },
  });
  return state;
}

export async function observeAttemptOnce(page, config, state, identityInfo) {
  const runStartedAt = Date.parse(state.timing.sent_at || state.timing.started_at || new Date().toISOString());
  const deadline = runStartedAt + config.runTimeoutSeconds * 1000;
  state.runtime ||= {};
  state.runtime.heartbeat_at = new Date().toISOString();
  const approvalResult = await handleExpectedApprovals(page, config, state);
  if (approvalResult.handled) {
    if (new Set(["PROMPT_SENT", "NEEDS_ATTENTION"]).has(state.phase)) {
      transitionState(state, "RUNNING", { safe_approval_handled: true });
    }
    state.error = null;
    await saveState(config, state);
    await updateExecutionRecord(config, identityInfo, {
      clientVersion: state.client.version,
      execution: { status: "pending", error: null },
    });
    return state;
  }
  const dom = await inspectDom(page);
  if (dom.attention.length) {
    await takeScreenshot(page, config, state, "09-needs-attention.png");
    const commands = approvalResult.approvals.map((approval) => approval.command).filter(Boolean);
    transitionState(state, "NEEDS_ATTENTION", {
      reason: "visible-approval",
      buttons: dom.attention,
      command_sha256: commands.map((command) => createHash("sha256").update(command).digest("hex")),
    });
    state.error = commands.length
      ? `QwenWork 等待人工处理：存在未列入安全规则的授权命令（${commands.length} 个）`
      : `QwenWork 等待人工处理：${dom.attention.join(" / ")}`;
    await saveState(config, state);
    await updateExecutionRecord(config, identityInfo, {
      clientVersion: state.client.version,
      execution: { status: "pending", error: state.error },
    });
    return state;
  }

  const sessions = await querySessions(config.sessionDb);
  const session = chooseQwenAttemptSession(sessions, state, config.workspace);
  if (session) {
    rememberSession(state, session);
    const classification = classifySessionStatus(session.status);
    if (classification.kind === "success") {
      await takeScreenshot(page, config, state, "10-succeeded.png");
      return finalize(config, state, identityInfo, "SUCCEEDED", { terminalSource: "qwenwork-session-db", finalText: session.finalText || dom.finalText });
    }
    if (classification.kind === "failure") {
      await takeScreenshot(page, config, state, "10-infra-failed.png");
      return finalize(config, state, identityInfo, "INFRA_FAILED", {
        terminalSource: "qwenwork-session-db",
        error: `QwenWork conversation 终态：${session.status}`,
        finalText: session.finalText || dom.finalText,
      });
    }
    if (classification.kind === "unknown") {
      await takeScreenshot(page, config, state, "09-unknown-session-status.png");
      transitionState(state, "NEEDS_ATTENTION", { reason: "unknown-session-status", raw_status: session.status });
      state.error = `无法识别 QwenWork session 状态：${session.status}`;
      await saveState(config, state);
      await updateExecutionRecord(config, identityInfo, { clientVersion: state.client.version, execution: { status: "pending", error: state.error } });
      return state;
    }
  } else if (hasTrustedDomCompletion(dom)) {
    await takeScreenshot(page, config, state, "10-succeeded.png");
    return finalize(config, state, identityInfo, "SUCCEEDED", {
      terminalSource: "qwenwork-dom-completion",
      finalText: dom.finalText,
    });
  } else if (dom.status.kind === "failure") {
    await takeScreenshot(page, config, state, "10-infra-failed.png");
    return finalize(config, state, identityInfo, "INFRA_FAILED", {
      terminalSource: "qwenwork-dom-completion",
      error: "QwenWork 页面显示执行失败终态",
      finalText: dom.finalText,
    });
  }
  if (new Set(["PROMPT_SENT", "NEEDS_ATTENTION"]).has(state.phase) && (session || dom.running)) {
    transitionState(state, "RUNNING", { recovered_observation: state.phase === "NEEDS_ATTENTION" });
  }
  state.error = null;
  await saveState(config, state);
  await updateExecutionRecord(config, identityInfo, {
    clientVersion: state.client.version,
    execution: { status: "pending", error: null },
  });
  if (Date.now() >= deadline) {
    return cancelTimedOutAttempt(page, config, state, identityInfo, dom, deadline);
  }
  return state;
}

async function waitForTerminal(page, config, state, identityInfo) {
  for (;;) {
    const observed = await observeAttemptOnce(page, config, state, identityInfo);
    if (TERMINAL_PHASES.has(observed.phase) || observed.phase === "NEEDS_ATTENTION") return observed;
    await sleep(config.pollIntervalSeconds * 1000);
  }
}

async function resumeAutomation(config, state, identityInfo) {
  if (TERMINAL_PHASES.has(state.phase)) return state;
  if (!RESUMABLE_PHASES.has(state.phase)) {
    throw new Error(`当前状态 ${state.phase} 尚未进入发送临界区；请检查 QwenWork 后使用新的 --output-dir 重试`);
  }
  state.session ||= { conversation_id: null, session_id: null, sub_chat_id: null, baseline: [] };
  state.runtime ||= {};
  state.runtime.driver_pid = process.pid;
  state.runtime.driver_started_at = new Date().toISOString();
  state.runtime.heartbeat_at = state.runtime.driver_started_at;
  if (config.restartApp && !hasStableConversationId(state)) {
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "client-restart-conversation-id-unavailable",
      "恢复前没有捕获稳定 conversation ID；禁止重启后猜测会话或重发 Prompt",
    );
  }
  let page = null;
  try {
    await requireUnlockedGui();
    if (config.restartApp) {
      state.client.launch = await restartQwenWork(config);
      await saveState(config, state);
    }
    else if (!(await endpointReady(config.endpoint))) throw new Error(`QwenWork 未开放调试端口 ${config.endpoint}`);
    state.client.process = await qwenWorkProcessIdentity();
    const { chromium } = await import("playwright-core");
    const browser = await chromium.connectOverCDP(config.endpoint);
    page = await chooseQwenWorkPage(browser, config.timeoutSeconds * 1000);
    page.setDefaultTimeout(config.timeoutSeconds * 1000);
    await page.bringToFront();
    const stableConversationAvailable = hasStableConversationId(state);
    if (stableConversationAvailable) {
      const opened = await openAttemptConversation(page, config, state, config.timeoutSeconds * 1000);
      state.session.resume_navigation = { ...opened, at: new Date().toISOString() };
      if (!opened.opened) {
        return persistNeedsAttention(
          config,
          state,
          identityInfo,
          "resume-conversation-not-found",
          `无法按稳定 conversation ID 恢复原会话：${opened.reason}`,
          page,
          "09-resume-conversation-not-found.png",
        );
      }
    }
    const session = chooseQwenAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
    const dom = await inspectDom(page);
    if (stableConversationAvailable && !session && dom.emptyConversation) {
      return persistNeedsAttention(
        config,
        state,
        identityInfo,
        "resume-conversation-empty",
        "已按稳定 conversation ID 打开原会话，但 QwenWork 显示暂无对话记录；禁止创建新任务或重发 Prompt",
        page,
        "09-resume-conversation-empty.png",
      );
    }
    if (!session && state.phase === "READY_TO_SEND" && !new Set(["running", "success", "failure"]).has(dom.status.kind)) {
      transitionState(state, "NEEDS_ATTENTION", { reason: "ambiguous-send-boundary" });
      state.error = "发送临界区中断且未找到可确认的 conversation；为避免重复提交，禁止自动重发";
      await takeScreenshot(page, config, state, "09-ambiguous-send-boundary.png");
      await updateExecutionRecord(config, identityInfo, { clientVersion: state.client.version, execution: { status: "pending", error: state.error } });
      return state;
    }
    if (session) {
      rememberSession(state, session);
      if (state.phase === "READY_TO_SEND") transitionState(state, "PROMPT_SENT", { recovered_from_session: true });
    } else if (state.phase === "READY_TO_SEND") {
      transitionState(state, "PROMPT_SENT", { recovered_from_dom: dom.status.status });
    }
    await saveState(config, state);
    return config.observeOnce
      ? observeAttemptOnce(page, config, state, identityInfo)
      : waitForTerminal(page, config, state, identityInfo);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const reason = observationFailureReason(error);
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      reason,
      `${message}；恢复过程未确认原会话终态，禁止重发 Prompt`,
      page,
      "09-resume-observation-failed.png",
    );
  } finally {
    // 入口会在状态落盘后退出进程。不能调用 browser.close()，否则会关闭
    // 用户正在运行的 QwenWork；Playwright 私有连接也不作为稳定 API 使用。
  }
}

function installDriverSignalHandlers(config, state, identityInfo) {
  let handling = false;
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.once(signal, () => {
      if (handling) return;
      handling = true;
      void (async () => {
        const interruptedAt = new Date().toISOString();
        const previousPhase = state.phase;
        state.runtime ||= {};
        state.runtime.interruption = { signal, at: interruptedAt, previous_phase: previousPhase };
        state.runtime.heartbeat_at = interruptedAt;
        if (!TERMINAL_PHASES.has(state.phase)) {
          transitionState(state, "NEEDS_ATTENTION", {
            reason: "driver-interrupted",
            signal,
            previous_phase: previousPhase,
          });
          state.error = `Driver 收到 ${signal}；QwenWork 任务可能仍在运行，必须使用 --resume 观察原会话`;
          await saveState(config, state);
          await updateExecutionRecord(config, identityInfo, {
            clientVersion: state.client.version,
            execution: { status: "pending", error: state.error },
          });
        }
        process.exit(signal === "SIGINT" ? 130 : 143);
      })().catch(() => process.exit(signal === "SIGINT" ? 130 : 143));
    });
  }
}

async function runAutomation(config, identityInfo) {
  await mkdir(config.outputDir, { recursive: true });
  let existingState = await readJsonIfExists(config.stateFile);
  let retryArchive = null;
  if (existingState) {
    assertStateMatches(existingState, config, identityInfo.identity);
    if (TERMINAL_PHASES.has(existingState.phase)) {
      if (!config.retryPreSendFailure) return existingState;
      retryArchive = await archiveRetryablePreSendFailure(config, existingState);
      existingState = null;
    }
  }
  if (existingState) {
    if (!config.resume) throw new Error(`已有未完成状态 ${existingState.phase}；必须使用 --resume，避免重复发送 Prompt`);
    installDriverSignalHandlers(config, existingState, identityInfo);
    return resumeAutomation(config, existingState, identityInfo);
  }
  if (config.resume && !retryArchive) throw new Error("--resume 要求已有 automation_state.json");

  const initialSnapshot = await snapshotTree(config.candidateWorkspace);
  const state = createInitialState(config, identityInfo.identity, initialSnapshot);
  if (retryArchive) {
    state.retry = {
      reason: "pre-send-infra-failure",
      previous_attempt_id: basename(retryArchive),
      archived_at: new Date().toISOString(),
      archive_dir: retryArchive,
    };
  }
  state.timing.started_at = new Date().toISOString();
  await saveState(config, state);
  installDriverSignalHandlers(config, state, identityInfo);
  await updateExecutionRecord(config, identityInfo, {
    clientVersion: "",
    execution: { status: "pending", started_at: state.timing.started_at, finished_at: null, duration_seconds: null, error: null },
  });

  let browser;
  let promptMayHaveBeenSent = false;
  try {
    await requireUnlockedGui();
    await prepareClientForNewAttempt(config, state);
    state.client.version = await appVersion(config.appPath);
    state.client.process = await qwenWorkProcessIdentity();
    transitionState(state, "CLIENT_READY");
    await saveState(config, state);

    const { chromium } = await import("playwright-core");
    browser = await chromium.connectOverCDP(config.endpoint);
    const timeout = config.timeoutSeconds * 1000;
    const page = await chooseQwenWorkPage(browser, timeout);
    page.setDefaultTimeout(timeout);
    await page.bringToFront();
    await takeScreenshot(page, config, state, "01-initial.png");

    await takeScreenshot(page, config, state, "02-before-new-project.png");
    state.workspace_selection = await createQwenProject(page, config, state, identityInfo, timeout);
    state.workspace_selection.confirmed_at = new Date().toISOString();
    state.session.local_project_id = state.workspace_selection.project_id;
    state.session.project_name = state.workspace_selection.project_name;
    transitionState(state, "WORKSPACE_CONFIRMED");
    await takeScreenshot(page, config, state, "04-workspace-selected.png");

    state.permission_selection = await ensurePermissionMode(page, config.permissionMode, timeout);
    transitionState(state, "PERMISSION_CONFIRMED");
    await takeScreenshot(page, config, state, "05-permission-selected.png");

    state.model_selection = await ensureModel(page, config.model, timeout);
    transitionState(state, "MODEL_CONFIRMED");
    await updateExecutionRecord(config, identityInfo, {
      clientVersion: state.client.version,
      modelSelection: state.model_selection,
      execution: { status: "pending", error: null },
    });
    await takeScreenshot(page, config, state, "06-model-selected.png");
    const editor = await findPromptEditor(page, timeout);
    await editor.click({ timeout });
    await editor.fill(config.prompt, { timeout });
    await takeScreenshot(page, config, state, "07-prompt-filled.png");

    state.session.baseline = (await querySessions(config.sessionDb))
      .filter((session) => session.cwd && resolve(String(session.cwd)) === config.workspace)
      .map((session) => ({
        conversation_id: session.conversationId,
        session_id: session.sessionId || null,
        sub_chat_id: session.subChatId || null,
        updated_at_ms: Number(session.updatedAt || session.createdAt || 0),
        raw_status: session.status || "",
      }));
    transitionState(state, "READY_TO_SEND");
    await saveState(config, state);
    state.send_method = await clickSend(page, editor, timeout);
    promptMayHaveBeenSent = true;
    state.timing.sent_at = new Date().toISOString();
    transitionState(state, "PROMPT_SENT");
    await saveState(config, state);
    await captureAttemptSession(config, state, Math.min(timeout, 15000));
    await saveState(config, state);
    await takeScreenshot(page, config, state, "08-prompt-sent.png");
    if (config.detachAfterSubmit) {
      if (!hasStableConversationId(state)) {
        return persistNeedsAttention(
          config,
          state,
          identityInfo,
          "detach-conversation-id-unavailable",
          "Prompt 已发送，但未捕获稳定 conversation ID；禁止后台猜测会话或重复发送",
          page,
          "09-detach-conversation-id-unavailable.png",
        );
      }
      transitionState(state, "RUNNING", { detached_after_submit: true });
      state.error = null;
      state.runtime.heartbeat_at = new Date().toISOString();
      await saveState(config, state);
      await updateExecutionRecord(config, identityInfo, {
        clientVersion: state.client.version,
        execution: { status: "pending", error: null },
      });
      return state;
    }
    return await waitForTerminal(page, config, state, identityInfo);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (error?.launchAttempts) {
      state.client.launch = { status: "FAILED", recovered_after_retry: false, attempts: error.launchAttempts };
    }
    if (promptMayHaveBeenSent || state.phase === "READY_TO_SEND" || state.phase === "PROMPT_SENT" || state.phase === "RUNNING") {
      const reason = observationFailureReason(error);
      transitionState(state, "NEEDS_ATTENTION", { reason });
      state.error = `${message}；Prompt 可能已发送，必须使用 --resume 检查，不能直接重试`;
      await saveState(config, state);
      await updateExecutionRecord(config, identityInfo, { clientVersion: state.client.version, execution: { status: "pending", error: state.error } });
      return state;
    }
    return finalize(config, state, identityInfo, "INFRA_FAILED", { terminalSource: "driver-error", error: message });
  } finally {
    // 仅附着 CDP；进程退出时释放连接，不能关闭目标 Electron 浏览器。
  }
}

async function probe(config) {
  const gui = await guiSessionStatus();
  const checks = {
    app_exists: true,
    client_version: await appVersion(config.appPath),
    endpoint_ready: await endpointReady(config.endpoint),
    session_database_readable: false,
    session_count: null,
    sqlite3: false,
    gui_session_unlocked: gui.unlocked,
    frontmost_application: gui.frontmost_application,
    project_database_readable: false,
    project_count: null,
    new_project_action_available: false,
    prompt_editor_available: false,
    model_selector_available: false,
    permission_setting_available: false,
    native_folder_helper_available: false,
    blocking_dialog_count: null,
  };
  try {
    const sqlite = await run("/usr/bin/sqlite3", ["--version"], { capture: true, allowFailure: true });
    checks.sqlite3 = sqlite.code === 0;
    const sessions = await querySessions(config.sessionDb);
    const projects = await queryProjects(config.sessionDb);
    checks.session_database_readable = true;
    checks.session_count = sessions.length;
    checks.project_database_readable = true;
    checks.project_count = projects.length;
    await access(NATIVE_FOLDER_HELPER);
    checks.native_folder_helper_available = true;
  } catch (error) {
    checks.session_database_error = error instanceof Error ? error.message : String(error);
  }
  if (checks.endpoint_ready) {
    try {
      const { chromium } = await import("playwright-core");
      const browser = await chromium.connectOverCDP(config.endpoint);
      const page = await chooseQwenWorkPage(browser, config.timeoutSeconds * 1000);
      checks.blocking_dialog_count = (await visibleLocators(page.locator('[role="dialog"]'))).length;
      checks.new_project_action_available = (await visibleLocators(page.locator('button[aria-label="新建项目"]'))).length > 0;
      checks.prompt_editor_available = (await visibleLocators(page.locator('[data-voice-input-target="chat-input"]'))).length === 1;
      checks.model_selection = await ensureModel(page, "", config.timeoutSeconds * 1000);
      checks.model_selector_available = Boolean(checks.model_selection.actual_model);
      checks.permission_setting = await inspectPermissionMode(page);
      checks.permission_setting_available = checks.permission_setting.available;
    } catch (error) {
      checks.ui_error = error instanceof Error ? error.message : String(error);
    }
  }
  return {
    driver: "qwenwork",
    version: DRIVER_VERSION,
    control_backend: "electron-cdp+qwenwork-project-dialog+macos-accessibility+agents-sqlite",
    terminal_source: "qwenwork-agents-sqlite+qwenwork-dom",
    ready: checks.endpoint_ready && checks.session_database_readable && checks.project_database_readable
      && checks.sqlite3 && checks.gui_session_unlocked && checks.native_folder_helper_available
      && checks.blocking_dialog_count === 0
      && checks.new_project_action_available && checks.prompt_editor_available
      && checks.model_selector_available && checks.permission_setting_available,
    checks,
  };
}

export async function main(argv) {
  let parsed;
  try {
    parsed = parseArgs(argv);
  } catch (error) {
    console.error(error.message);
    console.error(usage());
    return 2;
  }
  if (parsed.help) {
    console.log(usage());
    return 0;
  }
  try {
    const config = await resolveConfig(parsed);
    if (config.probe) {
      const result = await probe(config);
      console.log(JSON.stringify(result, null, 2));
      return result.ready ? 0 : 3;
    }
    const identityInfo = await resolveExecutionIdentity(config);
    const safeConfig = {
      workspace: config.workspace,
      candidateWorkspace: config.candidateWorkspace,
      promptFile: config.promptFile,
      promptSha256: config.promptSha256,
      promptBytes: config.promptBytes,
      requestedUiModel: config.model,
      requestedPermissionMode: config.permissionMode,
      identity: identityInfo.identity,
      endpoint: config.endpoint,
      outputDir: config.outputDir,
      stateFile: config.stateFile,
      executionRecord: config.executionRecord,
      restartApp: config.restartApp,
      resume: config.resume,
      retryPreSendFailure: config.retryPreSendFailure,
      detachAfterSubmit: config.detachAfterSubmit,
      observeOnce: config.observeOnce,
      postCancelQuiescenceSeconds: config.postCancelQuiescenceSeconds,
      dryRun: config.dryRun,
    };
    if (!config.quiet) console.log(JSON.stringify(safeConfig, null, 2));
    if (config.dryRun) return 0;
    const result = await runAutomation(config, identityInfo);
    if (!config.quiet) console.log(`QwenWork 自动化状态：${result.phase}；状态文件：${config.stateFile}`);
    if (result.phase === "SUCCEEDED") return 0;
    if (result.phase === "RUNNING" || result.phase === "PROMPT_SENT") return 0;
    if (result.phase === "NEEDS_ATTENTION") return 3;
    if (result.phase === "TIMEOUT") return 4;
    return 1;
  } catch (error) {
    console.error(`QwenWork 自动化失败：${error.message}`);
    return 1;
  }
}

const isEntrypoint = process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  const exitCode = await main(process.argv.slice(2));
  process.exitCode = exitCode;
  setImmediate(() => process.exit(exitCode));
}
