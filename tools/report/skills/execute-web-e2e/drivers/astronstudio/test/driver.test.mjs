import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, realpath, rename, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, posix, win32 } from "node:path";
import test from "node:test";

import {
  assertStateMatches,
  atomicWriteJson,
  createInitialState,
  parseArgs,
  queryFinalResponse,
  querySessions,
  resolveConfig,
  resolveExecutionIdentity,
  sqliteBackendStatus,
  updateExecutionRecord,
} from "../lib.mjs";
import {
  astronGuiSessionStatus,
  astronProcessIdentity,
  defaultAstronAppPath,
  defaultAstronSessionDb,
  gracefulQuitAstron,
  launchAstron,
  resolveAstronAppPath,
  terminateAstronProcess,
} from "../platform.mjs";
import {
  addProjectByManualPath,
  connectAstudioBrowser,
  dismissOpenMenus,
  ensureModel,
  ensurePermissionMode,
  findConversationSidebarToggles,
  findNewTaskButtons,
  hasStableThreadIdentity,
  inspectWorkspace,
  isProbeReady,
  isReusableEmptyTaskRoute,
  restartAstudio,
  selectWorkspace,
} from "../driver.mjs";

test("Windows atomic JSON persistence retries transient rename locks", async () => {
  const root = await mkdtemp(join(tmpdir(), "astronstudio-atomic-write-"));
  const output = join(root, "queue_state.json");
  const delays = [];
  let renameCalls = 0;
  await atomicWriteJson(output, { phase: "RUNNING" }, {
    platform: "win32",
    sleep: async (milliseconds) => { delays.push(milliseconds); },
    rename: async (...args) => {
      renameCalls += 1;
      if (renameCalls < 3) {
        const error = new Error("transient Windows file lock");
        error.code = "EPERM";
        throw error;
      }
      return rename(...args);
    },
  });
  assert.equal(renameCalls, 3);
  assert.deepEqual(delays, [25, 50]);
  assert.deepEqual(JSON.parse(await readFile(output, "utf8")), { phase: "RUNNING" });
});

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "astronstudio-driver-"));
  const harnessRoot = join(root, "batch__astronstudio");
  const taskId = "task-001";
  const taskRoot = join(harnessRoot, "execution", "tasks", taskId);
  const appPath = join(root, "AStudio.app");
  await mkdir(join(taskRoot, "workspace"), { recursive: true });
  await mkdir(join(appPath, "Contents", "Resources"), { recursive: true });
  await writeFile(join(appPath, "Contents", "Resources", "app.asar"), "fixture");
  await writeFile(join(taskRoot, "PROMPT.md"), "build a site\n");
  await writeFile(join(harnessRoot, "manifest.json"), JSON.stringify({
    schema_version: "wildclawbench.web-e2e-batch/v3",
    batch_id: "batch-001",
    harness: { id: "astronstudio", display_name: "AstronStudio" },
    tasks: [{ task_id: taskId, execution_dir: `execution/tasks/${taskId}` }],
  }));
  return { root, harnessRoot, taskId, taskRoot, appPath };
}

async function initializeSqlite(databasePath, sql) {
  const sqliteModule = await import("node:sqlite").catch(() => null);
  if (typeof sqliteModule?.DatabaseSync === "function") {
    const database = new sqliteModule.DatabaseSync(databasePath);
    try {
      database.exec(sql);
    } finally {
      database.close();
    }
    return;
  }
  const sqliteCommand = process.platform === "win32" ? "sqlite3.exe" : "/usr/bin/sqlite3";
  execFileSync(sqliteCommand, [databasePath, sql]);
}

function locatorFor(elements) {
  return {
    count: async () => elements.length,
    nth: (index) => elements[index],
  };
}

test("parseArgs uses AstronStudio defaults without changing model or reasoning", () => {
  const parsed = parseArgs(["--probe"]);
  assert.equal(parsed.appPath, defaultAstronAppPath());
  assert.equal(parsed.endpoint, "http://127.0.0.1:9240");
  assert.equal(parsed.sessionDb, defaultAstronSessionDb());
  assert.equal(parsed.model, "");
  assert.equal(parsed.permissionMode, "current");
  assert.equal(parsed.detachAfterSubmit, false);
  assert.equal(parseArgs(["--probe", "--detach-after-submit"]).detachAfterSubmit, true);
  assert.equal(
    parseArgs(["--probe", "--session-db", "C:\\custom\\state.sqlite"]).sessionDb,
    "C:\\custom\\state.sqlite",
  );
});

