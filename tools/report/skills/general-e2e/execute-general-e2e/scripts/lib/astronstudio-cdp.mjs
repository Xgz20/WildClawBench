import { queryExactProjectsForWorkspace, queryProjectForThread, queryNativeSessions, queryPristineThread } from "./astronstudio-state.mjs";
import { readCurrentCustomModel } from "./astronstudio-custom-model.mjs";
import {readNativeForegroundApp} from './astronstudio-native-foreground.mjs';

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

async function fetchJson(url, timeoutMs, fetchImpl = fetch) {
  const response = await fetchImpl(url, {
    method: "GET",
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  return response.json();
}

function isMainTarget(target) {
  if (target?.type !== "page" || String(target.title || "").trim() !== "AStudio") return false;
  try {
    const url = new URL(String(target.url || ""));
    return url.protocol === "acode:" && url.host === "app" && url.pathname === "/index.html";
  } catch {
    return false;
  }
}

export async function discoverMainTarget(endpoint, timeoutMs, fetchImpl = fetch) {
  const targets = await fetchJson(`${endpoint}/json/list`, timeoutMs, fetchImpl);
  const matches = Array.isArray(targets) ? targets.filter(isMainTarget) : [];
  if (matches.length !== 1) throw new Error(`AstronStudio 主页面数量异常：${matches.length}`);
  if (!matches[0].webSocketDebuggerUrl) throw new Error("AstronStudio 主页面缺少 CDP WebSocket URL");
  return matches[0];
}

export class CdpClient {
  constructor(socket, timeoutMs = 30_000) {
    this.socket = socket;
    this.timeoutMs = timeoutMs;
    this.nextId = 1;
    this.pending = new Map();
    socket.addEventListener("message", (event) => this.onMessage(event));
    socket.addEventListener("close", () => this.failPending(new Error("CDP WebSocket 已关闭")));
    socket.addEventListener("error", () => this.failPending(new Error("CDP WebSocket 连接失败")));
  }

  static async connect(webSocketUrl, timeoutMs = 30_000, WebSocketImpl = globalThis.WebSocket) {
    if (typeof WebSocketImpl !== "function") throw new Error("当前 Node.js 不提供 WebSocket API");
    const socket = new WebSocketImpl(webSocketUrl);
    await new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => rejectPromise(new Error("CDP WebSocket 连接超时")), timeoutMs);
      socket.addEventListener("open", () => {
        clearTimeout(timer);
        resolvePromise();
      }, { once: true });
      socket.addEventListener("error", () => {
        clearTimeout(timer);
        rejectPromise(new Error("CDP WebSocket 连接失败"));
      }, { once: true });
    });
    return new CdpClient(socket, timeoutMs);
  }

  onMessage(event) {
    let message;
    try {
      message = JSON.parse(String(event.data));
    } catch {
      return;
    }
    if (!message?.id || !this.pending.has(message.id)) return;
    const pending = this.pending.get(message.id);
    this.pending.delete(message.id);
    clearTimeout(pending.timer);
    if (message.error) pending.reject(new Error(message.error.message || "CDP 请求失败"));
    else pending.resolve(message.result || {});
  }

  failPending(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }

  send(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        rejectPromise(new Error(`CDP ${method} 超时`));
      }, this.timeoutMs);
      this.pending.set(id, { resolve: resolvePromise, reject: rejectPromise, timer });
      try {
        this.socket.send(JSON.stringify({ id, method, params }));
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        rejectPromise(error);
      }
    });
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
      userGesture: false,
    });
    if (result.exceptionDetails) {
      throw new Error(
        result.exceptionDetails.exception?.description
        || result.exceptionDetails.text
        || "CDP Runtime.evaluate 失败",
      );
    }
    return result.result?.value;
  }

  close() {
    try {
      this.socket.close();
    } catch {
      // Ignore a close race after Electron has already closed the socket.
    }
  }
}

export function isEndedCompletionToast(element, readStyle = getComputedStyle) {
  if (!element || typeof element.getAttribute !== 'function'
    || element.getAttribute('role') !== 'dialog' || element.getAttribute('aria-modal') !== 'false'
    || element.getAttribute('data-type') !== 'success' || element.getAttribute('data-position') !== 'top-center'
    || !element.hasAttribute('data-ending-style') || !element.querySelector('[data-slot="toast-title"]')
    || !element.querySelector('[data-slot="toast-description"]') || element.querySelectorAll('input,textarea,select').length) return false;
  const buttons = Array.from(element.querySelectorAll('button'));
  if (buttons.length !== 2 || buttons.filter(b => b.getAttribute('data-slot') === 'toast-action' && b.getAttribute('aria-label') === '打开').length !== 1
    || buttons.filter(b => b.getAttribute('data-slot') === 'toast-close' && b.getAttribute('aria-label') === '关闭通知').length !== 1) return false;
  const style = readStyle(element);
  return Number(style.opacity) === 0 && style.pointerEvents === 'none';
}

const HELPERS = `
  const isEndedCompletionToast = (${isEndedCompletionToast.toString()});
  const visible = (element) => {
    if (!(element instanceof Element)) return false;
    if (element.closest('[inert], [aria-hidden="true"]')) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
  };
  const blockingDialog = (element) => visible(element) && !isEndedCompletionToast(element);
  const exactText = (selector, pattern) => Array.from(document.querySelectorAll(selector))
    .filter(visible)
    .filter((element) => pattern.test((element.innerText || element.textContent || "").trim()));
  const threadId = () => {
    const match = location.hash.match(/^#\\/([^/?#]+)/u);
    return match?.[1] ? decodeURIComponent(match[1]) : null;
  };
`;

function expression(body) {
  return `(() => {${HELPERS}\n${body}\n})()`;
}

async function waitFor(read, accept, timeoutMs, description, pollMs = 200) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() <= deadline) {
    last = await read();
    if (accept(last)) return last;
    await sleep(Math.min(pollMs, Math.max(1, deadline - Date.now())));
  }
  throw new Error(`${description}超时：${JSON.stringify(last)}`);
}

