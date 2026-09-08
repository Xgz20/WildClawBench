#!/usr/bin/env node

import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { realpathSync } from "node:fs";
import { copyFile, mkdir, writeFile } from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_BUNDLE_ID,
  DRIVER_VERSION,
  RESUMABLE_PHASES,
  TERMINAL_PHASES,
  assertStateMatches,
  atomicWriteJson,
  chooseAttemptSession,
  classifySessionStatus,
  createInitialState,
  diffSnapshots,
  parseArgs,
  queryFinalResponse,
  querySessions,
  readJsonIfExists,
  resolveConfig,
  resolveExecutionIdentity,
  snapshotTree,
  transitionState,
  updateExecutionRecord,
} from "./lib.mjs";

function usage() {
  return `AstronStudio Web E2E 单题执行 Driver

用法：
  node driver.mjs --probe [选项]
  node driver.mjs --workspace <单题目录> [选项]

核心选项：
  --model <UI名称>                 可选；指定时选择并回读，省略时保持当前模型与推理强度
  --permission-mode <模式>         current（保持现状）或 full-access（显式开启完全访问）
  --model-id <ID>                  execution_record 模型身份；已有记录时仅校验
  --batch-id <ID> --task-id <ID>   没有 manifest/record 时必须显式提供
  --run-timeout-seconds <秒>       Agent 总执行超时，默认 3600
  --poll-interval-seconds <秒>     终态轮询间隔，默认 2
  --post-cancel-quiescence-seconds <秒> 超时停止后的 workspace 静默观察，默认 5
  --resume                         从已有 automation_state 恢复，禁止重复发送
  --observe-once                   恢复原 thread，只执行一次终态观察
  --restart-app                    确认无其他活动任务后，以本机 CDP 端口重启 AStudio
  --dry-run                        校验输入、身份和状态，不操作 AStudio
  -h, --help                       显示帮助`;
}

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

function run(command, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const { allowFailure = false, capture = false, ...spawnOptions } = options;
    const child = spawn(command, args, {
      stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
      ...spawnOptions,
    });
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
  const frontmost = await run(
    "/usr/bin/osascript",
    ["-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
    { capture: true, allowFailure: true },
  );
  const registry = await run(
    "/usr/sbin/ioreg",
    ["-n", "Root", "-d1"],
    { capture: true, allowFailure: true },
  );
  const frontmostApplication = frontmost.code === 0 ? frontmost.stdout.trim() : "unknown";
  const lockMatch = registry.stdout.match(/"IOConsoleLocked"\s*=\s*(Yes|No)/);
  const screenLocked = lockMatch ? lockMatch[1] === "Yes" : null;
  return {
    frontmost_application: frontmostApplication,
    screen_locked: screenLocked,
    lock_source: lockMatch ? "ioreg.IOConsoleLocked" : "frontmost-application-fallback",
    unlocked: screenLocked === null
      ? frontmost.code === 0 && frontmostApplication.toLowerCase() !== "loginwindow"
      : !screenLocked,
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
  const result = await run(
    "/usr/bin/defaults",
    ["read", join(appPath, "Contents", "Info"), "CFBundleShortVersionString"],
    { capture: true, allowFailure: true },
  );
  return result.code === 0 ? result.stdout.trim() : "unknown";
}

async function astudioProcessIdentity() {
  const result = await run(
    "/usr/bin/osascript",
    ["-e", `tell application "System Events" to get unix id of first application process whose bundle identifier is "${DEFAULT_BUNDLE_ID}"`],
    { capture: true, allowFailure: true },
  );
  const pid = Number(result.stdout.trim());
  if (result.code !== 0 || !Number.isInteger(pid) || pid <= 0) return null;
  const command = await run("/bin/ps", ["-p", String(pid), "-o", "command="], {
    capture: true,
    allowFailure: true,
  });
  return {
    pid,
    bundle_id: DEFAULT_BUNDLE_ID,
    command: command.stdout.trim() || null,
    captured_at: new Date().toISOString(),
  };
}

async function waitForEndpoint(endpoint, timeoutSeconds) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    if (await endpointReady(endpoint)) return;
    await sleep(500);
  }
  throw new Error(`等待 AstronStudio 调试端口超时：${endpoint}`);
}

async function waitForAstudioStopped(config, timeoutSeconds = 20) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    if (!(await astudioProcessIdentity()) && !(await endpointReady(config.endpoint))) return;
    await sleep(500);
  }
  throw new Error(`AstronStudio 旧进程或调试端口未在 ${timeoutSeconds} 秒内退出`);
}