test("Windows AstronStudio state database keeps the legacy path and falls back to the current-user data directory", () => {
  const home = "C:\\Users\\dynamic-user";
  const localAppData = "C:\\Users\\dynamic-user\\AppData\\Local";
  const legacy = "C:\\Users\\dynamic-user\\.acode\\acode\\userdata\\state.sqlite";
  const installedData = "C:\\Users\\dynamic-user\\AppData\\Local\\Programs\\AStudio Data\\userdata\\state.sqlite";
  const shared = {
    platform: "win32",
    environment: { LOCALAPPDATA: localAppData },
  };

  assert.equal(defaultAstronSessionDb(home, win32, {
    ...shared,
    existsPath: (candidate) => candidate === legacy,
  }), legacy);

  const checked = [];
  assert.equal(defaultAstronSessionDb(home, win32, {
    ...shared,
    existsPath: (candidate) => {
      checked.push(candidate);
      return candidate === installedData;
    },
  }), installedData);
  assert.deepEqual(checked, [legacy, installedData]);

  assert.equal(defaultAstronSessionDb(home, win32, {
    ...shared,
    existsPath: () => false,
  }), legacy);
});

test("Windows AstronStudio discovery prefers the registered install location", async () => {
  const root = await mkdtemp(join(tmpdir(), "astronstudio-windows-install-"));
  const installDir = join(root, "Programs", "AStudio");
  const executable = join(installDir, "AStudio.exe");
  await mkdir(join(installDir, "resources"), { recursive: true });
  await writeFile(executable, "fixture");
  await writeFile(join(installDir, "resources", "app.asar"), "fixture");
  const calls = [];
  const resolved = await resolveAstronAppPath("", {
    platform: "win32",
    pathApi: posix,
    environment: { LOCALAPPDATA: join(root, "fallback") },
    runCommand: async (command, args) => {
      calls.push([command, args]);
      if (args[1] === "HKCU\\Software\\AStudio") {
        return { code: 0, stdout: `    InstallLocation    REG_SZ    ${installDir}\r\n`, stderr: "" };
      }
      return { code: 1, stdout: "", stderr: "missing" };
    },
  });
  assert.equal(resolved, await realpath(executable));
  assert.equal(calls.length, 3);
  assert.equal(defaultAstronAppPath("win32"), "");
});

test("Windows AstronStudio process identity matches the exact executable and ignores renderers", async () => {
  const appPath = "C:\\Users\\tester\\AppData\\Local\\Programs\\AStudio\\AStudio.exe";
  const identity = await astronProcessIdentity(appPath, {
    platform: "win32",
    runCommand: async (command) => {
      assert.equal(command, "powershell.exe");
      return {
        code: 0,
        stderr: "",
        stdout: JSON.stringify([
          { ProcessId: 101, ParentProcessId: 10, ExecutablePath: appPath, CommandLine: `"${appPath}" --remote-debugging-port=9240` },
          { ProcessId: 102, ParentProcessId: 101, ExecutablePath: appPath, CommandLine: `"${appPath}" --type=renderer` },
          { ProcessId: 103, ParentProcessId: 101, ExecutablePath: appPath, CommandLine: `${appPath} --max-old-space-size=4033 server.mjs` },
          { ProcessId: 104, ParentProcessId: 101, ExecutablePath: appPath, CommandLine: `${appPath} -e "setInterval(() => {}, 250)"` },
          { ProcessId: 201, ParentProcessId: 10, ExecutablePath: "D:\\Other\\AStudio.exe", CommandLine: "D:\\Other\\AStudio.exe" },
        ]),
      };
    },
  });
  assert.equal(identity.pid, 101);
  assert.equal(identity.executable_path, appPath);
  assert.equal(identity.platform, "win32");
});

test("Windows AstronStudio process identity fails closed when the main PID is ambiguous", async () => {
  const appPath = "C:\\Apps\\AStudio\\AStudio.exe";
  await assert.rejects(
    astronProcessIdentity(appPath, {
      platform: "win32",
      runCommand: async () => ({
        code: 0,
        stderr: "",
        stdout: JSON.stringify([
          { ProcessId: 101, ParentProcessId: 10, ExecutablePath: appPath, CommandLine: `"${appPath}"` },
          { ProcessId: 102, ParentProcessId: 20, ExecutablePath: appPath, CommandLine: `"${appPath}" --remote-debugging-port=9240` },
        ]),
      }),
    }),
    /匹配的 AstronStudio 主进程，拒绝选择不唯一 PID/,
  );
});

test("Windows GUI probing fails closed when PowerShell cannot prove an unlocked desktop", async () => {
  const status = await astronGuiSessionStatus({
    platform: "win32",
    runCommand: async () => ({ code: 1, stdout: "", stderr: "access denied" }),
  });
  assert.equal(status.unlocked, false);
  assert.equal(status.lock_source, "windows-gui-probe-failed");
  assert.match(status.error, /access denied/);
});

