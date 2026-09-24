import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, realpath, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, posix, win32 } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  defaultQwenWorkAppPath,
  defaultQwenWorkSessionDb,
  launchQwenWork,
  QWEN_TOKEN_USAGE_ENV_NAME,
  QWEN_TOKEN_USAGE_ENV_VALUE,
  qwenWorkFolderHelperInvocation,
  qwenWorkGuiSessionStatus,
  qwenWorkProcessIdentity,
  qwenWorkSqliteBackendStatus,
  queryQwenWorkSqlite,
  resolveQwenWorkAppPath,
} from "../platform.mjs";

test("Windows QwenWork 默认路径按当前用户动态计算", () => {
  assert.equal(defaultQwenWorkAppPath("win32"), "");
  assert.equal(
    defaultQwenWorkSessionDb("C:\\Users\\dynamic-user", win32, { platform: "win32" }),
    "C:\\Users\\dynamic-user\\AppData\\Roaming\\QwenWorkCN\\data\\agents.db",
  );
});

test("Windows QwenWork 自动发现最新版本化安装子目录", async () => {
  const root = await mkdtemp(join(tmpdir(), "qwenwork-platform-"));
  const localAppData = join(root, "Local");
  const installRoot = join(localAppData, "Programs", "QwenWorkCN");
  const oldRoot = join(installRoot, "1.0.4-26010101");
  const newRoot = join(installRoot, "1.0.5-26090806");
  await mkdir(join(oldRoot, "resources"), { recursive: true });
  await mkdir(join(newRoot, "resources"), { recursive: true });
  await writeFile(join(oldRoot, "QwenWorkCN.exe"), "fixture");
  await writeFile(join(newRoot, "QwenWorkCN.exe"), "fixture");
  await writeFile(join(newRoot, "resources", "app.asar"), "fixture");

  const resolved = await resolveQwenWorkAppPath("", {
    platform: "win32",
    pathApi: posix,
    environment: { LOCALAPPDATA: localAppData },
    runCommand: async () => ({ code: 0, stdout: "null", stderr: "" }),
  });
  assert.equal(resolved, await realpath(join(newRoot, "QwenWorkCN.exe")));
});

test("Windows QwenWork 主进程识别排除 renderer 子进程", async () => {
  const appPath = "C:\\Users\\dynamic-user\\AppData\\Local\\Programs\\QwenWorkCN\\1.0.5\\QwenWorkCN.exe";
  const identity = await qwenWorkProcessIdentity(appPath, {
    platform: "win32",
    runCommand: async () => ({
      code: 0,
      stdout: JSON.stringify([
        { ProcessId: 1200, ParentProcessId: 800, ExecutablePath: appPath, CommandLine: `"${appPath}" --remote-debugging-port=9250` },
        { ProcessId: 1201, ParentProcessId: 1200, ExecutablePath: appPath, CommandLine: `"${appPath}" --type=renderer` },
      ]),
      stderr: "",
    }),
  });
  assert.equal(identity.pid, 1200);
  assert.equal(identity.executable_path, appPath);
});

test("Windows QwenWork SQLite 查询回退到 py -3 只读后端", async () => {
  const commands = [];
  const result = await queryQwenWorkSqlite(fileURLToPath(import.meta.url), "SELECT 1 AS value", {
    platform: "win32",
    loadNodeSqlite: async () => null,
    runCommand: async (command, args) => {
      commands.push([command, args]);
      return { code: 0, stdout: '[{"value":1}]', stderr: "" };
    },
  });
  assert.equal(result.backend, "python-sqlite3:py-3");
  assert.deepEqual(result.rows, [{ value: 1 }]);
  assert.equal(commands[0][0], "py.exe");
  assert.equal(commands[0][1][0], "-3");
});

