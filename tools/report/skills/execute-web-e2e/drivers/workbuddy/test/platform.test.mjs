import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, win32 } from "node:path";
import test from "node:test";

import {
  candidateWorkspaceProcessSnapshot,
  defaultWorkBuddyAppPath,
  defaultWorkBuddySessionDb,
  launchWorkBuddy,
  queryWorkBuddySessionSnapshot,
  resolveWorkBuddyAppPath,
  selectCandidateWorkspaceProcesses,
  terminateCandidateWorkspaceProcesses,
  workBuddyGuiSessionStatus,
  workBuddyProcessIdentity,
  workBuddySqliteBackendStatus,
} from "../platform.mjs";

test("Windows candidate process selection includes descendants and rejects prefix collisions", () => {
  const workspace = "D:\\debug-workspace\\web-e2e\\task-1\\workspace";
  const selected = selectCandidateWorkspaceProcesses([
    { ProcessId: 100, ParentProcessId: 1, Name: "node.exe", CommandLine: `node ${workspace}\\install-deps.cjs` },
    { ProcessId: 101, ParentProcessId: 100, Name: "node.exe", CommandLine: "node npm-cli.js install" },
    { ProcessId: 102, ParentProcessId: 1, Name: "node.exe", CommandLine: `node ${workspace}-other\\script.js` },
    { ProcessId: 103, ParentProcessId: 1, Name: "node.exe", CommandLine: `node D:/debug-workspace/web-e2e/task-1/workspace/site/build.js` },
  ], workspace);
  assert.deepEqual(selected.seed_pids, [100, 103]);
  assert.deepEqual(selected.workspace_seed_pids, [100, 103]);
  assert.deepEqual(selected.session_host_pids, []);
  assert.deepEqual(selected.root_pids, [100, 103]);
  assert.deepEqual(selected.targets.map((item) => item.pid), [100, 101, 103]);
  assert.equal(selected.targets.find((item) => item.pid === 101).matched_by_workspace, false);
});

test("Windows candidate process selection includes the unique WorkBuddy task session host", () => {
  const taskRoot = "D:\\debug-workspace\\web-e2e\\batch\\execution\\tasks\\task-a";
  const workspace = `${taskRoot}\\workspace`;
  const escapedTaskRoot = taskRoot.replaceAll("\\", "\\\\");
  const selected = selectCandidateWorkspaceProcesses([
    { ProcessId: 10, ParentProcessId: 1, Name: "WorkBuddy.exe", CommandLine: 'WorkBuddy.exe --remote-debugging-port=9229' },
    { ProcessId: 400, ParentProcessId: 10, Name: "WorkBuddy.exe", CommandLine: `WorkBuddy.exe --serve --session-id=session-a --config-json "{\\"trustedDirectories\\":[\\"${escapedTaskRoot}\\"]}"` },
    { ProcessId: 401, ParentProcessId: 400, Name: "node.exe", CommandLine: "node extension-host.js" },
    { ProcessId: 500, ParentProcessId: 10, Name: "WorkBuddy.exe", CommandLine: `WorkBuddy.exe --serve --session-id session-b --config-json ${escapedTaskRoot}-other` },
  ], workspace, { taskRoot, includeSessionHost: true });
  assert.deepEqual(selected.workspace_seed_pids, []);
  assert.deepEqual(selected.session_host_pids, [400]);
  assert.deepEqual(selected.root_pids, [400]);
  assert.deepEqual(selected.targets.map((item) => item.pid), [400, 401]);
  assert.equal(selected.targets[0].matched_by_session_host, true);
  assert.equal(selected.targets[1].matched_by_session_host, false);
});

test("Windows candidate process selection fails closed for duplicate WorkBuddy task session hosts", () => {
  const taskRoot = "D:\\batch\\execution\\tasks\\task-a";
  const processes = [600, 601].map((pid) => ({
    ProcessId: pid,
    ParentProcessId: 1,
    Name: "WorkBuddy.exe",
    CommandLine: `WorkBuddy.exe --serve --session-id session-${pid} --workspace "${taskRoot}"`,
  }));
  assert.throws(
    () => selectCandidateWorkspaceProcesses(processes, `${taskRoot}\\workspace`, { taskRoot, includeSessionHost: true }),
    /检测到 2 个.*会话宿主/u,
  );
});

