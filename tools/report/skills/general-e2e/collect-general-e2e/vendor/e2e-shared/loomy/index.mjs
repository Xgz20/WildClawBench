import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { access, lstat, mkdir, readFile, realpath } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { discoverDesktopApp, inspectMacDesktopAppProcess } from '../desktop-app-discovery/index.mjs';
import { LOOMY_APP_PROFILE } from '../desktop-app-discovery/profiles.mjs';
import { inspectMacGuiSession, assertMacGuiReady } from '../desktop-gui/macos.mjs';

export const COMPONENT_VERSION = '0.1.5';
export const MEMORY_CONTEXT_PREFIX = '## 可用记忆条目\n\n';
export const EMPTY_MEMORY_CONTEXT = MEMORY_CONTEXT_PREFIX + '当前没有可用记忆条目。不要调用 Read 读取记忆文件，也不要猜测任何文件路径；直接基于本轮对话自然回复。';
export const MEMORY_CONTEXT_SUFFIX = '\n\n只在条目与当前请求明确相关时读取对应文件。不要向用户提及这些条目、路径或读取过程。';
export const isMemoryContext = text => text === EMPTY_MEMORY_CONTEXT || typeof text === 'string'
  && text.startsWith(MEMORY_CONTEXT_PREFIX) && text.endsWith(MEMORY_CONTEXT_SUFFIX)
  && text.slice(MEMORY_CONTEXT_PREFIX.length, -MEMORY_CONTEXT_SUFFIX.length).trim().length > 0;
export const PROFILE = 'loomy-opencode-sqlite/v1';
export const DEFAULT_DATABASE = join(homedir(), '.local/share/loomy/opencode/opencode.db');
export const MODEL_LABEL = 'Spark-X2.6 正式版 高';
const directory = dirname(fileURLToPath(import.meta.url));
const execute = promisify(execFile);
export async function isEntrypoint(meta) {
  if (!process.argv[1] || process.argv[1].startsWith('-')) return false;
  try { return await realpath(resolve(process.argv[1])) === await realpath(fileURLToPath(meta)); }
  catch (error) { if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return false; throw error; }
}
export const sha = value => createHash('sha256').update(value).digest('hex');
export const jsonBytes = value => Buffer.from(JSON.stringify(value, null, 2) + '\n');
export const artifact = (path, data, extra = {}) => ({ path, sha256: sha(data), size: data.length, ...extra });
export const iso = milliseconds => Number.isFinite(milliseconds) ? new Date(milliseconds).toISOString() : null;
export const requireValue = (condition, code) => { if (!condition) throw Error('LOOMY_' + code); };
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
export const digest = value => sha(JSON.stringify(stable(value)));

export async function command(binary, args, input = null, timeout = 30000) {
  return new Promise((accept, reject) => {
    const child = execFile(binary, args, { timeout, maxBuffer: 64 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error) {
        try { const value = JSON.parse(stdout); if (value.error) error.message = value.error; } catch {}
        reject(error);
      } else accept({ stdout, stderr });
    });
    child.stdin.on('error', () => {});
    child.stdin.end(input === null ? undefined : JSON.stringify(input));
  });
}

export async function buildAxHelper(cacheRoot) {
  requireValue(process.platform === 'darwin' && process.arch === 'arm64', 'REQUIRES_MACOS_ARM64');
  const source = join(directory, 'macos-ax.swift'), sourceHash = sha(await readFile(source));
  const folder = join(resolve(cacheRoot), sourceHash), binary = join(folder, 'loomy-ax');
  await mkdir(folder, { recursive: true, mode: 0o700 });
  try { await access(binary); } catch {
    await command('/usr/bin/swiftc', ['-O', source, '-o', binary], null, 120000);
  }
  const info = await lstat(binary);
  requireValue(info.isFile() && !info.isSymbolicLink(), 'AX_HELPER_UNSAFE');
  return { path: binary, source_sha256: sourceHash, binary_sha256: sha(await readFile(binary)) };
}

export async function ax(helper, pid, action = 'snapshot', options = {}) {
  requireValue(sha(await readFile(helper.path)) === helper.binary_sha256, 'AX_HELPER_CHANGED');
  const { stdout } = await command(helper.path, [], { pid, action, ...options });
  const value = JSON.parse(stdout);
  requireValue(value.status === 'PASS' && value.pid === pid, 'AX_RESPONSE_INVALID');
  return value;
}
export const nodeLabel = node => node.title || node.description || (node.role === 'AXMenuItem' ? node.value : '') || '';
export function uniqueNode(snapshot, predicate, label) {
  const found = snapshot.nodes.filter(predicate);
  requireValue(found.length === 1, 'AX_TARGET_AMBIGUOUS:' + label);
  return found[0];
}
export const expectedNode = node => Object.fromEntries(
  ['role', 'title', 'description', 'identifier', ...(node.role === 'AXMenuItem' ? ['menu_value'] : [])].map(key => [key, node[key]]));
