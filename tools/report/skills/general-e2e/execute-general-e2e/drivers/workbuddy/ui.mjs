function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

export function assertWorkBuddyRuntimeSupport(runtime = {}) {
  const nodeVersion = runtime.nodeVersion || process.versions.node;
  const major = Number.parseInt(String(nodeVersion).split(".")[0], 10);
  const fetchImpl = runtime.fetchImpl || globalThis.fetch;
  const WebSocketImpl = runtime.WebSocketImpl || globalThis.WebSocket;
  const timeout = runtime.abortSignalTimeout || globalThis.AbortSignal?.timeout;
  if (!Number.isInteger(major) || major < 22) {
    throw new Error(`WorkBuddy Driver 要求 Node.js >=22，当前为 ${nodeVersion || "unknown"}`);
  }
  if (typeof fetchImpl !== "function" || typeof WebSocketImpl !== "function" || typeof timeout !== "function") {
    throw new Error("WorkBuddy Driver 缺少 Node 原生 fetch/WebSocket/AbortSignal.timeout API");
  }
  return { node_version: nodeVersion, dependency_mode: "node-builtins-only", verified: true };
}

async function fetchJson(url, timeoutMs, fetchImpl = fetch) {
  const response = await fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs) });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  return response.json();
}

export async function discoverWorkBuddyMainTarget(endpoint, timeoutMs, fetchImpl = fetch) {
  const targets = await fetchJson(`${endpoint}/json/list`, timeoutMs, fetchImpl);
  const matches = (Array.isArray(targets) ? targets : []).filter((item) => (
    item?.type === "page"
    && /(?:WorkBuddy|CodeBuddy)/iu.test(String(item.title || ""))
    && typeof item.webSocketDebuggerUrl === "string"
  ));
  if (matches.length !== 1) throw new Error(`WorkBuddy 主页面数量异常：${matches.length}`);
  return matches[0];
}

export class WorkBuddyCdpClient {
  constructor(socket, timeoutMs = 30_000) {
    this.socket = socket;
    this.timeoutMs = timeoutMs;
    this.nextId = 1;
    this.pending = new Map();
    socket.addEventListener("message", (event) => this.onMessage(event));
    socket.addEventListener("close", () => this.failPending(new Error("WorkBuddy CDP WebSocket 已关闭")));
    socket.addEventListener("error", () => this.failPending(new Error("WorkBuddy CDP WebSocket 连接失败")));
  }

  static async connect(webSocketUrl, timeoutMs = 30_000, WebSocketImpl = globalThis.WebSocket) {
    if (typeof WebSocketImpl !== "function") throw new Error("当前 Node.js 不提供 WebSocket API");
    const socket = new WebSocketImpl(webSocketUrl);
    await new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => rejectPromise(new Error("WorkBuddy CDP WebSocket 连接超时")), timeoutMs);
      socket.addEventListener("open", () => {
        clearTimeout(timer);
        resolvePromise();
      }, { once: true });
      socket.addEventListener("error", () => {
        clearTimeout(timer);
        rejectPromise(new Error("WorkBuddy CDP WebSocket 连接失败"));
      }, { once: true });
    });
    return new WorkBuddyCdpClient(socket, timeoutMs);
  }

  onMessage(event) {
    let message;
    try {
      message = JSON.parse(String(event.data));
    } catch {
      return;
    }
    const pending = this.pending.get(message?.id);
    if (!pending) return;
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

  async evaluate(expression, { userGesture = false } = {}) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
      userGesture,
    });
    if (result.exceptionDetails) {
      throw new Error(
        result.exceptionDetails.exception?.description
        || result.exceptionDetails.text
        || "WorkBuddy Runtime.evaluate 失败",
      );
    }
    return result.result?.value;
  }

  close() {
    try {
      this.socket.close();
    } catch {
      // Electron may already have closed the connection.
    }
  }
}

