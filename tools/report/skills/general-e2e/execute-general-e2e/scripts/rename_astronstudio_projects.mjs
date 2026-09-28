#!/usr/bin/env node
// Set AStudio's local project display aliases after the corresponding attempts are terminal.
// This never changes a task Workspace, Prompt, execution package, or native session.

import { createHash, randomUUID } from "node:crypto";
import { readFile, readdir, mkdir, rename, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve, relative, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { DatabaseSync } from "node:sqlite";

import { CdpClient, discoverMainTarget } from "./lib/astronstudio-cdp.mjs";
import { withStateSnapshot } from "./lib/astronstudio-state.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
let ROOT, UNIT, FROZEN_CONFIG, OUTPUT, STATE_DATABASE;
const PROBE_SCRIPT = join(HERE, "probe_astronstudio_macos.mjs");
const PERSISTED_KEY = "astudio:renderer-state:v8";
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

function requireCondition(ok, message) {
  if (!ok) throw new Error(message);
}

export function parseOptions(argv) {
  const {values} = parseArgs({args: argv, options: {
    "unit-root": {type: "string"}, "frozen-config": {type: "string"},
    "task-id": {type: "string", multiple: true}, help: {type: "boolean"},
  }});
  if (values.help) return {help: true};
  if (!isAbsolute(values["unit-root"] || "") || !isAbsolute(values["frozen-config"] || "")) throw Error("ABSOLUTE_UNIT_AND_CONFIG_REQUIRED");
  return {unit: resolve(values["unit-root"]), config: resolve(values["frozen-config"]), taskIds: values["task-id"] || []};
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function formalAttempt(taskId) {
  const state = await readJson(join(UNIT, ".general-e2e/execution", taskId, "automation-state.json"));
  requireCondition(["COMPLETED", "FAILED"].includes(state.phase), `task not terminal: ${taskId}`);
  const sentOnce = state.send.dispatch_attempt_count === 1 && state.prompt.send_status === "sent";
  const failedBeforeSend = state.phase === "FAILED"
    && state.send.dispatch_attempt_count === 0
    && state.prompt.send_status === "not_sent"
    && state.execution.business_status === "infrastructure_error"
    && state.execution.error?.code === "PRE_SEND_DRIVER_ERROR";
  requireCondition(state.identity.task_id === taskId && (sentOnce || failedBeforeSend), `task identity/send mismatch: ${taskId}`);
  const evidenceRoot = join(UNIT, "evidence/tasks", taskId);
  const entries = await readdir(evidenceRoot, { withFileTypes: true });
  const attempts = entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name);
  requireCondition(attempts.length === 1 && attempts[0] === state.identity.attempt_id, `formal attempt mismatch: ${taskId}`);
  await readFile(join(evidenceRoot, attempts[0], "execution-record.json"));
  return { attemptId: state.identity.attempt_id, sentOnce };
}

function assertNoExecutionWorker() {
  const result = spawnSync("/bin/ps", ["-axo", "pid=,command="], { encoding: "utf8" });
  requireCondition(result.status === 0, "could not inspect running processes");
  const conflicts = result.stdout.split("\n").filter((line) =>
    line.includes(UNIT)
    && (line.includes("run_astronstudio_macos_batch.mjs") || line.includes("execute_astronstudio_macos.mjs"))
  );
  requireCondition(conflicts.length === 0, "AstronStudio execution worker is still active");
}

async function freshProbe() {
  const suffix = randomUUID().slice(0, 8);
  const path = join(OUTPUT, `preflight-${suffix}.json`);
  const configPath = join(OUTPUT, `preflight-${suffix}-run-config.json`);
  const result = spawnSync(process.execPath, [PROBE_SCRIPT, "--output", path, "--config-output", configPath], {
    cwd: ROOT, encoding: "utf8", timeout: 180_000,
  });
  requireCondition(result.status === 0, `fresh AStudio probe failed: ${result.stderr?.slice(0, 240) || result.status}`);
  const probe = await readJson(path);
  const frozen = await readJson(FROZEN_CONFIG);
  const current = probe.frozen_run_config;
  requireCondition(probe.status === "PASS" && probe.gui?.unlocked === true
    && probe.state_database?.integrity === "ok"
    && probe.state_database?.active_or_pending_session_count === 0
    && probe.implementation?.source_revision === SOURCE_REVISION,
  "AStudio probe is not a trusted idle/configured state");
  requireCondition(current?.harness?.client_version === frozen.harness.client_version
    && current?.control?.endpoint === frozen.control.endpoint
    && JSON.stringify(current?.tested_model) === JSON.stringify(frozen.tested_model),
  "AStudio client/model/endpoint drift");
  return { path, sha256: createHash("sha256").update(await readFile(path)).digest("hex"), endpoint: current.control.endpoint };
}

async function projectRows(taskIds, attempts) {
  const expected = new Map(taskIds.map((taskId) => [taskId, join(UNIT, "execution/tasks", taskId, "workspace")]));
  const prefix = join(UNIT, "execution/tasks") + "/";
  const rows = await withStateSnapshot(STATE_DATABASE, async (snapshot) => {
    const db = new DatabaseSync(snapshot, { readOnly: true });
    try {
      return db.prepare("SELECT project_id, workspace_root FROM projection_projects WHERE workspace_root LIKE ?").all(`${prefix}%`);
    } finally { db.close(); }
  });
  const matches = new Map();
  for (const [taskId, cwd] of expected) {
    const found = rows.filter((row) => row.workspace_root === cwd);
    if (found.length === 0 && !attempts.get(taskId).sentOnce) {
      matches.set(taskId, null);
      continue;
    }
    requireCondition(found.length === 1 && /^[A-Za-z0-9_-]{1,128}$/.test(found[0].project_id || ""), `project/cwd identity is not unique: ${taskId}`);
    matches.set(taskId, found[0]);
  }
  const projectIds = [...matches.values()].filter(Boolean).map((row) => row.project_id);
  requireCondition(new Set(projectIds).size === projectIds.length, "project IDs are not unique");
  return matches;
}

async function uiState(client) {
  return client.evaluate(`(() => {
    const visible = (e) => { const s = getComputedStyle(e), r = e.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
    const buttons = [...document.querySelectorAll('button')].filter(visible);
    return {
      dialogs: [...document.querySelectorAll('[role="dialog"], [aria-modal="true"]')].filter(visible).length,
      stop: buttons.filter((b) => /^(?:停止生成|Stop generating)$/u.test(b.getAttribute('aria-label') || '')).length,
      send: buttons.filter((b) => /^(?:发送消息|Send message)$/u.test(b.getAttribute('aria-label') || '')).length,
    };
  })()`);
}

async function projectView(client, projectId, cwd) {
  return client.evaluate(`(() => {
    const rows = [...document.querySelectorAll('[data-project-hover-anchor="${projectId}"]')];
    const persisted = JSON.parse(localStorage.getItem('${PERSISTED_KEY}') || '{}');
    return { count: rows.length, text: rows.length === 1 ? (rows[0].parentElement?.innerText || '').trim() : null,
      alias: persisted.projectNamesByCwd?.[${JSON.stringify(cwd)}] ?? null };
  })()`);
}

async function ensureSidebarInteractive(client, projectId) {
  const state = await client.evaluate(`(() => {
    const e = document.querySelector('[data-project-hover-anchor="${projectId}"]');
    const motion = e?.closest('[data-slot="sidebar-content-motion"]');
    return { found: !!e, inert: motion?.inert ?? null, ariaHidden: motion?.getAttribute('aria-hidden') ?? null };
  })()`);
  requireCondition(state.found, "project row is absent before sidebar check");
  if (state.inert || state.ariaHidden === "true") {
    const opened = await client.evaluate(`(() => {
      const buttons = [...document.querySelectorAll('button[aria-label="切换对话侧边栏"],button[aria-label="Toggle conversation sidebar"]')]
        .filter((b) => { const r=b.getBoundingClientRect(), hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
          return !b.closest('[inert]') && (hit===b || b.contains(hit)); });
      if (buttons.length !== 1) return { count: buttons.length, clicked: false };
      buttons[0].click(); return { count: 1, clicked: true };
    })()`);
    requireCondition(opened.clicked, "active AStudio sidebar toggle is not unique");
  }
  for (let n = 0; n < 50; n += 1) {
    const ready = await client.evaluate(`(() => {
      const e=document.querySelector('[data-project-hover-anchor="${projectId}"]');
      const motion=e?.closest('[data-slot="sidebar-content-motion"]');
      return !!e && !!motion && !motion.inert && motion.getAttribute('aria-hidden') !== 'true'
        && getComputedStyle(e).pointerEvents !== 'none';
    })()`);
    if (ready) return;
    await sleep(100);
  }
  throw new Error("AStudio sidebar remained non-interactive after exact toggle");
}

async function renameOne(client, taskId, row) {
  const before = await projectView(client, row.project_id, row.workspace_root);
  requireCondition(before.count === 1, `sidebar project row not unique: ${taskId}`);
  if (before.alias === taskId && before.text?.startsWith(taskId)) return { status: "already_named", before };
  requireCondition(before.alias === null && before.text === "workspace", `unexpected existing project title: ${taskId}`);
  // A preview card from the previously hovered project can cover this row.
  // Move the pointer to empty page space and require the exact project row to be hit.
  await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 800, y: 100, button: "none" });
  await sleep(500);
  await client.evaluate(`(() => {
    const e = document.querySelector('[data-project-hover-anchor="${row.project_id}"]');
    e.scrollIntoView({ block: 'center', inline: 'nearest' });
  })()`);
  await sleep(150);
  const target = await client.evaluate(`(() => {
    const e = document.querySelector('[data-project-hover-anchor="${row.project_id}"]');
    const r = e.getBoundingClientRect();
    const x = r.x + r.width/2, y = r.y + r.height/2;
    return { x, y, height: innerHeight,
      hit: document.elementFromPoint(x, y)?.closest('[data-project-hover-anchor]')?.getAttribute('data-project-hover-anchor') ?? null };
  })()`);
  requireCondition(target.y > 0 && target.y < target.height && target.hit === row.project_id,
    `project row not safely hit after scroll: ${taskId} ${JSON.stringify(target)}`);
  await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: target.x, y: target.y, button: "none" });
  await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x: target.x, y: target.y, button: "right", clickCount: 1 });
  await client.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: target.x, y: target.y, button: "right", clickCount: 1 });
  let menu = null;
  for (let n = 0; n < 25; n += 1) {
    menu = await client.evaluate(`(() => {
      const items = [...document.querySelectorAll('[role="menuitem"]')].filter((e) => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0; });
      const matches = items.filter((e) => /^(?:编辑名称|Edit name)$/u.test((e.innerText || '').trim()));
      if (matches.length !== 1 || matches[0].getAttribute('aria-disabled') === 'true') return { matches: matches.length };
      matches[0].click(); return { matches: 1, clicked: true };
    })()`);
    if (menu.clicked) break;
    await sleep(100);
  }
  if (!menu?.clicked) {
    const visibleMenus = await client.evaluate(`(() => [...document.querySelectorAll('[role="menuitem"]')]
      .filter((e) => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0; })
      .map((e) => (e.innerText || '').trim()))()`);
    throw new Error(`unique project rename menu item unavailable: ${taskId} ${row.project_id} ${JSON.stringify(target)} ${JSON.stringify(visibleMenus)}`);
  }
  let dialog = null;
  for (let n = 0; n < 25; n += 1) {
    dialog = await client.evaluate(`(() => {
      const ds = [...document.querySelectorAll('[role="dialog"]')].filter((e) => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0 && /(?:重命名项目|Rename project)/u.test(e.innerText || ''); });
      if (ds.length !== 1) return { dialogs: ds.length };
      const inputs = [...ds[0].querySelectorAll('input')];
      const saves = [...ds[0].querySelectorAll('button')].filter((b) => /^(?:保存|Save)$/u.test((b.innerText || '').trim()));
      if (inputs.length !== 1 || saves.length !== 1 || inputs[0].value !== 'workspace') return { dialogs: 1, inputs: inputs.length, saves: saves.length, value: inputs[0]?.value };
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      if (!setter) throw Error('HTMLInputElement setter missing');
      setter.call(inputs[0], ${JSON.stringify(taskId)});
      inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
      inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
      return { dialogs: 1, inputs: 1, saves: 1, typed: inputs[0].value === ${JSON.stringify(taskId)} };
    })()`);
    if (dialog.typed) break;
    await sleep(100);
  }
  requireCondition(dialog?.typed, `project rename dialog ambiguous: ${taskId}`);
  const saved = await client.evaluate(`(() => {
    const ds = [...document.querySelectorAll('[role="dialog"]')].filter((e) => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0 && /(?:重命名项目|Rename project)/u.test(e.innerText || ''); });
    if (ds.length !== 1) return { dialogs: ds.length };
    const input=ds[0].querySelector('input');
    const saves=[...ds[0].querySelectorAll('button')].filter((b) => /^(?:保存|Save)$/u.test((b.innerText || '').trim()) && !b.disabled);
    if (input?.value !== ${JSON.stringify(taskId)} || saves.length !== 1) return { dialogs: 1, value: input?.value, saves: saves.length };
    saves[0].click(); return { clicked: true };
  })()`);
  requireCondition(saved.clicked, `project rename save not accepted: ${taskId}`);
  for (let n = 0; n < 50; n += 1) {
    const after = await projectView(client, row.project_id, row.workspace_root);
    const activity = await uiState(client);
    if (after.count === 1 && after.alias === taskId && after.text?.startsWith(taskId) && activity.dialogs === 0) {
      return { status: "renamed", before, after };
    }
    await sleep(100);
  }
  throw new Error(`project alias did not persist or dialog remained open: ${taskId}`);
}

