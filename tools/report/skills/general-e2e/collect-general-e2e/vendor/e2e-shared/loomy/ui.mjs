import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { act, ax, uniqueNode, nodeLabel, requireValue, sha, uiConfiguration } from './index.mjs';
import { requireFullAccess } from '../desktop-gui/formal-permission.mjs';

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
  if (!preparingWorkspace && config.permission_policy === 'require-full-access') requireFullAccess('loomy', ui.permission_label, 'ui-readback');
  requireValue(ui.model_label === config.configuration.model_label
    && ui.reasoning_effort === config.configuration.reasoning_effort
    && (preparingWorkspace && ['preserve-workspace-policy', 'require-full-access'].includes(config.permission_policy)
      || ui.permission_label === config.configuration.permission_label), 'UI_CONFIGURATION_CHANGED');
  return ui;
}

export async function dismissKnownPromotion(config, save) {
  const snapshot = await ax(config.ax_helper, config.process.pid);
  const isPromotion = node => node.role === 'AXGroup' && node.subrole === 'AXApplicationDialog' && node.title === '活动详情';
  const groups = snapshot.nodes.filter(isPromotion);
  if (groups.length === 0) return false;
  requireValue(groups.length === 1, 'PROMOTIONAL_DIALOG_AMBIGUOUS');
  const group = groups[0], nodes = snapshot.nodes.filter(node => group.path.every((part, i) => node.path[i] === part));
  const owners = snapshot.nodes.filter(node => node.role === 'AXWebArea' && node.path.every((part, i) => group.path[i] === part))
    .sort((a, b) => b.path.length - a.path.length);
  requireValue(owners.length > 0 && fileURLToPath(owners[0].url) === config.client.path + '/Contents/Resources/app.asar/dist/index.html', 'PROMOTIONAL_DIALOG_SOURCE_UNVERIFIED');
  requireValue(!nodes.some(node => ['AXTextField', 'AXTextArea', 'AXComboBox'].includes(node.role))
    && nodes.filter(node => node.role === 'AXButton' && nodeLabel(node) === '跳转').length === 1, 'PROMOTIONAL_DIALOG_UNRECOGNIZED');
  const close = uniqueNode({ nodes }, node => node.role === 'AXButton' && nodeLabel(node) === '关闭', 'close-known-promotion');
  await save('promotional-dialog-before', snapshot);
  await act(config, close);
  const after = await waitUi(config, row => !row.nodes.some(isPromotion)
    && row.nodes.some(node => node.role === 'AXPopUpButton' && nodeLabel(node) === config.configuration.model_label), 'promotion-closed');
  await save('promotional-dialog-after', after);
  return true;
}