const HELPERS = `
  const visible = (element) => {
    if (!(element instanceof Element)) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const visibleAll = (selector) => Array.from(document.querySelectorAll(selector)).filter(visible);
  const text = (element) => (element?.innerText || element?.textContent || '').trim();
  const editorContent = (editor) => {
    const clone = editor.cloneNode(true);
    clone.querySelectorAll?.('[data-slate-placeholder="true"]').forEach((node) => node.remove());
    const raw = 'value' in clone ? clone.value : (clone.innerText || clone.textContent || '');
    const normalized = String(raw || '')
      .replace(/\uFEFF/gu, '')
      // Slate renders the final paragraph boundary as one extra newline.
      .replace(/\\n{2,}$/gu, '\\n');
    return normalized.trim() ? normalized : '';
  };
  const selectedConversationId = () => {
    const rows = visibleAll('[data-conversation-id]').filter((element) =>
      element.matches(':has(.cb-agent-card[class*="selected"])')
      || element.getAttribute('aria-selected') === 'true'
      || String(element.className || '').includes('selected')
    );
    const ids = [...new Set(rows.map((element) => (element.getAttribute('data-conversation-id') || '').trim()).filter(Boolean))];
    return ids.length === 1 ? ids[0] : null;
  };
`;

function expression(body, argument = undefined) {
  const serialized = argument === undefined ? "undefined" : JSON.stringify(argument);
  return `(async (__arg) => {${HELPERS}\n${body}\n})(${serialized})`;
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

export async function readWorkBuddyUi(client) {
  return client.evaluate(expression(`
    const pickers = visibleAll('.cr-workspace-picker');
    let workspacePath = null;
    let workspaceProviderCount = 0;
    for (const picker of pickers) {
      const fiberKey = Object.keys(picker).find((key) => key.startsWith('__reactFiber$'));
      let fiber = fiberKey ? picker[fiberKey] : null;
      while (fiber) {
        const props = fiber.memoizedProps;
        const store = props?.store;
        const provider = props?.providers?.workspace;
        if (store?.api?.setCwd && typeof provider?.onChange === 'function') {
          workspaceProviderCount += 1;
          const snapshot = store.getSnapshot?.();
          workspacePath = props.selections?.cwd ?? snapshot?.draft?.selections?.cwd ?? null;
          break;
        }
        fiber = fiber.return;
      }
    }
    const models = visibleAll('button.cr-model-selector__trigger[role="combobox"]');
    const permissions = visibleAll('button.cr-permission-setting');
    const editors = visibleAll('textarea, [contenteditable="true"]');
    const controls = visibleAll('button[aria-label], button[title], [role="button"][aria-label]');
    const busyControls = controls.filter((control) => /(?:停止|取消|Stop|Cancel)/iu.test(
      (control.getAttribute('aria-label') || control.getAttribute('title') || text(control)).trim()
    ));
    const model = models.length === 1
      ? ((models[0].getAttribute('title') || text(models[0])).trim() || null)
      : null;
    const permissionClass = permissions.length === 1 ? String(permissions[0].className || '') : '';
    return {
      workspace_picker_count: pickers.length,
      workspace_provider_count: workspaceProviderCount,
      workspace_path: workspacePath,
      model_count: models.length,
      model,
      permission_count: permissions.length,
      permission: permissions.length === 1
        ? (permissionClass.split(/\\s+/u).includes('cr-permission-setting--danger') ? 'full-access' : 'default-sandbox')
        : null,
      editor_count: editors.length,
      editor_nonempty_count: editors.filter((editor) => editorContent(editor).trim().length > 0).length,
      busy_control_count: busyControls.length,
      selected_conversation_id: selectedConversationId()
    };
  `));
}

export function assertWorkBuddyUiIdle(ui) {
  const evidence = {
    verified: ui.editor_count <= 1
      && ui.editor_nonempty_count === 0
      && ui.busy_control_count === 0,
    editor_count: ui.editor_count,
    editor_nonempty_count: ui.editor_nonempty_count,
    busy_control_count: ui.busy_control_count,
  };
  if (!evidence.verified) {
    throw new Error(
      `WorkBuddy UI 存在活动或未知交互：editor=${ui.editor_count}; nonempty=${ui.editor_nonempty_count}; busy=${ui.busy_control_count}`,
    );
  }
  return evidence;
}

export async function createFreshWorkBuddyTask(client, timeoutMs) {
  const clicked = await client.evaluate(expression(`
    const buttons = visibleAll('button').filter((button) => /^(?:新建任务|New task)$/iu.test(text(button)));
    if (buttons.length !== 1) return { clicked: false, count: buttons.length };
    buttons[0].click();
    return { clicked: true, count: 1 };
  `), { userGesture: true });
  if (!clicked?.clicked) throw new Error(`WorkBuddy 新建任务按钮数量异常：${clicked?.count ?? "unknown"}`);
  return waitFor(
    () => readWorkBuddyUi(client),
    (value) => value.editor_count === 1,
    timeoutMs,
    "等待 WorkBuddy 新任务输入区",
  );
}

export async function selectWorkBuddyWorkspace(client, workspace, timeoutMs) {
  const selected = await client.evaluate(expression(`
    const pickers = visibleAll('.cr-workspace-picker');
    const providers = [];
    for (const picker of pickers) {
      const fiberKey = Object.keys(picker).find((key) => key.startsWith('__reactFiber$'));
      let fiber = fiberKey ? picker[fiberKey] : null;
      while (fiber) {
        const props = fiber.memoizedProps;
        if (props?.store?.api?.setCwd && typeof props?.providers?.workspace?.onChange === 'function') {
          providers.push(props.providers.workspace);
          break;
        }
        fiber = fiber.return;
      }
    }
    if (providers.length !== 1) return { selected: false, count: providers.length };
    await providers[0].onChange(__arg.workspace);
    return { selected: true, count: 1 };
  `, { workspace }), { userGesture: true });
  if (!selected?.selected) throw new Error(`WorkBuddy workspace provider 数量异常：${selected?.count ?? "unknown"}`);
  return waitFor(
    () => readWorkBuddyUi(client),
    (value) => value.workspace_provider_count === 1 && value.workspace_path === workspace,
    timeoutMs,
    "等待 WorkBuddy 完整 Workspace 回读",
  );
}

export function assertWorkBuddyUiConfiguration(ui, expected) {
  const mismatches = [];
  if (ui.workspace_provider_count !== 1 || ui.workspace_path !== expected.workspace) mismatches.push("workspace");
  if (ui.model_count !== 1 || ui.model !== expected.model) mismatches.push("model");
  if (ui.permission_count !== 1 || ui.permission !== expected.permission) mismatches.push("permission");
  if (ui.editor_count !== 1) mismatches.push("prompt-editor");
  if (mismatches.length) throw new Error(`WorkBuddy UI 配置回读不一致：${mismatches.join(",")}`);
  return {
    workspace: ui.workspace_path,
    model: ui.model,
    permission: ui.permission,
    selected_conversation_id: ui.selected_conversation_id,
    verified: true,
  };
}

export async function readWorkBuddyPromptState(client) {
  return client.evaluate(expression(`
    const editors = visibleAll('textarea, [contenteditable="true"]');
    const buttons = visibleAll('button[aria-label], button[title], [role="button"][aria-label]')
      .filter((button) => /(?:发送|Send)/iu.test(
        (button.getAttribute('aria-label') || button.getAttribute('title') || '').trim()
      ));
    const enabled = buttons.filter((button) => !button.disabled && button.getAttribute('aria-disabled') !== 'true');
    const content = editors.length === 1 ? editorContent(editors[0]) : null;
    const stores = new Set();
    if (editors.length === 1) {
      const key = Object.keys(editors[0]).find((name) => name.startsWith('__reactFiber$'));
      let fiber = key ? editors[0][key] : null;
      while (fiber) {
        if (fiber.memoizedProps?.store?.getSnapshot) stores.add(fiber.memoizedProps.store);
        fiber = fiber.return;
      }
    }
    const draft = stores.size === 1 ? [...stores][0].getSnapshot()?.draft?.content : null;
    const blocks = Array.isArray(draft?.blocks) ? draft.blocks : null;
    const draftText = blocks && blocks.every((block) => block.type === 'text')
      ? blocks.map((block) => String(block.text || '')).join('') : null;

    return {
      editor_count: editors.length,
      content,
      draft_provider_count: stores.size,
      draft_text: draftText,
      draft_processing: draft?.hasProcessingContent ?? null,
      send_control_count: buttons.length,
      send_enabled_count: enabled.length
    };
  `));
}

export async function fillWorkBuddyPrompt(client, prompt, timeoutMs = 30_000) {
  const focused = await client.evaluate(expression(`
    const editors = visibleAll('textarea, [contenteditable="true"]');
    if (editors.length !== 1) return { focused: false, count: editors.length, initial_content: null };
    const editor = editors[0];
    const initialContent = editorContent(editor);
    if (initialContent.length !== 0) {
      return { focused: false, count: 1, initial_content: initialContent };
    }
    editor.focus();
    return { focused: document.activeElement === editor, count: 1, initial_content: initialContent };
  `), { userGesture: true });
  if (!focused?.focused) {
    throw new Error(
      `WorkBuddy Prompt 编辑器不可安全聚焦：count=${focused?.count ?? "unknown"}; initial_length=${focused?.initial_content?.length ?? "unknown"}`,
    );
  }
  // Slate tracks user input intent on keydown. insertText alone can update
  // the DOM while the WorkBuddy send store stays empty. No text is emitted by
  // rawKeyDown; the complete Prompt is inserted exactly once below.
  const key = { key: "a", code: "KeyA", windowsVirtualKeyCode: 65 };
  await client.send("Input.dispatchKeyEvent", { type: "rawKeyDown", ...key });
  try {
    await client.send("Input.insertText", { text: prompt });
  } finally {
    await client.send("Input.dispatchKeyEvent", { type: "keyUp", ...key });
  }
  return waitFor(
    () => readWorkBuddyPromptState(client),
    (state) => state.editor_count === 1
      && state.content === prompt
      && state.draft_provider_count === 1
      && state.draft_text === prompt
      && state.draft_processing === false
      && state.send_control_count === 1
      && state.send_enabled_count === 1,
    timeoutMs,
    "等待 WorkBuddy Prompt 真实输入和发送控件启用",
  );
}

export async function dispatchWorkBuddyPrompt(client, timeoutMs = 30_000) {
  await client.send("Page.bringToFront");
  let previousPoint = null;
  let stableSince = 0;
  const result = await waitFor(() => client.evaluate(expression(`
    const buttons = visibleAll('button[aria-label], button[title], [role="button"][aria-label]')
      .filter((button) => /(?:发送|Send)/iu.test(
        (button.getAttribute('aria-label') || button.getAttribute('title') || '').trim()
      ));
    const enabled = buttons.filter((button) => !button.disabled && button.getAttribute('aria-disabled') !== 'true');
    if (enabled.length !== 1) return { clicked: false, count: enabled.length, selected_conversation_id: selectedConversationId() };
    const button = enabled[0];
    const rect = button.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return {
      clicked: Boolean(hit && button.contains(hit)),
      count: 1,
      selected_conversation_id: selectedConversationId(),
      point: { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
    };
  `), { userGesture: true }), (value) => {
    if (!value?.clicked || !value.point) {
      previousPoint = null;
      stableSince = 0;
      return false;
    }
    const point = JSON.stringify(value.point);
    if (point !== previousPoint) {
      previousPoint = point;
      stableSince = Date.now();
      return false;
    }
    return Date.now() - stableSince >= 200;
  }, timeoutMs, "等待 WorkBuddy 唯一发送控件可点击且位置稳定", 50);
  if (!result?.clicked) throw new Error(`WorkBuddy 发送按钮数量异常：${result?.count ?? "unknown"}`);
  // Use trusted Chromium input for the final user gesture. React's synthetic
  // HTMLElement.click() can leave the 5.5.x composer unchanged when the
  // window is backgrounded even though the button is enabled in the DOM.
  if (!result.point || !Number.isFinite(result.point.x) || !Number.isFinite(result.point.y)) {
    throw new Error("WorkBuddy 发送按钮坐标不可用");
  }
  await client.send("Input.dispatchMouseEvent", {
    type: "mouseMoved", x: result.point.x, y: result.point.y,
  });
  await client.send("Input.dispatchMouseEvent", {
    type: "mousePressed", x: result.point.x, y: result.point.y, button: "left", clickCount: 1,
  });
  await client.send("Input.dispatchMouseEvent", {
    type: "mouseReleased", x: result.point.x, y: result.point.y, button: "left", clickCount: 1,
  });
  const after = await waitFor(
    () => readWorkBuddyUi(client),
    (value) => Boolean(value.selected_conversation_id) || value.editor_nonempty_count === 0,
    timeoutMs,
    "等待 WorkBuddy 发送后的会话状态",
  );
  return { ...result, selected_conversation_id: after.selected_conversation_id || null };
}