export async function readUiConfiguration(client, stateDatabase) {
  const ui = await client.evaluate(expression(`
    const models = Array.from(document.querySelectorAll(
      'button[aria-label="切换模型和推理设置"], button[aria-label="Change model and reasoning"], button[aria-label="切换模型"], button[aria-label="Change model"]'
    )).filter(visible);
    const permissions = Array.from(document.querySelectorAll('button.runtime-permission-trigger')).filter(visible);
    const lines = models.length === 1
      ? (models[0].innerText || "").split(/\\r?\\n/u).map((value) => value.trim()).filter(Boolean)
      : [];
    return {
      thread_id: threadId(),
      model_count: models.length,
      model: lines[0] || null,
      reasoning: lines.length > 1 ? lines.slice(1).join(" ") : null,
      permission_count: permissions.length,
      permission: permissions.length === 1 ? (permissions[0].innerText || "").trim() || null : null
    };
  `));
  if (["自定义", "Custom"].includes(ui.reasoning)) {
    ui.custom_mapping = await readCurrentCustomModel(stateDatabase,
      { count: ui.model_count, text: `${ui.model}\n${ui.reasoning}` });
    ui.reasoning = ui.custom_mapping.reasoning_effort;
    ui.reasoning_source = "account-scoped-custom-config.explicit-defaultReasoning";
  }
  return ui;
}

async function editorState(client) {
  return client.evaluate(expression(`
    const editors = Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(visible);
    return {
      thread_id: threadId(),
      editor_count: editors.length,
      dialog_count: Array.from(document.querySelectorAll('[role="dialog"],[role="alertdialog"],[aria-modal="true"]')).filter(blockingDialog).length,
      editor_text: editors.length === 1 ? (editors[0].innerText || "").trim() : null,
      link_chips: editors.length === 1
        ? Array.from(editors[0].querySelectorAll('[role="link"][contenteditable="false"]'))
          .map((chip) => ({ title: chip.getAttribute('title'), display: chip.innerText || '' }))
        : []
    };
  `));
}

export function renderExpectedPrompt(expected, linkChips) {
  if (typeof expected !== "string" || !Array.isArray(linkChips)) return null;
  let cursor = 0;
  let rendered = "";
  for (const chip of linkChips) {
    if (typeof chip?.title !== "string" || !/^https?:\/\//u.test(chip.title)
      || typeof chip?.display !== "string" || !chip.display) return null;
    const index = expected.indexOf(chip.title, cursor);
    if (index < 0) return null;
    rendered += expected.slice(cursor, index) + chip.display;
    cursor = index + chip.title.length;
  }
  return rendered + expected.slice(cursor);
}

export async function clickNewTask(client) {
  return client.evaluate(expression(`
    let buttons = exactText('button', /^(?:新建任务|New task)$/iu);
    if (buttons.length === 0) {
      buttons = Array.from(document.querySelectorAll('button[data-testid="new-thread-button"]')).filter(visible);
    }
    if (buttons.length !== 1) return { clicked: false, count: buttons.length };
    buttons[0].click();
    return { clicked: true, count: 1 };
  `));
}

export async function clickSidebarToggle(client) {
  return client.evaluate(expression(`
    const candidates = Array.from(document.querySelectorAll('button[aria-label]'))
      .filter(visible)
      .filter((button) => /^(?:切换对话侧边栏|切换任务侧边栏|Toggle conversation sidebar|Toggle Sidebar)$/iu.test(
        (button.getAttribute('aria-label') || '').trim()
      ))
      .filter((button) => {
        if (typeof document.elementFromPoint !== 'function') return true;
        const rect = button.getBoundingClientRect();
        const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        return hit === button || button.contains(hit);
      });
    const controls = candidates.filter(button => button.getAttribute('data-sidebar') !== 'rail');
    const buttons = controls.length ? controls : candidates;
    if (buttons.length !== 1) return { clicked: false, count: buttons.length };
    buttons[0].click();
    return { clicked: true, count: 1 };
  `));
}

export async function createFreshTask(client, timeoutMs, stateDatabase) {
  const before = await editorState(client);
  if (before.dialog_count > 0) throw new Error('UNKNOWN_DIALOG_BLOCKS_NEW_TASK');
  if (before.editor_count === 1 && before.editor_text) {
    throw new Error("UNSENT_DRAFT_BLOCKS_NEW_TASK: preserve draft; use the bound zero-send preparation entrypoint before retrying");
  }
  const pristine = before.thread_id && before.editor_text === "" && stateDatabase
    ? await queryPristineThread(stateDatabase, before.thread_id) : false;
  let clicked = await clickNewTask(client);
  if (!clicked.clicked && clicked.count === 0) {
    const sidebar = await clickSidebarToggle(client);
    if (sidebar.count > 1) throw new Error(`AstronStudio 对话侧边栏按钮数量异常：${sidebar.count}`);
    if (sidebar.clicked) {
      clicked = await waitFor(
        () => clickNewTask(client),
        (value) => value.clicked || value.count > 1,
        timeoutMs,
        "等待 AstronStudio 新建任务按钮",
      );
    }
  }
  if (!clicked.clicked) throw new Error(`AstronStudio 新建任务按钮数量异常：${clicked.count}`);
  return waitFor(
    async () => {
      const state = await editorState(client);
      return {
        thread_id: state.thread_id,
        editor_count: state.editor_count,
        editor_empty: state.editor_text === "",
        editor_length: state.editor_text?.length ?? null,
      };
    },
    (value) => value.editor_count === 1
      && Boolean(value.thread_id)
      && value.editor_empty
      && (value.thread_id !== before.thread_id || pristine),
    timeoutMs,
    "等待 AstronStudio 空白任务路由",
  );
}

async function workspaceState(client) {
  return client.evaluate(expression(`
    const triggers = ['workspace-picker-trigger', 'project-picker-trigger']
      .flatMap((testId) => Array.from(document.querySelectorAll('[data-testid="' + testId + '"]')))
      .filter(visible);
    return {
      count: triggers.length,
      path: triggers.length === 1 ? (triggers[0].getAttribute('title') || '').trim() || null : null,
      menu_open: triggers.length === 1 && (triggers[0].getAttribute('aria-expanded') === 'true'
        || triggers[0].getAttribute('data-state') === 'open'),
      label: triggers.length === 1 ? (triggers[0].innerText || '').trim() || null : null
    };
  `));
}

async function clickWorkspaceTrigger(client) {
  return client.evaluate(expression(`
    const triggers = ['workspace-picker-trigger', 'project-picker-trigger']
      .flatMap((testId) => Array.from(document.querySelectorAll('[data-testid="' + testId + '"]')))
      .filter(visible);
    if (triggers.length !== 1) return { clicked: false, count: triggers.length };
    triggers[0].click();
    return { clicked: true, count: 1 };
  `));
}

