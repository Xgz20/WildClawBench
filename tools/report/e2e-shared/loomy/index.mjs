import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { access, lstat, mkdir, readFile, realpath, readdir } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { setTimeout as delay } from 'node:timers/promises';
import { discoverDesktopApp, inspectMacDesktopAppProcess } from '../desktop-app-discovery/index.mjs';
import { LOOMY_APP_PROFILE } from '../desktop-app-discovery/profiles.mjs';
import { inspectMacGuiSession, assertMacGuiReady } from '../desktop-gui/macos.mjs';

export const COMPONENT_VERSION = '0.1.12';
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
export async function inspectPinnedMain(config) {
  const pid = config.process.pid;
  const [comm, start, cmd] = await Promise.all([
    execute('/bin/ps', ['-p', String(pid), '-o', 'comm=']),
    execute('/bin/ps', ['-p', String(pid), '-o', 'lstart=']),
    execute('/bin/ps', ['-p', String(pid), '-o', 'command=']),
  ]);
  const executable = await realpath(comm.stdout.trim());
  const startedAt = new Date(Date.parse(start.stdout.trim())).toISOString();
  requireValue(executable === join(config.client.path, 'Contents/MacOS/Loomy')
    && startedAt === config.process.started_at
    && sha(cmd.stdout.trim()) === config.process.command_sha256, 'APP_PROCESS_CHANGED');
  return { pid, executable_path: executable, started_at: startedAt };
}
export async function act(config, node, action = 'press', options = {}) {
  assertMacGuiReady(await inspectMacGuiSession());
  const current = await inspectPinnedMain(config);
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

// OpenCode can close an empty assistant after retry exhaustion without copying
// the provider error into message.data. Admit only a bound primary HTTP 5xx log,
// an empty completed head, terminal tools, and a fresh idle owned runtime.
export function parseNativeHttpError(line) {
  const prefix = /^ERROR (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) .*?service=llm providerID=imodel modelID=spark-x2\.6 session\.id=(ses_[A-Za-z0-9]+) small=false agent=loomy mode=primary error=/u.exec(line);
  if (!prefix) return null;
  const source = line.slice(prefix[0].length);
  let depth = 0, quoted = false, escaped = false, end = -1;
  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    if (quoted) { if (escaped) escaped = false; else if (ch === '\\') escaped = true; else if (ch === '"') quoted = false; }
    else if (ch === '"') quoted = true;
    else if (ch === '{' || ch === '[') depth++;
    else if (ch === '}' || ch === ']') { depth--; if (depth === 0) { end = i + 1; break; } }
  }
  if (end < 0) return null;
  let parsed; try { parsed = JSON.parse(source.slice(0, end)); } catch { return null; }
  const error = parsed?.error;
  if (error?.name !== 'AI_APICallError' || error.url !== 'https://loomyad.xunfei.cn/api/v1/chat/completions'
    || !Number.isInteger(error.statusCode) || error.statusCode < 500 || error.statusCode > 599
    || error.requestBodyValues?.model !== 'spark-x2.6' || !Array.isArray(error.requestBodyValues.messages)) return null;
  return { session_id: prefix[2], occurred_at: prefix[1] + 'Z', error };
}
const userTexts = value => typeof value === 'string' ? [value] : Array.isArray(value)
  ? value.flatMap(userTexts) : value && typeof value === 'object' && value.type === 'text' ? userTexts(value.text) : [];