export async function restartAstudio(config, overrides = {}) {
  const dependencies = {
    querySessions,
    processIdentity: astudioProcessIdentity,
    endpointReady,
    run,
    sleep,
    waitForEndpoint,
    waitForStopped: waitForAstudioStopped,
    launchAttempts: 3,
    retryDelayMilliseconds: 2000,
    ...overrides,
  };
  const currentProcess = await dependencies.processIdentity();
  if (currentProcess) {
    const active = (await dependencies.querySessions(config.sessionDb)).filter((session) =>
      new Set(["running", "needs_attention", "pending", "starting"]).has(String(session.status)),
    );
    if (active.length > 0) {
      throw new Error(`AstronStudio 仍有 ${active.length} 个活动或待处理任务，拒绝重启客户端`);
    }
    await dependencies.run(
      "/usr/bin/osascript",
      ["-e", `tell application id "${DEFAULT_BUNDLE_ID}" to quit`],
      { allowFailure: true, capture: true },
    );
    await dependencies.waitForStopped(config);
  }
  const port = new URL(config.endpoint).port || "9240";
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
        evidence.endpoint_ready = await dependencies.endpointReady(config.endpoint);
      }
    } catch (error) {
      evidence.endpoint_error = error instanceof Error ? error.message : String(error);
    }
    if (evidence.endpoint_ready) {
      return { status: "READY", recovered_after_retry: attempt > 1, attempts };
    }
    if (attempt < dependencies.launchAttempts) {
      if (await dependencies.processIdentity() || await dependencies.endpointReady(config.endpoint)) {
        await dependencies.run(
          "/usr/bin/osascript",
          ["-e", `tell application id "${DEFAULT_BUNDLE_ID}" to quit`],
          { allowFailure: true, capture: true },
        );
        await dependencies.waitForStopped(config);
      }
      await dependencies.sleep(dependencies.retryDelayMilliseconds * attempt);
    }
  }
  const detail = attempts
    .map((item) => `#${item.attempt}: open=${item.open_exit_code ?? "spawn-error"}${item.endpoint_error ? `, ${item.endpoint_error}` : ""}`)
    .join("；");
  throw Object.assign(
    new Error(`AstronStudio 自动启动 ${dependencies.launchAttempts} 次后仍未开放调试端口 ${config.endpoint}：${detail}`),
    { launchAttempts: attempts },
  );
}

async function prepareClient(config, state) {
  if (config.restartApp) {
    state.client.launch = await restartAstudio(config);
    return;
  }
  if (!(await endpointReady(config.endpoint))) {
    throw new Error(`AstronStudio 未开放调试端口 ${config.endpoint}；请添加 --restart-app，或手工以 --remote-debugging-port 启动`);
  }
  state.client.launch = { status: "ATTACHED", attempts: [] };
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

export async function dismissOpenMenus(page, timeout) {
  const menus = await visibleLocators(page.getByRole("menu"));
  if (!menus.length) return { closed: false, count: 0 };
  await page.keyboard.press("Escape");
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if ((await visibleLocators(page.getByRole("menu"))).length === 0) {
      return { closed: true, count: menus.length };
    }
    await sleep(100);
  }
  throw new Error(`AstronStudio 已识别菜单弹层未能关闭：${menus.length}`);
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

async function chooseAstudioPage(browser, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const pages = browser.contexts().flatMap((context) => context.pages());
    for (const page of pages) {
      if (/^acode:\/\/app\//.test(page.url()) && /AStudio/i.test(await page.title().catch(() => ""))) {
        return page;
      }
    }
    if (pages.length === 1 && /^acode:\/\/app\//.test(pages[0].url())) return pages[0];
    await sleep(250);
  }
  throw new Error("调试端口已连接，但找不到 AstronStudio 主页面");
}

function threadIdFromUrl(url) {
  try {
    const match = new URL(url).hash.match(/^#\/([^/?#]+)/);
    return match?.[1] ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
}

export async function findNewTaskButtons(page) {
  const byTestId = await visibleLocators(page.getByTestId("new-thread-button"));
  if (byTestId.length === 1) return byTestId;

  const byText = await visibleLocators(page.locator("button").filter({ hasText: /^(?:新建任务|New task)$/i }));
  const exactText = [];
  for (const candidate of byText) {
    if (/^(?:新建任务|New task)$/i.test((await candidate.innerText()).trim())) exactText.push(candidate);
  }
  if (exactText.length === 1) return exactText;

  const byRole = await visibleLocators(page.getByRole("button", { name: /^(?:新建任务|New task)$/i }));
  if (byRole.length === 1) return byRole;
  return byTestId.length > 1 ? byTestId : (exactText.length ? exactText : byRole);
}

async function createFreshTask(page, timeout) {
  const previousThreadId = threadIdFromUrl(page.url());
  const button = await waitForUniqueVisible(
    () => findNewTaskButtons(page),
    timeout,
    "AstronStudio 新建任务按钮",
  );
  await button.click({ timeout });
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const threadId = threadIdFromUrl(page.url());
    const editorVisible = (await visibleLocators(page.getByTestId("composer-editor"))).length === 1;
    if (threadId && threadId !== previousThreadId && editorVisible) {
      return { thread_id_candidate: threadId, previous_thread_id: previousThreadId };
    }
    await sleep(250);
  }
  throw new Error("AstronStudio 新建任务后未进入新的可编辑任务路由");
}

async function visibleWorkspaceTriggers(page) {
  const triggers = [];
  for (const testId of ["workspace-picker-trigger", "project-picker-trigger"]) {
    for (const locator of await visibleLocators(page.getByTestId(testId))) {
      triggers.push({ locator, testId });
    }
  }
  return triggers;
}

export async function inspectWorkspace(page) {
  const triggers = await visibleWorkspaceTriggers(page);
  if (triggers.length !== 1) {
    return { available: false, reason: `visible-trigger-count:${triggers.length}`, path: null, label: null };
  }
  const { locator: trigger, testId } = triggers[0];
  return {
    available: true,
    reason: null,
    path: ((await trigger.getAttribute("title")) || "").trim() || null,
    label: (await trigger.innerText()).trim() || null,
    source_test_id: testId,
  };
}

async function waitForWorkspaceSelection(page, workspace, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const selected = await inspectWorkspace(page);
    if (selected.available && selected.path === workspace) {
      return {
        requested_path: workspace,
        confirmed_path: selected.path,
        confirmed_label: selected.label,
        method: "workspace-trigger-title-readback",
      };
    }
    await sleep(250);
  }
  throw new Error(`AstronStudio 未从 workspace trigger 回读目标绝对路径：${workspace}`);
}

async function closeProjectPicker(page, timeout) {
  const dialogs = await visibleLocators(page.getByRole("dialog"));
  if (!dialogs.length) return;
  await page.keyboard.press("Escape");
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if ((await visibleLocators(page.getByRole("dialog"))).length === 0) return;
    await sleep(100);
  }
  throw new Error("AstronStudio 项目选择弹层未能关闭");
}