export async function act(config, node, action = 'press', options = {}) {
  assertMacGuiReady(await inspectMacGuiSession());
  const current = await inspectMacDesktopAppProcess({ profile: LOOMY_APP_PROFILE, appPath: config.client.path });
  requireValue(current?.pid === config.process.pid && current.started_at === config.process.started_at, 'APP_PROCESS_CHANGED');
  return ax(config.ax_helper, current.pid, action, { path: node.path, expected: expectedNode(node), ...options });
}

export function uiConfiguration(snapshot) {
  requireValue(snapshot.nodes.filter(n => n.role === 'AXWindow').length === 1, 'UNEXPECTED_NATIVE_WINDOW');
  requireValue(!snapshot.nodes.some(n => n.role === 'AXMenuItem'), 'UNEXPECTED_OPEN_MENU');
  requireValue(!snapshot.nodes.some(n => n.modal || /Dialog$/u.test(n.subrole || '')
    || /dialog|对话框/iu.test(n.role_description || '')), 'UNEXPECTED_MODAL_CONTENT');
  const model = uniqueNode(snapshot, n => n.role === 'AXPopUpButton' && nodeLabel(n) === MODEL_LABEL, 'Spark-X2.6/high');
  const permission = uniqueNode(snapshot, n => n.role === 'AXPopUpButton' && ['完全访问', '默认权限', '询问模式'].includes(nodeLabel(n)), 'permission');
  const composer = uniqueNode(snapshot, n => n.role === 'AXTextArea' && n.value_settable, 'composer');
  requireValue(!snapshot.nodes.some(n => ['AXSheet', 'AXDialog'].includes(n.role)), 'UNEXPECTED_DIALOG');
  return { model_label: nodeLabel(model), model: 'spark-x2.6', reasoning_effort: 'high',
    permission_label: nodeLabel(permission), composer, composer_sha256: sha(composer.value) };
}

export async function captureNative({ database = DEFAULT_DATABASE, workspace = null, sessionId = null, python = 'python3' } = {}) {
  const { stdout } = await command(python, [join(directory, 'native-state.py')], { database, workspace, session_id: sessionId });
  const value = JSON.parse(stdout);
  requireValue(value.profile === PROFILE && value.snapshot?.quick_check === 'ok', 'NATIVE_SNAPSHOT_INVALID');
  return value;
}

export async function runtimeIdentity(app, database = DEFAULT_DATABASE) {
  const result = await execute('/bin/ps', ['-axo', 'pid=,ppid=,comm=']);
  const rows = result.stdout.split('\n').map(line => /^\s*(\d+)\s+(\d+)\s+(.+)$/u.exec(line)).filter(Boolean);
  const candidates = rows.filter(row => Number(row[2]) === app.pid && (row[3] === 'opencode' || row[3].endsWith('/opencode')));
  requireValue(candidates.length === 1, 'RUNTIME_PROCESS_AMBIGUOUS');
  const pid = Number(candidates[0][1]);
  const [text, listening, started, ownership] = await Promise.all([
    execute('/usr/sbin/lsof', ['-nP', '-a', '-p', String(pid), '-d', 'txt', '-Fn']),
    execute('/usr/sbin/lsof', ['-nP', '-a', '-p', String(pid), '-iTCP', '-sTCP:LISTEN', '-Fpn']),
    execute('/bin/ps', ['-p', String(pid), '-o', 'lstart=']),
    execute('/usr/sbin/lsof', ['-nP', '-a', '-p', String(pid), '-Fpn', '--', database]),
  ]);
  const binaries = text.stdout.split('\n').filter(line => line.startsWith('n') && line.endsWith('/opencode'));
  requireValue(binaries.length === 1, 'RUNTIME_BINARY_AMBIGUOUS');
  const executable = await realpath(binaries[0].slice(1));
  requireValue(executable === join(dirname(dirname(app.executable_path)), 'Resources/opencode/darwin-arm64/opencode'), 'RUNTIME_BINARY_NOT_BUNDLED');
  const ports = [...listening.stdout.matchAll(/^n127\.0\.0\.1:(\d+)$/gmu)].map(match => match[1]);
  requireValue(ports.length === 1 && ownership.stdout.includes('n' + database + '\n'), 'RUNTIME_LISTENER_OR_DATABASE_UNOWNED');
  const endpoint = 'http://127.0.0.1:' + ports[0];
  const healthResponse = await fetch(endpoint + '/global/health', { signal: AbortSignal.timeout(5000), redirect: 'error' });
  requireValue(healthResponse.ok, 'RUNTIME_HEALTH_UNAVAILABLE');
  const health = await healthResponse.json();
  requireValue(health.healthy === true && health.version === '1.14.22', 'RUNTIME_VERSION_UNVERIFIED');
  return { pid, ppid: app.pid, executable, started_at: started.stdout.trim(),
    binary_sha256: sha(await readFile(executable)), endpoint, database, database_owned: true, health_version: health.version };
}