async function selectExistingWorkspace(client, workspace) {
  return client.evaluate(expression(`
    const expected = ${JSON.stringify(workspace)};
    const options = Array.from(document.querySelectorAll('[role="option"]')).filter(visible);
    const matches = options.filter((option) => {
      const paths = option.querySelectorAll('.project-picker-path');
      return paths.length === 1 && (paths[0].innerText || '').trim() === expected;
    });
    if (matches.length !== 1) return { selected: false, count: matches.length, option_count: options.length };
    matches[0].click();
    return { selected: true, count: 1, option_count: options.length };
  `));
}

async function clickExactButton(client, patternSource, description) {
  const result = await client.evaluate(expression(`
    const pattern = new RegExp(${JSON.stringify(patternSource)}, 'iu');
    const buttons = exactText('button', pattern);
    if (buttons.length !== 1) return { clicked: false, count: buttons.length };
    buttons[0].click();
    return { clicked: true, count: 1 };
  `));
  if (!result.clicked) throw new Error(`${description}数量异常：${result.count}`);
}

export async function clickProjectsTab(client) {
  const result = await client.evaluate(expression(`
    const pickers = Array.from(document.querySelectorAll('.sidebar-segmented-picker')).filter(visible);
    if (pickers.length !== 1) return { clicked: false, picker_count: pickers.length, count: 0 };
    const buttons = Array.from(pickers[0].querySelectorAll('button')).filter(visible)
      .filter(button => /^(?:项目|Projects)$/iu.test((button.innerText || '').trim()));
    if (buttons.length !== 1) return { clicked: false, picker_count: 1, count: buttons.length };
    buttons[0].click();
    return { clicked: true, picker_count: 1, count: 1 };
  `));
  if (!result.clicked) throw new Error(`AstronStudio 侧栏项目标签不唯一：${JSON.stringify(result)}`);
  return result;
}

export async function submitExactProjectPath(client, workspace) {
  return client.evaluate(expression(`
    const expected = ${JSON.stringify(workspace)};
    const inputs = Array.from(document.querySelectorAll(
      'input[aria-label="项目路径"], input[aria-label="Project path"]'
    )).filter(visible);
    if (inputs.length !== 1 || inputs[0].value !== expected
      || inputs[0].getAttribute('value') !== expected) return { clicked: false, reason: 'path-not-committed' };
    // The native setter can update value before React commits its handler.
    // Require the rendered value attribute, then use only the adjacent field
    // submit control. The sidebar toggle has the same accessible label.
    const row = inputs[0].closest('[data-slot="input-control"]')?.parentElement;
    if (!row || row.querySelectorAll('input').length !== 1) return { clicked: false, reason: 'path-row-unknown' };
    const buttons = Array.from(row.querySelectorAll(
      'button[aria-label="添加项目"], button[aria-label="Add project"]'
    )).filter(visible).filter(button => !button.disabled);
    if (buttons.length !== 1) return { clicked: false, count: buttons.length };
    buttons[0].click(); return { clicked: true, count: 1, workspace: expected, source: 'committed-path-field-submit' };
  `));
}

export async function readProjectPathCompletion(client, workspace) {
  return client.evaluate(expression(`
    const paths = Array.from(document.querySelectorAll(
      '[data-testid="workspace-picker-trigger"], [data-testid="project-picker-trigger"]'
    )).filter(visible).map(element => element.getAttribute('title'));
    const inputs = Array.from(document.querySelectorAll(
      'input[aria-label="项目路径"], input[aria-label="Project path"]'
    )).filter(visible);
    const cancel = Array.from(document.querySelectorAll(
      'button[aria-label="取消添加项目"], button[aria-label="Cancel adding project"]'
    )).filter(visible);
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"]')).filter(blockingDialog);
    return { complete: inputs.length === 0 && cancel.length === 0 && dialogs.length === 0
      && paths.length === 1 && paths[0] === ${JSON.stringify(workspace)},
      input_count: inputs.length, cancel_count: cancel.length, dialog_count: dialogs.length, paths };
  `));
}

export async function addWorkspace(client, workspace, timeoutMs) {
  await clickProjectsTab(client);
  await resetOwnedProjectPathForm(client,workspace);
  await waitFor(
    () => client.evaluate(expression(`
      const pickers = Array.from(document.querySelectorAll('.sidebar-segmented-picker'))
        .filter(visible);
      const tabs = pickers.length === 1 ? Array.from(pickers[0].querySelectorAll('button')) : [];
      const projects = tabs.filter((button) => /^(?:项目|Projects)$/iu.test(
        (button.innerText || '').trim()
      ));
      const adds = Array.from(document.querySelectorAll(
        'button[aria-label="添加项目"], button[aria-label="Add project"]'
      )).filter(visible).filter((button) => !button.disabled);
      return { picker_count: pickers.length, project_tab_count: projects.length,
        project_selected: projects.length === 1 && projects[0].classList.contains('font-semibold'),
        add_count: adds.length };
    `)),
    (value) => value.picker_count === 1 && value.project_tab_count === 1
      && value.project_selected && value.add_count === 1,
    timeoutMs,
    "等待 AstronStudio 项目标签切换完成",
  );
  const add = await client.evaluate(expression(`
    const buttons = Array.from(document.querySelectorAll(
      'button[aria-label="添加项目"], button[aria-label="Add project"]'
    )).filter(visible).filter((button) => !button.disabled);
    if (buttons.length !== 1) return { clicked: false, count: buttons.length };
    buttons[0].click();
    return { clicked: true, count: 1 };
  `));
  if (!add.clicked) throw new Error(`AstronStudio 添加项目按钮数量异常：${add.count}`);
  await waitFor(
    () => client.evaluate(expression(`
      const buttons = exactText('button', /^(?:输入路径|Type path)$/iu);
      if (buttons.length !== 1) return { clicked: false, count: buttons.length };
      buttons[0].click();
      return { clicked: true, count: 1 };
    `)),
    (value) => value.clicked,
    timeoutMs,
    "等待 AstronStudio 输入项目路径按钮",
  );
  const typed = await waitFor(
    () => client.evaluate(expression(`
      const expected = ${JSON.stringify(workspace)};
      const inputs = Array.from(document.querySelectorAll(
        'input[aria-label="项目路径"], input[aria-label="Project path"]'
      )).filter(visible);
      if (inputs.length !== 1) return { typed: false, count: inputs.length };
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      if (!setter) throw new Error('HTMLInputElement value setter unavailable');
      setter.call(inputs[0], expected);
      inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
      inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
      return { typed: inputs[0].value === expected, count: 1 };
    `)),
    (value) => value.typed,
    timeoutMs,
    "等待 AstronStudio 项目路径输入框",
  );
  if (!typed.typed) throw new Error("AstronStudio 项目路径输入失败");
  const submitted = await waitFor(
    () => submitExactProjectPath(client, workspace),
    (value) => value.clicked,
    timeoutMs,
    "等待 AstronStudio 项目路径提交按钮",
  );
  if (!submitted.clicked) throw new Error("AstronStudio 项目路径提交失败");
  let settledAt = null;
  await waitFor(
    () => readProjectPathCompletion(client, workspace),
    value => {
      if (!value.complete) { settledAt = null; return false; }
      settledAt ??= Date.now();
      return Date.now() - settledAt >= 200;
    },
    timeoutMs,
    '等待 AstronStudio 项目路径提交完成及完整工作区回显',
  );
}

