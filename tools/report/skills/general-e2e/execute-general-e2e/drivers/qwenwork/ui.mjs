import { basename, resolve } from "node:path";

export const QWEN_MODEL_SELECTOR = ".new-task-model-selector button";
export const QWEN_PERMISSION_SELECTOR = 'button[aria-label="选择权限模式"]';
export const QWEN_PROJECT_SELECTOR = '.new-task-chat-input button[aria-haspopup="menu"]';
export const QWEN_PROMPT_SELECTOR = '[data-voice-input-target="chat-input"]';
export const QWEN_SEND_SELECTOR = [
  'button[aria-label="发送"]:visible',
  'button[title="发送"]:visible',
  'button[aria-label="Send"]:visible',
  'button[title="Send"]:visible',
  '[data-chat-input-surface="new-task"] button[type="button"].bg-text:visible',
].join(", ");
export const QWEN_STOP_SELECTOR = [
  'button[aria-label*="停止"]:not([disabled]):not([aria-disabled="true"]):visible',
  'button[title*="停止"]:not([disabled]):not([aria-disabled="true"]):visible',
  'button[aria-label*="Stop"]:not([disabled]):not([aria-disabled="true"]):visible',
  'button[title*="Stop"]:not([disabled]):not([aria-disabled="true"]):visible',
].join(", ");
export const QWEN_TASK_VIEW_SELECTOR = ".agents-chat-view-root";
export const QWEN_NEW_TASK_SELECTOR = 'button[aria-label="新任务"]';
export const QWEN_QUESTION_SELECTOR = '[data-slot="user-question"]';
export const QWEN_INTERACTION_SELECTOR = '[data-pending-interaction-id], [data-testid="pending-sandbox-panel"], [role="dialog"], [role="alertdialog"]';

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

export async function visibleLocators(locator) {
  const matches = [];
  const count = await locator.count();
  for (let index = 0; index < count; index += 1) {
    const candidate = locator.nth(index);
    if (await candidate.isVisible().catch(() => false)) matches.push(candidate);
  }
  return matches;
}

export async function requireUniqueVisible(locator, description) {
  const matches = await visibleLocators(locator);
  if (matches.length !== 1) throw new Error(`QWENWORK_UI_CONTROL_COUNT: ${description}:${matches.length}`);
  return matches[0];
}

export async function waitForUniqueVisible(readVisible, timeoutMilliseconds, description, pause = sleep) {
  const deadline = Date.now() + timeoutMilliseconds;
  let lastCount = 0;
  while (Date.now() <= deadline) {
    const matches = await readVisible();
    lastCount = matches.length;
    if (lastCount === 1) return matches[0];
    if (lastCount > 1) throw new Error(`QWENWORK_UI_CONTROL_COUNT: ${description}:${lastCount}`);
    await pause(Math.min(100, Math.max(1, deadline - Date.now())));
  }
  throw new Error(`QWENWORK_UI_CONTROL_COUNT: ${description}:${lastCount}`);
}

function visibleValue(value) {
  return String(value || "").trim();
}

export function classifyQwenPermissionLabel(label) {
  const value = visibleValue(label);
  if (/完全访问(?:权限)?|Full access/iu.test(value)) return "full-access";
  if (/默认权限|Default permission|Sandbox/iu.test(value)) return "default-sandbox";
  return null;
}

export async function readQwenUiConfiguration(page) {
  const modelTrigger = await requireUniqueVisible(page.locator(QWEN_MODEL_SELECTOR), "model-trigger");
  const model = visibleValue(
    await modelTrigger.getAttribute("title")
    || await modelTrigger.getAttribute("aria-label")
    || await modelTrigger.innerText(),
  );
  if (!model) throw new Error("QWENWORK_MODEL_READBACK_EMPTY");

  const permissionTrigger = await requireUniqueVisible(page.locator(QWEN_PERMISSION_SELECTOR), "permission-trigger");
  const permissionLabel = visibleValue(
    await permissionTrigger.innerText().catch(() => "")
    || await permissionTrigger.getAttribute("title")
    || await permissionTrigger.getAttribute("aria-label"),
  );
  const permissionMode = classifyQwenPermissionLabel(permissionLabel);
  if (!permissionMode) throw new Error(`QWENWORK_PERMISSION_READBACK_UNKNOWN: ${permissionLabel || "<empty>"}`);
  return {
    model: {
      policy: "keep-current",
      requested_model: null,
      actual_model: model,
      changed: false,
      method: "visible-current-value",
    },
    permission: {
      policy: "keep-current",
      requested_mode: "current",
      confirmed_mode: permissionMode,
      label: permissionLabel,
      changed: false,
      method: "visible-current-value",
    },
  };
}

