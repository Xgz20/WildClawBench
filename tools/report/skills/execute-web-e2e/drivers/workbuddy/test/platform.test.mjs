import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, win32 } from "node:path";
import test from "node:test";

import {
  defaultWorkBuddyAppPath,
  defaultWorkBuddySessionDb,
  launchWorkBuddy,
  queryWorkBuddySessionSnapshot,
  resolveWorkBuddyAppPath,
  workBuddyGuiSessionStatus,
  workBuddyProcessIdentity,
  workBuddySqliteBackendStatus,
} from "../platform.mjs";

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
