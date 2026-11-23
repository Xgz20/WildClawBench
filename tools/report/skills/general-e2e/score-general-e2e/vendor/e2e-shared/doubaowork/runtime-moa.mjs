import { createHash, randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { inspectEndpointListener } from './platform.mjs';

// Pinned installed AND live entry-moa source, inspected on DoubaoWork 2.35.15.
export const MOA_SOURCE_SHA256 = 'd7fb756b89560ae2fc8e0939d3afc1478c05bbfa5d1ed890927b731d6cbe5e42';
export const MOA_23519_SOURCE_SHA256 = 'e387108b1ffd23a898591d3822c37f578ebce07b52510a54e5bd25a186d03900';
const profiles = Object.freeze({
  '2.35.15': Object.freeze({ version: '2.35.15', sourceSha: MOA_SOURCE_SHA256, contextGetter: 'sE', serviceGetter: 'Rh',
    backendProfile: 'doubaowork-moa-2.35.15-inspector/v1', sdkProfile: 'doubaowork-native-moa-sdk-model-protocol-2.35.15/v1' }),
  '2.35.19': Object.freeze({ version: '2.35.19', sourceSha: MOA_23519_SOURCE_SHA256, contextGetter: 'sd', serviceGetter: 'wv',
    backendProfile: 'doubaowork-moa-2.35.19-inspector/v1', sdkProfile: 'doubaowork-native-moa-sdk-model-protocol-2.35.19/v1' }),
});
export const moaProfileForVersion = version => Object.hasOwn(profiles, version) ? profiles[version] : null;
export const moaProfileForSource = source => Object.values(profiles).find(p => p.sourceSha === source) || null;
const URL_BASE = 'http://127.0.0.1:9261';
const configured = new WeakMap();
const sha = value => createHash('sha256').update(value).digest('hex');
const check = (ok, code) => { if (!ok) throw Error('DOUBAOWORK_MOA_' + code); };
const readProcess = promisify(execFile);

export function configureMoaBackend(browser, { app, uiEndpoint }) {
  const profile = moaProfileForVersion(app.version);
  if (!profile) return false;
  check(uiEndpoint === 'http://127.0.0.1:9260', 'DEFAULT_LOOPBACK_PORTS_REQUIRED');
  configured.set(browser, { app, uiEndpoint, profile });
  return true;
}
export const isMoaBackend = browser => configured.has(browser);

export function validateMoaListener({ pid, parentPid, command, address, target }, uiPid, appPath) {
  check(Number.isSafeInteger(pid) && pid > 0 && parentPid === uiPid, 'WORKER_PARENT_MISMATCH');
  check(address === '127.0.0.1:9261' && command.startsWith(appPath + '/Contents/Helpers/DoubaoWork Browser.app/Contents/Frameworks/')
    && command.includes('/Helpers/DoubaoWork Browser Helper.app/Contents/MacOS/DoubaoWork Browser Helper ')
    && /(?:^|\s)--type=utility(?:\s|$)/u.test(command)
    && /(?:^|\s)--utility-sub-type=jsrt\.mojom\.Service(?:\s|$)/u.test(command), 'WORKER_PROCESS_UNVERIFIED');
  check(target?.type === 'node' && target.url === 'aha-runtime'
    && target.title === `aha-runtime [pid: ${pid}]`
    && /^ws:\/\/127\.0\.0\.1:9261\/ws\/[A-Za-z0-9-]+$/u.test(target.webSocketDebuggerUrl || ''), 'INSPECTOR_TARGET_UNVERIFIED');
}

export function validateMoaBackendProof(value, expectedSourceSha = value?.worker_source_sha256) {
  const profile = moaProfileForSource(expectedSourceSha);
  check(profile && value?.profile === profile.backendProfile && value.worker_id === 'entry-moa'
    && value.worker_source_sha256 === profile.sourceSha && value.endpoint === URL_BASE
    && value.source_verification === 'live-debugger-script-sha256'
    && value.script_url === 'https://resource.sandbox.invalid/local_webcontents/apps/entry-moa/main.js'
    && Number.isSafeInteger(value.worker_pid) && value.worker_pid > 0
    && Number.isSafeInteger(value.browser_pid) && value.browser_pid > 0 && value.worker_pid !== value.browser_pid
    && typeof value.worker_start_identity === 'string' && value.worker_start_identity.trim()
    && typeof value.browser_start_identity === 'string' && value.browser_start_identity.trim()
    && /^[a-f0-9]{64}$/u.test(value.worker_command_sha256 || '')
    && /^[a-f0-9]{64}$/u.test(value.browser_command_sha256 || '')
    && /^[A-Za-z0-9-]{20,80}$/u.test(value.inspector_target_id || ''), 'BACKEND_PROOF_INVALID');
}

async function readIdentity(browser, config) {
  const listener = await inspectEndpointListener(config.uiEndpoint, config.app);
  check(listener.unique_expected_listener && listener.listeners.length === 1, 'UI_LISTENER_UNVERIFIED');
  const ui = await (await fetch(config.uiEndpoint + '/json/list', { signal: AbortSignal.timeout(3000) })).json();
  const actual = await browser.newBrowserCDPSession();
  try {
    const { targetInfos } = await actual.send('Target.getTargets');
    const chat = ui.filter(t => /^(?:chrome|doubaowork):\/\/doubaowork-chat\/chat(?:\/[0-9]+)?\/?(?:\?[^#]*)?$/u.test(t.url || ''));
    check(chat.length === 1 && targetInfos.some(t => t.targetId === chat[0].id), 'UI_BROWSER_CONNECTION_MISMATCH');
  } finally { await actual.detach(); }
  const list = await (await fetch(URL_BASE + '/json/list', { signal: AbortSignal.timeout(3000) })).json();
  check(Array.isArray(list) && list.length === 1, 'INSPECTOR_TARGET_AMBIGUOUS');
  const ls = await readProcess('/usr/sbin/lsof', ['-nP', '-iTCP:9261', '-sTCP:LISTEN', '-Fpn'], { encoding: 'utf8', timeout: 5000 });
  const pids = [...ls.stdout.matchAll(/^p(\d+)$/gmu)].map(x => Number(x[1]));
  const addresses = [...ls.stdout.matchAll(/^n(.+)$/gmu)].map(x => x[1]);
  check(pids.length === 1 && addresses.length === 1, 'INSPECTOR_LISTENER_AMBIGUOUS');
  const ps = await readProcess('/bin/ps', ['-p', String(pids[0]), '-o', 'ppid=,lstart=,command='], { encoding: 'utf8', timeout: 5000 });
  const match = ps.stdout.trim().match(/^(\d+)\s+(\S+\s+\S+\s+\d+\s+\S+\s+\d+)\s+(.+)$/u);
  check(match, 'WORKER_IDENTITY_UNAVAILABLE');
  const identity = { pid: pids[0], parentPid: Number(match[1]), command: match[3], address: addresses[0], target: list[0] };
  validateMoaListener(identity, listener.listeners[0].pid, config.app.app_path);
  return { ...identity, process_start_identity: match[2].replace(/\s+/gu, ' '), command_sha256: sha(match[3]),
    browser_pid: listener.listeners[0].pid, browser_start_identity: listener.listeners[0].process_start_identity,
    browser_command_sha256: listener.listeners[0].command_sha256 };
}

class Inspector {
  constructor(socket) {
    this.socket = socket; this.next = 0; this.pending = new Map(); this.events = new Set();
    socket.addEventListener('message', event => {
      const value = JSON.parse(event.data), entry = this.pending.get(value.id);
      if (entry) { this.pending.delete(value.id); clearTimeout(entry.timer);
        value.error ? entry.reject(Error(JSON.stringify(value.error))) : entry.resolve(value.result);
      } else if (value.method) for (const receive of this.events) receive(value);
    });
    socket.addEventListener('close', () => { for (const p of this.pending.values()) {
      clearTimeout(p.timer); p.reject(Error('DOUBAOWORK_MOA_INSPECTOR_CLOSED')); } this.pending.clear(); });
  }
  static async connect(url) {
    const socket = new WebSocket(url);
    await new Promise((resolve, reject) => { const timer = setTimeout(() => reject(Error('DOUBAOWORK_MOA_CONNECT_TIMEOUT')), 5000);
      socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
      socket.addEventListener('error', error => { clearTimeout(timer); reject(error); }, { once: true }); });
    return new Inspector(socket);
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => { const id = ++this.next;
      const timer = setTimeout(() => { this.pending.delete(id); reject(Error('DOUBAOWORK_MOA_RPC_TIMEOUT:' + method)); }, 10000);
      this.pending.set(id, { resolve, reject, timer }); this.socket.send(JSON.stringify({ id, method, params })); });
  }
  close() { this.socket.close(); }
}

async function verifyEntry(c, profile) {
  const scripts = [], receive = event => {
    if (event.method === 'Debugger.scriptParsed' && event.params.url === 'https://resource.sandbox.invalid/local_webcontents/apps/entry-moa/main.js') scripts.push(event.params);
  };
  c.events.add(receive);
  try {
    await c.send('Debugger.enable'); check(scripts.length === 1, 'ENTRY_SCRIPT_AMBIGUOUS');
    const source = await c.send('Debugger.getScriptSource', { scriptId: scripts[0].scriptId });
    check(sha(source.scriptSource) === profile.sourceSha, 'LIVE_SOURCE_UNVERIFIED');
  } finally { c.events.delete(receive); await c.send('Debugger.disable').catch(() => {}); }
}

async function checked(c, method, params) {
  const value = await c.send(method, params);
  if (value.exceptionDetails) throw Error('DOUBAOWORK_MOA_INSPECTION_FAILED:' + (value.exceptionDetails.exception?.description || value.exceptionDetails.text));
  return value;
}

async function toolObjects(c, group, profile) {
  const proto = await checked(c, 'Runtime.evaluate', { expression: 'Object.prototype', objectGroup: group });
  const all = await c.send('Runtime.queryObjects', { prototypeObjectId: proto.result.objectId, objectGroup: group });
  const typed = await checked(c, 'Runtime.callFunctionOn', { objectId: all.objects.objectId, objectGroup: group,
    functionDeclaration: `function(){const a=this.filter(o=>{try{const f=Object.getOwnPropertyDescriptor(o,'start')?.value;return typeof f==='function'&&String(f).includes('ToolCallManager has been destroyed')&&typeof o.executeForQueue==='function'&&typeof o.getFinalized==='function'}catch{return false}});if(a.length!==1)throw Error('Tool prototype not unique');return a[0]}` });
  const instances = await c.send('Runtime.queryObjects', { prototypeObjectId: typed.result.objectId, objectGroup: group });
  const manager = await checked(c, 'Runtime.callFunctionOn', { objectId: instances.objects.objectId, objectGroup: group,
    functionDeclaration: `function(){if(this.length!==1||this[0].destroyed!==false)throw Error('Tool manager not unique');return this[0]}` });
  const methods = await c.send('Runtime.getProperties', { objectId: typed.result.objectId, ownProperties: true });
  const start = methods.result.find(x => x.name === 'start')?.value?.objectId;
  check(start, 'START_METHOD_UNAVAILABLE');
  const scopes = await c.send('Runtime.getProperties', { objectId: start });
  const scopeId = scopes.internalProperties?.find(x => x.name === '[[Scopes]]')?.value?.objectId;
  check(scopeId, 'NATIVE_SCOPES_UNAVAILABLE');
  const list = await c.send('Runtime.getProperties', { objectId: scopeId, ownProperties: true });
  let pair;
  for (const scope of list.result.filter(x => x.value?.description?.startsWith('Closure'))) {
    const variables = await c.send('Runtime.getProperties', { objectId: scope.value.objectId, ownProperties: true });
    const context = variables.result.find(x => x.name === profile.contextGetter)?.value,
      service = variables.result.find(x => x.name === profile.serviceGetter)?.value;
    if (context?.type === 'function' && service?.type === 'function') {
      check(!pair, 'NATIVE_GETTERS_AMBIGUOUS'); pair = { context, service };
    }
  }
  check(pair, 'NATIVE_GETTERS_UNAVAILABLE');
  const get = async (fn, marker) => checked(c, 'Runtime.callFunctionOn', { objectId: fn.objectId, objectGroup: group,
    arguments: [{ value: marker }], functionDeclaration: `function(marker){const s=String(this);if(!s.includes(marker)||!s.includes('current'))throw Error('Readonly getter source changed');return this()}` });
  const context = await get(pair.context, 'tool_context_source_not_initialized');
  const service = await get(pair.service, 'LocalToolSSE is not initialized');
  const store = await checked(c, 'Runtime.callFunctionOn', { objectId: context.result.objectId, objectGroup: group,
    functionDeclaration: `function(){if(!(this.store?.contextsBySandboxId instanceof Map))throw Error('Context store unavailable');return this.store}` });
  return { managerId: manager.result.objectId, storeId: store.result.objectId, serviceId: service.result.objectId };
}

export async function moaDispatcherCall(browser, operation, values, observer) {
  const config = configured.get(browser); check(config, 'NOT_CONFIGURED');
  const before = await readIdentity(browser, config), c = await Inspector.connect(before.target.webSocketDebuggerUrl);
  const group = 'wcb-moa-dispatch-' + randomUUID();
  try {
    await verifyEntry(c, config.profile);
    const objects = await toolObjects(c, group, config.profile);
    const after = await readIdentity(browser, config);
    check(before.pid === after.pid && before.process_start_identity === after.process_start_identity
      && before.command_sha256 === after.command_sha256 && before.target.id === after.target.id
      && before.browser_pid === after.browser_pid && before.browser_start_identity === after.browser_start_identity, 'PROCESS_DRIFT');
    const result = await checked(c, 'Runtime.callFunctionOn', { objectId: objects.managerId, objectGroup: group, returnByValue: true,
      arguments: [{ objectId: objects.storeId }, { value: { ...values, operation, profileSha: config.profile.sourceSha } },
        { objectId: objects.serviceId }], functionDeclaration: observer.toString() });
    check(result.result?.value, 'OBSERVER_RESULT_UNAVAILABLE');
    return { ...result.result.value, native_backend: { profile: config.profile.backendProfile,
      worker_id: 'entry-moa', worker_source_sha256: config.profile.sourceSha, worker_pid: before.pid,
      worker_start_identity: before.process_start_identity, worker_command_sha256: before.command_sha256,
      browser_pid: before.browser_pid, browser_start_identity: before.browser_start_identity,
      browser_command_sha256: before.browser_command_sha256, inspector_target_id: before.target.id,
      endpoint: URL_BASE, source_verification: 'live-debugger-script-sha256',
      script_url: 'https://resource.sandbox.invalid/local_webcontents/apps/entry-moa/main.js' } };
  } finally { await c.send('Runtime.releaseObjectGroup', { objectGroup: group }).catch(() => {}); c.close(); }
}