export function assertStableQwenUiConfiguration(before, after) {
  if (!before?.model?.actual_model || !before?.permission?.confirmed_mode) {
    throw new Error("QWENWORK_UI_CONFIGURATION_BASELINE_MISSING");
  }
  if (before.model.actual_model !== after?.model?.actual_model) {
    throw new Error(`QWENWORK_MODEL_DRIFT: ${before.model.actual_model} -> ${after?.model?.actual_model || "<empty>"}`);
  }
  if (before.permission.confirmed_mode !== after?.permission?.confirmed_mode) {
    throw new Error(`QWENWORK_PERMISSION_DRIFT: ${before.permission.confirmed_mode} -> ${after?.permission?.confirmed_mode || "<empty>"}`);
  }
  return after;
}

export function confirmQwenWorkspaceProject({ projects, workspace, baselineProjectIds = [], expectedProjectId = null }) {
  const expectedWorkspace = resolve(workspace);
  const baseline = new Set(baselineProjectIds);
  const normalized = projects.map((project) => ({
    project_id: project.project_id || project.projectId || null,
    project_name: project.project_name || project.name || null,
    confirmed_path: project.cwd ? resolve(String(project.cwd)) : null,
  }));
  const matches = normalized.filter((project) => (
    project.confirmed_path === expectedWorkspace
    && (!expectedProjectId || project.project_id === expectedProjectId)
    && (expectedProjectId || !baseline.has(project.project_id))
  ));
  if (matches.length !== 1) {
    throw new Error(`QWENWORK_WORKSPACE_PROJECT_COUNT: ${matches.length}`);
  }
  if (!matches[0].project_id || !matches[0].project_name) {
    throw new Error("QWENWORK_WORKSPACE_PROJECT_IDENTITY_MISSING");
  }
  return {
    ...matches[0],
    verification_method: "agents-sqlite-local_projects.root_paths[0]",
  };
}

function isQwenProjectAccessibleName(label, expectedProjectName = null, knownProjectNames = []) {
  const value = visibleValue(label);
  if (/^(?:选择项目|Select project)$/iu.test(value)) return true;
  const knownNames = new Set([
    expectedProjectName,
    ...knownProjectNames,
  ].map(visibleValue).filter(Boolean));
  return knownNames.has(value);
}

async function selectedProjectTrigger(page, expectedProjectName = null, knownProjectNames = []) {
  // QwenWork keeps stale/hidden chat roots mounted. Resolve the current new
  // task view first; a global menu-button count can mix project, workspace,
  // permission, and hidden-window controls.
  const taskView = await requireUniqueVisible(
    page.locator(QWEN_TASK_VIEW_SELECTOR),
    "task-view",
  );
  if (typeof taskView.locator !== "function") {
    throw new Error("QWENWORK_TASK_VIEW_LOCATOR_UNSUPPORTED");
  }
  const candidates = await visibleLocators(taskView.locator(QWEN_PROJECT_SELECTOR));
  const projectSelectors = [];
  for (const candidate of candidates) {
    const label = visibleValue(
      await candidate.getAttribute("aria-label")
      || await candidate.getAttribute("title")
      || await candidate.innerText(),
    );
    if (isQwenProjectAccessibleName(label, expectedProjectName, knownProjectNames)) projectSelectors.push(candidate);
  }
  if (projectSelectors.length !== 1) {
    throw new Error(`QWENWORK_UI_CONTROL_COUNT: project-trigger:${projectSelectors.length}`);
  }
  return projectSelectors[0];
}

export async function ensureQwenNewTaskView(
  page,
  timeoutMilliseconds,
  expectedProjectName = null,
  knownProjectNames = [],
) {
  try {
    return await selectedProjectTrigger(page, expectedProjectName, knownProjectNames);
  } catch (error) {
    if (!/QWENWORK_UI_CONTROL_COUNT: project-trigger:0/u.test(String(error?.message))) throw error;
  }
  const newTask = await requireUniqueVisible(
    page.locator(QWEN_NEW_TASK_SELECTOR),
    "new-task-button",
  );
  await newTask.click({ timeout: timeoutMilliseconds });
  return waitForUniqueVisible(async () => {
    try {
      return [await selectedProjectTrigger(page, expectedProjectName, knownProjectNames)];
    } catch (error) {
      if (/QWENWORK_UI_CONTROL_COUNT: project-trigger:0/u.test(String(error?.message))) return [];
      throw error;
    }
  }, timeoutMilliseconds, "new-task-project-trigger");
}

