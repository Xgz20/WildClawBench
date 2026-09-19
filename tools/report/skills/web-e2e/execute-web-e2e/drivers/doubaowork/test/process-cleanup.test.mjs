import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  cleanupDoubaoCandidateProcesses,
  parseMacCwdRecords,
  parseMacProcessTable,
  readMacProcessInventory,
  selectDoubaoCandidateProcesses,
  snapshotDoubaoCandidateProcesses,
} from "../process-cleanup.mjs";

function fixtureProcess(pid, parentPid, cwd, {
  start = "Sat Sep 19 19:41:11 2026",
  executable = "/usr/bin/python3",
  processGroupId = pid,
  commandName = "python3",
} = {}) {
  return {
    pid,
    parent_pid: parentPid,
    process_group_id: processGroupId,
    process_start_identity: start,
    executable_path: executable,
    command_name: commandName,
    cwd,
  };
}

function snapshotFrom(candidateWorkspace, processes, { device = "1", inode = "1" } = {}) {
  return {
    supported: true,
    workspace: {
      requested_path: candidateWorkspace,
      canonical_path: candidateWorkspace,
      device,
      inode,
    },
    ...selectDoubaoCandidateProcesses(processes, candidateWorkspace, { excludedPids: [] }),
  };
}

function killFixturePid(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 0) return;
  try {
    process.kill(pid, "SIGKILL");
  } catch (error) {
    if (error?.code !== "ESRCH") throw error;
  }
}

test("解析 macOS ps 与 lsof cwd 时保留启动身份和完整路径", () => {
  const processes = parseMacProcessTable([
    " 83934 3662 83934 Sat Sep 19 19:41:11 2026 /bin/bash",
    " 83960 83934 83934 Sat Sep 19 19:41:11 2026 /Library/Application Support/DoubaoWork/python3",
  ].join("\n"));
  assert.equal(processes.length, 2);
  assert.equal(processes[0].process_start_identity, "Sat Sep 19 19:41:11 2026");
  assert.equal(processes[1].executable_path, "/Library/Application Support/DoubaoWork/python3");
  const cwdRecords = parseMacCwdRecords([
    "p83934",
    "cbash",
    "fcwd",
    "n/private/debug/task/workspace/countdown",
    "p83960",
    "cpython3",
    "fcwd",
    "n/private/debug/task/workspace/countdown",
  ].join("\n"));
  assert.deepEqual(cwdRecords.map((item) => item.cwd), [
    "/private/debug/task/workspace/countdown",
    "/private/debug/task/workspace/countdown",
  ]);
});

test("ps 身份在 cwd 读取前后变化时不按 PID 拼接为候选进程", async () => {
  const responses = [
    {
      code: 0,
      stdout: " 600 1 600 Sat Sep 19 19:41:11 2026 /usr/bin/python3\n",
      stderr: "",
    },
    {
      code: 0,
      stdout: "p600\ncpython3\nfcwd\nn/private/debug/task/workspace\n",
      stderr: "",
    },
    {
      code: 0,
      stdout: " 600 1 600 Sat Sep 19 20:41:11 2026 /usr/bin/python3\n",
      stderr: "",
    },
  ];
  const inventory = await readMacProcessInventory({
    runCommand: async () => responses.shift(),
  });
  assert.deepEqual(inventory, []);
  assert.equal(responses.length, 0);
});

test("候选选择只接受完整 cwd 边界并包含后代，不匹配同名其他任务", () => {
  const workspace = "/private/debug/task/workspace";
  const selected = selectDoubaoCandidateProcesses([
    fixtureProcess(100, 1, `${workspace}/site`, { executable: "/bin/bash", commandName: "bash" }),
    fixtureProcess(101, 100, "/private/tmp", { executable: "/usr/bin/python3" }),
    fixtureProcess(200, 1, `${workspace}-other`, { executable: "/usr/bin/python3" }),
    fixtureProcess(300, 1, "/private/other/task/workspace", { executable: "/usr/bin/python3" }),
  ], workspace, { excludedPids: [] });
  assert.deepEqual(selected.workspace_seed_pids, [100]);
  assert.deepEqual(selected.root_pids, [100]);
  assert.deepEqual(selected.targets.map((item) => item.pid), [100, 101]);
  assert.equal(selected.targets.find((item) => item.pid === 101).matched_by_workspace_cwd, false);
});