export function verifyNativeHttpFailure(proof, { native, workspace, prompt, baseline, sessionId, identity }) {
  requireValue(proof?.profile === 'loomy-native-primary-http-failure/v1'
    && digest(proof.identity) === digest(identity) && proof.prompt_sha256 === sha(Buffer.from(prompt)), 'HTTP_FAILURE_IDENTITY_INVALID');
  const binding = verifyBinding(native, { workspace, prompt, baseline, sessionId }); checkEmptyHead(binding);
  requireValue(binding.user.parsed.model?.providerID === 'imodel' && binding.user.parsed.model?.modelID === 'spark-x2.6'
    && binding.user.parsed.model?.variant === 'high' && binding.messages.filter(row => row.session_id === binding.root.id && row.parsed.role === 'assistant')
      .every(row => row.parsed.providerID === 'imodel' && row.parsed.modelID === 'spark-x2.6' && row.parsed.variant === 'high'), 'HTTP_FAILURE_MODEL_INVALID');
  requireValue(proof.final_message_id === binding.final.id && proof.session_id === binding.root.id
    && Array.isArray(proof.source_lines) && proof.source_lines.length > 0
    && sameRuntimeInstallation(proof.original_runtime, proof.observed_runtime)
    && binding.session_ids.every(id => !proof.runtime_status[id] || proof.runtime_status[id].type === 'idle'), 'HTTP_FAILURE_TERMINAL_INVALID');
  const start = binding.final.parsed.time.created, finish = binding.final.parsed.time.completed;
  const errors = proof.source_lines.map(row => {
    const bytes = Buffer.from(row.bytes_base64, 'base64');
    requireValue(sha(bytes) === row.sha256 && bytes.length === row.size && Number.isSafeInteger(row.line_number) && row.line_number > 0,
      'HTTP_FAILURE_LOG_HASH_INVALID');
    const parsed = parseNativeHttpError(bytes.toString('utf8'));
    requireValue(parsed?.session_id === sessionId && Date.parse(parsed.occurred_at) >= start - 1000
      && Date.parse(parsed.occurred_at) <= finish + 1000
      && parsed.error.requestBodyValues.messages.some(message => message.role === 'user'
        && userTexts(message.content).some(text => text === prompt || text.includes(prompt))), 'HTTP_FAILURE_LOG_BINDING_INVALID');
    return parsed;
  });
  requireValue(Date.parse(proof.observed_at) >= finish, 'HTTP_FAILURE_OBSERVATION_INVALID');
  return { binding, errors, error: { code: 'LOOMY_NATIVE_HTTP_ERROR', message: 'Native primary model HTTP ' + errors.at(-1).error.statusCode + ' after provider retries' } };
}
function checkEmptyHead(binding) {
  const final = binding.final?.parsed;
  requireValue(final && !final.finish && !final.error && Number.isSafeInteger(final.time?.created)
    && Number.isSafeInteger(final.time.completed) && final.time.completed >= final.time.created
    && !binding.parts.some(row => row.message_id === binding.final.id)
    && binding.parts.filter(row => row.parsed.type === 'tool').every(row => ['completed', 'error'].includes(row.parsed.state?.status)), 'HTTP_FAILURE_EMPTY_HEAD_UNPROVED');
}
export async function captureNativeHttpFailure(context, journal, runtime, native) {
  const binding = verifyBinding(native, { workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline, sessionId: journal.session?.id });
  try { checkEmptyHead(binding); } catch { return null; }
  const original = journal.runtime_binding || context.config.runtime;
  const logRoot = join(dirname(original.database), 'log');
  requireValue(await realpath(logRoot) === logRoot, 'HTTP_FAILURE_LOG_ROOT_UNSAFE');
  const expectedStart = Date.parse(original.started_at);
  requireValue(Number.isFinite(expectedStart), 'HTTP_FAILURE_RUNTIME_START_UNPROVED');
  const names = (await readdir(logRoot)).filter(name => /^\d{4}-\d{2}-\d{2}T\d{6}\.log$/u.test(name));
  const sourceLines = [];
  for (const name of names) {
    const stamp = name.slice(0, 13) + ':' + name.slice(13, 15) + ':' + name.slice(15, 17) + 'Z';
    if (Math.abs(Date.parse(stamp) - expectedStart) > 2000) continue;
    const path = join(logRoot, name), info = await lstat(path);
    requireValue(info.isFile() && !info.isSymbolicLink() && info.size <= 32 * 1024 * 1024, 'HTTP_FAILURE_LOG_UNSAFE');
    const bytes = await readFile(path);
    for (const [i, line] of bytes.toString('utf8').split('\n').entries()) {
      const parsed = parseNativeHttpError(line);
      if (parsed?.session_id !== binding.root.id || Date.parse(parsed.occurred_at) < binding.final.parsed.time.created - 1000
        || Date.parse(parsed.occurred_at) > binding.final.parsed.time.completed + 1000) continue;
      const data = Buffer.from(line);
      sourceLines.push({ source_path: path, source_sha256: sha(bytes), line_number: i + 1,
        sha256: sha(data), size: data.length, bytes_base64: data.toString('base64') });
    }
  }
  if (!sourceLines.length) return null;
  const statuses = await runtimeStatus(runtime, context.workspace);
  const proof = { profile: 'loomy-native-primary-http-failure/v1', identity: journal.identity,
    prompt_sha256: context.locks.prompt, session_id: binding.root.id, final_message_id: binding.final.id,
    observed_at: new Date().toISOString(), original_runtime: original, observed_runtime: runtime,
    runtime_status: statuses, source_lines: sourceLines };
  verifyNativeHttpFailure(proof, { native, workspace: context.workspace, prompt: context.prompt,
    baseline: journal.baseline, sessionId: binding.root.id, identity: journal.identity });
  return proof;
}