export async function readSelectedQwenProjectName(page, expectedProjectName = null, knownProjectNames = []) {
  const trigger = await selectedProjectTrigger(page, expectedProjectName, knownProjectNames);
  const value = visibleValue(await trigger.getAttribute("aria-label") || await trigger.innerText());
  if (!value) throw new Error("QWENWORK_PROJECT_READBACK_EMPTY");
  return value;
}

export async function openQwenProjectByName(page, projectName, timeoutMilliseconds, knownProjectNames = []) {
  const trigger = await selectedProjectTrigger(page, projectName, knownProjectNames);
  const current = visibleValue(await trigger.getAttribute("aria-label") || await trigger.innerText());
  if (current === projectName) return { opened: true, method: "already-selected", project_name: projectName };
  await trigger.click({ timeout: timeoutMilliseconds });
  const menu = await waitForUniqueVisible(
    () => visibleLocators(page.getByRole("menu")),
    timeoutMilliseconds,
    "project-menu",
  );
  const label = await waitForUniqueVisible(
    () => visibleLocators(menu.getByText(projectName, { exact: true })),
    timeoutMilliseconds,
    "project-menu-item",
  );
  const item = label.locator('xpath=ancestor-or-self::*[@role="menuitem" or @role="menuitemradio"][1]');
  if (await item.count() !== 1) throw new Error("QWENWORK_PROJECT_MENU_STRUCTURE_INVALID");
  await item.click({ timeout: timeoutMilliseconds });
  const readback = await waitForUniqueVisible(
    async () => (await readSelectedQwenProjectName(page, projectName, [projectName])) === projectName ? [trigger] : [],
    timeoutMilliseconds,
    "selected-project-readback",
  );
  if (!readback) throw new Error("QWENWORK_PROJECT_READBACK_FAILED");
  return { opened: true, method: "project-menu-selection", project_name: projectName };
}

export async function restoreQwenPreparedProject(page, projectName, timeoutMilliseconds, knownProjectNames = []) {
  await ensureQwenNewTaskView(page, timeoutMilliseconds, projectName, knownProjectNames);
  return openQwenProjectByName(page, projectName, timeoutMilliseconds, knownProjectNames);
}

export async function inspectQwenPendingInteraction(page, expectedSession, sessionRows) {
  if (currentQwenConversationId(page.url()) !== expectedSession.conversation_id) {
    throw new Error("QWENWORK_INTERACTION_CONVERSATION_MISMATCH");
  }
  const taskView = await requireUniqueVisible(page.locator(QWEN_TASK_VIEW_SELECTOR), "task-view");
  const heading = visibleValue((await taskView.innerText()).split(/\r?\n/u)[0]);
  const name = heading || visibleValue(await page.title());
  const peers = sessionRows.filter((row) => row.conversation_id === expectedSession.conversation_id
    && row.sub_chat_name === expectedSession.sub_chat_name);
  if (!name || name !== expectedSession.sub_chat_name || peers.length !== 1
      || peers[0].sub_chat_id !== expectedSession.sub_chat_id
      || peers[0].session_id !== expectedSession.session_id) {
    throw new Error("QWENWORK_INTERACTION_SUBCHAT_UNVERIFIED");
  }
  const questions = await visibleLocators(taskView.locator(QWEN_QUESTION_SELECTOR));
  const panels = await visibleLocators(page.locator(QWEN_INTERACTION_SELECTOR));
  let unknownPanels = 0;
  for (const panel of panels) {
    const approvals = await visibleLocators(panel.getByRole("button", {
      name: /^(?:允许|批准|确认执行|始终允许|拒绝|Allow|Approve|Deny)$/iu,
    }));
    if (approvals.length) return { kind: "approval", question_count: questions.length, auto_approve: false };
    // A pending-interaction wrapper around the recognized question is expected.
    // Any other dialog remains a blocker, even without a known button label.
    if ((await visibleLocators(panel.locator(QWEN_QUESTION_SELECTOR))).length !== 1) unknownPanels += 1;
  }
  if (unknownPanels || questions.length > 1) return { kind: "unknown", question_count: questions.length, panel_count: unknownPanels };
  return { kind: questions.length === 1 ? "clarification" : "none", question_count: questions.length };
}

