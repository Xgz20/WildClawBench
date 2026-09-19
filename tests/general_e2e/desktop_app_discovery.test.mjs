import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, posix } from "node:path";
import test from "node:test";

import {
  DesktopAppDiscoveryError,
  discoverDesktopApp,
  inspectMacDesktopAppProcess,
  sameDesktopAppPath,
  verifyDesktopAppPath,
} from "../../tools/report/e2e-shared/desktop-app-discovery/index.mjs";

const PROFILE = Object.freeze({
  id: "fixture-app",
  displayName: "Fixture App",
  windows: Object.freeze({
    executableNames: Object.freeze(["Fixture App.exe"]),
    requiredRelativePaths: Object.freeze(["resources/app.asar"]),
    standardPaths: Object.freeze([]),
  }),
});

const MAC_PROFILE = Object.freeze({
  id: "fixture-mac-app",
  displayName: "Fixture Mac App",
  macos: Object.freeze({
    bundleIds: Object.freeze(["example.fixture.app"]),
    appNames: Object.freeze(["Fixture.app"]),
    executableNames: Object.freeze(["Fixture"]),
    requiredRelativePaths: Object.freeze(["Contents/Info.plist"]),
    standardPaths: Object.freeze([]),
  }),
});

async function createInstall(root, name) {
  const directory = join(root, name);
  const executable = join(directory, "Fixture App.exe");
  await mkdir(join(directory, "resources"), { recursive: true });
  await writeFile(executable, "fixture");
  await writeFile(join(directory, "resources", "app.asar"), "fixture");
  return { directory, executable: await realpath(executable) };
}

async function createMacInstall(root) {
  const directory = join(root, "Fixture.app");
  const executable = join(directory, "Contents", "MacOS", "Fixture");
  await mkdir(join(directory, "Contents", "MacOS"), { recursive: true });
  await writeFile(executable, "fixture");
  await writeFile(join(directory, "Contents", "Info.plist"), "fixture");
  return { directory: await realpath(directory), executable: await realpath(executable) };
}

function overrides(candidatesByTier) {
  return {
    pathApi: posix,
    candidatesByTier,
    runCommand: async () => ({ code: 1, stdout: "", stderr: "unavailable" }),
  };
}