async function addProjectByManualPath(page, workspace, timeout) {
  const projectTab = await waitForUniqueVisible(
    async () => {
      const matches = await visibleLocators(page.locator("button").filter({ hasText: /^(?:项目|Projects)$/i }));
      const exact = [];
      for (const button of matches) {
        if (/^(?:项目|Projects)$/i.test((await button.innerText()).trim())) exact.push(button);
      }
      return exact;
    },
    timeout,
    "AstronStudio 项目侧栏标签",
  );
  await projectTab.click({ timeout });
  const addProject = await waitForUniqueVisible(
    () => visibleLocators(page.getByRole("button", { name: /^(?:添加项目|Add project)$/i })),
    timeout,
    "AstronStudio 添加项目侧栏按钮",
  );
  if (!(await addProject.isEnabled())) throw new Error("AstronStudio 添加项目侧栏按钮未启用");
  await addProject.evaluate((button) => button.click());
  const typePath = await waitForUniqueVisible(
    () => visibleLocators(page.getByRole("button", { name: /^(?:输入路径|Type path)$/i })),
    timeout,
    "AstronStudio 输入项目路径按钮",
  );
  await typePath.click({ timeout });
  const pathInput = await waitForUniqueVisible(
    () => visibleLocators(page.getByRole("textbox", { name: /^(?:项目路径|Project path)$/i })),
    timeout,
    "AstronStudio 项目路径输入框",
  );
  await pathInput.fill(workspace, { timeout });
  await pathInput.press("Enter", { timeout });
  return { method: "sidebar-manual-path" };
}

async function selectWorkspace(page, workspace, timeout) {
  const trigger = await waitForUniqueVisible(
    async () => (await visibleWorkspaceTriggers(page)).map(({ locator }) => locator),
    timeout,
    "AstronStudio 项目选择按钮",
  );
  await trigger.click({ timeout });
  const visibleOptions = await visibleLocators(page.getByRole("option"));
  const existingMatches = [];
  for (const option of visibleOptions) {
    const pathNodes = option.locator(".project-picker-path");
    const pathCount = await pathNodes.count();
    if (pathCount !== 1) continue;
    if ((await pathNodes.first().innerText()).trim() === workspace) existingMatches.push(option);
  }
  let backend;
  if (existingMatches.length === 1) {
    await existingMatches[0].click({ timeout });
    backend = { method: "existing-project-option" };
  } else if (existingMatches.length > 1) {
    throw new Error(`AstronStudio 项目列表中目标绝对路径不唯一：${workspace}`);
  } else {
    await closeProjectPicker(page, timeout);
    backend = await addProjectByManualPath(page, workspace, timeout);
  }
  return { backend, page: await waitForWorkspaceSelection(page, workspace, timeout) };
}

function permissionModeFromLabel(label) {
  if (/完全访问|Full access/i.test(label)) return "full-access";
  if (/帮我批准|auto|Auto approve/i.test(label)) return "auto";
  if (/请求批准|approval|required|Ask/i.test(label)) return "approval-required";
  return "unknown";
}

async function inspectPermissionMode(page) {
  const triggers = await visibleLocators(page.locator("button.runtime-permission-trigger"));
  if (triggers.length !== 1) {
    return { available: false, reason: `visible-trigger-count:${triggers.length}`, mode: "unknown", label: "" };
  }
  const label = (await triggers[0].innerText()).trim();
  return {
    available: true,
    reason: null,
    enabled: await triggers[0].isEnabled(),
    mode: permissionModeFromLabel(label),
    label,
  };
}