export async function newTask(config, save) {
  await ax(config.ax_helper, config.process.pid, 'activate');
  let snapshot = await waitUi(config, row => row.frontmost_pid === config.process.pid, 'foreground');
  if (await dismissKnownPromotion(config, save)) snapshot = await ax(config.ax_helper, config.process.pid);
  const before = assertConfiguration(snapshot, config, { preparingWorkspace: true });
  requireValue(before.composer.value === '', 'FOREIGN_DRAFT');
  await save('before-new-task', snapshot);
  const button = uniqueNode(snapshot, node => node.role === 'AXButton' && nodeLabel(node) === '新任务 ⌘K', 'new-task');
  await act(config, button);
  await dismissKnownPromotion(config, save);
  snapshot = await waitUi(config, row => row.nodes.some(node => node.role === 'AXWebArea'
    && /(?:#\/|#\/home)$/u.test(node.url)), 'new-task-route');
  requireValue(assertConfiguration(snapshot, config, { preparingWorkspace: true }).composer.value === '', 'NEW_TASK_NOT_EMPTY');
  await save('new-task', snapshot);
  return snapshot;
}

export function registeredWorkspaceItems(snapshot, workspace) {
  const items = snapshot.nodes.filter(node => node.role === 'AXMenuItem');
  return items.filter(item => snapshot.nodes.some(node => node.help === workspace
    && item.path.length <= node.path.length && item.path.every((part, i) => node.path[i] === part)));
}

export async function selectWorkspace(config, workspace, save, { provisionFullAccess = false } = {}) {
  let snapshot = await ax(config.ax_helper, config.process.pid);
  assertConfiguration(snapshot, config, { preparingWorkspace: true });
  const selector = uniqueNode(snapshot, node => node.role === 'AXPopUpButton'
    && node.description === '选择工作目录', 'workspace-selector');
  await act(config, selector);
  snapshot = await waitUi(config, row => row.nodes.some(node => node.role === 'AXMenuItem'
    && nodeLabel(node) === '打开本地文件夹'), 'workspace-menu');
  const selectRegistered = async menu => {
    const items = registeredWorkspaceItems(menu, workspace);
    requireValue(items.length === 1, 'AX_TARGET_AMBIGUOUS:registered-workspace-menu-item');
    await save('workspace-full-path-readback', menu);
    await act(config, items[0], 'press', { workspace_guard: workspace });
    let selected = await waitUi(config, row => !row.nodes.some(node => node.role === 'AXMenuItem'
      || /Dialog$/u.test(node.subrole || '')), 'workspace-menu-closed');
    if (provisionFullAccess) selected = await prepareFullAccess(config, selected, save);
    await save('workspace-selected', selected);
    const observed = assertConfiguration(selected, config, { preparingWorkspace: true });
    const fullAccess = requireFullAccess('loomy', observed.permission_label, 'workspace-selected');
    return { workspace, selection_method: 'native-ui-menu-exact-full-path', full_path_verified: true, full_access_gate: fullAccess,
      configuration: { model_label: observed.model_label, reasoning_effort: observed.reasoning_effort, permission_label: observed.permission_label } };
  };
  if (registeredWorkspaceItems(snapshot, workspace).length) return selectRegistered(snapshot);
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
  snapshot = await waitUi(config, row => registeredWorkspaceItems(row, workspace).length > 0, 'workspace-registration-full-path');
  return { ...await selectRegistered(snapshot), native_folder_path_verified: true };
}

const permissionOption = '完全访问 突破工作区边界；所有操作免询问。';
const confirmationTitle = '开启完全访问？';
const confirmationButton = '我已了解风险，开启完全访问';
const isButton = label => node => node.role === 'AXButton' && nodeLabel(node) === label && node.enabled;
const permissionButton = label => node => node.role === 'AXPopUpButton' && nodeLabel(node) === label;

async function prepareFullAccess(config, selected, save) {
  const ui = assertConfiguration(selected, config, { preparingWorkspace: true });
  requireValue(ui.composer.value === '' && config.permission_policy === 'require-full-access'
    && config.configuration.permission_label === '完全访问', 'PERMISSION_PROVISION_REQUIRES_EMPTY_COMPOSER_AND_POLICY');
  if (ui.permission_label === '完全访问') return selected;
  requireValue(ui.permission_label === '默认权限', 'PERMISSION_PROVISION_UNRECOGNIZED_MODE');
  await save('workspace-before-permission', selected);
  await act(config, uniqueNode(selected, permissionButton(ui.permission_label), 'workspace-permission'));
  const menu = await waitUi(config, row => row.nodes.some(isButton(permissionOption)), 'workspace-permission-menu');
  const menuGroup = uniqueNode(menu, n => n.subrole === 'AXApplicationDialog', 'workspace-permission-menu-group');
  const within = (snapshot, group) => ({ nodes: snapshot.nodes.filter(node => group.path.every((part, i) => node.path[i] === part)) });
  const menuContents = within(menu, menuGroup);
  requireValue(menuContents.nodes.some(n => n.role === 'AXStaticText' && n.value === '当前工作区权限'), 'PERMISSION_MENU_TITLE_CHANGED');
  await save('workspace-permission-menu', menu);
  await act(config, uniqueNode(menuContents, isButton(permissionOption), 'exact-full-access-option'));
  const dialog = await waitUi(config, row => row.nodes.some(isButton(confirmationButton)), 'workspace-permission-confirmation');
  const alert = uniqueNode(dialog, n => n.subrole === 'AXApplicationAlertDialog' && nodeLabel(n) === confirmationTitle, 'workspace-permission-alert');
  const contents = within(dialog, alert);
  requireValue(contents.nodes.some(n => n.role === 'AXHeading' && nodeLabel(n) === confirmationTitle)
    && contents.nodes.some(isButton('取消'))
    && contents.nodes.filter(n => n.role === 'AXButton').length === 2, 'PERMISSION_CONFIRMATION_CHANGED');
  await save('workspace-permission-confirmation', dialog);
  await act(config, uniqueNode(contents, isButton(confirmationButton), 'confirm-exact-full-access-option'));
  return waitUi(config, row => !row.nodes.some(n => /Dialog$/u.test(n.subrole || ''))
    && row.nodes.some(permissionButton('完全访问')), 'workspace-full-access-readback');
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

export function assertSendGuard(proof, config, workspace, prompt, dispatched) {
  const fullAccess = requireFullAccess('loomy', proof?.permission_label, dispatched ? 'physical-send' : 'before-send-intent');
  requireValue(proof.status === 'PASS' && proof.pid === config.process.pid && proof.workspace === workspace
    && proof.model_label === config.configuration.model_label && proof.prompt_sha256 === sha(Buffer.from(prompt))
    && proof.workspace_selection === 'guarded-native-exact-menu-path'
    && proof.dispatched === dispatched && proof.action === (dispatched ? 'send' : 'verify-send'), 'AX_SEND_PROOF_MISMATCH');
  return fullAccess;
}

export async function guardSend(config, workspace, prompt, dispatched) {
  requireFullAccess('loomy', config.configuration.permission_label, 'frozen-send-expectation');
  const snapshot = await ax(config.ax_helper, config.process.pid);
  const ui = assertConfiguration(snapshot, config);
  requireValue(ui.composer.value === prompt, 'PROMPT_CHANGED_BEFORE_SEND');
  const button = uniqueNode(snapshot, node => node.role === 'AXButton'
    && node.description === '发送消息' && node.enabled, 'send');
  const proof = await act(config, button, dispatched ? 'send' : 'verify-send', { send_guard: { prompt, workspace,
    model_label: config.configuration.model_label, permission_label: config.configuration.permission_label } });
  return { observed: proof, full_access_gate: assertSendGuard(proof, config, workspace, prompt, dispatched) };
}