export async function resetOwnedProjectPathForm(client,workspace) {
  const result=await client.evaluate(expression(`
    const inputs=Array.from(document.querySelectorAll('input[aria-label="项目路径"], input[aria-label="Project path"]')).filter(visible);
    if(!inputs.length)return {reset:false,absent:true};
    const cancel=Array.from(document.querySelectorAll('button[aria-label="取消添加项目"], button[aria-label="Cancel adding project"]')).filter(visible);
    const dialogs=Array.from(document.querySelectorAll('[role="dialog"],dialog')).filter(blockingDialog);
    if(inputs.length!==1||inputs[0].value!==${JSON.stringify(workspace)}||cancel.length!==1||dialogs.length)
      return {reset:false,unsafe:true};
    cancel[0].click();return {reset:true,owned_workspace:${JSON.stringify(workspace)}};
  `));
  if(result.unsafe)throw Error('PROJECT_PATH_DRAFT_NOT_OWNED');
  return result;
}

export async function waitForExactProjectIdentity(stateDatabase, workspace, timeoutMs, overrides = {}) {
  const read = overrides.queryExactProjectsForWorkspace || queryExactProjectsForWorkspace;
  const rows = await waitFor(async () => {
    const value = await read(stateDatabase, workspace);
    if (value.length > 1) throw new Error(`AstronStudio 目标项目原生身份不唯一：${value.length}`);
    return value;
  }, (value) => value.length === 1, timeoutMs, "等待 AstronStudio 原生项目登记");
  if (rows.length !== 1 || typeof rows[0].project_id !== "string") {
    throw new Error(`AstronStudio 目标项目原生身份不唯一：${rows.length}`);
  }
  return rows[0].project_id;
}

export async function reloadIdleProjectProjection(client, stateDatabase, overrides = {}) {
  const sessions = await (overrides.queryNativeSessions || queryNativeSessions)(stateDatabase);
    if (sessions.some((row) => row.active_turn_id
      || ["running", "starting", "pending", "needs_attention"].includes(String(row.status).toLowerCase()))) {
      throw new Error("AstronStudio 项目投影缺失且有活动任务；不能刷新客户端");
    }
    const readSafety = () => client.evaluate(expression(`
      const editors = Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(visible);
      return { editor_count: editors.length, empty: editors.length === 1 && (editors[0].innerText || '').trim() === '',
        dialogs: Array.from(document.querySelectorAll('[role="dialog"],[aria-modal="true"]')).filter(blockingDialog).length,
        stops: Array.from(document.querySelectorAll('button[aria-label]')).filter(visible)
          .filter((button) => /^(?:停止生成|Stop generating)$/iu.test(button.getAttribute('aria-label') || '')).length };
    `));
    let safe = await readSafety();
    if (safe.editor_count === 0 && !safe.dialogs && !safe.stops) {
      safe = await waitFor(readSafety, (row) => row.editor_count !== 0 || row.dialogs || row.stops,
        overrides.timeoutMs || 5_000, "等待 AstronStudio 刷新前编辑器就绪");
    }
    if (safe.editor_count !== 1 || !safe.empty || safe.dialogs || safe.stops) {
      throw new Error("AstronStudio 项目投影刷新存在草稿、弹窗或活动任务");
    }
    const currentSessions = await (overrides.queryNativeSessions || queryNativeSessions)(stateDatabase);
    if (currentSessions.some((row) => row.active_turn_id
      || ["running", "starting", "pending", "needs_attention"].includes(String(row.status).toLowerCase()))) {
      throw new Error("AstronStudio 刷新前出现活动任务");
    }
    await client.send("Page.reload");
}