export async function ensurePermissionMode(page, requestedMode, timeout) {
  let before = await inspectPermissionMode(page);
  if (!before.available) throw new Error(`AstronStudio 权限设置不可用：${before.reason}`);
  if (before.mode === "unknown") throw new Error(`无法识别 AstronStudio 当前权限：${before.label || "空"}`);
  if (requestedMode === "current" || before.mode === "full-access") {
    return {
      requested_mode: requestedMode,
      confirmed_mode: before.mode,
      changed: false,
      method: "visible-current-value",
    };
  }
  if (!before.enabled) throw new Error("AstronStudio 权限按钮当前不可操作");
  const trigger = (await visibleLocators(page.locator("button.runtime-permission-trigger")))[0];
  await trigger.click({ timeout });
  const option = await waitForUniqueVisible(
    () => visibleLocators(page.getByRole("menuitemradio").filter({ hasText: /^(?:完全访问|Full access)/i })),
    timeout,
    "AstronStudio 完全访问选项",
  );
  await option.click({ timeout });
  const confirmButtons = await visibleLocators(page.getByRole("button", { name: /启用完全访问|Enable full access/i }));
  if (confirmButtons.length === 1) await confirmButtons[0].click({ timeout });
  else if (confirmButtons.length > 1) throw new Error(`AstronStudio 完全访问确认按钮数量异常：${confirmButtons.length}`);

  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    before = await inspectPermissionMode(page);
    if (before.available && before.mode === "full-access") {
      return {
        requested_mode: requestedMode,
        confirmed_mode: before.mode,
        changed: true,
        method: "permission-menu+risk-confirmation+trigger-readback",
      };
    }
    await sleep(250);
  }
  throw new Error("AstronStudio 未回读完全访问状态");
}

async function modelTrigger(page) {
  const localized = page.locator('button[aria-label="切换模型和推理设置"], button[aria-label="Change model and reasoning"]');
  return visibleLocators(localized);
}

async function readCurrentModel(page, timeout) {
  const trigger = await waitForUniqueVisible(
    () => modelTrigger(page),
    timeout,
    "AstronStudio 模型与推理设置按钮",
  );
  const lines = (await trigger.innerText()).split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines[0]) throw new Error("AstronStudio 当前模型显示值为空");
  return { trigger, model: lines[0], reasoning: lines.slice(1).join(" ") || null };
}

export async function ensureModel(page, requestedModel, timeout) {
  let current = await readCurrentModel(page, timeout);
  if (!requestedModel) {
    return {
      mode: "current",
      requested_model: null,
      actual_model: current.model,
      reasoning_display: current.reasoning,
      method: "visible-current-value",
    };
  }
  if (current.model === requestedModel) {
    return {
      mode: "explicit",
      requested_model: requestedModel,
      actual_model: current.model,
      reasoning_display: current.reasoning,
      method: "visible-current-value",
    };
  }
  await current.trigger.click({ timeout });
  const modelMenu = await waitForUniqueVisible(
    () => visibleLocators(page.getByRole("menuitem").filter({ hasText: /^(?:模型|Model)/i })),
    timeout,
    "AstronStudio 模型子菜单",
  );
  await modelMenu.hover();
  const option = await waitForUniqueVisible(
    async () => {
      const all = await visibleLocators(page.getByRole("menuitemradio"));
      const matched = [];
      for (const item of all) {
        if ((await item.innerText()).trim() === requestedModel) matched.push(item);
      }
      return matched;
    },
    timeout,
    `AstronStudio 模型选项“${requestedModel}”`,
  );
  await option.click({ timeout });
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    current = await readCurrentModel(page, timeout);
    if (current.model === requestedModel) {
      return {
        mode: "explicit",
        requested_model: requestedModel,
        actual_model: current.model,
        reasoning_display: current.reasoning,
        method: "model-submenu-selection+trigger-readback",
      };
    }
    await sleep(250);
  }
  throw new Error(`AstronStudio 未回读目标模型“${requestedModel}”`);
}

async function findPromptEditor(page, timeout) {
  return waitForUniqueVisible(
    () => visibleLocators(page.getByTestId("composer-editor")),
    timeout,
    "AstronStudio Prompt 输入框",
  );
}

async function clickSend(page, timeout) {
  const button = await waitForUniqueVisible(
    () => visibleLocators(page.locator('button[type="submit"][aria-label="发送消息"], button[type="submit"][aria-label="Send message"]')),
    timeout,
    "AstronStudio 发送按钮",
  );
  if (!(await button.isEnabled())) throw new Error("AstronStudio 发送按钮未启用");
  await button.click({ timeout });
  return "submit-button-accessible-label";
}