export async function skipQwenClarification(page, conversationId, timeoutMilliseconds = 30_000) {
  if (currentQwenConversationId(page.url()) !== conversationId) {
    throw new Error("QWENWORK_CLARIFICATION_CONVERSATION_MISMATCH");
  }
  const taskView = await requireUniqueVisible(page.locator(QWEN_TASK_VIEW_SELECTOR), "task-view");
  const cards = await visibleLocators(taskView.locator(QWEN_QUESTION_SELECTOR));
  if (cards.length === 0) return { skipped: false };
  if (cards.length !== 1) throw new Error(`QWENWORK_CLARIFICATION_CARD_COUNT: ${cards.length}`);
  const skipButtons = await visibleLocators(cards[0].getByRole("button", { name: "跳过", exact: true }));
  if (skipButtons.length === 0) return { skipped: false };
  if (skipButtons.length !== 1) throw new Error(`QWENWORK_CLARIFICATION_SKIP_COUNT: ${skipButtons.length}`);
  const nextButtons = await visibleLocators(cards[0].getByRole("button", { name: /^下一题/u }));
  if (nextButtons.length !== 1) throw new Error(`QWENWORK_CLARIFICATION_NEXT_COUNT: ${nextButtons.length}`);
  await skipButtons[0].click({ timeout: timeoutMilliseconds });
  const deadline = Date.now() + timeoutMilliseconds;
  while (await skipButtons[0].isVisible().catch(() => false)) {
    if (Date.now() >= deadline) throw new Error("QWENWORK_CLARIFICATION_SKIP_NOT_DISMISSED");
    await sleep(100);
  }
  return { skipped: true, method: "unique-clarification-skip", conversation_id: conversationId };
}

export async function openQwenTaskByProjectAndName(
  page,
  projectName,
  subChatName,
  conversationId,
  timeoutMilliseconds = 30_000,
) {
  if (!subChatName) throw new Error("QWENWORK_SUB_CHAT_NAME_MISSING");
  const currentConversation = currentQwenConversationId(page.url());
  if (currentConversation === conversationId) return { opened: true, method: "already-selected" };
  const projectToggle = await requireUniqueVisible(
    page.getByRole("button", { name: `展开或折叠项目「${projectName}」`, exact: true }),
    "project-sidebar-toggle",
  );
  const section = projectToggle.locator("xpath=../..");
  let task = section.getByRole("button", { name: subChatName, exact: true });
  if (await visibleLocators(task).then((items) => items.length) !== 1) {
    await projectToggle.click({ timeout: timeoutMilliseconds });
    await waitForUniqueVisible(
      () => visibleLocators(section.getByRole("button", { name: subChatName, exact: true })),
      timeoutMilliseconds,
      "project-sidebar-task",
    );
  }
  task = await requireUniqueVisible(
    section.getByRole("button", { name: subChatName, exact: true }),
    "project-sidebar-task",
  );
  await task.click({ timeout: timeoutMilliseconds });
  await waitForUniqueVisible(
    () => page.url().includes(`chat=${conversationId}`) ? [task] : [],
    timeoutMilliseconds,
    "project-sidebar-task-route",
  );
  return { opened: true, method: "project-sidebar-task" };
}