export async function openExactProjectConversation(client, workspace, stateDatabase, timeoutMs, options = {}) {
  if (!stateDatabase) throw new Error("AstronStudio 目标项目导航缺少原生状态库路径");
  const projectId = await waitForExactProjectIdentity(stateDatabase, workspace, timeoutMs);
  const initialRoute = await currentThreadId(client);
  const readActivity = () => client.evaluate(expression(`
    const editors = Array.from(document.querySelectorAll('[data-testid="composer-editor"]'))
      .filter(visible);
    const buttons = Array.from(document.querySelectorAll('button')).filter(visible);
    return { editor_count: editors.length,
      editor_empty: editors.length === 1 && (editors[0].innerText || '').trim() === '',
      dialog_count: Array.from(document.querySelectorAll(
        '[role="dialog"], [aria-modal="true"]'
      )).filter(blockingDialog).length,
      stop_count: buttons.filter((button) => /^(?:停止生成|Stop generating)$/iu.test(
        (button.getAttribute('aria-label') || '').trim()
      )).length };
  `));
  let activity = await readActivity();
  if (activity.editor_count === 0 && activity.dialog_count === 0 && activity.stop_count === 0) {
    activity = await waitFor(readActivity, (row) => row.editor_count !== 0 || row.dialog_count || row.stop_count,
      Math.min(timeoutMs, 5_000), "等待 AstronStudio 目标项目编辑器就绪");
  }
  if (activity.editor_count !== 1 || !activity.editor_empty
    || activity.dialog_count !== 0 || activity.stop_count !== 0) {
    throw new Error("AstronStudio 目标项目导航时存在草稿、弹窗或活动任务");
  }
  const lateWorkspace = await workspaceState(client);
  if (lateWorkspace.count === 1 && lateWorkspace.path === workspace) {
    // The picker can finish rendering after the initial route was sampled.
    // Accept only a fresh, stable route with the exact native project binding.
    const lateEditor = await editorState(client);
    if (lateEditor.editor_count !== 1 || lateEditor.editor_text !== "") {
      throw new Error("AstronStudio 延迟项目导航期间出现草稿或编辑器歧义");
    }
    const lateRoute = lateEditor.thread_id;
    const native = lateRoute ? await queryProjectForThread(stateDatabase, lateRoute) : [];
    const pristine = !options.forceNew || (lateRoute && await queryPristineThread(stateDatabase, lateRoute));
    const stableEditor = await editorState(client);
    const stableWorkspace = await workspaceState(client);
    if (stableEditor.editor_count !== 1 || stableEditor.editor_text !== "") {
      throw new Error("AstronStudio 延迟项目核验期间出现草稿或编辑器歧义");
    }
    if (lateRoute && lateRoute === stableEditor.thread_id && stableWorkspace.count === 1
      && stableWorkspace.path === workspace && pristine && native.length === 1
      && native[0].project_id === projectId && native[0].workspace_root === workspace) {
      return { method: options.forceNew ? "native-pristine-project-conversation" : "late-visible-current-value", project_id: projectId,
        thread_id: lateRoute, editor_count: 1, editor_empty: true, ...stableWorkspace };
    }
    // A visible picker selection alone does not rebind a pristine conversation.
    // Continue through the exact project's own New conversation entry below.
    activity = await readActivity();
    if (activity.editor_count !== 1 || !activity.editor_empty || activity.dialog_count || activity.stop_count) {
      throw new Error("AstronStudio 原生项目切换前出现草稿、弹窗或活动任务");
    }
  }
  if (lateWorkspace.count > 1 || (!options.forceNew && lateWorkspace.count === 1
    && lateWorkspace.path !== null && lateWorkspace.path !== workspace)) {
    throw new Error(`AstronStudio 目标项目导航前路径歧义：${JSON.stringify(lateWorkspace)}`);
  }
  const readProjectRow = () => client.evaluate(expression(`
      const rows = Array.from(document.querySelectorAll(
        '[data-project-hover-anchor="${projectId}"]'
      ));
      const motion = rows.length === 1 ? rows[0].closest('[data-slot="sidebar-content-motion"]') : null;
      return { count: rows.length, inert: motion?.inert ?? null,
        hidden: motion?.getAttribute('aria-hidden') ?? null };
    `));
  let projectionReloaded = false;
  let firstRow = await readProjectRow();
  if (firstRow.count === 0) {
    try {
      firstRow = await waitFor(readProjectRow, (row) => row.count !== 0,
        Math.min(timeoutMs, 3_000), "等待 AstronStudio 项目投影就绪");
    } catch { firstRow = await readProjectRow(); }
  }
  if (firstRow.count === 0) {
    // Native registration can succeed while the renderer misses its snapshot.
    // A reload is safe only before filling a prompt and with all native tasks idle.
    await reloadIdleProjectProjection(client, stateDatabase);
    projectionReloaded = true;
  }
  const sidebar = await waitFor(
    readProjectRow,
    (value) => value.count === 1,
    timeoutMs,
    "等待 AstronStudio 目标项目行",
  );
  if (sidebar.inert || sidebar.hidden === "true") {
    const opened = await clickSidebarToggle(client);
    if (!opened.clicked) throw new Error(`AstronStudio 目标项目侧边栏按钮数量异常：${opened.count}`);
  }
  await waitFor(
    () => client.evaluate(expression(`
      const rows = Array.from(document.querySelectorAll(
        '[data-project-hover-anchor="${projectId}"]'
      ));
      const motion = rows.length === 1 ? rows[0].closest('[data-slot="sidebar-content-motion"]') : null;
      return { count: rows.length, interactive: Boolean(motion) && !motion.inert
        && motion.getAttribute('aria-hidden') !== 'true' };
    `)),
    (value) => value.count === 1 && value.interactive,
    timeoutMs,
    "等待 AstronStudio 目标项目侧边栏可交互",
  );
  await client.evaluate(expression(`
    document.querySelector('[data-project-hover-anchor="${projectId}"]')
      ?.scrollIntoView({ block: 'center', inline: 'nearest' });
  `));
  await sleep(150);
  const point = await client.evaluate(expression(`
    const row = document.querySelector('[data-project-hover-anchor="${projectId}"]');
    const buttons = row ? Array.from(row.querySelectorAll('button[aria-label]'))
      .filter((button) => /^(?:在 .+ 中新建(?:对话|任务)|New chat in .+|New task in .+)$/iu.test(
        (button.getAttribute('aria-label') || '').trim()
      )) : [];
    const rect = buttons.length === 1 ? buttons[0].getBoundingClientRect() : null;
    return { count: buttons.length, x: rect ? rect.x + rect.width / 2 : null,
      y: rect ? rect.y + rect.height / 2 : null, viewport_width: innerWidth,
      viewport_height: innerHeight };
  `));
  if (point.count !== 1 || point.x <= 0 || point.x >= point.viewport_width
    || point.y <= 0 || point.y >= point.viewport_height) {
    throw new Error(`AstronStudio 目标项目新建对话按钮不唯一或不可见：${JSON.stringify(point)}`);
  }
  await client.send("Input.dispatchMouseEvent", {
    type: "mouseMoved", x: point.x, y: point.y, button: "none",
  });
  const clicked = await client.evaluate(expression(`
    const dialogs = Array.from(document.querySelectorAll(
      '[role="dialog"], [aria-modal="true"]'
    )).filter(blockingDialog);
    const stops = Array.from(document.querySelectorAll('button[aria-label]'))
      .filter(visible).filter((button) => /^(?:停止生成|Stop generating)$/iu.test(
        (button.getAttribute('aria-label') || '').trim()
      ));
    if (dialogs.length || stops.length) {
      return { clicked: false, dialogs: dialogs.length, stops: stops.length };
    }
    const rows = Array.from(document.querySelectorAll(
      '[data-project-hover-anchor="${projectId}"]'
    ));
    const buttons = rows.length === 1 ? Array.from(rows[0].querySelectorAll('button[aria-label]'))
      .filter((button) => /^(?:在 .+ 中新建(?:对话|任务)|New chat in .+|New task in .+)$/iu.test(
        (button.getAttribute('aria-label') || '').trim()
      )) : [];
    if (buttons.length !== 1 || buttons[0].disabled || buttons[0].closest('[inert]')) {
      return { clicked: false, rows: rows.length, buttons: buttons.length };
    }
    const rect = buttons[0].getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    if (hit !== buttons[0] && !buttons[0].contains(hit)) {
      return { clicked: false, rows: 1, buttons: 1, hit: false };
    }
    buttons[0].click();
    return { clicked: true, rows: 1, buttons: 1 };
  `));
  if (!clicked.clicked) {
    throw new Error(`AstronStudio 目标项目新建对话按钮被遮挡或身份歧义：${JSON.stringify(clicked)}`);
  }
  const confirmed = await waitFor(
    async () => {
      const editor = await editorState(client);
      const selected = await workspaceState(client);
      return { thread_id: editor.thread_id, editor_count: editor.editor_count,
        editor_empty: editor.editor_text === "", ...selected };
    },
    (value) => value.thread_id && value.editor_count === 1 && value.editor_empty
      && value.count === 1 && value.path === workspace,
    timeoutMs,
    "等待 AstronStudio 目标项目新对话路由和绝对路径",
  );
  await waitFor(async () => {
    const editor = await editorState(client);
    const selected = await workspaceState(client);
    const active = await readActivity();
    if (editor.thread_id !== confirmed.thread_id || editor.editor_count !== 1 || editor.editor_text !== ""
      || selected.count !== 1 || selected.path !== workspace || active.dialog_count || active.stop_count) {
      throw new Error("AstronStudio 等待原生项目同步期间路由、路径、草稿或活动状态发生变化");
    }
    const native = await queryProjectForThread(stateDatabase, confirmed.thread_id);
    if (native.length > 1) throw new Error("AstronStudio 新对话原生项目身份歧义");
    const pristine = !options.forceNew || await queryPristineThread(stateDatabase, confirmed.thread_id);
    if (native.length === 1 && !pristine) {
      throw new Error("AstronStudio 目标项目新对话并非未使用的原生路由");
    }
    return { thread_id: confirmed.thread_id, native_projects: native, pristine,
      expected_project_id: projectId, expected_workspace: workspace };
  }, (value) => value.pristine && value.native_projects.length === 1
    && value.native_projects[0].project_id === projectId
    && value.native_projects[0].workspace_root === workspace,
  timeoutMs, "等待 AstronStudio 新对话原生项目与目标 Workspace 精确同步");
  // A delayed workspace selection can complete on the initial, already
  // pristine target route. The native project and unused-thread checks above
  // establish freshness; a different opaque route ID is not required.
  const finalEditor = await editorState(client);
  const finalWorkspace = await workspaceState(client);
  if (finalEditor.thread_id !== confirmed.thread_id || finalEditor.editor_count !== 1
    || finalEditor.editor_text !== "" || finalWorkspace.count !== 1 || finalWorkspace.path !== workspace) {
    throw new Error("AstronStudio 原生项目核验后路由、路径或草稿发生变化");
  }
  return { method: confirmed.thread_id === initialRoute
    ? (options.forceNew ? "native-pristine-project-conversation" : "late-visible-current-value") : "exact-project-new-conversation",
    project_id: projectId, projection_reloaded: projectionReloaded, ...confirmed };
}

