// Mechanical UI preparation: never sends a Prompt or changes a workspace.
import { readFile, writeFile, mkdir, open, unlink, realpath } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { resolve, join, relative, isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import { discoverMainTarget, CdpClient, renderExpectedPrompt, createFreshTask } from './lib/astronstudio-cdp.mjs';
import { queryNativeSessions, queryPristineThread, queryProjectForThread } from './lib/astronstudio-state.mjs';
import { isRetryablePreSendFailure, isBlockingActiveSession } from './execute_astronstudio_macos.mjs';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function require(ok, code) { if (!ok) throw new Error(code); }
function inside(root, value) {
  const path = resolve(root, value), rel = relative(root, path);
  require(rel && !isAbsolute(rel) && rel !== '..' && !rel.startsWith('../'), 'ZERO_SEND_PATH_ESCAPE');
  return path;
}
export function identifyOwnedDraft(ui, candidates) {
  require(ui.count === 1 && !ui.dialogs.length && typeof ui.text === 'string', 'UNKNOWN_OR_BLOCKED_UI_PRESERVED');
  if (!ui.text) return null;
  const matches = candidates.filter(candidate => renderExpectedPrompt(candidate.prompt, ui.chips)?.trim() === ui.text);
  require(matches.length === 1, 'DRAFT_NOT_UNIQUE_FROZEN_PROMPT');
  const candidate = matches[0];
  require(isRetryablePreSendFailure(candidate.state), 'DRAFT_ATTEMPT_NOT_ZERO_SEND_ELIGIBLE');
  require(ui.workspace.includes(candidate.workspace), 'DRAFT_WORKSPACE_NOT_BOUND');
  require(candidate.state.identity.task_id === candidate.task_id, 'DRAFT_TASK_IDENTITY_MISMATCH');
  return candidate;
}

export async function prepareZeroSendUi({ unitRoot, stateDatabase, endpoint, auditDir, timeoutMs = 30000 }, overrides = {}) {
  const api = { queryNativeSessions, queryPristineThread, queryProjectForThread, discoverMainTarget,
    connect: CdpClient.connect, createFreshTask, ...overrides };
  unitRoot = await realpath(unitRoot);
  const manifest = JSON.parse(await readFile(join(unitRoot, 'manifest.json'), 'utf8'));
  const active = (await api.queryNativeSessions(stateDatabase)).filter(isBlockingActiveSession);
  require(!active.length, 'ZERO_SEND_UI_REQUIRES_NATIVE_GLOBAL_IDLE');
  await mkdir(auditDir, { recursive: true });
  const lockPath = join(unitRoot, '.general-e2e/astronstudio-ui.lock');
  const lock = await open(lockPath, 'wx', 0o600);
  await lock.writeFile(JSON.stringify({ pid: process.pid, kind: 'bound-zero-send-ui-preparation' }));
  let client;
  const id = `${Date.now()}-${randomUUID()}`;
  const proof = { at: new Date().toISOString(), formal_send_calls: 0, workspace_files_changed: false };
  try {
    const target = await api.discoverMainTarget(endpoint, 5000);
    client = await api.connect(target.webSocketDebuggerUrl);
    const ui = await client.evaluate(`(() => {const es=Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(e=>e.getBoundingClientRect().width>0);const e=es[0];return{route:location.hash,count:es.length,text:e?.innerText?.trim(),chips:e?Array.from(e.querySelectorAll('[role="link"][contenteditable="false"]')).map(c=>({title:c.getAttribute('title'),display:c.innerText})):[],workspace:Array.from(document.querySelectorAll('[data-testid="workspace-picker-trigger"],[data-testid="project-picker-trigger"]')).map(e=>e.getAttribute('title')),dialogs:Array.from(document.querySelectorAll('[role="dialog"],[role="alertdialog"],[aria-modal="true"]')).filter(e=>e.getBoundingClientRect().width>0).map(e=>e.getAttribute('role'))}})()`);
    proof.before = { route: ui.route, editor_count: ui.count, text_length: ui.text?.length ?? null,
      text_sha256: typeof ui.text === 'string' ? sha(ui.text) : null, dialogs: ui.dialogs };
    const candidates = [];
    for (const task of manifest.tasks) {
      require(/^[A-Za-z0-9_.-]+$/.test(task.task_id), 'ZERO_SEND_TASK_ID_INVALID');
      const promptPath = inside(unitRoot, task.prompt.path);
      require(await realpath(promptPath) === promptPath, 'ZERO_SEND_PROMPT_SYMLINK');
      const prompt = await readFile(promptPath);
      require(sha(prompt) === task.prompt.sha256, 'ZERO_SEND_PROMPT_SHA_MISMATCH');
      const statePath = join(unitRoot, '.general-e2e/execution', task.task_id, 'automation-state.json');
      let bytes;
      try { bytes = await readFile(statePath); } catch (error) { if (error.code === 'ENOENT') continue; throw error; }
      require(await realpath(statePath) === statePath, 'ZERO_SEND_STATE_SYMLINK');
      const state = JSON.parse(bytes);
      require(state.identity.batch_id === manifest.batch_id && state.identity.unit_id === manifest.unit_id,
        'ZERO_SEND_STATE_IDENTITY_MISMATCH');
      candidates.push({ task_id: task.task_id, prompt: prompt.toString('utf8'), state, statePath,
        state_sha256: sha(bytes), workspace: inside(unitRoot, task.workspace.path) });
    }
    const owned = identifyOwnedDraft(ui, candidates);
    if (owned) {
      require(/^#\/[A-Za-z0-9-]+$/.test(ui.route), 'DRAFT_NATIVE_ROUTE_UNKNOWN');
      const thread = ui.route.slice(2);
      const projects = await api.queryProjectForThread(stateDatabase, thread);
      require(projects.length === 1 && projects[0].workspace_root === owned.workspace
        && await api.queryPristineThread(stateDatabase, thread), 'DRAFT_NATIVE_PRISTINE_BINDING_NOT_PROVEN');
      proof.owned_draft = { task_id: owned.task_id, attempt_id: owned.state.identity.attempt_id,
        state_sha256: owned.state_sha256, state_path: owned.statePath, prompt: owned.prompt,
        rendered_text: ui.text, chips: ui.chips, workspace: owned.workspace, native_project: projects[0] };
      await writeFile(join(auditDir, id + '.before.json'), JSON.stringify(proof, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
      require(sha(await readFile(owned.statePath)) === owned.state_sha256, 'DRAFT_ATTEMPT_CHANGED');
      require(!(await api.queryNativeSessions(stateDatabase)).some(isBlockingActiveSession)
        && await api.queryPristineThread(stateDatabase, thread), 'DRAFT_NATIVE_ACTIVITY_CHANGED');
      const selected = await client.evaluate(`(() => {const e=document.querySelector('[data-testid="composer-editor"]');if(location.hash!==${JSON.stringify(ui.route)}||e?.innerText?.trim()!==${JSON.stringify(ui.text)})return false;e.focus();const r=document.createRange();r.selectNodeContents(e);const s=getSelection();s.removeAllRanges();s.addRange(r);return document.activeElement===e;})()`);
      require(selected, 'DRAFT_OR_FOCUS_CHANGED');
      await client.send('Input.dispatchKeyEvent', {type:'keyDown',key:'Backspace',code:'Backspace'});
      await client.send('Input.dispatchKeyEvent', {type:'keyUp',key:'Backspace',code:'Backspace'});
      const empty = await client.evaluate(`(() => {const e=document.querySelector('[data-testid="composer-editor"]');return{route:location.hash,text:e?.innerText?.trim(),chips:e?.querySelectorAll('[role="link"][contenteditable="false"]').length}})()`);
      require(empty.text === '' && empty.chips === 0 && empty.route === ui.route, 'DRAFT_RESET_NOT_VERIFIED');
      require(sha(await readFile(owned.statePath)) === owned.state_sha256, 'DRAFT_ATTEMPT_CHANGED');
      proof.reset = { operation: 'clear only bound preserved zero-send draft', after: empty };
    }
    proof.fresh = await api.createFreshTask(client, timeoutMs, stateDatabase);
    proof.status = 'PASS';
    return proof;
  } catch (error) { proof.status = 'FAIL'; proof.error = error.message; throw error; }
  finally {
    try {
      await writeFile(join(auditDir, id + '.result.json'), JSON.stringify(proof, null, 2) + '\n', {flag:'wx',mode:0o600});
    } finally {
      client?.close(); await lock.close();
      if (JSON.parse(await readFile(lockPath, 'utf8')).pid === process.pid) await unlink(lockPath);
    }
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  const options = {}, names = {'--unit-root':'unitRoot','--state-database':'stateDatabase','--endpoint':'endpoint','--audit-dir':'auditDir'};
  try {
    if (process.argv.includes('--help') || process.argv.includes('-h')) {
      console.log('Usage: node prepare_astronstudio_zero_send_ui.mjs --unit-root ABS --state-database ABS --endpoint URL --audit-dir NEW_AUDIT_DIR\nOnly clears a preserved, exact frozen, native-pristine zero-send draft; never sends a Prompt.');
      process.exit(0);
    }
    for (let i=2;i<process.argv.length;i++) { require(names[process.argv[i]] && process.argv[i+1], 'ZERO_SEND_ARGUMENT_INVALID'); options[names[process.argv[i++]]] = process.argv[i]; }
    require(Object.values(names).every(k=>options[k]), 'Required: --unit-root --state-database --endpoint --audit-dir');
    console.log(JSON.stringify(await prepareZeroSendUi(options), null, 2));
  } catch (error) { console.error(error.message); process.exitCode=2; }
}
