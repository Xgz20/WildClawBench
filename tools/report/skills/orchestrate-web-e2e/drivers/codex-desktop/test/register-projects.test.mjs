import assert from "node:assert/strict";
import test from "node:test";

import {
  assertLoopbackEndpoint,
  choosePageInventory,
  pageRank,
  parseArgs,
} from "../register-projects.mjs";
import {
  folderHelperInvocation,
  resolveCodexAppPath,
} from "../platform.mjs";

test("parseArgs accepts probe and repeated project paths", () => {
  const args = parseArgs([
    "--project", "/tmp/a",
    "--project", "/tmp/b",
    "--renderer-bridge",
    "--endpoint", "http://localhost:9230",
  ]);
  assert.deepEqual(args.projects, ["/tmp/a", "/tmp/b"]);
  assert.equal(args.rendererBridge, true);
  assert.equal(args.endpoint, "http://localhost:9230");
});

test("registrar only accepts loopback HTTP endpoints", () => {
  assert.equal(assertLoopbackEndpoint("http://127.0.0.1:9230").hostname, "127.0.0.1");
  assert.throws(() => assertLoopbackEndpoint("https://127.0.0.1:9230"), /只允许本机/);
  assert.throws(() => assertLoopbackEndpoint("http://192.0.2.1:9230"), /只允许本机/);
});

test("Codex app page outranks browser and DevTools pages", () => {
  assert.ok(pageRank({ title: "Codex", url: "app://-/" }) > pageRank({ title: "Browser", url: "https://example.com" }));
  assert.ok(pageRank({ title: "ChatGPT", url: "app://-/index.html" }) > pageRank({ title: "ChatGPT", url: "app://-/index.html?initialRoute=%2Favatar-overlay" }));
  assert.ok(pageRank({ title: "DevTools", url: "devtools://devtools" }) < 0);
  const selected = choosePageInventory([
    { index: 0, title: "Example", url: "https://example.com" },
    { index: 1, title: "Codex", url: "app://-/" },
  ]);
  assert.equal(selected.index, 1);
});

test("multiple equal app pages require an exact URL", () => {
  const pages = [
    { index: 0, title: "Codex", url: "app://-/one" },
    { index: 1, title: "Codex", url: "app://-/two" },
  ];
  assert.throws(() => choosePageInventory(pages), /多个同等候选/);
  assert.equal(choosePageInventory(pages, "app://-/two").index, 1);
});

test("Windows Codex Desktop path is discovered from the process using the requested CDP port", async () => {
  const appPath = "C:\\Users\\tester\\AppData\\Local\\Programs\\ChatGPT\\ChatGPT.exe";
  const resolved = await resolveCodexAppPath("", "http://127.0.0.1:9230", {
    platform: "win32",
    realpathPath: async (value) => value,
    statPath: async (value) => ({
      isFile: () => value.toLowerCase() === appPath.toLowerCase(),
      isDirectory: () => false,
    }),
    runCommand: async (command, args) => {
      assert.equal(command, "powershell.exe");
      assert.match(args.join(" "), /remote-debugging-port=9230/);
      return {
        code: 0,
        stderr: "",
        stdout: JSON.stringify({ ProcessId: 101, ExecutablePath: appPath, CommandLine: `"${appPath}" --remote-debugging-port=9230` }),
      };
    },
    environment: {},
  });
  assert.equal(resolved, appPath);
});

test("Windows project registration uses the UI Automation folder helper", () => {
  const invocation = folderHelperInvocation({
    platform: "win32",
    driverDir: "C:\\skills\\orchestrate-web-e2e\\drivers\\codex-desktop",
    bundleId: "unused",
    appPath: "C:\\Apps\\ChatGPT.exe",
    project: "C:\\scores\\task-1",
    timeoutSeconds: 15,
  });
  assert.equal(invocation.command, "powershell.exe");
  assert.deepEqual(invocation.args.slice(0, 6), [
    "-NoProfile",
    "-NonInteractive",
    "-STA",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
  ]);
  assert.match(invocation.args[6], /select-folder\.ps1$/);
  assert.deepEqual(invocation.args.slice(-6), [
    "-AppPath",
    "C:\\Apps\\ChatGPT.exe",
    "-Folder",
    "C:\\scores\\task-1",
    "-TimeoutSeconds",
    "15",
  ]);
});