test("子目录名以两个句点开头时仍按完整路径边界匹配", () => {
  const workspace = "/private/debug/task/workspace";
  const selected = selectDoubaoCandidateProcesses([
    fixtureProcess(110, 1, `${workspace}/..cache`),
    fixtureProcess(120, 1, `${workspace}-other`),
  ], workspace, { excludedPids: [] });
  assert.deepEqual(selected.targets.map((item) => item.pid), [110]);
});

test("候选子进程缺少启动身份时失败关闭", () => {
  const workspace = "/private/debug/task/workspace";
  assert.throws(() => selectDoubaoCandidateProcesses([
    fixtureProcess(100, 1, workspace),
    { ...fixtureProcess(101, 100, "/private/tmp"), process_start_identity: "" },
  ], workspace, { excludedPids: [] }), /缺少启动时间或可执行文件身份/u);
});

test("PID 被同名新进程复用时拒绝发送信号", async () => {
  const workspace = "/private/debug/task/workspace";
  const before = snapshotFrom(workspace, [fixtureProcess(200, 1, workspace)]);
  const reused = snapshotFrom(workspace, [fixtureProcess(200, 1, workspace, {
    start: "Sat Sep 19 20:41:11 2026",
  })]).targets[0];
  const signaled = [];
  const result = await cleanupDoubaoCandidateProcesses(workspace, {
    platform: "darwin",
    snapshot: async () => before,
    readIdentity: async () => reused,
    sendSignal: async (pid, signal) => signaled.push([pid, signal]),
    termGraceMilliseconds: 0,
    killGraceMilliseconds: 0,
    quietMilliseconds: 0,
    waitMilliseconds: 0,
  });
  assert.equal(result.success, false);
  assert.equal(result.error_code, "PROCESS_IDENTITY_VERIFICATION_FAILED");
  assert.equal(result.identity_errors[0].code, "PID_IDENTITY_CHANGED");
  assert.deepEqual(signaled, []);
  assert.ok(result.termination_attempts.every((item) => item.result === "refused-identity-changed"));
});

test("PID 首次变更后即使后续 snapshot 把新进程列为候选也永久禁止发信号", async () => {
  const workspace = "/private/debug/task/workspace";
  const original = fixtureProcess(210, 1, workspace);
  const reused = fixtureProcess(210, 1, workspace, {
    start: "Sat Sep 19 20:41:11 2026",
  });
  const before = snapshotFrom(workspace, [original]);
  const afterReuse = snapshotFrom(workspace, [reused]);
  let snapshotCount = 0;
  const signaled = [];
  const result = await cleanupDoubaoCandidateProcesses(workspace, {
    platform: "darwin",
    snapshot: async () => (snapshotCount++ === 0 ? before : afterReuse),
    readIdentity: async () => reused,
    sendSignal: async (pid, signal) => signaled.push([pid, signal]),
    termGraceMilliseconds: 0,
    killGraceMilliseconds: 0,
    quietMilliseconds: 0,
    waitMilliseconds: 0,
  });
  assert.equal(result.success, false);
  assert.equal(result.error_code, "PROCESS_IDENTITY_VERIFICATION_FAILED");
  assert.deepEqual(signaled, []);
  assert.ok(result.identity_errors.some((item) => item.code === "PID_IDENTITY_CHANGED"));
});