export async function main(argv = process.argv.slice(2)) {
  const options = parseOptions(argv);
  if (options.help) { console.log("Rename collected AstronStudio project aliases: --unit-root ABS --frozen-config ABS [--task-id ID ...]. Requires idle client and formal terminal evidence; never changes Workspace or Prompt."); return; }
  UNIT = ROOT = options.unit; FROZEN_CONFIG = options.config;
  OUTPUT = join(UNIT, ".general-e2e", "project-aliases");
  const frozen = await readJson(FROZEN_CONFIG);
  STATE_DATABASE = frozen.state_database?.path;
  requireCondition(isAbsolute(STATE_DATABASE || ""), "frozen native state path required");
  await mkdir(OUTPUT, { recursive: true });
  const manifest = await readJson(join(UNIT, "manifest.json"));
  const taskIds = options.taskIds.length ? options.taskIds : manifest.task_ids;
  requireCondition(Array.isArray(taskIds) && taskIds.length > 0 && new Set(taskIds).size === taskIds.length
    && taskIds.every(id => manifest.task_ids.includes(id) && /^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(id)), "task selection not in frozen manifest");
  const attempts = new Map();
  for (const taskId of taskIds) attempts.set(taskId, await formalAttempt(taskId));
  assertNoExecutionWorker();
  const preflight = await freshProbe();
  const rows = await projectRows(taskIds, attempts);
  assertNoExecutionWorker();
  const target = await discoverMainTarget(preflight.endpoint, 10_000);
  const client = await CdpClient.connect(target.webSocketDebuggerUrl, 10_000);
  try {
    await client.send("Page.bringToFront");
    const activity = await uiState(client);
    requireCondition(activity.dialogs === 0 && activity.stop === 0 && activity.send === 1, "AStudio UI is not idle or has a dialog");
    const firstProject = [...rows.values()].find(Boolean);
    if (firstProject) await ensureSidebarInteractive(client, firstProject.project_id);
    for (const taskId of taskIds) {
      const current = await uiState(client);
      requireCondition(current.dialogs === 0 && current.stop === 0 && current.send === 1, `AStudio activity changed before renaming ${taskId}`);
      const row = rows.get(taskId);
      const result = row ? await renameOne(client, taskId, row) : { status: "not_created_before_send" };
      const workspace = join(UNIT, "execution/tasks", taskId, "workspace");
      const receipt = { schema_version: 1, task_id: taskId, project_id: row?.project_id ?? null,
        workspace, alias: row ? taskId : null, status: result.status,
        preflight_path: preflight.path, preflight_sha256: preflight.sha256,
        verified_at: new Date().toISOString() };
      const file = join(OUTPUT, `${taskId}.json`);
      const existing = await readFile(file, "utf8").catch((error) => {
        if (error?.code === "ENOENT") return null;
        throw error;
      });
      if (existing !== null) {
        const saved = JSON.parse(existing);
        requireCondition(saved.task_id === taskId && saved.project_id === receipt.project_id
          && saved.workspace === workspace && saved.alias === receipt.alias,
        `existing project rename receipt conflicts: ${taskId}`);
      } else {
        const temp = `${file}.${randomUUID().slice(0, 8)}.tmp`;
        await writeFile(temp, `${JSON.stringify(receipt, null, 2)}\n`, { flag: "wx" });
        await rename(temp, file);
      }
      console.log(JSON.stringify({ task_id: taskId, status: result.status }));
    }
  } finally { client.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((error) => { console.error(error instanceof Error ? error.message : String(error)); process.exitCode = 2; });