async function captureAttemptThread(page, config, state, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const routeThreadId = threadIdFromUrl(page.url());
    const sessions = await querySessions(config.sessionDb);
    const exact = sessions.find((session) =>
      session.conversationId === routeThreadId && resolve(String(session.cwd || "")) === config.workspace,
    );
    const candidate = exact || chooseAttemptSession(sessions, state, config.workspace);
    if (candidate) {
      state.session.conversation_id = candidate.conversationId;
      state.session.dom_conversation_id = routeThreadId === candidate.conversationId ? routeThreadId : null;
      state.session.cwd = candidate.cwd;
      state.session.raw_status = candidate.status;
      state.session.turn_id = candidate.turnId || candidate.activeTurnId || null;
      state.session.updated_at_ms = candidate.updatedAt || null;
      state.session.dom_conversation_captured_at = new Date().toISOString();
      return candidate.conversationId;
    }
    await sleep(250);
  }
  return null;
}

async function openAttemptThread(page, state, timeout) {
  const threadId = state.session?.conversation_id || state.session?.dom_conversation_id || null;
  if (!threadId) return { opened: false, reason: "thread-id-unavailable" };
  if (!/^[A-Za-z0-9._:-]{1,160}$/.test(threadId)) {
    return { opened: false, reason: "thread-id-format-invalid", thread_id: threadId };
  }
  if (threadIdFromUrl(page.url()) !== threadId) {
    await page.evaluate((target) => { window.location.hash = `#/${target}`; }, threadId);
  }
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (threadIdFromUrl(page.url()) === threadId) {
      const editor = await visibleLocators(page.getByTestId("composer-editor"));
      if (editor.length === 1) {
        return { opened: true, thread_id: threadId, method: "astudio-thread-route" };
      }
    }
    await sleep(250);
  }
  return { opened: false, reason: "thread-route-not-confirmed", thread_id: threadId };
}

async function inspectDom(page) {
  const stopButtons = await visibleLocators(page.locator('button[aria-label="停止生成"], button[aria-label="Stop generation"]'));
  const approvalButtons = await visibleLocators(page.getByRole("button", {
    name: /^(?:允许|批准|拒绝|始终允许|Allow|Approve|Deny|Decline|下一题|Next question|提交回答|Submit answers)$/i,
  }));
  const attention = [];
  for (const button of approvalButtons) {
    const text = ((await button.getAttribute("aria-label")) || (await button.innerText())).trim();
    if (text) attention.push(text);
  }
  const assistantRows = page.locator('[data-timeline-row-kind="message"][data-message-role="assistant"]');
  const assistantTexts = await assistantRows.allInnerTexts().catch(() => []);
  const finalText = assistantTexts.map((value) => value.trim()).filter(Boolean).at(-1) || "";
  const visibleErrors = await page.locator('[role="alert"]:visible').allInnerTexts().catch(() => []);
  return {
    running: stopButtons.length > 0,
    attention: [...new Set(attention)],
    finalText: finalText.slice(-50000),
    errors: visibleErrors.map((value) => value.trim()).filter(Boolean).slice(-10),
  };
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
    await writeFile(transcriptPath, `${finalText.trim()}\n`, "utf8");
    state.evidence.final_response = {
      source: "astudio-dom",
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
      error,
    },
  });
  return state;
}

async function persistNeedsAttention(config, state, identityInfo, reason, error, page = null, screenshotName = null) {
  if (page && screenshotName) await takeScreenshot(page, config, state, screenshotName).catch(() => {});
  transitionState(state, "NEEDS_ATTENTION", { reason });
  state.error = error;
  state.runtime.heartbeat_at = new Date().toISOString();
  await saveState(config, state);
  await updateExecutionRecord(config, identityInfo, {
    clientVersion: state.client.version,
    execution: { status: "pending", error },
  });
  return state;
}