test("Windows launch and exact-PID termination use native process APIs", async () => {
  const launches = [];
  const launch = await launchAstron("C:\\Apps\\AStudio\\AStudio.exe", "9240", {
    platform: "win32",
    launchDetached: async (command, args) => {
      launches.push([command, args]);
      return { code: 0, stdout: "", stderr: "", pid: 321 };
    },
  });
  assert.equal(launch.pid, 321);
  assert.deepEqual(launches, [[
    "C:\\Apps\\AStudio\\AStudio.exe",
    ["--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9240"],
  ]]);

  const commands = [];
  await gracefulQuitAstron({ pid: 321 }, {
    platform: "win32",
    runCommand: async (command, args) => {
      commands.push([command, args]);
      return { code: 0, stdout: "", stderr: "" };
    },
  });
  await terminateAstronProcess({ pid: 321 }, {
    platform: "win32",
    runCommand: async (command, args) => {
      commands.push([command, args]);
      return { code: 0, stdout: "", stderr: "" };
    },
  });
  assert.equal(commands[0][0], "powershell.exe");
  assert.equal(commands[0][1].at(-1), "321");
  assert.deepEqual(commands[1], ["taskkill.exe", ["/PID", "321", "/T", "/F"]]);
});

test("SQLite backend prefers the Node runtime on Windows without requiring sqlite3.exe", async () => {
  const status = await sqliteBackendStatus({
    platform: "win32",
    loadNodeSqlite: async () => ({ DatabaseSync: class {} }),
    runCommand: async () => { throw new Error("CLI should not be called"); },
  });
  assert.deepEqual(status, { available: true, backend: "node:sqlite", command: null, error: null });
});

test("detached dispatch requires a route-confirmed AstronStudio thread turn and cwd", () => {
  const workspace = "/tmp/task-1";
  const state = {
    session: {
      conversation_id: "thread-1",
      dom_conversation_id: "thread-1",
      turn_id: "turn-1",
      cwd: workspace,
    },
  };
  assert.equal(hasStableThreadIdentity(state, workspace), true);
  assert.equal(hasStableThreadIdentity({ session: { ...state.session, turn_id: null } }, workspace), false);
  assert.equal(hasStableThreadIdentity({ session: { ...state.session, dom_conversation_id: "thread-other" } }, workspace), false);
  assert.equal(hasStableThreadIdentity({ session: { ...state.session, cwd: "/tmp/task-other" } }, workspace), false);
});

test("AstronStudio CDP connection retries transient failures with a bounded timeout", async () => {
  const calls = [];
  const browser = { contexts: () => [] };
  const result = await connectAstudioBrowser({}, "http://127.0.0.1:9240", 30000, {
    attempts: 3,
    retryDelayMilliseconds: 0,
    sleep: async () => {},
    connect: async (endpoint, options) => {
      calls.push({ endpoint, options });
      if (calls.length < 3) throw new Error(`transient-${calls.length}`);
      return browser;
    },
  });
  assert.equal(result, browser);
  assert.deepEqual(calls, [
    { endpoint: "http://127.0.0.1:9240", options: { timeout: 10000 } },
    { endpoint: "http://127.0.0.1:9240", options: { timeout: 10000 } },
    { endpoint: "http://127.0.0.1:9240", options: { timeout: 10000 } },
  ]);
});

test("AstronStudio identity and execution record keep the Harness boundary", async () => {
  const item = await fixture();
  const config = await resolveConfig(parseArgs([
    "--workspace", item.taskRoot,
    "--app-path", item.appPath,
    "--model", "GLM-5.2",
  ]), { platform: "darwin" });
  const info = await resolveExecutionIdentity(config);
  assert.equal(info.identity.harness.id, "astronstudio");
  const state = createInitialState(config, info.identity, { sha256: "initial", entries: [] });
  assert.equal(state.driver.id, "astronstudio");
  assertStateMatches(state, config, info.identity);
  await updateExecutionRecord(config, info, {
    clientVersion: "3.0.0-alpha.19",
    modelSelection: { mode: "explicit", requested_model: "GLM-5.2", actual_model: "GLM-5.2" },
    execution: { status: "pending" },
  });
  const record = JSON.parse(await readFile(config.executionRecord, "utf8"));
  assert.equal(record.harness.id, "astronstudio");
  assert.equal(record.harness.version, "3.0.0-alpha.19");
  assert.equal(record.model.id, "GLM-5.2");
});

test("AstronStudio state cannot be resumed by another Driver profile", async () => {
  const item = await fixture();
  const config = await resolveConfig(
    parseArgs(["--workspace", item.taskRoot, "--app-path", item.appPath]),
    { platform: "darwin" },
  );
  const info = await resolveExecutionIdentity(config);
  const state = createInitialState(config, info.identity, { sha256: "initial", entries: [] });
  state.driver.id = "workbuddy";
  assert.throws(() => assertStateMatches(state, config, info.identity), /driver_id/);
});