export async function runtimeIdentity(app, database = DEFAULT_DATABASE) {
  const result = await execute('/bin/ps', ['-axo', 'pid=,ppid=,comm=']);
  const rows = result.stdout.split('\n').map(line => /^\s*(\d+)\s+(\d+)\s+(.+)$/u.exec(line)).filter(Boolean);
  const candidates = rows.filter(row => Number(row[2]) === app.pid && (row[3] === 'opencode' || row[3].endsWith('/opencode')));
  requireValue(candidates.length > 0, 'RUNTIME_NOT_RUNNING');
  requireValue(candidates.length === 1, 'RUNTIME_PROCESS_AMBIGUOUS');
  const pid = Number(candidates[0][1]);
  const [text, listening, started, ownership] = await Promise.all([
    execute('/usr/sbin/lsof', ['-nP', '-a', '-p', String(pid), '-d', 'txt', '-Fn']).catch(() => ({ stdout: '' })),
    execute('/usr/sbin/lsof', ['-nP', '-a', '-p', String(pid), '-iTCP', '-sTCP:LISTEN', '-Fpn']).catch(() => ({ stdout: '' })),
    execute('/bin/ps', ['-p', String(pid), '-o', 'lstart=']),
    execute('/usr/sbin/lsof', ['-nP', '-a', '-p', String(pid), '-Fpn', '--', database]).catch(() => ({ stdout: '' })),
  ]);
  const binaries = text.stdout.split('\n').filter(line => line.startsWith('n') && line.endsWith('/opencode'));
  requireValue(binaries.length > 0, 'RUNTIME_STARTING');
  requireValue(binaries.length === 1, 'RUNTIME_BINARY_AMBIGUOUS');
  const executable = await realpath(binaries[0].slice(1));
  requireValue(executable === join(dirname(dirname(app.executable_path)), 'Resources/opencode/darwin-arm64/opencode'), 'RUNTIME_BINARY_NOT_BUNDLED');
  const ports = [...listening.stdout.matchAll(/^n127\.0\.0\.1:(\d+)$/gmu)].map(match => match[1]);
  requireValue(ports.length > 0 && ownership.stdout.includes('n' + database + '\n'), 'RUNTIME_STARTING');
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
  if (!['ppid', 'executable', 'binary_sha256', 'database'].every(key => before?.[key] === after?.[key])) return false;
  if (before?.state === 'absent') return isAbsentRuntime(before)
    && after?.database_owned === true && after?.health_version === before.binary_version;
  return ['database_owned', 'health_version'].every(key => before?.[key] === after?.[key]);
}
export const isAbsentRuntime = runtime => runtime?.state === 'absent' && runtime.pid === null
  && runtime.endpoint === null && runtime.started_at === null && runtime.database_owned === false
  && runtime.health_version === null && runtime.binary_version === '1.14.22';

async function inspectAbsentRuntime(app, database) {
  const executable = await realpath(join(dirname(dirname(app.executable_path)), 'Resources/opencode/darwin-arm64/opencode'));
  const bytes = await readFile(executable);
  const { stdout } = await command(executable, ['--version']);
  requireValue(stdout.trim() === '1.14.22', 'RUNTIME_VERSION_UNVERIFIED');
  requireValue(await realpath(database) === database, 'RUNTIME_DATABASE_PATH_UNSAFE');
  // No listener, PID, ownership or health response was observed. Keep them absent.
  return { state: 'absent', pid: null, ppid: app.pid, executable, started_at: null,
    binary_sha256: sha(bytes), endpoint: null, database, database_owned: false,
    health_version: null, binary_version: stdout.trim() };
}
export async function currentOwnedRuntime(config) {
  const app = await inspectPinnedMain(config);
  const current = await runtimeIdentity(app, config.runtime.database);
  requireValue(sameRuntimeInstallation(config.runtime, current), 'RUNTIME_INSTALLATION_CHANGED');
  return current;
}
export function assertIdle(status, allowed = []) {
  const permitted = new Set(allowed);
  requireValue(Object.entries(status).every(([id, row]) => row.type === 'idle' || permitted.has(id)), 'FOREIGN_NATIVE_ACTIVITY');
}
export async function assertArchivedFailuresIdle(runtime, failures = []) {
  if (isAbsentRuntime(runtime)) return;
  for (const workspace of new Set(failures.map(row => row.directory))) {
    assertIdle(await runtimeStatus(runtime, workspace));
  }
}
export function assertNativeActivity(native, allowed = [], archivedFailures = []) {
  requireValue(Array.isArray(native.session_activity), 'GLOBAL_ACTIVITY_UNAVAILABLE');
  const permitted = new Set(allowed);
  const sessions = new Map((native.session_index || []).map(row => [row.id, row]));
  for (let changed = true; changed;) {
    changed = false;
    for (const row of sessions.values()) if (permitted.has(row.parent_id) && !permitted.has(row.id)
      && sessions.get(row.parent_id)?.directory === row.directory) { permitted.add(row.id); changed = true; }
  }
  const archived = new Set();
  for (const proof of archivedFailures) {
    const row = native.session_activity.find(item => item.session_id === proof.session_id);
    requireValue(!archived.has(proof.session_id) && row?.parent_id === null && row.directory === proof.directory
      && row.last_message_id === proof.last_message_id && row.last_message_sha256 === proof.last_message_sha256
      && row.last_role === 'assistant' && row.completed_at === proof.completed_at
      && row.pending_tool_count === 0 && !row.finish && !row.has_error, 'ARCHIVED_FAILURE_HEAD_CHANGED');
    archived.add(proof.session_id);
  }
  requireValue(native.session_activity.every(row => row.status === 'settled'
    || row.status === 'active_or_unknown' && (permitted.has(row.session_id) || archived.has(row.session_id))), 'FOREIGN_OR_UNSETTLED_NATIVE_SESSION');
}
export async function waitNativeActivity({ database, python = 'python3', allowed = [], archivedFailures = [], timeoutMs = 30000 }) {
  const until = Date.now() + timeoutMs;
  do {
    const native = await captureNative({ database, python });
    try { assertNativeActivity(native, allowed, archivedFailures); return native; }
    catch (error) {
      if (error.message !== 'LOOMY_FOREIGN_OR_UNSETTLED_NATIVE_SESSION' || Date.now() >= until) throw error;
    }
    await delay(200);
  } while (true);
}