export async function createQwenLocalProject({
  page,
  workspace,
  projectName,
  queryProjects,
  selectNativeFolder,
  timeoutMilliseconds = 30_000,
}) {
  // Recover only the dialog whose exact name belongs to this attempt.
  const dialogs = await visibleLocators(page.getByRole("dialog", { name: "新建个人项目" }));
  if (dialogs.length > 1) throw new Error("QWENWORK_PROJECT_DIALOG_AMBIGUOUS");
  if (dialogs.length === 1) {
    const ownDialog = dialogs[0];
    const name = await ownDialog.getByRole("textbox", { name: "项目名称" }).inputValue();
    if (name !== projectName) throw new Error("QWENWORK_FOREIGN_PROJECT_DIALOG");
    const cancel = await requireUniqueVisible(ownDialog.getByRole("button", { name: "取消", exact: true }), "own-project-dialog-cancel");
    await cancel.click({ timeout: timeoutMilliseconds });
    await ownDialog.waitFor({ state: "hidden", timeout: timeoutMilliseconds });
  }
  const before = await queryProjects();
  const knownProjectNames = before.map((entry) => entry.project_name || entry.name).filter(Boolean);
  await ensureQwenNewTaskView(page, timeoutMilliseconds, projectName, knownProjectNames);
  const existing = before.filter((project) => (
    project.cwd && resolve(String(project.cwd)) === resolve(workspace)
  ));
  if (existing.length) {
    const project = confirmQwenWorkspaceProject({ projects: before, workspace });
    if (project.project_name !== projectName) {
      throw new Error("QWENWORK_EXISTING_WORKSPACE_PROJECT_NAME_MISMATCH");
    }
    await openQwenProjectByName(
      page,
      project.project_name,
      timeoutMilliseconds,
      knownProjectNames,
    );
    return {
      ...project,
      verification_method: `${project.verification_method}+exact-deterministic-name-recovery`,
    };
  }
  const baselineProjectIds = before.map((project) => project.project_id || project.projectId).filter(Boolean);
  const createButton = await requireUniqueVisible(page.locator('button[aria-label="新建项目"]'), "new-project-button");
  await createButton.evaluate((element) => element.click());
  const dialog = await waitForUniqueVisible(
    () => visibleLocators(page.getByRole("dialog", { name: "新建个人项目" })),
    timeoutMilliseconds,
    "new-project-dialog",
  );
  await dialog.getByRole("textbox", { name: "项目名称" }).fill(projectName, { timeout: timeoutMilliseconds });
  const selectedPickers = dialog.locator('[data-slot="path-picker-root"][data-selected="true"] [data-slot="path-picker-trigger"]');
  const picker = await requireUniqueVisible(
    (await visibleLocators(selectedPickers)).length ? selectedPickers : dialog.locator('[data-slot="path-picker-trigger"]'),
    "folder-picker",
  );
  await picker.evaluate((element) => element.click());
  await selectNativeFolder(resolve(workspace));
  const label = dialog.locator(
    '[data-slot="path-picker-root"][data-selected="true"] [data-slot="path-picker-value"]',
  );
  const expectedLabel = basename(workspace);
  await waitForUniqueVisible(async () => {
    const actual = visibleValue(await label.innerText().catch(() => ""));
    return actual === expectedLabel ? [label] : [];
  }, timeoutMilliseconds, "folder-label-readback");
  const submit = await requireUniqueVisible(dialog.getByRole("button", { name: "新建项目", exact: true }), "create-project-submit");
  await submit.click({ timeout: timeoutMilliseconds });
  await dialog.waitFor({ state: "hidden", timeout: timeoutMilliseconds });

  const project = await waitForUniqueVisible(async () => {
    try {
      return [confirmQwenWorkspaceProject({
        projects: await queryProjects(),
        workspace,
        baselineProjectIds,
      })];
    } catch (error) {
      if (/PROJECT_COUNT: 0/u.test(String(error?.message))) return [];
      throw error;
    }
  }, timeoutMilliseconds, "sqlite-workspace-project");
  await openQwenProjectByName(
    page,
    project.project_name,
    timeoutMilliseconds,
    [...knownProjectNames, project.project_name],
  );
  return project;
}

export async function findQwenPromptEditor(page) {
  return requireUniqueVisible(page.locator(QWEN_PROMPT_SELECTOR), "prompt-editor");
}

export function normalizeQwenPromptText(value) {
  return String(value || "")
    .replace(/\r\n?/gu, "\n")
    .replace(/\n{3,}/gu, "\n\n");
}

export async function readQwenPrompt(page) {
  const editor = await findQwenPromptEditor(page);
  const value = await editor.innerText().catch(async () => (
    await editor.inputValue().catch(async () => (
      await editor.textContent().catch(() => "")
    ))
  ));
  return normalizeQwenPromptText(value);
}

export async function fillQwenPrompt(page, prompt, timeoutMilliseconds = 30_000) {
  const editor = await findQwenPromptEditor(page);
  await editor.fill(prompt, { timeout: timeoutMilliseconds });
  const readback = await readQwenPrompt(page);
  if (readback !== prompt) throw new Error("QWENWORK_PROMPT_READBACK_MISMATCH");
  return editor;
}

export async function dispatchQwenPrompt(page, timeoutMilliseconds = 30_000) {
  const button = await requireUniqueVisible(page.locator(QWEN_SEND_SELECTOR), "send-button");
  if (!await button.isEnabled().catch(() => false)) throw new Error("QWENWORK_SEND_BUTTON_DISABLED");
  await button.click({ timeout: timeoutMilliseconds });
  return { invoked: true, method: "unique-accessible-send-button" };
}