test("model and full-access settings are read without opening their menus", async () => {
  let clicked = 0;
  const modelTrigger = {
    isVisible: async () => true,
    innerText: async () => "GLM-5.2\nHigh",
    click: async () => { clicked += 1; },
  };
  const permissionTrigger = {
    isVisible: async () => true,
    isEnabled: async () => true,
    innerText: async () => "完全访问",
    click: async () => { clicked += 1; },
  };
  const page = {
    locator: (selector) => {
      if (selector === "button.runtime-permission-trigger") return locatorFor([permissionTrigger]);
      if (selector.includes("切换模型和推理设置")) return locatorFor([modelTrigger]);
      throw new Error(`unexpected locator: ${selector}`);
    },
  };
  assert.deepEqual(await ensureModel(page, "", 100), {
    mode: "current",
    requested_model: null,
    actual_model: "GLM-5.2",
    reasoning_display: "High",
    method: "visible-current-value",
  });
  assert.deepEqual(await ensurePermissionMode(page, "current", 100), {
    requested_mode: "current",
    confirmed_mode: "full-access",
    changed: false,
    method: "visible-current-value",
  });
  assert.equal(clicked, 0);
});

test("only a recognized open menu is dismissed before creating a task", async () => {
  let visible = true;
  let escapeCount = 0;
  const menu = { isVisible: async () => visible };
  const page = {
    getByRole: (role) => {
      assert.equal(role, "menu");
      return locatorFor(visible ? [menu] : []);
    },
    keyboard: {
      press: async (key) => {
        assert.equal(key, "Escape");
        escapeCount += 1;
        visible = false;
      },
    },
  };
  assert.deepEqual(await dismissOpenMenus(page, 100), { closed: true, count: 1 });
  assert.equal(escapeCount, 1);
});

test("a duplicated new-thread test id falls back to the unique exact-text button", async () => {
  const duplicated = [
    { isVisible: async () => true },
    { isVisible: async () => true },
    { isVisible: async () => true },
  ];
  const exactButton = {
    isVisible: async () => true,
    innerText: async () => "新建任务",
  };
  const page = {
    getByTestId: (testId) => {
      assert.equal(testId, "new-thread-button");
      return locatorFor(duplicated);
    },
    locator: (selector) => {
      assert.equal(selector, "button");
      return { filter: () => locatorFor([exactButton]) };
    },
    getByRole: () => {
      throw new Error("unique exact text should win before the role fallback");
    },
  };

  assert.deepEqual(await findNewTaskButtons(page), [exactButton]);
});

test("covered new-thread nodes are ignored in favor of the pointer-reachable button", async () => {
  const covered = {
    isVisible: async () => true,
    evaluate: async () => false,
  };
  const reachable = {
    isVisible: async () => true,
    evaluate: async () => true,
  };
  const page = {
    getByTestId: (testId) => {
      assert.equal(testId, "new-thread-button");
      return locatorFor([covered, reachable]);
    },
    locator: () => ({ filter: () => locatorFor([]) }),
    getByRole: () => locatorFor([]),
  };

  assert.deepEqual(await findNewTaskButtons(page), [reachable]);
});

test("sidebar toggle discovery survives Electron titlebar hit-test overlays", async () => {
  const coveredDuplicate = {
    isVisible: async () => true,
    getAttribute: async (name) => (name === "aria-label" ? "切换对话侧边栏" : null),
    evaluate: async () => false,
  };
  const reachableToggle = {
    isVisible: async () => true,
    getAttribute: async (name) => (name === "aria-label" ? "切换对话侧边栏" : null),
    evaluate: async () => true,
  };
  const page = {
    locator: (selector) => {
      assert.equal(selector, "button[aria-label]");
      return locatorFor([coveredDuplicate, reachableToggle]);
    },
  };

  assert.deepEqual(await findConversationSidebarToggles(page), [reachableToggle]);
});

test("workspace readback accepts the project-bound trigger after adding a project", async () => {
  const workspace = "/tmp/batch/execution/tasks/task-001";
  const projectTrigger = {
    isVisible: async () => true,
    getAttribute: async (name) => (name === "title" ? workspace : null),
    innerText: async () => "task-001",
  };
  const page = {
    getByTestId: (testId) => locatorFor(testId === "project-picker-trigger" ? [projectTrigger] : []),
  };
  assert.deepEqual(await inspectWorkspace(page), {
    available: true,
    reason: null,
    path: workspace,
    label: "task-001",
    source_test_id: "project-picker-trigger",
  });
});