export async function identifyGuiMain(client, helper) {
  const { stdout } = await execute('/bin/ps', ['-axo', 'pid=,ppid=,comm=']);
  const candidates = stdout.split('\n').map(line => /^\s*(\d+)\s+(\d+)\s+(.+)$/u.exec(line)).filter(Boolean)
    .filter(row => row[3] === client.executable_path);
  const valid = [];
  for (const row of candidates) {
    const pid = Number(row[1]);
    try {
      const snapshot = await ax(helper, pid);
      if (snapshot.nodes.some(node => node.role === 'AXWebArea' && node.url?.startsWith('file://' + client.path + '/Contents/Resources/app.asar/dist/index.html'))) valid.push(pid);
    } catch { /* Electron-as-Node MCP hosts have no application GUI. */ }
  }
  requireValue(valid.length === 1, 'GUI_MAIN_PROCESS_AMBIGUOUS');
  const pid = valid[0];
  const [started, cmd] = await Promise.all([execute('/bin/ps', ['-p', String(pid), '-o', 'lstart=']), execute('/bin/ps', ['-p', String(pid), '-o', 'command='])]);
  return { pid, started_at: new Date(Date.parse(started.stdout.trim())).toISOString(), executable_path: client.executable_path, command: cmd.stdout.trim() };
}

export async function probe({ appPath = '', database = DEFAULT_DATABASE, cacheRoot, python = 'python3', allowedSessionIds = [], archivedFailureRecords = [] }) {
  requireValue(process.platform === 'darwin' && process.arch === 'arm64', 'REQUIRES_MACOS_ARM64');
  const client = await discoverDesktopApp({ profile: LOOMY_APP_PROFILE, requestedPath: appPath });
  requireValue(client.version === '0.9.39', 'CLIENT_VERSION_UNVERIFIED');
  const helper = await buildAxHelper(cacheRoot);
  const processInfo = await identifyGuiMain(client, helper);
  requireValue(processInfo?.pid && processInfo.started_at, 'APP_NOT_RUNNING');
  const processIdentity = { pid: processInfo.pid, started_at: processInfo.started_at,
    executable_path: processInfo.executable_path, command_sha256: sha(processInfo.command || '') };
  const gui = await inspectMacGuiSession(); assertMacGuiReady(gui);
  const [snapshot, runtime, native] = await Promise.all([
    ax(helper, processInfo.pid), runtimeIdentity(processInfo, database).catch(error => {
      if (error.message !== 'LOOMY_RUNTIME_NOT_RUNNING') throw error;
      return inspectAbsentRuntime(processInfo, database);
    }), captureNative({ database, python }),
  ]);
  const status = isAbsentRuntime(runtime) ? null : await runtimeStatus(runtime);
  if (status !== null) assertIdle(status, allowedSessionIds);
  const { readArchivedHttpFailure } = await import('./verification.mjs');
  const archivedFailures = await Promise.all(archivedFailureRecords.map(path => readArchivedHttpFailure(path, runtime)));
  await assertArchivedFailuresIdle(runtime, archivedFailures);
  assertNativeActivity(native, allowedSessionIds, archivedFailures);
  const ui = uiConfiguration(snapshot);
  const config = { schema_version: 'wildclawbench.general-e2e-loomy-run-config/v1', version: COMPONENT_VERSION,
    client, process: processIdentity, runtime, ax_helper: helper, python,
    configuration: { model: ui.model, model_label: ui.model_label, reasoning_effort: ui.reasoning_effort, permission_label: ui.permission_label },
    permission_policy: 'preserve-workspace-policy',
    archived_http_failures: archivedFailures,
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