test("Windows candidate process snapshot fails closed when process inventory is unavailable", async () => {
  await assert.rejects(
    candidateWorkspaceProcessSnapshot("D:\\task\\workspace", {
      platform: "win32",
      runCommand: async () => ({ code: 1, stdout: "", stderr: "access denied" }),
    }),
    /无法读取 Windows 候选进程表.*access denied/u,
  );
});

test("Windows candidate process cleanup terminates only exact workspace roots and verifies zero residue", async () => {
  const workspace = "D:\\task\\workspace";
  let inventoryReads = 0;
  const commands = [];
  const result = await terminateCandidateWorkspaceProcesses(workspace, {
    platform: "win32",
    excludedPids: [],
    waitMilliseconds: 0,
    runCommand: async (command, args) => {
      commands.push([command, args]);
      if (command === "powershell.exe") {
        inventoryReads += 1;
        return {
          code: 0,
          stdout: inventoryReads === 1
            ? JSON.stringify([
              { ProcessId: 200, ParentProcessId: 1, Name: "node.exe", CommandLine: `node ${workspace}\\install.cjs` },
              { ProcessId: 201, ParentProcessId: 200, Name: "node.exe", CommandLine: "node npm-cli.js" },
              { ProcessId: 300, ParentProcessId: 1, Name: "node.exe", CommandLine: "node unrelated.js" },
            ])
            : "null",
          stderr: "",
        };
      }
      assert.equal(command, "taskkill.exe");
      assert.deepEqual(args, ["/PID", "200", "/T", "/F"]);
      return { code: 0, stdout: "terminated", stderr: "" };
    },
  });
  assert.equal(result.success, true);
  assert.deepEqual(result.before.targets.map((item) => item.pid), [200, 201]);
  assert.deepEqual(result.after.targets, []);
  assert.equal(commands.filter(([command]) => command === "taskkill.exe").length, 1);
});

test("Windows candidate process cleanup catches a process that appears during the quiet window", async () => {
  const workspace = "D:\\task\\workspace";
  let inventoryReads = 0;
  let clock = 0;
  const killed = [];
  const result = await terminateCandidateWorkspaceProcesses(workspace, {
    platform: "win32",
    excludedPids: [],
    quietMilliseconds: 3,
    waitMilliseconds: 20,
    now: () => clock,
    sleep: async (milliseconds) => { clock += milliseconds; },
    runCommand: async (command, args) => {
      if (command === "powershell.exe") {
        inventoryReads += 1;
        return {
          code: 0,
          stdout: inventoryReads === 3
            ? JSON.stringify({ ProcessId: 700, ParentProcessId: 1, Name: "python.exe", CommandLine: `python ${workspace}\\server.py` })
            : "null",
          stderr: "",
        };
      }
      killed.push(Number(args[1]));
      return { code: 0, stdout: "terminated", stderr: "" };
    },
  });
  assert.equal(result.success, true);
  assert.equal(result.late_process_detected, true);
  assert.ok(result.quiet_observed_milliseconds >= 3);
  assert.deepEqual(killed, [700]);
  assert.equal(result.termination_attempts[0].detected_late, true);
});

test("Windows defaults keep app discovery dynamic and session data under the current user", () => {
  assert.equal(defaultWorkBuddyAppPath("win32"), "");
  assert.equal(
    defaultWorkBuddySessionDb("C:\\Users\\dynamic-user", win32, { platform: "win32" }),
    "C:\\Users\\dynamic-user\\.workbuddy\\workbuddy.db",
  );
});

test("Windows app discovery accepts the default per-user installation", async () => {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-platform-"));
  const localAppData = join(root, "Local");
  const installRoot = join(localAppData, "Programs", "WorkBuddy");
  const executable = join(installRoot, "WorkBuddy.exe");
  await mkdir(join(installRoot, "resources"), { recursive: true });
  await writeFile(executable, "fixture");
  await writeFile(join(installRoot, "resources", "app.asar"), "fixture");

  const resolved = await resolveWorkBuddyAppPath("", {
    platform: "win32",
    environment: { LOCALAPPDATA: localAppData },
    runCommand: async () => ({ code: 0, stdout: "null", stderr: "" }),
  });
  assert.equal(resolved, executable);
});