test("an unchanged AstronStudio route is reusable only when it is an empty task draft", async () => {
  const heading = { isVisible: async () => true };
  const editor = {
    isVisible: async () => true,
    innerText: async () => "\n",
  };
  const emptyPage = {
    getByTestId: (testId) => locatorFor(
      testId === "empty-landing-heading" ? [heading] : testId === "composer-editor" ? [editor] : [],
    ),
  };
  assert.equal(await isReusableEmptyTaskRoute(emptyPage), true);

  editor.innerText = async () => "unsent draft";
  assert.equal(await isReusableEmptyTaskRoute(emptyPage), false);

  const historyPage = {
    getByTestId: (testId) => locatorFor(testId === "composer-editor" ? [editor] : []),
  };
  assert.equal(await isReusableEmptyTaskRoute(historyPage), false);
});

test("manual project entry uses Windows-compatible ARIA selectors and bypasses covered buttons", async () => {
  const workspace = "C:\\batch\\execution\\tasks\\task-001\\workspace";
  const calls = [];
  let pathEntryOpen = false;
  const projectTab = {
    isVisible: async () => true,
    innerText: async () => "项目",
    click: async () => calls.push("project-tab-click"),
  };
  const addProject = {
    isVisible: async () => true,
    isEnabled: async () => true,
    evaluate: async () => calls.push("add-project-dom-click"),
  };
  const typePath = {
    isVisible: async () => true,
    innerText: async () => "输入路径",
    evaluate: async () => {
      calls.push("type-path-dom-click");
      pathEntryOpen = true;
    },
  };
  const pathInput = {
    isVisible: async () => true,
    fill: async () => assert.fail("project path must not use keyboard-backed fill"),
    press: async () => assert.fail("project path must not use Enter submission"),
    evaluate: async (_callback, value) => calls.push(["set-native-value", value]),
  };
  const submitProject = {
    isVisible: async () => true,
    isEnabled: async () => true,
    evaluate: async () => calls.push("submit-project-dom-click"),
  };
  const page = {
    locator: (selector) => {
      if (selector === "button") {
        return {
          filter: ({ hasText }) => locatorFor(
            hasText.test("项目") ? [projectTab] : hasText.test("输入路径") ? [typePath] : [],
          ),
        };
      }
      if (selector === 'button[aria-label="添加项目"], button[aria-label="Add project"]') {
        return locatorFor([pathEntryOpen ? submitProject : addProject]);
      }
      if (selector === 'input[aria-label="项目路径"], input[aria-label="Project path"]') {
        return locatorFor([pathInput]);
      }
      throw new Error(`unexpected selector: ${selector}`);
    },
  };

  assert.deepEqual(await addProjectByManualPath(page, workspace, 100), {
    method: "sidebar-manual-path",
  });
  assert.deepEqual(calls, [
    "project-tab-click",
    "add-project-dom-click",
    "type-path-dom-click",
    ["set-native-value", workspace],
    "submit-project-dom-click",
  ]);
});

test("workspace selection adds an absolute path when the empty task has no picker trigger", async () => {
  const workspace = "C:\\batch\\execution\\tasks\\task-001\\workspace";
  let selected = false;
  let pathEntryOpen = false;
  const projectTab = {
    isVisible: async () => true,
    innerText: async () => "项目",
    click: async () => {},
  };
  const addProject = {
    isVisible: async () => true,
    isEnabled: async () => true,
    evaluate: async () => {},
  };
  const typePath = {
    isVisible: async () => true,
    innerText: async () => "输入路径",
    evaluate: async () => { pathEntryOpen = true; },
  };
  const pathInput = {
    isVisible: async () => true,
    fill: async () => assert.fail("project path must not use keyboard-backed fill"),
    press: async () => assert.fail("project path must not use Enter submission"),
    evaluate: async (_callback, value) => assert.equal(value, workspace),
  };
  const submitProject = {
    isVisible: async () => true,
    isEnabled: async () => true,
    evaluate: async () => { selected = true; },
  };
  const selectedTrigger = {
    isVisible: async () => true,
    getAttribute: async (name) => (name === "title" ? workspace : null),
    innerText: async () => "task-001",
  };
  const page = {
    getByTestId: (testId) => locatorFor(
      selected && testId === "project-picker-trigger" ? [selectedTrigger] : [],
    ),
    locator: (selector) => {
      if (selector === "button") {
        return {
          filter: ({ hasText }) => locatorFor(
            hasText.test("项目") ? [projectTab] : hasText.test("输入路径") ? [typePath] : [],
          ),
        };
      }
      if (selector === 'button[aria-label="添加项目"], button[aria-label="Add project"]') {
        return locatorFor([pathEntryOpen ? submitProject : addProject]);
      }
      if (selector === 'input[aria-label="项目路径"], input[aria-label="Project path"]') {
        return locatorFor([pathInput]);
      }
      throw new Error(`unexpected selector: ${selector}`);
    },
  };

  assert.deepEqual(await selectWorkspace(page, workspace, 100), {
    backend: { method: "sidebar-manual-path" },
    page: {
      requested_path: workspace,
      confirmed_path: workspace,
      confirmed_label: "task-001",
      method: "workspace-trigger-title-readback",
    },
  });
});