function currentQwenConversationId(address) {
  try {
    const parsed = new URL(address);
    const parameters = new URLSearchParams(parsed.search);
    if (parsed.hash.length > 1 && parsed.hash.includes("=")) {
      new URLSearchParams(parsed.hash.slice(1)).forEach((value, key) => parameters.set(key, value));
    }
    return parameters.get("chat") || null;
  } catch {
    return null;
  }
}

export async function inspectQwenTaskUi(page, observedAt, expectedSession = null, sessionRows = []) {
  const stopControls = await visibleLocators(page.locator(QWEN_STOP_SELECTOR));
  const taskViews = await visibleLocators(page.locator(QWEN_TASK_VIEW_SELECTOR));
  const address = typeof page.url === "function" ? page.url() : "";
  const title = visibleValue(typeof page.title === "function" ? await page.title().catch(() => "") : "");
  const conversationId = currentQwenConversationId(address);
  const expectedConversationId = expectedSession?.conversation_id || null;
  const expectedSubChatId = expectedSession?.sub_chat_id || null;
  const expectedSessionId = expectedSession?.session_id || null;
  const expectedSubChatName = visibleValue(expectedSession?.sub_chat_name);
  const peers = Array.isArray(sessionRows) ? sessionRows.filter((entry) => (
    entry?.conversation_id === expectedConversationId
    && visibleValue(entry?.sub_chat_name) === expectedSubChatName
  )) : [];
  const taskHeading = taskViews.length === 1
    ? visibleValue((await taskViews[0].innerText().catch(() => "")).split(/\r?\n/u)[0])
    : "";
  const uiSubChatName = taskHeading || title;
  const exactPeer = peers.length === 1
    && peers[0]?.sub_chat_id === expectedSubChatId
    && peers[0]?.session_id === expectedSessionId;
  const targetSessionVerified = Boolean(
    expectedConversationId
    && expectedSubChatId
    && expectedSessionId
    && expectedSubChatName
    && conversationId === expectedConversationId
    && uiSubChatName === expectedSubChatName
    && exactPeer
    && taskViews.length === 1
  );
  const conflicts = [];
  if (!expectedConversationId || conversationId !== expectedConversationId) {
    conflicts.push(`ui-conversation-mismatch:${conversationId || "<none>"}`);
  }
  if (!expectedSubChatName || uiSubChatName !== expectedSubChatName) {
    conflicts.push(`ui-sub-chat-title-mismatch:${uiSubChatName || "<none>"}`);
  }
  if (!exactPeer) conflicts.push(`ui-sub-chat-identity-count:${peers.length}`);
  if (taskViews.length !== 1) conflicts.push(`ui-task-view-count:${taskViews.length}`);
  if (stopControls.length > 1) conflicts.push(`visible-stop-control-count:${stopControls.length}`);
  return {
    observed_at: observedAt,
    source: "electron-cdp-route-title-task-container-visible-controls+sqlite-identity",
    target_session_verified: targetSessionVerified,
    ui_binding: {
      conversation_id: conversationId,
      sub_chat_id: targetSessionVerified ? expectedSubChatId : null,
      session_id: targetSessionVerified ? expectedSessionId : null,
      sub_chat_name: uiSubChatName || null,
      unique_database_identity: exactPeer,
    },
    active_stream: targetSessionVerified ? stopControls.length === 1 : null,
    stop_confirmed: targetSessionVerified && stopControls.length === 0,
    conflicts,
  };
}

export function isQwenWorkMainPage({ title = "", url = "" }) {
  const address = String(url);
  if (/(?:[?#&])windowId=main(?:[&#]|$)/iu.test(address)) return true;
  return /QwenWork|千问办公/iu.test(String(title)) && !/voice-overlay\.html/iu.test(address);
}

export async function chooseQwenWorkMainPage(browser, timeoutMilliseconds, pause = sleep) {
  const deadline = Date.now() + timeoutMilliseconds;
  while (Date.now() <= deadline) {
    const pages = browser.contexts().flatMap((context) => context.pages());
    const matches = [];
    for (const page of pages) {
      const descriptor = { title: await page.title().catch(() => ""), url: page.url() };
      if (isQwenWorkMainPage(descriptor)) matches.push(page);
    }
    if (matches.length === 1) return matches[0];
    if (matches.length > 1) throw new Error(`QWENWORK_MAIN_PAGE_AMBIGUOUS: ${matches.length}`);
    await pause(Math.min(100, Math.max(1, deadline - Date.now())));
  }
  throw new Error("QWENWORK_MAIN_PAGE_NOT_FOUND");
}