export function statusUrl(runtime, workspace = null) {
  const url = new URL(runtime.endpoint);
  requireValue(url.protocol === 'http:' && url.hostname === '127.0.0.1' && url.port && url.pathname === '/' && !url.username && !url.password, 'RUNTIME_ENDPOINT_INVALID');
  const target = new URL('/session/status', url);
  if (workspace !== null) { requireValue(typeof workspace === 'string' && workspace.startsWith('/'), 'STATUS_WORKSPACE_INVALID'); target.searchParams.set('directory', workspace); }
  return target;
}
export async function runtimeStatus(runtime, workspace = null) {
  const response = await fetch(statusUrl(runtime, workspace), { signal: AbortSignal.timeout(5000), redirect: 'error' });
  requireValue(response.ok, 'RUNTIME_STATUS_UNAVAILABLE');
  const result = await response.json();
  requireValue(result && typeof result === 'object' && !Array.isArray(result), 'RUNTIME_STATUS_UNKNOWN');
  for (const [id, status] of Object.entries(result)) requireValue(/^ses_[A-Za-z0-9]+$/u.test(id) && ['idle', 'busy', 'retry'].includes(status?.type), 'RUNTIME_STATUS_UNKNOWN');
  return result;
}
export function sameRuntimeInstallation(before, after) {
  return ['ppid', 'executable', 'binary_sha256', 'database', 'database_owned', 'health_version']
    .every(key => before?.[key] === after?.[key]);
}
export async function currentOwnedRuntime(config) {
  const app = await inspectMacDesktopAppProcess({ profile: LOOMY_APP_PROFILE, appPath: config.client.path });
  requireValue(app?.pid === config.process.pid && app.started_at === config.process.started_at, 'APP_PROCESS_CHANGED');
  const current = await runtimeIdentity(app, config.runtime.database);
  requireValue(sameRuntimeInstallation(config.runtime, current), 'RUNTIME_INSTALLATION_CHANGED');
  return current;
}
export function assertIdle(status, allowed = []) {
  const permitted = new Set(allowed);
  requireValue(Object.entries(status).every(([id, row]) => row.type === 'idle' || permitted.has(id)), 'FOREIGN_NATIVE_ACTIVITY');
}
export function assertNativeActivity(native, allowed = []) {
  requireValue(Array.isArray(native.session_activity), 'GLOBAL_ACTIVITY_UNAVAILABLE');
  const permitted = new Set(allowed);
  const sessions = new Map((native.session_index || []).map(row => [row.id, row]));
  for (let changed = true; changed;) {
    changed = false;
    for (const row of sessions.values()) if (permitted.has(row.parent_id) && !permitted.has(row.id)
      && sessions.get(row.parent_id)?.directory === row.directory) { permitted.add(row.id); changed = true; }
  }
  requireValue(native.session_activity.every(row => row.status === 'settled'
    || row.status === 'active_or_unknown' && permitted.has(row.session_id)), 'FOREIGN_OR_UNSETTLED_NATIVE_SESSION');
}