test("probe stays ready on a history page where the workspace picker is deferred", () => {
  assert.equal(isProbeReady({
    endpoint_ready: true,
    state_database_readable: true,
    sqlite3: true,
    gui_session_unlocked: true,
    new_task_available: true,
    workspace_picker_available: false,
    permission_setting_available: true,
    model_setting_available: true,
    composer_available: true,
  }), true);
});

test("SQLite projection states normalize completion, running and pending interaction", async () => {
  const root = await mkdtemp(join(tmpdir(), "astronstudio-state-"));
  const db = join(root, "state.sqlite");
  const sql = `
    CREATE TABLE projection_projects(project_id TEXT PRIMARY KEY, workspace_root TEXT, deleted_at TEXT);
    CREATE TABLE projection_threads(thread_id TEXT PRIMARY KEY, project_id TEXT, latest_turn_id TEXT, model_selection_json TEXT, deleted_at TEXT);
    CREATE TABLE projection_thread_sessions(thread_id TEXT PRIMARY KEY, active_turn_id TEXT, status TEXT, last_error TEXT, updated_at TEXT);
    CREATE TABLE projection_turns(row_id INTEGER PRIMARY KEY, thread_id TEXT, turn_id TEXT, requested_at TEXT, started_at TEXT, completed_at TEXT, state TEXT, termination_origin TEXT, checkpoint_turn_count INTEGER);
    CREATE TABLE projection_pending_interactions(thread_id TEXT, status TEXT);
    CREATE TABLE provider_runtime_open_turns(thread_id TEXT);
    CREATE TABLE projection_thread_messages(message_id TEXT, thread_id TEXT, turn_id TEXT, role TEXT, text TEXT, is_streaming INTEGER, created_at TEXT, updated_at TEXT, sequence INTEGER);
    INSERT INTO projection_projects VALUES ('p1','/tmp/one',NULL),('p2','/tmp/two',NULL),('p3','/tmp/three',NULL);
    INSERT INTO projection_threads VALUES ('t1','p1','turn1','{}',NULL),('t2','p2','turn2','{}',NULL),('t3','p3','turn3','{}',NULL);
    INSERT INTO projection_thread_sessions VALUES
      ('t1',NULL,'ready',NULL,'2026-09-08T01:00:00.000Z'),
      ('t2','turn2','running',NULL,'2026-09-08T02:00:00.000Z'),
      ('t3',NULL,'ready',NULL,'2026-09-08T03:00:00.000Z');
    INSERT INTO projection_turns VALUES
      (1,'t1','turn1','2026-09-08T01:00:00.000Z','2026-09-08T01:00:01.000Z','2026-09-08T01:00:02.000Z','completed','natural',NULL),
      (2,'t2','turn2','2026-09-08T02:00:00.000Z','2026-09-08T02:00:01.000Z',NULL,'running',NULL,NULL),
      (3,'t3','turn3','2026-09-08T03:00:00.000Z','2026-09-08T03:00:01.000Z',NULL,'running',NULL,NULL);
    INSERT INTO projection_pending_interactions VALUES ('t3','pending');
    INSERT INTO provider_runtime_open_turns VALUES ('t2');
    INSERT INTO projection_thread_messages VALUES
      ('m1','t1','turn1','assistant','working',0,'2026-09-08T01:00:01.000Z','2026-09-08T01:00:01.000Z',1),
      ('m2','t1','turn1','assistant','final response',0,'2026-09-08T01:00:02.000Z','2026-09-08T01:00:02.000Z',2),
      ('m3','t1','turn1','assistant','streaming draft',1,'2026-09-08T01:00:03.000Z','2026-09-08T01:00:03.000Z',3);
  `;
  await initializeSqlite(db, sql);
  const sessions = await querySessions(db);
  const statuses = Object.fromEntries(sessions.map((session) => [session.conversationId, session.status]));
  assert.deepEqual(statuses, { t3: "needs_attention", t2: "running", t1: "completed" });
  assert.equal(await queryFinalResponse(db, "t1", "turn1"), "final response");
});

