import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { act, ax, uniqueNode, nodeLabel, requireValue, uiConfiguration } from './index.mjs';

export async function waitUi(config, predicate, label, timeoutMs = 15000) {
  const until = Date.now() + timeoutMs;
  do {
    const snapshot = await ax(config.ax_helper, config.process.pid);
    if (predicate(snapshot)) return snapshot;
    await delay(150);
  } while (Date.now() < until);
  throw Error('LOOMY_UI_TIMEOUT:' + label);
}

export function assertConfiguration(snapshot, config, { preparingWorkspace = false } = {}) {
  const ui = uiConfiguration(snapshot);
  requireValue(ui.model_label === config.configuration.model_label
    && ui.reasoning_effort === config.configuration.reasoning_effort
    && (preparingWorkspace && config.permission_policy === 'preserve-workspace-policy'
      || ui.permission_label === config.configuration.permission_label), 'UI_CONFIGURATION_CHANGED');
  return ui;
}

export async function newTask(config, save) {
  await ax(config.ax_helper, config.process.pid, 'activate');
  let snapshot = await waitUi(config, row => row.frontmost_pid === config.process.pid, 'foreground');
  const before = assertConfiguration(snapshot, config, { preparingWorkspace: true });
  requireValue(before.composer.value === '', 'FOREIGN_DRAFT');
  await save('before-new-task', snapshot);
  const button = uniqueNode(snapshot, node => node.role === 'AXButton' && nodeLabel(node) === '新任务 ⌘K', 'new-task');
  await act(config, button);
  snapshot = await waitUi(config, row => row.nodes.some(node => node.role === 'AXWebArea'
    && /(?:#\/|#\/home)$/u.test(node.url)), 'new-task-route');
  requireValue(assertConfiguration(snapshot, config, { preparingWorkspace: true }).composer.value === '', 'NEW_TASK_NOT_EMPTY');
  await save('new-task', snapshot);
  return snapshot;
}

export async function selectWorkspace(config, workspace, save) {
  let snapshot = await ax(config.ax_helper, config.process.pid);
  assertConfiguration(snapshot, config, { preparingWorkspace: true });
  const selector = uniqueNode(snapshot, node => node.role === 'AXPopUpButton'
    && node.description === '选择工作目录', 'workspace-selector');
  await act(config, selector);
  snapshot = await waitUi(config, row => row.nodes.some(node => node.role === 'AXMenuItem'
    && nodeLabel(node) === '打开本地文件夹'), 'workspace-menu');
  const selectRegistered = async menu => {
    const pathNode = uniqueNode(menu, node => node.help === workspace, 'registered-workspace-full-path');
    const items = menu.nodes.filter(node => node.role === 'AXMenuItem' && node.path.length < pathNode.path.length
      && node.path.every((part, i) => pathNode.path[i] === part)).sort((a, b) => b.path.length - a.path.length);
    requireValue(items.length > 0, 'REGISTERED_WORKSPACE_ITEM_MISSING');
    await save('workspace-full-path-readback', menu);
    await act(config, items[0], 'press', { workspace_guard: workspace });
    const selected = await waitUi(config, row => !row.nodes.some(node => node.role === 'AXMenuItem'), 'workspace-menu-closed');
    const observed = assertConfiguration(selected, config, { preparingWorkspace: true });
    await save('workspace-selected', selected);
    return { workspace, selection_method: 'native-ui-menu-exact-full-path', full_path_verified: true,
      configuration: { model_label: observed.model_label, reasoning_effort: observed.reasoning_effort, permission_label: observed.permission_label } };
  };
  if (snapshot.nodes.some(node => node.help === workspace)) return selectRegistered(snapshot);
  await act(config, uniqueNode(snapshot, node => node.role === 'AXMenuItem'
    && nodeLabel(node) === '打开本地文件夹', 'open-folder'));
  snapshot = await waitUi(config, row => row.nodes.some(node => node.role === 'AXWindow'
    && node.title === '打开'), 'native-folder-panel');
  await save('folder-panel', snapshot);
  await act(config, uniqueNode(snapshot, node => node.role === 'AXWindow' && node.title === '打开', 'folder-panel'), 'key', { key: 'go-to-folder' });
  const pathInput = node => node.path[0] === 0 && node.focused && node.value_settable
    && ['AXComboBox', 'AXTextField'].includes(node.role);
  snapshot = await waitUi(config, row => row.nodes.some(pathInput) && row.nodes.some(node => node.role === 'AXSheet'), 'go-to-folder');
  const field = uniqueNode(snapshot, pathInput, 'folder-path-field');
  const navigationPath = dirname(workspace);
  await act(config, field, 'set-value', { value: navigationPath });
  snapshot = await waitUi(config, row => row.nodes.some(node => node.value === navigationPath
    && node.value_settable), 'exact-folder-path');
  await save('folder-path-readback', snapshot);
  await act(config, uniqueNode(snapshot, node => node.value_settable && node.value === navigationPath, 'exact-folder-path'), 'key', { key: 'return' });
  const isFolder = node => { try { return node.url.startsWith('file:') && resolve(fileURLToPath(node.url)) === workspace; } catch { return false; } };
  snapshot = await waitUi(config, row => !row.nodes.some(node => node.role === 'AXSheet')
    && row.nodes.some(isFolder)
    && row.nodes.some(node => node.role === 'AXWindow' && node.title === '打开'), 'folder-navigation');
  const entry = uniqueNode(snapshot, isFolder, 'exact-folder-url');
  const rows = snapshot.nodes.filter(node => node.role === 'AXRow' && node.path.length < entry.path.length
    && node.path.every((part, i) => entry.path[i] === part)).sort((a, b) => b.path.length - a.path.length);
  requireValue(rows.length > 0, 'FOLDER_ROW_MISSING');
  await act(config, rows[0], 'select-row', { folder: workspace });
  snapshot = await waitUi(config, value => value.nodes.some(node => node.role === 'AXRow' && node.selected
    && node.path.every((part, i) => entry.path[i] === part)), 'folder-row-selected');
  await save('folder-navigation', snapshot);
  await act(config, uniqueNode(snapshot, node => node.path[0] === 0 && node.role === 'AXButton'
    && node.title === '打开' && node.enabled, 'confirm-folder'), 'press', { folder_guard: workspace });
  snapshot = await waitUi(config, row => row.nodes.filter(node => node.role === 'AXWindow').length === 1
    && row.nodes.some(node => node.role === 'AXPopUpButton' && node.description === '选择工作目录'), 'workspace-selected');
  // The trigger's aria-label hides its directory text. Read the complete path
  // from the menu item's native AXHelp, then select that exact item once more.
  await act(config, uniqueNode(snapshot, node => node.role === 'AXPopUpButton'
    && node.description === '选择工作目录', 'selected-workspace'));
  snapshot = await waitUi(config, row => row.nodes.some(node => node.help === workspace), 'workspace-registration-full-path');
  return { ...await selectRegistered(snapshot), native_folder_path_verified: true };
}

export async function fillPrompt(config, prompt, save) {
  let snapshot = await ax(config.ax_helper, config.process.pid);
  const ui = assertConfiguration(snapshot, config);
  requireValue(ui.composer.value === '', 'FOREIGN_DRAFT');
  await act(config, ui.composer, 'set-value', { value: prompt });
  snapshot = await waitUi(config, row => {
    const inputs = row.nodes.filter(node => node.role === 'AXTextArea' && node.value_settable);
    return inputs.length === 1 && inputs[0].value === prompt;
  }, 'prompt-full-readback');
  assertConfiguration(snapshot, config);
  await save('prompt-readback', snapshot);
  return snapshot;
}

export async function sendOnce(config, prompt) {
  const snapshot = await ax(config.ax_helper, config.process.pid);
  const ui = assertConfiguration(snapshot, config);
  requireValue(ui.composer.value === prompt, 'PROMPT_CHANGED_BEFORE_SEND');
  const button = uniqueNode(snapshot, node => node.role === 'AXButton'
    && node.description === '发送消息' && node.enabled, 'send');
  return act(config, button, 'press', { send_guard: { prompt,
    model_label: config.configuration.model_label, permission_label: config.configuration.permission_label } });
}