test("Windows QwenWork SQLite 可用性探测回读具体后端", async () => {
  const status = await qwenWorkSqliteBackendStatus({
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

test("Windows QwenWork 文件夹选择器调用本地 PowerShell UIA helper", () => {
  const invocation = qwenWorkFolderHelperInvocation({
    platform: "win32",
    driverDir: "D:\\repo\\qwenwork",
    appPath: "C:\\Apps\\QwenWorkCN.exe",
    folder: "D:\\tasks\\task-a",
    timeoutSeconds: 30,
  });
  assert.equal(invocation.command, "powershell.exe");
  assert.deepEqual(invocation.args.slice(-6), [
    "-AppPath", "C:\\Apps\\QwenWorkCN.exe",
    "-Folder", "D:\\tasks\\task-a",
    "-TimeoutSeconds", "30",
  ]);
  assert.match(invocation.args[invocation.args.indexOf("-File") + 1], /qwenwork\\select-folder\.ps1$/iu);
});

test("Windows QwenWork 文件夹选择器只扫描标准系统对话框", async () => {
  const helper = await readFile(new URL("../select-folder.ps1", import.meta.url), "utf8");
  const classFilter = helper.indexOf('className.ToString() == "#32770"');
  const nativeEnumeration = helper.indexOf("FindVisibleTopLevelDialogs");
  const fromHandle = helper.indexOf("AutomationElement]::FromHandle");
  const descendantScan = helper.indexOf("$window.FindAll(");
  assert.ok(classFilter >= 0);
  assert.ok(nativeEnumeration >= 0);
  assert.ok(fromHandle > nativeEnumeration);
  assert.ok(descendantScan > fromHandle);
  assert.doesNotMatch(helper, /RootElement\.FindAll/);
});

test("Windows QwenWork 启动透传精确 CDP 参数", async () => {
  const observed = {};
  const result = await launchQwenWork("C:\\Apps\\QwenWorkCN.exe", "9250", {
    platform: "win32",
    launchDetached: async (command, args) => {
      observed.command = command;
      observed.args = args;
      return { code: 0, stdout: "", stderr: "", pid: 4321 };
    },
  });
  assert.equal(observed.command, "C:\\Apps\\QwenWorkCN.exe");
  assert.deepEqual(observed.args, [
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=9250",
  ]);
  assert.equal(result.pid, 4321);
});

test("Windows QwenWork GUI 探测失败时关闭放行", async () => {
  const status = await qwenWorkGuiSessionStatus({
    platform: "win32",
    runCommand: async () => ({ code: 1, stdout: "", stderr: "access denied" }),
  });
  assert.equal(status.unlocked, false);
  assert.equal(status.lock_source, "windows-gui-probe-failed");
  assert.equal(status.error, "access denied");
});

test("Token 暴露由 Driver 自动注入新进程且不修改调用者环境", async () => {
  for (const value of [undefined, "1", "false", "invalid"]) {
    const environment = value === undefined ? {} : { QODERCN_EXPOSE_TOKEN_USAGE: value };
    const original = { ...environment };
    let args;
    await launchQwenWork("/Applications/QwenWorkCN.app", "9250", {
      platform: "darwin", environment,
      runCommand: async (_command, actual) => { args = actual; return { code: 0 }; },
    });
    assert.equal(args.includes("--env"), true);
    assert.equal(args[args.indexOf("--env") + 1], `${QWEN_TOKEN_USAGE_ENV_NAME}=${QWEN_TOKEN_USAGE_ENV_VALUE}`);
    assert.deepEqual(environment, original);
  }
  const environment = { PATH: "fixture", QODERCN_EXPOSE_TOKEN_USAGE: "false" };
  await launchQwenWork("C:\\Apps\\QwenWorkCN.exe", "9250", {
    platform: "win32", environment,
    launchDetached: async (_command, _args, options) => {
      assert.deepEqual(options.env, { PATH: "fixture", QODERCN_EXPOSE_TOKEN_USAGE: "1" });
      return { code: 0 };
    },
  });
  assert.deepEqual(environment, { PATH: "fixture", QODERCN_EXPOSE_TOKEN_USAGE: "false" });
});

test('macOS GUI admission consumes the shared console ownership and lock proof', async () => {
  for (const gui of [{screen_locked:true,console_session_verified:true,unlocked:false},
    {screen_locked:false,console_session_verified:false,unlocked:false},
    {screen_locked:null,console_session_verified:false,unlocked:false}]) {
    assert.equal((await qwenWorkGuiSessionStatus({platform:'darwin',inspectMacGui:async()=>gui})).unlocked,false);
  }
  const good=await qwenWorkGuiSessionStatus({platform:'darwin',inspectMacGui:async()=>({screen_locked:false,console_session_verified:true,unlocked:true})});
  assert.equal(good.unlocked,true);
});

test('macOS main identity excludes only the exact native relay script and refuses real duplicate roots', async () => {
  const app='/Applications/QwenWorkCN.app',exe=app+'/Contents/MacOS/QwenWorkCN',relay=app+'/Contents/Resources/app.asar/out/main/browser-extension-relay-worker.js';
  let other=`${exe} ${relay}`;
  const overrides={platform:'darwin',realpathPath:async x=>x,runCommand:async(_cmd,args)=>{
    if(args.includes('-axo'))return{code:0,stdout:`10 1 ${exe}\n11 1 ${exe}\n`};
    if(args.includes('lstart='))return{code:0,stdout:'Wed Sep 23 13:54:14 2026'};
    return{code:0,stdout:args[1]==='10'?`${exe} --remote-debugging-port=9250`:other};
  }};
  const identity=await qwenWorkProcessIdentity(app,overrides);assert.equal(identity.pid,10);assert.equal(identity.excluded_auxiliary_processes[0].pid,11);
  for(const command of [`${exe} --remote-debugging-port=9251`,`${exe} ${relay} --unknown`,`${exe} /other/browser-extension-relay-worker.js`]){
    other=command;await assert.rejects(qwenWorkProcessIdentity(app,overrides),/multiple QwenWork root processes/);
  }
});