test("restart protection refuses to close AstronStudio while a task is active", async () => {
  let mutationCalls = 0;
  await assert.rejects(
    restartAstudio(
      { endpoint: "http://127.0.0.1:9240", appPath: "/Applications/AStudio.app", sessionDb: "/tmp/state.sqlite" },
      {
        processIdentity: async () => ({ pid: 123 }),
        querySessions: async () => [{ status: "running" }],
        run: async () => { mutationCalls += 1; return { code: 0, stdout: "", stderr: "" }; },
      },
    ),
    /仍有 1 个活动或待处理任务，拒绝重启/,
  );
  assert.equal(mutationCalls, 0);
});

test("restart recovery allows only the single tracked active AstronStudio session", async () => {
  const mutations = [];
  const result = await restartAstudio(
    { endpoint: "http://127.0.0.1:9240", appPath: "/Applications/AStudio.app", sessionDb: "/tmp/state.sqlite" },
    {
      processIdentity: async () => ({ pid: 123 }),
      querySessions: async () => [{
        status: "running",
        conversationId: "thread-1",
        activeTurnId: "turn-1",
        turnId: "turn-1",
        cwd: "/tmp/task-1",
      }],
      gracefulQuit: async () => { mutations.push("graceful-quit"); return { code: 0, stdout: "", stderr: "" }; },
      launchApp: async () => { mutations.push("launch-app"); return { code: 0, stdout: "", stderr: "" }; },
      waitForEndpoint: async () => {},
      waitForStopped: async () => {},
    },
    { threadId: "thread-1", turnId: "turn-1", cwd: "/tmp/task-1" },
  );
  assert.deepEqual(mutations, ["graceful-quit", "launch-app"]);
  assert.deepEqual(result.restart_safety, {
    mode: "tracked-recovery-session",
    tracked_thread_id: "thread-1",
    tracked_turn_id: "turn-1",
    tracked_cwd: "/tmp/task-1",
    active_session_count: 1,
    tracked_session_matched: true,
    shutdown: { method: "application-quit", pid: 123 },
  });
});

test("restart recovery refuses an active AstronStudio session outside the tracked identity", async () => {
  let mutationCalls = 0;
  await assert.rejects(
    restartAstudio(
      { endpoint: "http://127.0.0.1:9240", appPath: "/Applications/AStudio.app", sessionDb: "/tmp/state.sqlite" },
      {
        processIdentity: async () => ({ pid: 123 }),
        querySessions: async () => [{
          status: "running",
          conversationId: "thread-other",
          activeTurnId: "turn-other",
          turnId: "turn-other",
          cwd: "/tmp/task-other",
        }],
        run: async () => { mutationCalls += 1; return { code: 0, stdout: "", stderr: "" }; },
      },
      { threadId: "thread-1", turnId: "turn-1", cwd: "/tmp/task-1" },
    ),
    /仍有 1 个活动或待处理任务，拒绝重启/,
  );
  assert.equal(mutationCalls, 0);
});

test("restart safely falls back to SIGTERM only for the same verified AstronStudio PID", async () => {
  const mutations = [];
  let stoppedChecks = 0;
  const result = await restartAstudio(
    { endpoint: "http://127.0.0.1:9240", appPath: "/Applications/AStudio.app", sessionDb: "/tmp/state.sqlite" },
    {
      processIdentity: async () => ({ pid: 123 }),
      querySessions: async () => [],
      gracefulQuit: async (processInfo) => {
        mutations.push(["graceful-quit", processInfo.pid]);
        return { code: 0, stdout: "", stderr: "" };
      },
      terminateProcess: async (processInfo) => {
        mutations.push(["terminate", processInfo.pid]);
        return { code: 0, stdout: "", stderr: "" };
      },
      launchApp: async () => {
        mutations.push(["launch-app"]);
        return { code: 0, stdout: "", stderr: "" };
      },
      waitForEndpoint: async () => {},
      waitForStopped: async () => {
        stoppedChecks += 1;
        if (stoppedChecks === 1) throw new Error("graceful quit timeout");
      },
    },
  );
  assert.deepEqual(mutations, [
    ["graceful-quit", 123],
    ["terminate", 123],
    ["launch-app"],
  ]);
  assert.equal(result.restart_safety.shutdown.method, "sigterm-after-quit-timeout");
  assert.equal(result.restart_safety.shutdown.pid, 123);
});

test("restart refuses SIGTERM when the AstronStudio PID changes after quit timeout", async () => {
  const mutations = [];
  let processChecks = 0;
  await assert.rejects(
    restartAstudio(
      { endpoint: "http://127.0.0.1:9240", appPath: "/Applications/AStudio.app", sessionDb: "/tmp/state.sqlite" },
      {
        processIdentity: async () => ({ pid: processChecks++ === 0 ? 123 : 456 }),
        querySessions: async () => [],
        gracefulQuit: async () => {
          mutations.push("graceful-quit");
          return { code: 0, stdout: "", stderr: "" };
        },
        waitForStopped: async () => { throw new Error("graceful quit timeout"); },
      },
    ),
    /进程身份已变化，拒绝发送 SIGTERM：原 PID 123，当前 PID 456/,
  );
  assert.deepEqual(mutations, ["graceful-quit"]);
});