test("explicit paths with spaces have highest priority and retain audit evidence", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-discovery-explicit-"));
  try {
    const install = await createInstall(root, "Fixture App Custom");
    const result = await discoverDesktopApp({
      profile: PROFILE,
      requestedPath: install.directory,
      platform: "win32",
      environment: {},
      home: root,
    }, overrides({
      running_process: [{ path: join(root, "ignored"), source: "running_process" }],
    }));
    assert.equal(result.path, install.executable);
    assert.equal(result.source, "explicit");
    assert.equal(result.identity_verified, true);
    assert.equal(result.candidates_checked.length, 1);
    assert.equal(result.candidates_checked[0].status, "valid");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("a verified running process outranks registered and standard installations", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-discovery-running-"));
  try {
    const running = await createInstall(root, "running");
    const registered = await createInstall(root, "registered");
    const standard = await createInstall(root, "standard");
    const result = await discoverDesktopApp({
      profile: PROFILE,
      platform: "win32",
      environment: {},
      home: root,
    }, overrides({
      running_process: [{ path: running.executable, source: "running_process" }],
      system_registration: [{ path: registered.directory, source: "windows_app_paths" }],
      standard_directory: [{ path: standard.directory, source: "standard_directory" }],
    }));
    assert.equal(result.path, running.executable);
    assert.equal(result.source, "running_process");
    assert.equal(result.candidates_checked.length, 1);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("macOS running-process discovery uses ps without Apple Events", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-discovery-macos-running-"));
  try {
    const install = await createMacInstall(root);
    const calls = [];
    const result = await discoverDesktopApp({
      profile: MAC_PROFILE,
      platform: "darwin",
      environment: {},
      home: root,
    }, {
      runCommand: async (command, args) => {
        calls.push([command, args]);
        if (command === "/bin/ps") {
          return {
            code: 0,
            stdout: `  101 ${install.executable}\n  102 ${install.executable}\n`,
            stderr: "",
          };
        }
        if (args.includes("Print :CFBundleIdentifier")) {
          return { code: 0, stdout: "example.fixture.app\n", stderr: "" };
        }
        if (args.includes("Print :CFBundleShortVersionString")) {
          return { code: 0, stdout: "1.2.3\n", stderr: "" };
        }
        return { code: 1, stdout: "", stderr: "unavailable" };
      },
    });
    assert.equal(result.path, install.directory);
    assert.equal(result.executable_path, install.executable);
    assert.equal(result.source, "running_process");
    assert.equal(result.bundle_id, "example.fixture.app");
    assert.equal(calls.some(([command]) => command === "/usr/bin/osascript"), false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("macOS process inspection selects the root PID for repeated executable paths", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-process-macos-root-"));
  try {
    const install = await createMacInstall(root);
    const calls = [];
    const processInfo = await inspectMacDesktopAppProcess({
      profile: MAC_PROFILE,
      appPath: install.directory,
    }, {
      runCommand: async (command, args) => {
        calls.push([command, args]);
        if (args[0] === "-axo") {
          return {
            code: 0,
            stdout: `  101 1 ${install.executable}\n  102 101 ${install.executable}\n`,
            stderr: "",
          };
        }
        if (args.at(-1) === "command=") {
          return { code: 0, stdout: `${install.executable} --remote-debugging-port=9240\n`, stderr: "" };
        }
        if (args.at(-1) === "lstart=") {
          return { code: 0, stdout: "Fri Sep 19 10:20:30 2026\n", stderr: "" };
        }
        return { code: 1, stdout: "", stderr: "unexpected" };
      },
    });
    assert.equal(processInfo.pid, 101);
    assert.equal(processInfo.ppid, 1);
    assert.equal(processInfo.executable_path, install.executable);
    assert.match(processInfo.command, /remote-debugging-port=9240/u);
    assert.equal(calls.some(([command]) => command === "/usr/bin/osascript"), false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("macOS process inspection fails closed for multiple root processes", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-process-macos-ambiguous-"));
  try {
    const install = await createMacInstall(root);
    await assert.rejects(
      inspectMacDesktopAppProcess({
        profile: MAC_PROFILE,
        appPath: install.directory,
      }, {
        runCommand: async (_command, args) => args[0] === "-axo"
          ? {
            code: 0,
            stdout: `  101 1 ${install.executable}\n  201 1 ${install.executable}\n`,
            stderr: "",
          }
          : { code: 1, stdout: "", stderr: "unexpected" },
      }),
      (error) => error instanceof DesktopAppDiscoveryError
        && error.code === "AMBIGUOUS_RUNNING_PROCESS",
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("stale candidates are recorded and discovery proceeds to the next priority tier", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-discovery-stale-"));
  try {
    const standard = await createInstall(root, "standard");
    const result = await discoverDesktopApp({
      profile: PROFILE,
      platform: "win32",
      environment: {},
      home: root,
    }, overrides({
      running_process: [{ path: join(root, "missing.exe"), source: "running_process" }],
      system_registration: [{ path: join(root, "stale"), source: "windows_uninstall_registry" }],
      standard_directory: [{ path: standard.directory, source: "standard_directory" }],
    }));
    assert.equal(result.path, standard.executable);
    assert.deepEqual(
      result.candidates_checked.map((item) => item.status),
      ["invalid", "invalid", "valid"],
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("multiple verified installations in the same priority tier fail closed", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-discovery-ambiguous-"));
  try {
    const first = await createInstall(root, "first");
    const second = await createInstall(root, "second");
    await assert.rejects(
      discoverDesktopApp({
        profile: PROFILE,
        platform: "win32",
        environment: {},
        home: root,
      }, overrides({
        running_process: [],
        system_registration: [
          { path: first.directory, source: "windows_app_paths" },
          { path: second.directory, source: "windows_uninstall_registry" },
        ],
      })),
      (error) => {
        assert(error instanceof DesktopAppDiscoveryError);
        assert.equal(error.code, "AMBIGUOUS_INSTALLATION");
        assert.equal(error.candidatesChecked.filter((item) => item.status === "valid").length, 2);
        return true;
      },
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("a frozen path can be revalidated without rediscovering another installation", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-discovery-frozen-"));
  try {
    const install = await createInstall(root, "frozen");
    const verified = await verifyDesktopAppPath({
      profile: PROFILE,
      path: install.executable,
      platform: "win32",
    }, overrides({}));
    assert.equal(verified.path, install.executable);
    await rm(join(install.directory, "resources"), { recursive: true, force: true });
    await assert.rejects(
      verifyDesktopAppPath({
        profile: PROFILE,
        path: install.executable,
        platform: "win32",
      }, overrides({})),
      /required application file is missing/u,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("macOS verification rejects a bundle whose supported executable is missing", async () => {
  const root = await mkdtemp(join(tmpdir(), "desktop-discovery-macos-missing-executable-"));
  try {
    const install = await createMacInstall(root);
    await rm(install.executable);
    await assert.rejects(
      verifyDesktopAppPath({
        profile: MAC_PROFILE,
        path: install.directory,
        platform: "darwin",
      }, {
        runCommand: async (_command, args) => {
          if (args.includes("Print :CFBundleIdentifier")) {
            return { code: 0, stdout: "example.fixture.app\n", stderr: "" };
          }
          return { code: 1, stdout: "", stderr: "unavailable" };
        },
      }),
      /supported application executable was not found/u,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("Windows frozen paths compare case-insensitively after canonicalization", () => {
  assert.equal(
    sameDesktopAppPath(
      "C:\\Program Files\\AStudio\\AStudio.exe",
      "c:/program files/astudio/ASTUDIO.EXE",
      "win32",
    ),
    true,
  );
  assert.equal(
    sameDesktopAppPath("C:\\Program Files\\AStudio\\AStudio.exe", "D:\\AStudio\\AStudio.exe", "win32"),
    false,
  );
});
