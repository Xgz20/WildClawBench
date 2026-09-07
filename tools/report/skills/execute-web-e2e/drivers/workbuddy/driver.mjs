#!/usr/bin/env node
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { realpathSync } from "node:fs";
import { access, copyFile, mkdir, rename, writeFile } from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_BUNDLE_ID,
  RESUMABLE_PHASES,
  TERMINAL_PHASES,
  assertStateMatches,
  atomicWriteJson,
  chooseAttemptSession,
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
  return `WorkBuddy Web E2E 单题执行 Driver

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
  --restart-app                    正常退出后以本地 CDP 端口重启 WorkBuddy
  --dry-run                        校验输入、身份和状态，不操作 WorkBuddy
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

async function workBuddyProcessIdentity() {
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
  const result = await run("/usr/bin/sqlite3", ["-readonly", "-json", sessionDb, "SELECT CAST(value AS TEXT) AS value FROM ItemTable"], { capture: true });
  const rows = result.stdout.trim() ? JSON.parse(result.stdout) : [];
  const sessions = [];
  for (const row of rows) {
    try {
      const value = JSON.parse(row.value);
      if (value && typeof value === "object" && value.conversationId) sessions.push(value);
    } catch {
      // Ignore unrelated/corrupt rows; an exact session is still required for success.
    }
  }
  return sessions;
}

async function waitForEndpoint(endpoint, timeoutSeconds) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    if (await endpointReady(endpoint)) return;
    await sleep(500);
  }
  throw new Error(`等待 WorkBuddy 调试端口超时：${endpoint}`);
}

async function waitForWorkBuddyStopped(config, dependencies, timeoutSeconds = 15) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    const [processIdentity, ready] = await Promise.all([
      dependencies.processIdentity(),
      dependencies.endpointReady(config.endpoint),
    ]);
    if (!processIdentity && !ready) return;
    await dependencies.sleep(500);
  }
  throw new Error(`WorkBuddy 旧进程或调试端口未在 ${timeoutSeconds} 秒内退出`);
}

export async function restartWorkBuddy(config, overrides = {}) {
  const dependencies = {
    run,
    sleep,
    endpointReady,
    waitForEndpoint,
    processIdentity: workBuddyProcessIdentity,
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
    await dependencies.run("/usr/bin/osascript", ["-e", quitScript], { allowFailure: true, capture: true });
    await waitForWorkBuddyStopped(config, dependencies);
  };
  await stopCurrentInstance();
  const port = new URL(config.endpoint).port || "9229";
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
    new Error(`WorkBuddy 自动启动 ${dependencies.launchAttempts} 次后仍未开放调试端口 ${config.endpoint}：${detail}`),
    { launchAttempts: attempts },
  );
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

async function inspectWorkspaceInputProvider(page) {
  const pickers = await visibleLocators(page.locator(".cr-workspace-picker"));
  if (!pickers.length) return { available: false, reason: "workspace-picker-not-visible", cwd: "" };
  return pickers[pickers.length - 1].evaluate((element) => {
    const fiberKey = Object.keys(element).find((key) => key.startsWith("__reactFiber$"));
    let fiber = fiberKey ? element[fiberKey] : null;
    while (fiber) {
      const props = fiber.memoizedProps;
      const store = props?.store;
      const workspaceProvider = props?.providers?.workspace;
      if (store?.api?.setCwd && typeof workspaceProvider?.onChange === "function") {
        const snapshot = store.getSnapshot?.();
        return {
          available: true,
          reason: null,
          cwd: props.selections?.cwd ?? snapshot?.draft?.selections?.cwd ?? "",
          component: fiber.elementType?.displayName || fiber.elementType?.name || "input-box-root",
        };
      }
      fiber = fiber.return;
    }
    return { available: false, reason: "workspace-input-provider-not-found", cwd: "" };
  });
}

async function selectWorkspaceViaInputProvider(page, workspace, timeout) {
  const pickers = await visibleLocators(page.locator(".cr-workspace-picker"));
  if (!pickers.length) throw new Error("WorkBuddy 未显示工作空间选择器");
  const requested = await pickers[pickers.length - 1].evaluate(async (element, targetPath) => {
    const fiberKey = Object.keys(element).find((key) => key.startsWith("__reactFiber$"));
    let fiber = fiberKey ? element[fiberKey] : null;
    while (fiber) {
      const props = fiber.memoizedProps;
      const store = props?.store;
      const workspaceProvider = props?.providers?.workspace;
      if (store?.api?.setCwd && typeof workspaceProvider?.onChange === "function") {
        await workspaceProvider.onChange(targetPath);
        return {
          component: fiber.elementType?.displayName || fiber.elementType?.name || "input-box-root",
          method: "workbuddy-workspace-provider-onChange",
        };
      }
      fiber = fiber.return;
    }
    throw new Error("当前 WorkBuddy 版本未暴露可用的 workspace input provider");
  }, workspace);

  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const current = await inspectWorkspaceInputProvider(page);
    if (current.available && current.cwd === workspace) {
      return { ...requested, confirmed_path: current.cwd };
    }
    await sleep(250);
  }
  throw new Error(`WorkBuddy workspace input provider 未回读目标路径：${workspace}`);
}

async function waitForWorkspaceSelection(page, workspace, timeout) {
  const expectedLabel = basename(workspace);
  const labels = page.locator(".cr-input-footer-item__label[data-text]");
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const provider = await inspectWorkspaceInputProvider(page);
    for (let index = 0; index < await labels.count(); index += 1) {
      const candidate = labels.nth(index);
      if (!(await candidate.isVisible().catch(() => false))) continue;
      const value = await candidate.getAttribute("data-text");
      if (value === expectedLabel && provider.available && provider.cwd === workspace) {
        return {
          expected_label: expectedLabel,
          confirmed_label: value,
          confirmed_path: provider.cwd,
          method: "input-provider-state+composer-footer-label",
        };
      }
    }
    await sleep(250);
  }
  throw new Error(`WorkBuddy 未同时回读工作空间绝对路径和输入区标签“${expectedLabel}”`);
}

export async function ensureModel(page, model, timeout) {
  const trigger = await waitForUniqueVisible(
    () => visibleLocators(page.locator('button.cr-model-selector__trigger[role="combobox"]')),
    timeout,
    "WorkBuddy 模型选择按钮",
  );
  const current = ((await trigger.getAttribute("title")) || (await trigger.innerText())).trim();
  if (!current) throw new Error("WorkBuddy 当前模型显示值为空");
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
  const listbox = await waitForUniqueVisible(
    () => visibleLocators(page.locator('[role="listbox"]')),
    timeout,
    "WorkBuddy 模型下拉框",
  );
  const label = await waitForUniqueVisible(
    () => visibleLocators(listbox.getByText(model, { exact: true })),
    timeout,
    `WorkBuddy 模型选项“${model}”`,
  );
  const option = label.locator('xpath=ancestor-or-self::*[@role="option"][1]');
  if (await option.count() !== 1) throw new Error(`WorkBuddy 模型选项“${model}”结构异常`);
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
  throw new Error(`WorkBuddy 未回读目标模型“${model}”`);
}

async function inspectPermissionMode(page) {
  const triggers = await visibleLocators(page.locator("button.cr-permission-setting"));
  if (triggers.length !== 1) {
    return { available: false, reason: `visible-trigger-count:${triggers.length}`, mode: "unknown", label: "" };
  }
  const trigger = triggers[0];
  const label = (await trigger.locator(".cr-input-footer-item__label").getAttribute("data-text").catch(() => null))
    || (await trigger.innerText().catch(() => ""));
  const className = await trigger.getAttribute("class") || "";
  const mode = className.split(/\s+/).includes("cr-permission-setting--danger")
    ? "full-access"
    : "default-sandbox";
  return {
    available: true,
    reason: null,
    mode,
    label: label.trim(),
    enabled: await trigger.isEnabled().catch(() => false),
  };
}

async function ensurePermissionMode(page, requestedMode, timeout) {
  let before = await inspectPermissionMode(page);
  if (!before.available) throw new Error(`WorkBuddy 权限设置不可用：${before.reason}`);
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
    if (!before.available) throw new Error(`WorkBuddy 权限设置不可用：${before.reason}`);
    if (before.mode === "full-access") {
      return { requested_mode: requestedMode, confirmed_mode: before.mode, changed: false, method: "visible-current-value" };
    }
  }
  if (!before.enabled) throw new Error(`等待 WorkBuddy 权限设置可操作超时（${timeout}ms）`);

  const trigger = (await visibleLocators(page.locator("button.cr-permission-setting")))[0];
  await trigger.click({ timeout });
  const menu = page.locator(".cr-permission-setting-popover:visible");
  await menu.waitFor({ state: "visible", timeout });
  const toggle = menu.getByRole("switch");
  if (await toggle.getAttribute("aria-checked") !== "true") await toggle.click({ timeout });

  const dialog = page.getByRole("dialog").filter({ hasText: /允许完全访问|Allow full access/i });
  await dialog.waitFor({ state: "visible", timeout });
  await dialog.locator('input[type="checkbox"]').check({ timeout });
  await dialog.getByRole("button", { name: /允许完全访问|Allow full access/i }).click({ timeout });

  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const current = await inspectPermissionMode(page);
    if (current.available && current.mode === "full-access") {
      await page.keyboard.press("Escape");
      await menu.waitFor({ state: "hidden", timeout });
      return {
        requested_mode: requestedMode,
        confirmed_mode: current.mode,
        changed: true,
        method: "permission-popover+risk-confirmation",
      };
    }
    await sleep(250);
  }
  throw new Error("WorkBuddy 未回读“允许完全访问”状态");
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

async function chooseWorkBuddyPage(browser, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const pages = browser.contexts().flatMap((context) => context.pages());
    for (const page of pages) if (/WorkBuddy/i.test(await page.title().catch(() => ""))) return page;
    if (pages.length === 1) return pages[0];
    await sleep(250);
  }
  throw new Error("调试端口已连接，但找不到 WorkBuddy 主页面");
}

async function inspectSelectedConversationId(page) {
  const selected = await visibleLocators(page.locator('[data-conversation-id]:has(.cb-agent-card[class*="selected"])'));
  const ids = [];
  for (const item of selected) {
    const value = (await item.getAttribute("data-conversation-id").catch(() => ""))?.trim();
    if (value) ids.push(value);
  }
  return [...new Set(ids)].length === 1 ? ids[0] : null;
}

async function captureAttemptConversation(page, state, timeout) {
  const baseline = state.session.dom_baseline_conversation_id || null;
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const conversationId = await inspectSelectedConversationId(page);
    if (conversationId && conversationId !== baseline) {
      state.session.dom_conversation_id = conversationId;
      state.session.dom_conversation_captured_at = new Date().toISOString();
      return conversationId;
    }
    await sleep(250);
  }
  return null;
}

async function openAttemptConversation(page, state, timeout) {
  const conversationId = state.session.dom_conversation_id || state.session.conversation_id || null;
  if (!conversationId) return { opened: false, reason: "conversation-id-unavailable" };
  if (!/^[A-Za-z0-9._:-]{1,160}$/.test(conversationId)) {
    return { opened: false, reason: "conversation-id-format-invalid" };
  }
  const selected = await inspectSelectedConversationId(page);
  if (selected === conversationId) return { opened: true, conversation_id: conversationId, method: "already-selected" };
  const deadline = Date.now() + timeout;
  let matches = [];
  while (Date.now() < deadline) {
    matches = await visibleLocators(page.locator(`[data-conversation-id="${conversationId}"]`));
    if (matches.length === 1) break;
    await sleep(250);
  }
  if (matches.length !== 1) {
    return { opened: false, reason: `conversation-item-count:${matches.length}`, conversation_id: conversationId };
  }
  await matches[0].click({ timeout });
  const selectionDeadline = Date.now() + timeout;
  while (Date.now() < selectionDeadline) {
    if (await inspectSelectedConversationId(page) === conversationId) {
      return { opened: true, conversation_id: conversationId, method: "sidebar-data-conversation-id" };
    }
    await sleep(250);
  }
  return { opened: false, reason: "conversation-selection-not-confirmed", conversation_id: conversationId };
}

async function inspectDom(page) {
  const stop = page.locator('button[aria-label*="停止"]:visible, button[title*="停止"]:visible, button[aria-label*="Stop"]:visible, button[title*="Stop"]:visible');
  const running = (await visibleLocators(stop)).length > 0;
  const attentionButtons = page.getByRole("button", { name: /允许|批准|确认执行|始终允许|Allow|Approve|Deny|拒绝/ });
  const attention = [];
  for (const button of await visibleLocators(attentionButtons)) {
    const name = (await button.innerText().catch(() => "")) || (await button.getAttribute("aria-label")) || "";
    if (name.trim()) attention.push(name.trim());
  }
  const agentTurns = page.locator(".cr-agent:visible");
  const agentValues = await agentTurns.allInnerTexts().catch(() => []);
  const agentText = agentValues.map((value) => value.trim()).filter(Boolean).at(-1) || "";
  const latestAgent = agentTurns.last();
  const finishedFooters = await visibleLocators(latestAgent.locator('[data-testid="conversation-finished-footer"]'));
  const completionStatus = (await latestAgent.locator(".cr-agent__completion-status").innerText().catch(() => "")).trim();
  const explicitFinished = finishedFooters.length === 1
    && /^(?:已完成|Completed)(?:\s|\d|$)/i.test(completionStatus);
  const emptyConversation = (await visibleLocators(page.getByText("暂无对话记录", { exact: true }))).length > 0;
  const statusFrames = await visibleLocators(page.locator('[data-cr-frame="true"][data-status]'));
  const rawStatus = statusFrames.length
    ? ((await statusFrames.at(-1).getAttribute("data-status").catch(() => "")) || "")
    : "";
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
    attention: [...new Set(attention)],
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
  const session = chooseAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
  if (session) {
    const classification = classifySessionStatus(session.status);
    if (classification.kind === "success") {
      await takeScreenshot(page, config, state, "10-succeeded-at-timeout-boundary.png");
      return finalize(config, state, identityInfo, "SUCCEEDED", {
        terminalSource: "workbuddy-session-db",
        finalText: currentDom.finalText || lastDom.finalText,
      });
    }
    if (classification.kind === "failure") {
      await takeScreenshot(page, config, state, "10-failed-at-timeout-boundary.png");
      return finalize(config, state, identityInfo, "INFRA_FAILED", {
        terminalSource: "workbuddy-session-db",
        error: `WorkBuddy conversation 终态：${session.status}`,
        finalText: currentDom.finalText || lastDom.finalText,
      });
    }
  }
  if (hasTrustedDomCompletion({
    ...currentDom,
    finalText: currentDom.finalText || lastDom.finalText,
  })) {
    await takeScreenshot(page, config, state, "10-succeeded-at-timeout-boundary.png");
    return finalize(config, state, identityInfo, "SUCCEEDED", {
      terminalSource: "workbuddy-dom-completion",
      finalText: currentDom.finalText || lastDom.finalText,
    });
  }
  if (currentDom.status.kind === "failure") {
    await takeScreenshot(page, config, state, "10-failed-at-timeout-boundary.png");
    return finalize(config, state, identityInfo, "INFRA_FAILED", {
      terminalSource: "workbuddy-dom-completion",
      error: "WorkBuddy 页面在超时边界显示执行失败终态",
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
      `超过 ${config.runTimeoutSeconds} 秒，但无法唯一确认并停止当前 WorkBuddy 会话`,
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
    const currentSession = chooseAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
    if (currentSession) {
      const classification = classifySessionStatus(currentSession.status);
      if (classification.kind === "success") {
        cancellationSource = "workbuddy-session-db-terminal-after-stop";
        break;
      }
      if (classification.kind === "failure") {
        cancellationSource = "workbuddy-session-db";
        break;
      }
    }
    if (dom.status.kind === "success") {
      cancellationSource = "workbuddy-dom-terminal-after-stop";
      break;
    }
    if (dom.status.kind === "failure") {
      cancellationSource = "workbuddy-dom-cancelled";
      break;
    }
    if (!dom.running) stableNonRunningPolls += 1;
    else stableNonRunningPolls = 0;
    if (stableNonRunningPolls >= 2) {
      cancellationSource = "workbuddy-dom-non-running";
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
      `超过 ${config.runTimeoutSeconds} 秒，已请求停止但无法确认 WorkBuddy 不再运行`,
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
      "WorkBuddy 已停止，但候选 workspace 在静默观察窗口内仍发生变化",
      page,
      "10-timeout-workspace-changing.png",
    );
  }
  state.timeout.cancellation_confirmed = true;
  state.timeout.cancellation_confirmed_at = new Date().toISOString();
  await takeScreenshot(page, config, state, "10-timeout-cancelled.png");
  return finalize(config, state, identityInfo, "TIMEOUT", {
    terminalSource: "driver-timeout+cancellation-confirmed",
    error: `超过 ${config.runTimeoutSeconds} 秒，已确认 WorkBuddy 停止且 workspace 保持静默`,
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
    throw new Error("WorkBuddy 授权面板数量在检查期间发生变化");
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
      source: "workbuddy-dom",
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

async function waitForTerminal(page, config, state, identityInfo) {
  const runStartedAt = Date.parse(state.timing.sent_at || state.timing.started_at || new Date().toISOString());
  const deadline = runStartedAt + config.runTimeoutSeconds * 1000;
  let lastDom = { running: false, attention: [], finalText: "", explicitFinished: false };
  while (Date.now() < deadline) {
    state.runtime ||= {};
    state.runtime.heartbeat_at = new Date().toISOString();
    const approvalResult = await handleExpectedApprovals(page, config, state);
    if (approvalResult.handled) {
      await sleep(500);
      continue;
    }
    lastDom = await inspectDom(page);
    if (lastDom.attention.length) {
      await takeScreenshot(page, config, state, "09-needs-attention.png");
      const commands = approvalResult.approvals.map((approval) => approval.command).filter(Boolean);
      transitionState(state, "NEEDS_ATTENTION", {
        reason: "visible-approval",
        buttons: lastDom.attention,
        command_sha256: commands.map((command) => createHash("sha256").update(command).digest("hex")),
      });
      state.error = commands.length
        ? `WorkBuddy 等待人工处理：存在未列入安全规则的授权命令（${commands.length} 个）`
        : `WorkBuddy 等待人工处理：${lastDom.attention.join(" / ")}`;
      await saveState(config, state);
      await updateExecutionRecord(config, identityInfo, {
        clientVersion: state.client.version,
        execution: { status: "pending", error: state.error },
      });
      return state;
    }

    const sessions = await querySessions(config.sessionDb);
    const session = chooseAttemptSession(sessions, state, config.workspace);
    if (session) {
      state.session = {
        ...state.session,
        conversation_id: session.conversationId,
        cwd: session.cwd,
        raw_status: session.status,
        updated_at_ms: session.updatedAt || null,
      };
      const classification = classifySessionStatus(session.status);
      if (classification.kind === "success") {
        await takeScreenshot(page, config, state, "10-succeeded.png");
        return finalize(config, state, identityInfo, "SUCCEEDED", { terminalSource: "workbuddy-session-db", finalText: lastDom.finalText });
      }
      if (classification.kind === "failure") {
        await takeScreenshot(page, config, state, "10-infra-failed.png");
        return finalize(config, state, identityInfo, "INFRA_FAILED", {
          terminalSource: "workbuddy-session-db",
          error: `WorkBuddy conversation 终态：${session.status}`,
          finalText: lastDom.finalText,
        });
      }
      if (classification.kind === "unknown") {
        await takeScreenshot(page, config, state, "09-unknown-session-status.png");
        transitionState(state, "NEEDS_ATTENTION", { reason: "unknown-session-status", raw_status: session.status });
        state.error = `无法识别 WorkBuddy session 状态：${session.status}`;
        await saveState(config, state);
        await updateExecutionRecord(config, identityInfo, { clientVersion: state.client.version, execution: { status: "pending", error: state.error } });
        return state;
      }
    } else if (hasTrustedDomCompletion(lastDom)) {
      await takeScreenshot(page, config, state, "10-succeeded.png");
      return finalize(config, state, identityInfo, "SUCCEEDED", {
        terminalSource: "workbuddy-dom-completion",
        finalText: lastDom.finalText,
      });
    } else if (lastDom.status.kind === "failure") {
      await takeScreenshot(page, config, state, "10-infra-failed.png");
      return finalize(config, state, identityInfo, "INFRA_FAILED", {
        terminalSource: "workbuddy-dom-completion",
        error: "WorkBuddy 页面显示执行失败终态",
        finalText: lastDom.finalText,
      });
    }
    if (new Set(["PROMPT_SENT", "NEEDS_ATTENTION"]).has(state.phase) && (session || lastDom.running)) {
      transitionState(state, "RUNNING", { recovered_observation: state.phase === "NEEDS_ATTENTION" });
    }
    await saveState(config, state);
    await sleep(config.pollIntervalSeconds * 1000);
  }
  return cancelTimedOutAttempt(page, config, state, identityInfo, lastDom, deadline);
}

async function resumeAutomation(config, state, identityInfo) {
  if (TERMINAL_PHASES.has(state.phase)) return state;
  if (!RESUMABLE_PHASES.has(state.phase)) {
    throw new Error(`当前状态 ${state.phase} 尚未进入发送临界区；请检查 WorkBuddy 后使用新的 --output-dir 重试`);
  }
  state.session ||= { conversation_id: null, dom_conversation_id: null, baseline: [] };
  state.runtime ||= {};
  state.runtime.driver_pid = process.pid;
  state.runtime.driver_started_at = new Date().toISOString();
  state.runtime.heartbeat_at = state.runtime.driver_started_at;
  if (config.restartApp && !(state.session.dom_conversation_id || state.session.conversation_id)) {
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
      state.client.launch = await restartWorkBuddy(config);
      await saveState(config, state);
    }
    else if (!(await endpointReady(config.endpoint))) throw new Error(`WorkBuddy 未开放调试端口 ${config.endpoint}`);
    state.client.process = await workBuddyProcessIdentity();
    const { chromium } = await import("playwright-core");
    const browser = await chromium.connectOverCDP(config.endpoint);
    page = await chooseWorkBuddyPage(browser, config.timeoutSeconds * 1000);
    page.setDefaultTimeout(config.timeoutSeconds * 1000);
    await page.bringToFront();
    const hasStableConversationId = Boolean(state.session.dom_conversation_id || state.session.conversation_id);
    if (hasStableConversationId) {
      const opened = await openAttemptConversation(page, state, config.timeoutSeconds * 1000);
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
    const session = chooseAttemptSession(await querySessions(config.sessionDb), state, config.workspace);
    const dom = await inspectDom(page);
    if (hasStableConversationId && !session && dom.emptyConversation) {
      return persistNeedsAttention(
        config,
        state,
        identityInfo,
        "resume-conversation-empty",
        "已按稳定 conversation ID 打开原会话，但 WorkBuddy 显示暂无对话记录；禁止创建新任务或重发 Prompt",
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
      state.session.conversation_id = session.conversationId;
      state.session.cwd = session.cwd;
      state.session.raw_status = session.status;
      state.session.updated_at_ms = session.updatedAt || null;
      if (state.phase === "READY_TO_SEND") transitionState(state, "PROMPT_SENT", { recovered_from_session: true });
    } else if (state.phase === "READY_TO_SEND") {
      transitionState(state, "PROMPT_SENT", { recovered_from_dom: dom.status.status });
    }
    await saveState(config, state);
    return waitForTerminal(page, config, state, identityInfo);
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
    // 用户正在运行的 WorkBuddy；Playwright 私有连接也不作为稳定 API 使用。
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
          state.error = `Driver 收到 ${signal}；WorkBuddy 任务可能仍在运行，必须使用 --resume 观察原会话`;
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
    if (config.restartApp) await restartWorkBuddy(config);
    else if (!(await endpointReady(config.endpoint))) {
      throw new Error(`WorkBuddy 未开放调试端口 ${config.endpoint}；请添加 --restart-app，或手工以 --remote-debugging-port 启动`);
    }
    state.client.version = await appVersion(config.appPath);
    state.client.process = await workBuddyProcessIdentity();
    transitionState(state, "CLIENT_READY");
    await saveState(config, state);

    const { chromium } = await import("playwright-core");
    browser = await chromium.connectOverCDP(config.endpoint);
    const timeout = config.timeoutSeconds * 1000;
    const page = await chooseWorkBuddyPage(browser, timeout);
    page.setDefaultTimeout(timeout);
    await page.bringToFront();
    await takeScreenshot(page, config, state, "01-initial.png");

    await clickExactText(page, "新建任务", timeout);
    await takeScreenshot(page, config, state, "02-new-task.png");
    let workspaceBackend;
    try {
      workspaceBackend = await selectWorkspaceViaInputProvider(page, config.workspace, timeout);
    } catch (providerError) {
      await clickExactText(page, "选择工作空间", timeout);
      await takeScreenshot(page, config, state, "03-workspace-menu.png");
      await clickExactText(page, "打开本地文件夹", timeout);
      workspaceBackend = {
        method: "macos-accessibility-fallback",
        native: await selectNativeFolder(config.workspace, config.timeoutSeconds),
        provider_error: providerError instanceof Error ? providerError.message : String(providerError),
      };
    }
    state.workspace_selection = {
      requested_path: config.workspace,
      backend: workspaceBackend,
      page: await waitForWorkspaceSelection(page, config.workspace, timeout),
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
      .filter((session) => session.cwd && resolve(String(session.cwd)) === config.workspace)
      .map((session) => ({
        conversation_id: session.conversationId,
        updated_at_ms: Number(session.updatedAt || session.createdAt || 0),
        raw_status: session.status || "",
      }));
    state.session.dom_baseline_conversation_id = await inspectSelectedConversationId(page);
    transitionState(state, "READY_TO_SEND");
    await saveState(config, state);
    state.send_method = await clickSend(page, editor, timeout);
    promptMayHaveBeenSent = true;
    state.timing.sent_at = new Date().toISOString();
    transitionState(state, "PROMPT_SENT");
    await saveState(config, state);
    await captureAttemptConversation(page, state, Math.min(timeout, 10000));
    await saveState(config, state);
    await takeScreenshot(page, config, state, "08-prompt-sent.png");
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
    workspace_input_provider_available: false,
    permission_setting_available: false,
  };
  try {
    const sqlite = await run("/usr/bin/sqlite3", ["--version"], { capture: true, allowFailure: true });
    checks.sqlite3 = sqlite.code === 0;
    const sessions = await querySessions(config.sessionDb);
    checks.session_database_readable = true;
    checks.session_count = sessions.length;
  } catch (error) {
    checks.session_database_error = error instanceof Error ? error.message : String(error);
  }
  if (checks.endpoint_ready) {
    try {
      const { chromium } = await import("playwright-core");
      const browser = await chromium.connectOverCDP(config.endpoint);
      const page = await chooseWorkBuddyPage(browser, config.timeoutSeconds * 1000);
      checks.workspace_input_provider = await inspectWorkspaceInputProvider(page);
      checks.workspace_input_provider_available = checks.workspace_input_provider.available;
      checks.permission_setting = await inspectPermissionMode(page);
      checks.permission_setting_available = checks.permission_setting.available;
    } catch (error) {
      checks.workspace_input_provider_error = error instanceof Error ? error.message : String(error);
    }
  }
  return {
    driver: "workbuddy",
    version: DRIVER_VERSION,
    control_backend: "electron-cdp+workbuddy-workspace-provider+macos-accessibility-fallback",
    terminal_source: "workbuddy-session-db+workbuddy-dom",
    ready: checks.endpoint_ready && checks.session_database_readable && checks.sqlite3
      && checks.gui_session_unlocked && checks.workspace_input_provider_available
      && checks.permission_setting_available,
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
      postCancelQuiescenceSeconds: config.postCancelQuiescenceSeconds,
      dryRun: config.dryRun,
    };
    console.log(JSON.stringify(safeConfig, null, 2));
    if (config.dryRun) return 0;
    const result = await runAutomation(config, identityInfo);
    console.log(`WorkBuddy 自动化状态：${result.phase}；状态文件：${config.stateFile}`);
    if (result.phase === "SUCCEEDED") return 0;
    if (result.phase === "NEEDS_ATTENTION") return 3;
    if (result.phase === "TIMEOUT") return 4;
    return 1;
  } catch (error) {
    console.error(`WorkBuddy 自动化失败：${error.message}`);
    return 1;
  }
}

const isEntrypoint = process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  const exitCode = await main(process.argv.slice(2));
  process.exitCode = exitCode;
  setImmediate(() => process.exit(exitCode));
}