test("restart retries a failed open call and records bounded evidence", async () => {
  let openCalls = 0;
  const result = await restartAstudio(
    { endpoint: "http://127.0.0.1:9240", appPath: "/Applications/AStudio.app", sessionDb: "/tmp/state.sqlite" },
    {
      processIdentity: async () => null,
      endpointReady: async () => false,
      querySessions: async () => [],
      waitForEndpoint: async () => {},
      waitForStopped: async () => {},
      sleep: async () => {},
      launchAttempts: 3,
      retryDelayMilliseconds: 1,
      launchApp: async () => {
        openCalls += 1;
        return openCalls === 1
          ? { code: 1, stdout: "", stderr: "open failed" }
          : { code: 0, stdout: "", stderr: "" };
      },
    },
  );
  assert.equal(openCalls, 2);
  assert.equal(result.recovered_after_retry, true);
  assert.equal(result.attempts[0].endpoint_ready, false);
  assert.equal(result.attempts[1].endpoint_ready, true);
});

test("restart force-terminates the same verified retry process after graceful cleanup times out", async () => {
  const mutations = [];
  let openCalls = 0;
  let processChecks = 0;
  let stoppedChecks = 0;
  const result = await restartAstudio(
    { endpoint: "http://127.0.0.1:9240", appPath: "C:\\Program Files\\AStudio\\AStudio.exe", sessionDb: "C:\\AStudio Data\\state.sqlite" },
    {
      processIdentity: async () => {
        processChecks += 1;
        if (processChecks === 1) return null;
        return { pid: 321 };
      },
      endpointReady: async () => false,
      querySessions: async () => [],
      waitForEndpoint: async () => {
        if (openCalls === 1) throw new Error("debug endpoint timeout");
      },
      waitForStopped: async () => {
        stoppedChecks += 1;
        if (stoppedChecks === 1) throw new Error("graceful cleanup timeout");
      },
      gracefulQuit: async (processInfo) => {
        mutations.push(["graceful-quit", processInfo.pid]);
        return { code: 0, stdout: "", stderr: "" };
      },
      terminateProcess: async (processInfo) => {
        mutations.push(["terminate", processInfo.pid]);
        return { code: 0, stdout: "", stderr: "" };
      },
      sleep: async () => {},
      launchAttempts: 3,
      retryDelayMilliseconds: 1,
      launchApp: async () => {
        openCalls += 1;
        mutations.push(["launch-app", openCalls]);
        return { code: 0, stdout: "", stderr: "", pid: 321 };
      },
    },
  );
  assert.deepEqual(mutations, [
    ["launch-app", 1],
    ["graceful-quit", 321],
    ["terminate", 321],
    ["launch-app", 2],
  ]);
  assert.equal(result.recovered_after_retry, true);
  assert.deepEqual(result.attempts[0].retry_cleanup, {
    method: "sigterm-after-quit-timeout",
    pid: 321,
    graceful_error: "graceful cleanup timeout",
  });
});

test("restart refuses to force-terminate a different process during retry cleanup", async () => {
  let processChecks = 0;
  let terminateCalls = 0;
  await assert.rejects(
    restartAstudio(
      { endpoint: "http://127.0.0.1:9240", appPath: "C:\\Program Files\\AStudio\\AStudio.exe", sessionDb: "C:\\AStudio Data\\state.sqlite" },
      {
        processIdentity: async () => {
          processChecks += 1;
          if (processChecks === 1) return null;
          if (processChecks === 2) return { pid: 321 };
          return { pid: 456 };
        },
        endpointReady: async () => false,
        querySessions: async () => [],
        waitForEndpoint: async () => { throw new Error("debug endpoint timeout"); },
        waitForStopped: async () => { throw new Error("graceful cleanup timeout"); },
        gracefulQuit: async () => ({ code: 0, stdout: "", stderr: "" }),
        terminateProcess: async () => {
          terminateCalls += 1;
          return { code: 0, stdout: "", stderr: "" };
        },
        sleep: async () => {},
        launchAttempts: 2,
        retryDelayMilliseconds: 1,
        launchApp: async () => ({ code: 0, stdout: "", stderr: "", pid: 321 }),
      },
    ),
    /启动重试清理超时后进程身份已变化，拒绝强制终止：原 PID 321，当前 PID 456/,
  );
  assert.equal(terminateCalls, 0);
});