test("父进程退出且子进程重挂后仍按已跟踪身份收口子进程", async () => {
  const workspace = "/private/debug/task/workspace";
  const parent = fixtureProcess(300, 1, workspace, { executable: "/bin/bash" });
  const child = fixtureProcess(301, 300, "/private/tmp", { executable: "/usr/bin/python3" });
  const reparentedChild = { ...child, parent_pid: 1 };
  const before = snapshotFrom(workspace, [parent, child]);
  const emptySnapshot = snapshotFrom(workspace, []);
  const alive = new Map([[parent.pid, parent], [child.pid, child]]);
  const signaled = [];
  let snapshotCount = 0;
  const result = await cleanupDoubaoCandidateProcesses(workspace, {
    platform: "darwin",
    snapshot: async () => (snapshotCount++ === 0 ? before : emptySnapshot),
    readIdentity: async (pid) => {
      if (pid === child.pid && alive.has(pid) && !alive.has(parent.pid)) return reparentedChild;
      return alive.get(pid) ?? null;
    },
    sendSignal: async (pid, signal) => {
      signaled.push([pid, signal]);
      if (pid === parent.pid || signal === "SIGKILL") alive.delete(pid);
    },
    termGraceMilliseconds: 0,
    killGraceMilliseconds: 0,
    quietMilliseconds: 0,
    waitMilliseconds: 0,
  });
  assert.equal(result.success, true);
  assert.ok(signaled.some(([pid, signal]) => pid === child.pid && signal === "SIGTERM"));
  assert.ok(signaled.some(([pid, signal]) => pid === child.pid && signal === "SIGKILL"));
  assert.deepEqual(result.tracked_residue, []);
});

test("发信号前 seed cwd 已离开候选 workspace 时拒绝清理", async () => {
  const workspace = "/private/debug/task/workspace";
  const target = fixtureProcess(400, 1, workspace);
  const moved = { ...target, cwd: "/private/unrelated" };
  const before = snapshotFrom(workspace, [target]);
  const signaled = [];
  const result = await cleanupDoubaoCandidateProcesses(workspace, {
    platform: "darwin",
    snapshot: async () => before,
    readIdentity: async () => moved,
    sendSignal: async (pid, signal) => signaled.push([pid, signal]),
    termGraceMilliseconds: 0,
    killGraceMilliseconds: 0,
    quietMilliseconds: 0,
    waitMilliseconds: 0,
  });
  assert.equal(result.success, false);
  assert.deepEqual(signaled, []);
  assert.ok(result.identity_errors.some((item) => item.code === "PROCESS_OWNERSHIP_UNVERIFIED"));
});

test("首次归属核验通过后同身份进程移出 cwd 仍持续跟踪", async () => {
  const workspace = "/private/debug/task/workspace";
  const target = fixtureProcess(450, 1, workspace);
  const moved = { ...target, cwd: "/private/unrelated" };
  const before = snapshotFrom(workspace, [target]);
  const emptySnapshot = snapshotFrom(workspace, []);
  let snapshotCount = 0;
  let identityReadCount = 0;
  let alive = true;
  const signaled = [];
  const result = await cleanupDoubaoCandidateProcesses(workspace, {
    platform: "darwin",
    snapshot: async () => (snapshotCount++ === 0 ? before : emptySnapshot),
    readIdentity: async () => {
      if (!alive) return null;
      identityReadCount += 1;
      return identityReadCount === 1 ? target : moved;
    },
    sendSignal: async (pid, signal) => {
      signaled.push([pid, signal]);
      alive = false;
    },
    termGraceMilliseconds: 0,
    killGraceMilliseconds: 0,
    quietMilliseconds: 0,
    waitMilliseconds: 0,
  });
  assert.equal(result.success, true);
  assert.deepEqual(signaled, [[target.pid, "SIGTERM"]]);
});