async function cancelTimedOutAttempt(page, config, state, identityInfo, lastDom, deadlineAt) {
  const stopButtons = await visibleLocators(page.locator('button[aria-label="停止生成"], button[aria-label="Stop generation"]'));
  if (stopButtons.length !== 1) {
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "timeout-stop-control-unavailable",
      `超过 ${config.runTimeoutSeconds} 秒，但无法唯一确认 AstronStudio 停止按钮`,
      page,
      "10-timeout-stop-unavailable.png",
    );
  }
  await stopButtons[0].click({ timeout: config.timeoutSeconds * 1000 });
  const stopDeadline = Date.now() + config.timeoutSeconds * 1000;
  let stopped = false;
  while (Date.now() < stopDeadline) {
    const session = chooseAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
    const dom = await inspectDom(page);
    if (session && classifySessionStatus(session.status).kind !== "running" && !dom.running) {
      stopped = true;
      break;
    }
    await sleep(500);
  }
  if (!stopped) {
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "timeout-stop-unconfirmed",
      `超过 ${config.runTimeoutSeconds} 秒，已请求停止但无法确认 AstronStudio 不再运行`,
      page,
      "10-timeout-stop-unconfirmed.png",
    );
  }
  const quietBefore = await snapshotTree(config.candidateWorkspace);
  await sleep(config.postCancelQuiescenceSeconds * 1000);
  const quietAfter = await snapshotTree(config.candidateWorkspace);
  if (quietBefore.sha256 !== quietAfter.sha256) {
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "timeout-workspace-not-quiescent",
      "AstronStudio 已停止，但候选 workspace 在静默观察窗口内仍发生变化",
      page,
      "10-timeout-workspace-active.png",
    );
  }
  state.timeout = {
    deadline_at: new Date(deadlineAt).toISOString(),
    stop_requested_at: new Date().toISOString(),
    stop_confirmed: true,
    workspace_quiescent: true,
    cancellation_confirmed: true,
    quiescence: {
      stable: true,
      before_sha256: quietBefore.sha256,
      after_sha256: quietAfter.sha256,
      observed_seconds: config.postCancelQuiescenceSeconds,
    },
    last_dom_running: lastDom.running,
  };
  await takeScreenshot(page, config, state, "10-timeout.png");
  return finalize(config, state, identityInfo, "TIMEOUT", {
    terminalSource: "astudio-session-db+stop-confirmation+workspace-quiescence",
    error: `超过 ${config.runTimeoutSeconds} 秒，已确认 AstronStudio 停止且 workspace 保持静默`,
    finalText: lastDom.finalText,
  });
}

