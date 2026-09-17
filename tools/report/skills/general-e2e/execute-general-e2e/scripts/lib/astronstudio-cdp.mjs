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

const HELPERS = `
  const visible = (element) => {
    if (!(element instanceof Element)) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
  };
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

export async function readUiConfiguration(client) {
  return client.evaluate(expression(`
    const models = Array.from(document.querySelectorAll(
      'button[aria-label="切换模型和推理设置"], button[aria-label="Change model and reasoning"]'
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
}

async function editorState(client) {
  return client.evaluate(expression(`
    const editors = Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(visible);
    return {
      thread_id: threadId(),
      editor_count: editors.length,
      editor_text: editors.length === 1 ? (editors[0].innerText || "").trim() : null
    };
  `));
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

async function clickSidebarToggle(client) {
  return client.evaluate(expression(`
    const buttons = Array.from(document.querySelectorAll('button[aria-label]'))
      .filter(visible)
      .filter((button) => /^(?:切换对话侧边栏|Toggle conversation sidebar)$/iu.test(
        (button.getAttribute('aria-label') || '').trim()
      ));
    if (buttons.length !== 1) return { clicked: false, count: buttons.length };
    buttons[0].click();
    return { clicked: true, count: 1 };
  `));
}

export async function createFreshTask(client, timeoutMs) {
  const before = await editorState(client);
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
    () => editorState(client),
    (value) => value.editor_count === 1
      && Boolean(value.thread_id)
      && value.editor_text === ""
      && (value.thread_id !== before.thread_id || before.editor_text === ""),
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

async function addWorkspace(client, workspace, timeoutMs) {
  await clickExactButton(client, "^(?:项目|Projects)$", "AstronStudio 项目标签");
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
    () => client.evaluate(expression(`
      const buttons = Array.from(document.querySelectorAll(
        'button[aria-label="添加项目"], button[aria-label="Add project"]'
      )).filter(visible).filter((button) => !button.disabled);
      if (buttons.length !== 1) return { clicked: false, count: buttons.length };
      buttons[0].click();
      return { clicked: true, count: 1 };
    `)),
    (value) => value.clicked,
    timeoutMs,
    "等待 AstronStudio 项目路径提交按钮",
  );
  if (!submitted.clicked) throw new Error("AstronStudio 项目路径提交失败");
}

export async function selectWorkspace(client, workspace, timeoutMs) {
  const before = await workspaceState(client);
  if (before.count > 1) throw new Error(`AstronStudio 项目选择按钮数量异常：${before.count}`);
  if (before.count === 1 && before.path === workspace) return { method: "visible-current-value", ...before };
  if (before.count === 1) {
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
      await addWorkspace(client, workspace, timeoutMs);
    }
  } else {
    await addWorkspace(client, workspace, timeoutMs);
  }
  const confirmed = await waitFor(
    () => workspaceState(client),
    (value) => value.count === 1 && value.path === workspace,
    timeoutMs,
    "等待 AstronStudio 项目绝对路径回读",
  );
  return { method: "exact-path-selection", ...confirmed };
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
      return { ...state, matches: String(state.editor_text || "").replaceAll("\r\n", "\n") === expected };
    },
    (value) => value.editor_count === 1 && value.matches,
    timeoutMs,
    "等待 AstronStudio Prompt 内容回读",
  );
}

export async function clickSend(client) {
  return client.evaluate(expression(`
    const buttons = Array.from(document.querySelectorAll(
      'button[type="submit"][aria-label="发送消息"], button[type="submit"][aria-label="Send message"]'
    )).filter(visible).filter((button) => !button.disabled);
    if (buttons.length !== 1) return { clicked: false, count: buttons.length };
    buttons[0].click();
    return { clicked: true, count: 1, thread_id: threadId() };
  `));
}

export async function currentThreadId(client) {
  const state = await editorState(client);
  return state.thread_id;
}

export async function prepareExecutionUi(client, config) {
  await client.send("Page.bringToFront");
  const task = await createFreshTask(client, config.timeoutMs);
  const workspace = await selectWorkspace(client, config.candidateWorkspace, config.timeoutMs);
  const ui = await readUiConfiguration(client);
  if (ui.model_count !== 1 || ui.model !== config.expectedModel) {
    throw new Error(`AstronStudio 当前模型不匹配：${ui.model || "unknown"} vs ${config.expectedModel}`);
  }
  if (ui.reasoning !== config.expectedReasoning) {
    throw new Error(`AstronStudio 当前推理强度不匹配：${ui.reasoning || "unknown"} vs ${config.expectedReasoning}`);
  }
  if (ui.permission_count !== 1 || ui.permission !== config.expectedPermission) {
    throw new Error(`AstronStudio 当前权限不匹配：${ui.permission || "unknown"} vs ${config.expectedPermission}`);
  }
  await fillPrompt(client, config.prompt, config.timeoutMs);
  return { task, workspace, ui };
}