test("workspace inode 在发信号前被替换时失败关闭且不触碰新实体进程", async () => {
  const workspace = "/private/debug/task/workspace";
  const target = fixtureProcess(500, 1, workspace);
  const before = snapshotFrom(workspace, [target], { device: "1", inode: "10" });
  const replacementIdentity = {
    ...before.workspace,
    inode: "11",
  };
  const signaled = [];
  const result = await cleanupDoubaoCandidateProcesses(workspace, {
    platform: "darwin",
    snapshot: async () => before,
    readWorkspaceIdentity: async () => replacementIdentity,
    readIdentity: async () => target,
    sendSignal: async (pid, signal) => signaled.push([pid, signal]),
    termGraceMilliseconds: 0,
    killGraceMilliseconds: 0,
    quietMilliseconds: 0,
    waitMilliseconds: 0,
  });
  assert.equal(result.success, false);
  assert.deepEqual(signaled, []);
  assert.ok(result.identity_errors.some((item) => item.code === "WORKSPACE_IDENTITY_CHANGED"));
});

test("macOS cleanup 只终止自建 fixture cwd 进程树并回读零残留", {
  skip: process.platform !== "darwin",
  timeout: 45_000,
}, async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-cleanup-fixture-"));
  const requestedWorkspace = join(root, "workspace");
  await mkdir(join(requestedWorkspace, "site"), { recursive: true });
  const workspace = await realpath(requestedWorkspace);
  const site = join(workspace, "site");
  let childPid = null;
  const fixture = spawn(process.execPath, ["-e", `
    const { spawn } = require("node:child_process");
    const child = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], {
      cwd: process.cwd(),
      stdio: "ignore",
    });
    process.stdout.write(String(child.pid) + "\\n");
    setInterval(() => {}, 1000);
  `], {
    cwd: site,
    stdio: ["ignore", "pipe", "ignore"],
  });
  context.after(async () => {
    killFixturePid(childPid);
    killFixturePid(fixture.pid);
    await rm(root, { recursive: true, force: true });
  });
  childPid = await new Promise((resolvePromise, rejectPromise) => {
    let buffered = "";
    const timeout = setTimeout(() => rejectPromise(new Error("fixture child PID timeout")), 3000);
    fixture.stdout.setEncoding("utf8");
    fixture.stdout.on("data", (chunk) => {
      buffered += chunk;
      const match = buffered.match(/^(\d+)\n/u);
      if (!match) return;
      clearTimeout(timeout);
      resolvePromise(Number(match[1]));
    });
    fixture.once("error", (error) => {
      clearTimeout(timeout);
      rejectPromise(error);
    });
  });
  let initial = null;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    initial = await snapshotDoubaoCandidateProcesses(workspace, { excludedPids: [process.pid] });
    if (initial.targets.some((item) => item.pid === fixture.pid)
        && initial.targets.some((item) => item.pid === childPid)) break;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  assert.ok(initial.targets.some((item) => item.pid === fixture.pid));
  assert.ok(initial.targets.some((item) => item.pid === childPid));
  const result = await cleanupDoubaoCandidateProcesses(workspace, {
    excludedPids: [process.pid],
    termGraceMilliseconds: 100,
    killGraceMilliseconds: 100,
    quietMilliseconds: 250,
    waitMilliseconds: 1500,
  });
  assert.equal(result.supported, true);
  assert.equal(result.success, true);
  assert.deepEqual(result.after.targets, []);
  assert.ok(result.before.targets.every((item) => isPathWithinFixture(item, workspace, fixture.pid, childPid)));
  const signaledPids = new Set(result.termination_attempts
    .filter((item) => item.result === "signaled")
    .map((item) => item.pid));
  assert.deepEqual(signaledPids, new Set([fixture.pid, childPid]));
});

function isPathWithinFixture(item, workspace, parentPid, childPid) {
  if (![parentPid, childPid].includes(item.pid)) return false;
  return item.cwd === workspace || item.cwd?.startsWith(`${workspace}/`);
}