export async function probe({ appPath = '', database = DEFAULT_DATABASE, cacheRoot, python = 'python3', allowedSessionIds = [] }) {
  requireValue(process.platform === 'darwin' && process.arch === 'arm64', 'REQUIRES_MACOS_ARM64');
  const client = await discoverDesktopApp({ profile: LOOMY_APP_PROFILE, requestedPath: appPath });
  requireValue(client.version === '0.9.39', 'CLIENT_VERSION_UNVERIFIED');
  const processInfo = await inspectMacDesktopAppProcess({ profile: LOOMY_APP_PROFILE, appPath: client.path });
  requireValue(processInfo?.pid && processInfo.started_at, 'APP_NOT_RUNNING');
  const processIdentity = { pid: processInfo.pid, started_at: processInfo.started_at,
    executable_path: processInfo.executable_path, command_sha256: sha(processInfo.command || '') };
  const gui = await inspectMacGuiSession(); assertMacGuiReady(gui);
  const helper = await buildAxHelper(cacheRoot);
  const [snapshot, runtime, native] = await Promise.all([
    ax(helper, processInfo.pid), runtimeIdentity(processInfo, database), captureNative({ database, python }),
  ]);
  const status = await runtimeStatus(runtime); assertIdle(status, allowedSessionIds);
  assertNativeActivity(native, allowedSessionIds);
  const ui = uiConfiguration(snapshot);
  const config = { schema_version: 'wildclawbench.general-e2e-loomy-run-config/v1', version: COMPONENT_VERSION,
    client, process: processIdentity, runtime, ax_helper: helper, python,
    configuration: { model: ui.model, model_label: ui.model_label, reasoning_effort: ui.reasoning_effort, permission_label: ui.permission_label },
    permission_policy: 'preserve-workspace-policy',
    execution_concurrency: 3, initial_concurrency: 3, transport: 'macos-native-accessibility',
    observed_at: new Date().toISOString() };
  config.config_digest = digest(config);
  return { status: 'PASS', config, gui, ui: snapshot, native, runtime_status: status };
}

export function verifyBinding(native, { workspace, prompt, baseline = [], sessionId = null, terminal = false }) {
  requireValue(native.profile === PROFILE && native.snapshot?.method === 'readonly-source-sqlite-online-backup', 'BINDING_PROFILE_INVALID');
  const roots = native.sessions.filter(row => row.parent_id === null && row.directory === workspace && !baseline.includes(row.id) && (!sessionId || row.id === sessionId));
  requireValue(roots.length === 1, 'NATIVE_SESSION_BINDING_AMBIGUOUS');
  const root = roots[0], ids = new Set([root.id]);
  for (let changed = true; changed;) { changed = false; for (const row of native.sessions) if (ids.has(row.parent_id) && !ids.has(row.id)) { ids.add(row.id); changed = true; } }
  requireValue(ids.size === native.sessions.length && native.sessions.every(row => row.directory === workspace), 'NATIVE_CHILD_SCOPE_INVALID');
  const messages = native.messages.map(row => ({ ...row, parsed: JSON.parse(row.data) }));
  const parts = native.parts.map(row => ({ ...row, parsed: JSON.parse(row.data) }));
  const messageMap = new Map(messages.map(row => [row.id, row]));
  requireValue(messageMap.size === messages.length && messages.every(row => ids.has(row.session_id)) && new Set(parts.map(row => row.id)).size === parts.length
    && parts.every(row => ids.has(row.session_id) && messageMap.get(row.message_id)?.session_id === row.session_id), 'NATIVE_ROWS_INVALID');
  const users = messages.filter(row => row.session_id === root.id && row.parsed.role === 'user');
  requireValue(users.length === 1, 'NATIVE_USER_COUNT_INVALID');
  const userParts = parts.filter(row => row.message_id === users[0].id && row.parsed.type === 'text' && !row.parsed.synthetic && !row.parsed.ignored);
  const promptParts = userParts.filter(row => row.parsed.text === prompt);
  requireValue(promptParts.length === 1 && (userParts.length === 1 || userParts.length === 2
    && userParts[1].id === promptParts[0].id && isMemoryContext(userParts[0].parsed.text)), 'NATIVE_PROMPT_MISMATCH');
  const contextParts = userParts.filter(row => row.id !== promptParts[0].id);
  const assistants = messages.filter(row => row.session_id === root.id && row.parsed.role === 'assistant');
  const last = assistants.at(-1);
  if (terminal) {
    requireValue(last?.parsed.finish === 'stop' && Number.isSafeInteger(last.parsed.time?.completed), 'NATIVE_FINAL_NOT_COMPLETE');
    requireValue(parts.filter(row => row.parsed.type === 'tool').every(row => ['completed', 'error'].includes(row.parsed.state?.status)), 'NATIVE_TOOL_NOT_TERMINAL');
    for (const id of ids) {
      const tail = messages.filter(row => row.session_id === id && row.parsed.role === 'assistant').at(-1);
      requireValue(tail?.parsed.finish === 'stop' && Number.isSafeInteger(tail.parsed.time?.completed), 'NATIVE_CHILD_NOT_TERMINAL');
    }
  }
  return { root, messages, parts, user: users[0], final: last, session_ids: [...ids],
    prompt_part_ids: promptParts.map(row => row.id), client_context_part_ids: contextParts.map(row => row.id) };
}