test("Windows process identity selects only the exact main executable", async () => {
  const appPath = "C:\\Users\\dynamic-user\\AppData\\Local\\Programs\\WorkBuddy\\WorkBuddy.exe";
  const processes = [
    {
      ProcessId: 1200,
      ParentProcessId: 800,
      ExecutablePath: appPath,
      CommandLine: `"${appPath}" --remote-debugging-port=9229`,
    },
    {
      ProcessId: 1201,
      ParentProcessId: 1200,
      ExecutablePath: appPath,
      CommandLine: `"${appPath}" --type=renderer`,
    },
    {
      ProcessId: 2200,
      ParentProcessId: 800,
      ExecutablePath: "C:\\Other\\WorkBuddy.exe",
      CommandLine: "C:\\Other\\WorkBuddy.exe",
    },
  ];
  const identity = await workBuddyProcessIdentity(appPath, {
    platform: "win32",
    runCommand: async () => ({ code: 0, stdout: JSON.stringify(processes), stderr: "" }),
  });
  assert.equal(identity.pid, 1200);
  assert.equal(identity.executable_path, appPath);
  assert.match(identity.command, /remote-debugging-port=9229/u);
});

test("Windows process identity fails closed for multiple matching main processes", async () => {
  const appPath = "C:\\Apps\\WorkBuddy\\WorkBuddy.exe";
  await assert.rejects(
    workBuddyProcessIdentity(appPath, {
      platform: "win32",
      runCommand: async () => ({
        code: 0,
        stdout: JSON.stringify([
          { ProcessId: 1200, ParentProcessId: 1, ExecutablePath: appPath, CommandLine: `"${appPath}"` },
          { ProcessId: 1300, ParentProcessId: 1, ExecutablePath: appPath, CommandLine: `"${appPath}"` },
        ]),
        stderr: "",
      }),
    }),
    /检测到 2 个.*主进程/u,
  );
});

test("Windows GUI probe fails closed when native desktop status is unavailable", async () => {
  const status = await workBuddyGuiSessionStatus({
    platform: "win32",
    runCommand: async () => ({ code: 1, stdout: "", stderr: "access denied" }),
  });
  assert.equal(status.unlocked, false);
  assert.equal(status.lock_source, "windows-gui-probe-failed");
  assert.equal(status.error, "access denied");
});

test("Windows launch forwards the exact CDP address and port", async () => {
  const observed = {};
  const result = await launchWorkBuddy("C:\\Apps\\WorkBuddy\\WorkBuddy.exe", "9229", {
    platform: "win32",
    launchDetached: async (command, args) => {
      observed.command = command;
      observed.args = args;
      return { code: 0, stdout: "", stderr: "", pid: 4321 };
    },
  });
  assert.equal(observed.command, "C:\\Apps\\WorkBuddy\\WorkBuddy.exe");
  assert.deepEqual(observed.args, [
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=9229",
  ]);
  assert.equal(result.pid, 4321);
});

test("Windows session query falls back to Python sqlite and normalizes the sessions schema", async () => {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-sqlite-"));
  const sessionDb = join(root, "workbuddy.db");
  await writeFile(sessionDb, "fixture");
  const snapshot = await queryWorkBuddySessionSnapshot(sessionDb, {
    platform: "win32",
    loadNodeSqlite: async () => null,
    runCommand: async (command, args) => {
      assert.equal(command, "py.exe");
      assert.equal(args[0], "-3");
      return {
        code: 0,
        stdout: JSON.stringify({
          schema: "sessions",
          sessions: [{
            conversationId: "session-1",
            cwd: "D:\\debug-workspace\\web-e2e\\task-1",
            status: "completed",
            createdAt: 10,
            updatedAt: 20,
            model: "custom-local:xopglm52",
            permissionMode: "bypassPermissions",
            thoughtLevel: "high",
          }],
        }),
        stderr: "",
      };
    },
  });
  assert.equal(snapshot.backend, "python-sqlite3:py-3");
  assert.equal(snapshot.schema, "sessions");
  assert.deepEqual(snapshot.sessions[0], {
    conversationId: "session-1",
    cwd: "D:\\debug-workspace\\web-e2e\\task-1",
    status: "completed",
    createdAt: 10,
    updatedAt: 20,
    model: "custom-local:xopglm52",
    permissionMode: "bypassPermissions",
    thoughtLevel: "high",
  });
});

test("Windows SQLite readiness recognizes the py -3 fallback", async () => {
  const status = await workBuddySqliteBackendStatus({
    platform: "win32",
    loadNodeSqlite: async () => null,
    runCommand: async (command) => ({ code: command === "py.exe" ? 0 : 1, stdout: "", stderr: "" }),
  });
  assert.deepEqual(status, {
    available: true,
    backend: "python-sqlite3:py-3",
    command: "py.exe",
    error: null,
  });
});