export async function selectWorkspace(client, workspace, timeoutMs, stateDatabase) {
  const before = await workspaceState(client);
  if (before.count > 1) throw new Error(`AstronStudio 项目选择按钮数量异常：${before.count}`);
  if (before.count === 1 && before.path === workspace) return { method: "visible-current-value", ...before };
  const native = stateDatabase ? await queryExactProjectsForWorkspace(stateDatabase, workspace) : null;
  if (native && native.length > 1) throw new Error("AstronStudio 目标项目原生身份不唯一");
  if (native && native.length === 0) {
    // A clean profile has no options in its workspace picker. Register the
    // exact directory directly, then verify the native project and route below.
    if (before.menu_open) {
      await client.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
      await client.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" });
      await waitFor(() => workspaceState(client), (row) => !row.menu_open,
        Math.min(timeoutMs, 5_000), "等待 AstronStudio 项目选择菜单关闭");
    }
    await addWorkspace(client, workspace, timeoutMs);
  } else if (before.count === 1) {
    const trigger = await clickWorkspaceTrigger(client);
    if (!trigger.clicked) throw new Error(`AstronStudio 项目选择按钮数量异常：${trigger.count}`);
    const existing = await waitFor(
      () => selectExistingWorkspace(client, workspace),
      (value) => value.selected || value.option_count > 0,
      timeoutMs,
      "等待 AstronStudio 项目列表",
    );
    if (!existing.selected) {
      await client.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
      await client.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" });
      await waitFor(
        () => client.evaluate(expression(`
          const dialogs = Array.from(document.querySelectorAll(
            '[role="dialog"], [aria-modal="true"]'
          )).filter(blockingDialog);
          const options = Array.from(document.querySelectorAll('[role="option"]'))
            .filter(visible);
          return { dialog_count: dialogs.length, option_count: options.length };
        `)),
        (value) => value.dialog_count === 0 && value.option_count === 0,
        Math.min(timeoutMs, 5_000),
        "等待 AstronStudio 项目选择菜单关闭",
      );
      await addWorkspace(client, workspace, timeoutMs);
    }
  } else {
    await addWorkspace(client, workspace, timeoutMs);
  }
  let immediate = await workspaceState(client);
  if (immediate.count === 0 || (immediate.count === 1 && immediate.path === null)) {
    try {
      immediate = await waitFor(
        () => workspaceState(client),
        (value) => value.count !== 0,
        Math.min(timeoutMs, 1_500),
        "等待 AstronStudio 项目选择控件出现",
      );
    } catch {
      immediate = await workspaceState(client);
    }
  }
  if (shouldOpenExactProjectConversation(immediate)) {
    return openExactProjectConversation(client, workspace, stateDatabase, timeoutMs);
  }
  const confirmed = await waitFor(
    () => workspaceState(client),
    (value) => value.count === 1 && value.path === workspace,
    timeoutMs,
    "等待 AstronStudio 项目绝对路径回读",
  );
  return { method: "exact-path-selection", ...confirmed };
}