export async function observeAttemptOnce(page, config, state, identityInfo) {
  const runStartedAt = Date.parse(state.timing.sent_at || state.timing.started_at || new Date().toISOString());
  const deadline = runStartedAt + config.runTimeoutSeconds * 1000;
  state.runtime.heartbeat_at = new Date().toISOString();
  const dom = await inspectDom(page);
  const session = chooseAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
  if (session) {
    state.session = {
      ...state.session,
      conversation_id: session.conversationId,
      dom_conversation_id: threadIdFromUrl(page.url()) === session.conversationId
        ? session.conversationId
        : state.session.dom_conversation_id,
      cwd: session.cwd,
      raw_status: session.status,
      turn_id: session.turnId || session.activeTurnId || state.session.turn_id || null,
      updated_at_ms: session.updatedAt || null,
    };
    const classification = classifySessionStatus(session.status);
    if (classification.kind === "success") {
      const finalText = dom.finalText || await queryFinalResponse(
        config.sessionDb,
        session.conversationId,
        session.turnId || state.session.turn_id || null,
      ).catch(() => "");
      await takeScreenshot(page, config, state, "10-succeeded.png");
      return finalize(config, state, identityInfo, "SUCCEEDED", {
        terminalSource: "astudio-state-sqlite",
        finalText,
      });
    }
    if (classification.kind === "failure") {
      const finalText = dom.finalText || await queryFinalResponse(
        config.sessionDb,
        session.conversationId,
        session.turnId || state.session.turn_id || null,
      ).catch(() => "");
      await takeScreenshot(page, config, state, "10-infra-failed.png");
      return finalize(config, state, identityInfo, "INFRA_FAILED", {
        terminalSource: "astudio-state-sqlite",
        error: `AstronStudio turn 终态：${session.status}`,
        finalText,
      });
    }
    if (session.status === "needs_attention") {
      return persistNeedsAttention(
        config,
        state,
        identityInfo,
        "pending-interaction",
        "AstronStudio 正在等待授权或用户输入，自动化不会代替被评测 Agent 作答",
        page,
        "09-needs-attention.png",
      );
    }
    if (classification.kind === "unknown" && session.status !== "ready") {
      return persistNeedsAttention(
        config,
        state,
        identityInfo,
        "unknown-session-status",
        `无法识别 AstronStudio session 状态：${session.status}`,
        page,
        "09-unknown-session-status.png",
      );
    }
  }
  if (dom.attention.length > 0) {
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "visible-interaction",
      `AstronStudio 等待人工处理：${dom.attention.join(" / ")}`,
      page,
      "09-needs-attention.png",
    );
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
    throw new Error(`当前状态 ${state.phase} 尚未进入发送临界区；不能用 --resume 猜测或重发 Prompt`);
  }
  state.runtime.driver_pid = process.pid;
  state.runtime.driver_started_at = new Date().toISOString();
  state.runtime.heartbeat_at = state.runtime.driver_started_at;
  let page = null;
  try {
    await requireUnlockedGui();
    if (config.restartApp) {
      if (!(state.session?.conversation_id || state.session?.dom_conversation_id)) {
        return persistNeedsAttention(
          config,
          state,
          identityInfo,
          "client-restart-thread-id-unavailable",
          "恢复前没有捕获稳定 AstronStudio thread ID；禁止重启后猜测会话或重发 Prompt",
        );
      }
      state.client.launch = await restartAstudio(config);
    } else if (!(await endpointReady(config.endpoint))) {
      throw new Error(`AstronStudio 未开放调试端口 ${config.endpoint}`);
    }
    state.client.process = await astudioProcessIdentity();
    const { chromium } = await import("playwright-core");
    const browser = await chromium.connectOverCDP(config.endpoint);
    page = await chooseAstudioPage(browser, config.timeoutSeconds * 1000);
    page.setDefaultTimeout(config.timeoutSeconds * 1000);
    await page.bringToFront();
    const opened = await openAttemptThread(page, state, config.timeoutSeconds * 1000);
    state.session.resume_navigation = { ...opened, at: new Date().toISOString() };
    if (!opened.opened) {
      return persistNeedsAttention(
        config,
        state,
        identityInfo,
        "resume-thread-not-found",
        `无法按稳定 thread ID 恢复原会话：${opened.reason}`,
        page,
        "09-resume-thread-not-found.png",
      );
    }
    await saveState(config, state);
    return config.observeOnce
      ? observeAttemptOnce(page, config, state, identityInfo)
      : waitForTerminal(page, config, state, identityInfo);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return persistNeedsAttention(
      config,
      state,
      identityInfo,
      "resume-observation-failed",
      `${message}；恢复过程未确认原会话终态，禁止重发 Prompt`,
      page,
      "09-resume-observation-failed.png",
    );
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
        state.runtime.interruption = { signal, at: interruptedAt, previous_phase: previousPhase };
        state.runtime.heartbeat_at = interruptedAt;
        if (!TERMINAL_PHASES.has(state.phase)) {
          transitionState(state, "NEEDS_ATTENTION", {
            reason: "driver-interrupted",
            signal,
            previous_phase: previousPhase,
          });
          state.error = `Driver 收到 ${signal}；AstronStudio 任务可能仍在运行，必须使用 --resume 观察原 thread`;
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
  const existingState = await readJsonIfExists(config.stateFile);
  if (existingState) {
    assertStateMatches(existingState, config, identityInfo.identity);
    if (TERMINAL_PHASES.has(existingState.phase)) return existingState;
    if (!config.resume) throw new Error(`已有未完成状态 ${existingState.phase}；必须使用 --resume，避免重复发送 Prompt`);
    installDriverSignalHandlers(config, existingState, identityInfo);
    return resumeAutomation(config, existingState, identityInfo);
  }
  if (config.resume) throw new Error("--resume 要求已有 automation_state.json");
  if (config.retryPreSendFailure) throw new Error("AstronStudio 首版暂不支持 --retry-pre-send-failure");
  if (config.detachAfterSubmit) throw new Error("AstronStudio 首版 run_slots 固定为 1，不支持 --detach-after-submit");

  const initialSnapshot = await snapshotTree(config.candidateWorkspace);
  const state = createInitialState(config, identityInfo.identity, initialSnapshot);
  state.timing.started_at = new Date().toISOString();
  await saveState(config, state);
  installDriverSignalHandlers(config, state, identityInfo);
  await updateExecutionRecord(config, identityInfo, {
    clientVersion: "",
    execution: {
      status: "pending",
      started_at: state.timing.started_at,
      finished_at: null,
      duration_seconds: null,
      error: null,
    },
  });

  let promptMayHaveBeenSent = false;
  try {
    await requireUnlockedGui();
    await prepareClient(config, state);
    state.client.version = await appVersion(config.appPath);
    state.client.process = await astudioProcessIdentity();
    transitionState(state, "CLIENT_READY");
    await saveState(config, state);

    const { chromium } = await import("playwright-core");
    const browser = await chromium.connectOverCDP(config.endpoint);
    const timeout = config.timeoutSeconds * 1000;
    const page = await chooseAstudioPage(browser, timeout);
    page.setDefaultTimeout(timeout);
    await page.bringToFront();
    state.client.dismissed_transient_ui = await dismissOpenMenus(page, timeout);
    await takeScreenshot(page, config, state, "01-initial.png");

    state.task_creation = await createFreshTask(page, timeout);
    await takeScreenshot(page, config, state, "02-new-task.png");
    state.workspace_selection = {
      requested_path: config.workspace,
      ...(await selectWorkspace(page, config.workspace, timeout)),
      confirmed_at: new Date().toISOString(),
    };
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
      .filter((session) => resolve(String(session.cwd || "")) === config.workspace)
      .map((session) => ({
        conversation_id: session.conversationId,
        updated_at_ms: Number(session.updatedAt || 0),
        raw_status: session.status || "",
      }));
    state.session.dom_baseline_conversation_id = threadIdFromUrl(page.url());
    transitionState(state, "READY_TO_SEND");
    await saveState(config, state);

    state.send_method = await clickSend(page, timeout);
    promptMayHaveBeenSent = true;
    state.timing.sent_at = new Date().toISOString();
    transitionState(state, "PROMPT_SENT");
    await saveState(config, state);
    await captureAttemptThread(page, config, state, Math.min(timeout, 15000));
    if (!state.session.conversation_id) {
      return persistNeedsAttention(
        config,
        state,
        identityInfo,
        "thread-id-unavailable-after-send",
        "Prompt 已发送，但未从 AstronStudio 路由和状态库共同确认稳定 thread ID；禁止重发",
        page,
        "09-thread-id-unavailable.png",
      );
    }
    await saveState(config, state);
    await takeScreenshot(page, config, state, "08-prompt-sent.png");
    return waitForTerminal(page, config, state, identityInfo);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (promptMayHaveBeenSent || new Set(["READY_TO_SEND", "PROMPT_SENT", "RUNNING"]).has(state.phase)) {
      return persistNeedsAttention(
        config,
        state,
        identityInfo,
        "post-send-driver-error",
        `${message}；Prompt 可能已发送，必须使用 --resume 检查，不能直接重试`,
      );
    }
    return finalize(config, state, identityInfo, "INFRA_FAILED", {
      terminalSource: "driver-error",
      error: message,
    });
  }
}

export function isProbeReady(checks) {
  return checks.endpoint_ready && checks.state_database_readable && checks.sqlite3
    && checks.gui_session_unlocked && checks.new_task_available
    && checks.permission_setting_available && checks.model_setting_available
    && checks.composer_available;
}

async function probe(config) {
  const gui = await guiSessionStatus();
  const checks = {
    app_exists: true,
    client_version: await appVersion(config.appPath),
    endpoint_ready: await endpointReady(config.endpoint),
    state_database_readable: false,
    session_count: null,
    sqlite3: false,
    gui_session_unlocked: gui.unlocked,
    screen_locked: gui.screen_locked,
    gui_lock_source: gui.lock_source,
    frontmost_application: gui.frontmost_application,
    new_task_available: false,
    workspace_picker_available: false,
    permission_setting_available: false,
    model_setting_available: false,
    composer_available: false,
  };
  try {
    const sqlite = await run("/usr/bin/sqlite3", ["--version"], { capture: true, allowFailure: true });
    checks.sqlite3 = sqlite.code === 0;
    const sessions = await querySessions(config.sessionDb);
    checks.state_database_readable = true;
    checks.session_count = sessions.length;
    checks.active_session_count = sessions.filter((session) =>
      new Set(["running", "needs_attention", "pending", "starting"]).has(String(session.status)),
    ).length;
  } catch (error) {
    checks.state_database_error = error instanceof Error ? error.message : String(error);
  }
  if (checks.endpoint_ready) {
    try {
      const { chromium } = await import("playwright-core");
      const browser = await chromium.connectOverCDP(config.endpoint);
      const page = await chooseAstudioPage(browser, config.timeoutSeconds * 1000);
      const testIdNewTask = await visibleLocators(page.getByTestId("new-thread-button"));
      const textNewTask = await visibleLocators(page.locator("button").filter({ hasText: /^(?:新建任务|New task)$/i }));
      checks.new_task_available = testIdNewTask.length === 1 || textNewTask.length === 1;
      checks.workspace_picker = await inspectWorkspace(page);
      checks.workspace_picker_available = checks.workspace_picker.available;
      checks.permission_setting = await inspectPermissionMode(page);
      checks.permission_setting_available = checks.permission_setting.available;
      checks.model_setting = await readCurrentModel(page, config.timeoutSeconds * 1000)
        .then(({ model, reasoning }) => ({ available: true, model, reasoning }))
        .catch((error) => ({ available: false, error: error.message }));
      checks.model_setting_available = checks.model_setting.available;
      checks.composer_available = (await visibleLocators(page.getByTestId("composer-editor"))).length === 1;
      checks.page = { title: await page.title(), url_scheme: new URL(page.url()).protocol };
    } catch (error) {
      checks.dom_probe_error = error instanceof Error ? error.message : String(error);
    }
  }
  return {
    driver: "astronstudio",
    version: DRIVER_VERSION,
    control_backend: "electron-cdp+astudio-project-picker+sidebar-manual-path",
    terminal_source: "astudio-state-sqlite+astudio-dom",
    concurrency: { ui_slots: 1, run_slots: 1, verified: false },
    ready: isProbeReady(checks),
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
      observeOnce: config.observeOnce,
      dryRun: config.dryRun,
    };
    if (!config.quiet) console.log(JSON.stringify(safeConfig, null, 2));
    if (config.dryRun) return 0;
    const result = await runAutomation(config, identityInfo);
    if (!config.quiet) console.log(`AstronStudio 自动化状态：${result.phase}；状态文件：${config.stateFile}`);
    if (result.phase === "SUCCEEDED") return 0;
    if (result.phase === "RUNNING" || result.phase === "PROMPT_SENT") return 0;
    if (result.phase === "NEEDS_ATTENTION") return 3;
    if (result.phase === "TIMEOUT") return 4;
    return 1;
  } catch (error) {
    console.error(`AstronStudio 自动化失败：${error.message}`);
    return 1;
  }
}

const isEntrypoint = process.argv[1]
  && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  const exitCode = await main(process.argv.slice(2));
  process.exitCode = exitCode;
  setImmediate(() => process.exit(exitCode));
}