export function shouldOpenExactProjectConversation(workspaceStateValue) {
  return workspaceStateValue?.count === 0
    || (workspaceStateValue?.count === 1 && workspaceStateValue?.path === null);
}

export async function fillPrompt(client, prompt, timeoutMs) {
  const prepared = await client.evaluate(expression(`
    const editors = Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(visible);
    if (editors.length !== 1) return { ready: false, count: editors.length, text: null };
    const editor = editors[0];
    const text = (editor.innerText || '').trim();
    if (text) return { ready: false, count: 1, text };
    editor.focus();
    const range = document.createRange();
    range.selectNodeContents(editor);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    return { ready: true, count: 1, text: '' };
  `));
  if (!prepared.ready) {
    throw new Error(
      prepared.count === 1
        ? "AstronStudio Prompt 输入框不是空白，拒绝覆盖"
        : `AstronStudio Prompt 输入框数量异常：${prepared.count}`,
    );
  }
  await client.send("Input.insertText", { text: prompt });
  const expected = prompt.trim().replaceAll("\r\n", "\n");
  return waitFor(
    async () => {
      const state = await editorState(client);
      const rendered = renderExpectedPrompt(expected, state.link_chips);
      return {
        thread_id: state.thread_id,
        editor_count: state.editor_count,
        editor_length: state.editor_text?.length ?? null,
        link_chip_count: state.link_chips.length,
        matches: rendered !== null
          && String(state.editor_text || "").replaceAll("\r\n", "\n") === rendered,
      };
    },
    (value) => value.editor_count === 1 && value.matches,
    timeoutMs,
    "等待 AstronStudio Prompt 内容回读",
  );
}

export async function clearOwnedComposerDraft(client, {route, text}, timeoutMs=5000) {
  const focused=await client.evaluate(expression(`
    const es=Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(visible);
    const dialogs=Array.from(document.querySelectorAll('[role="dialog"],[role="alertdialog"],[aria-modal="true"]')).filter(blockingDialog);
    if(location.hash!==${JSON.stringify(route)}||es.length!==1||dialogs.length
      ||es[0].innerText?.trim()!==${JSON.stringify(text)})return false;
    es[0].focus();return document.activeElement===es[0];
  `));
  if(!focused)throw new Error('OWNED_DRAFT_CHANGED_BEFORE_NATIVE_SELECTION');
  // Native editing commands update the editor's own selection state. A DOM
  // Range alone can leave a final character in a controlled rich-text editor.
  await client.send('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'a',code:'KeyA',modifiers:4,commands:['selectAll']});
  await client.send('Input.dispatchKeyEvent',{type:'keyUp',key:'a',code:'KeyA',modifiers:4});
  await client.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace'});
  await client.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace'});
  let emptySince=null;
  return waitFor(async()=>{const value=await client.evaluate(expression(`
    const es=Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(visible),e=es[0];
    return {route:location.hash,count:es.length,text:e?.innerText?.trim(),
      chips:e?.querySelectorAll('[role="link"][contenteditable="false"]').length,
      dialogs:Array.from(document.querySelectorAll('[role="dialog"],[role="alertdialog"],[aria-modal="true"]')).filter(blockingDialog).length};
  `));const empty=value.route===route&&value.count===1&&value.text===''&&value.chips===0&&value.dialogs===0;
    if(empty&&emptySince===null)emptySince=Date.now();if(!empty)emptySince=null;
    return {...value,empty_stable_ms:emptySince===null?0:Date.now()-emptySince};
  },v=>v.route===route&&v.count===1&&v.text===''&&v.chips===0&&v.dialogs===0&&v.empty_stable_ms>=200,timeoutMs,'验证本题草稿完全清空');
}

export async function inspectSendTarget(client, prompt, workspace) {
  const expectedPrompt = prompt.trim().replaceAll("\r\n", "\n");
  return client.evaluate(expression(`
    const expectedPrompt = ${JSON.stringify(expectedPrompt)};
    const expectedWorkspace = ${JSON.stringify(workspace)};
    const renderExpected = ${renderExpectedPrompt.toString()};
    const editors = Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(visible);
    const workspaces = ['workspace-picker-trigger', 'project-picker-trigger']
      .flatMap((testId) => Array.from(document.querySelectorAll('[data-testid="' + testId + '"]')))
      .filter(visible);
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"]')).filter(blockingDialog);
    const buttons = Array.from(document.querySelectorAll(
      'button[type="submit"][aria-label="发送消息"], button[type="submit"][aria-label="Send message"]'
    )).filter(visible).filter((button) => !button.disabled);
    const editorText = editors.length === 1
      ? (editors[0].innerText || '').replaceAll('\\r\\n', '\\n').trim() : null;
    const linkChips = editors.length === 1
      ? Array.from(editors[0].querySelectorAll('[role="link"][contenteditable="false"]'))
        .map((chip) => ({ title: chip.getAttribute('title'), display: chip.innerText || '' }))
      : [];
    const renderedExpected = renderExpected(expectedPrompt, linkChips);
    const promptMatches = renderedExpected !== null && editorText === renderedExpected;
    const workspacePath = workspaces.length === 1
      ? (workspaces[0].getAttribute('title') || '').trim() : null;
    if (editors.length !== 1 || !promptMatches
      || workspaces.length !== 1 || workspacePath !== expectedWorkspace
      || dialogs.length !== 0 || buttons.length !== 1 || document.visibilityState === 'hidden') {
      return {
        ready: false, count: buttons.length, editor_count: editors.length,
        thread_id: threadId(),
        prompt_matches: promptMatches, link_chip_count: linkChips.length,
        workspace_count: workspaces.length, workspace_matches: workspacePath === expectedWorkspace,
        dialog_count: dialogs.length,
        document_visibility: document.visibilityState || null,
        dialogs: dialogs.map((dialog) => ({ role: dialog.getAttribute('role'),
          label: dialog.getAttribute('aria-label'),
          headings: Array.from(dialog.querySelectorAll('h1,h2,[role="heading"]')).map((e) => e.innerText),
          buttons: Array.from(dialog.querySelectorAll('button')).map((e) => e.innerText || e.getAttribute('aria-label')) }))
      };
    }
    const rect = buttons[0].getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const hit = document.elementFromPoint(x, y);
    if (!hit || (hit !== buttons[0] && !buttons[0].contains(hit))) {
      return { ready: false, count: 1, reason: 'send-button-obscured' };
    }
    return { ready: true, count: 1, x, y, thread_id: threadId(), document_visibility: document.visibilityState || null };
  `));
}

export async function ensureSendTargetReady(client, prompt, workspace, options = {}) {
  // Project preview cards can cover the composer after selecting a Workspace.
  // Verify the exact target before persisting any send intent. A failed check
  // here is provably before the first mouse press.
  const viewport = await client.evaluate("({ width: innerWidth, height: innerHeight })");
  if (!Number.isFinite(viewport?.width) || !Number.isFinite(viewport?.height)
    || viewport.width < 200 || viewport.height < 200) {
    throw new Error("AstronStudio 发送前视口尺寸不可用");
  }
  await client.send("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: Math.floor(viewport.width * 0.6),
    y: Math.min(100, Math.floor(viewport.height * 0.2)),
    button: "none",
  });
  await sleep(500);
  let target = await inspectSendTarget(client, prompt, workspace);
  const boundRoute = target.thread_id;
  const started = Date.now();
  const deadline = started + (options.dialogWaitMs ?? 5_000);
  const sleepFor = options.sleep || sleep;
  let observedDialog = false;
  while (!target.ready && target.dialog_count > 0 && typeof boundRoute === 'string'
    && boundRoute && target.thread_id === boundRoute && target.count === 1
    && target.editor_count === 1 && target.prompt_matches && target.workspace_count === 1
    && target.workspace_matches && Date.now() < deadline) {
    // Wait only for an overlay to disappear on its own. Never approve, dismiss
    // or click a dialog. Any route, prompt or workspace change remains fatal.
    observedDialog = true;
    await sleepFor(Math.min(100, Math.max(1, deadline - Date.now())));
    target = await inspectSendTarget(client, prompt, workspace);
  }
  if (observedDialog && target.thread_id !== boundRoute) {
    throw new Error("AstronStudio 弹窗等待期间目标原生路由发生变化");
  }
  if (!target.ready) {
    throw new Error(`AstronStudio 发送前目标未就绪：${JSON.stringify(target)}`);
  }
  return observedDialog ? { ...target, settled_transient_dialog: true,
    dialog_wait_ms: Date.now() - started } : target;
}

export async function clickSend(client, prompt, workspace, options={}) {
  const target = await inspectSendTarget(client, prompt, workspace);
  if (!target.ready) return { clicked: false, ...target };
  if (Number.isInteger(options.expectedNativePid)) {
    const native = await (options.readNativeForegroundApp || readNativeForegroundApp)();
    if (native.pid !== options.expectedNativePid) return {clicked:false,reason:'native-foreground-owner-changed',native_foreground:native};
  }
  await client.send("Input.dispatchMouseEvent", {
    type: "mouseMoved", x: target.x, y: target.y,
  });
  await client.send("Input.dispatchMouseEvent", {
    type: "mousePressed", x: target.x, y: target.y, button: "left", clickCount: 1,
  });
  await client.send("Input.dispatchMouseEvent", {
    type: "mouseReleased", x: target.x, y: target.y, button: "left", clickCount: 1,
  });
  return { clicked: true, count: 1, thread_id: await currentThreadId(client) };
}

export async function currentThreadId(client) {
  const state = await editorState(client);
  return state.thread_id;
}

export async function prepareExecutionUi(client, config) {
  await client.send("Page.bringToFront");
  const projects = await queryExactProjectsForWorkspace(config.stateDatabase, config.candidateWorkspace);
  if (projects.length > 1) throw new Error("AstronStudio 目标 Workspace 原生项目不唯一");
  let task;
  let workspace;
  if (projects.length === 1) {
    const current = await editorState(client);
    const sessions = await queryNativeSessions(config.stateDatabase);
    if (sessions.some((row) => row.thread_id === current.thread_id && (row.active_turn_id
      || ["running", "starting", "pending", "needs_attention"].includes(String(row.status).toLowerCase())))) {
      task = await createFreshTask(client, config.timeoutMs, config.stateDatabase);
    }
    workspace = await openExactProjectConversation(client, config.candidateWorkspace,
      config.stateDatabase, config.timeoutMs, { forceNew: true });
    task ||= { thread_id: workspace.thread_id, editor_count: 1, editor_empty: true };
  } else {
    const current = await editorState(client);
    const sessions = await queryNativeSessions(config.stateDatabase);
    const active = sessions.some((row) => row.thread_id === current.thread_id && (row.active_turn_id
      || ["running", "starting", "pending", "needs_attention"].includes(String(row.status).toLowerCase())));
    // A startup draft may not have a native thread yet. It is only a landing
    // surface for project registration; the final native route is verified below.
    task = current.editor_count === 1 && current.editor_text === "" && !active
      ? { thread_id: current.thread_id, editor_count: 1, editor_empty: true,
        method: "empty-editor-for-project-preparation" }
      : await createFreshTask(client, config.timeoutMs, config.stateDatabase);
    await selectWorkspace(client, config.candidateWorkspace, config.timeoutMs, config.stateDatabase);
    workspace = await openExactProjectConversation(client, config.candidateWorkspace,
      config.stateDatabase, config.timeoutMs, { forceNew: true });
  }
  const ui = await readUiConfiguration(client, config.stateDatabase);
  if (ui.model_count !== 1 || ui.model !== config.expectedModel) {
    throw new Error(`AstronStudio 当前模型不匹配：${ui.model || "unknown"} vs ${config.expectedModel}`);
  }
  if (ui.reasoning !== config.expectedReasoning) {
    throw new Error(`AstronStudio 当前推理强度不匹配：${ui.reasoning || "unknown"} vs ${config.expectedReasoning}`);
  }
  if (ui.permission_count !== 1 || ui.permission !== config.expectedPermission) {
    throw new Error(`AstronStudio 当前权限不匹配：${ui.permission || "unknown"} vs ${config.expectedPermission}`);
  }
  if (JSON.stringify(ui.custom_mapping || null)
    !== JSON.stringify(config.runConfig.tested_model.custom_mapping || null)) {
    throw new Error("AstronStudio custom model/account/revision differs from frozen configuration");
  }
  return { task, workspace, ui };
}
