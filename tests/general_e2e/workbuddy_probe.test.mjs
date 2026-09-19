import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  identifyWorkBuddyMacosInstallation,
  inspectWorkBuddyMacos,
  parseArgs,
  queryWorkBuddySessions,
  WORKBUDDY_MACOS_APP_PROFILE,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/probe.mjs";

test("WorkBuddy probe arguments reject non-loopback CDP endpoints", () => {
  assert.throws(() => parseArgs(["--endpoint", "http://192.0.2.10:9229"]), /loopback/u);
  assert.equal(parseArgs(["--timeout-ms", "1234"]).timeoutMs, 1234);
});

test("WorkBuddy macOS profile accepts only the verified 5.5.3 Electron variant", () => {
  assert.equal(WORKBUDDY_MACOS_APP_PROFILE.macos.executableNames.includes("Electron"), true);
  assert.equal(identifyWorkBuddyMacosInstallation({
    executable_path: "/Applications/WorkBuddy.app/Contents/MacOS/Electron",
    version: "5.5.3",
  }), "workbuddy-macos-5.5.3-electron");
  assert.throws(() => identifyWorkBuddyMacosInstallation({
    executable_path: "/Applications/WorkBuddy.app/Contents/MacOS/Electron",
    version: "5.5.4",
  }), /unsupported WorkBuddy macOS installation identity/u);
  assert.equal(identifyWorkBuddyMacosInstallation({
    executable_path: "/Applications/WorkBuddy.app/Contents/MacOS/WorkBuddy",
    version: "9.9.9",
  }), "shared-profile");
});

test("WorkBuddy probe reads identity and native source layout without starting the app", async () => {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-probe-test-"));
  try {
    const appPath = join(root, "WorkBuddy.app");
    const executable = join(appPath, "Contents", "MacOS", "Electron");
    const sessionDb = join(root, "codebuddy-sessions.vscdb");
    const dataRoot = join(root, "WorkBuddyExtension", "Data");
    const historyRoot = join(
      dataRoot,
      "account-fixture",
      "VSCode",
      "identity-fixture",
      "history",
      "workspace-hash",
      "conversation-id",
      "messages",
    );
    await mkdir(join(appPath, "Contents", "Resources"), { recursive: true });
    await mkdir(join(appPath, "Contents", "MacOS"), { recursive: true });
    await mkdir(historyRoot, { recursive: true });
    await writeFile(executable, "fixture", "utf8");
    await writeFile(join(appPath, "Contents", "Resources", "app.asar"), "fixture", "utf8");
    await writeFile(sessionDb, "sqlite-fixture", "utf8");
    await writeFile(join(historyRoot, "message.json"), "{}\n", "utf8");

    const sessionValue = {
      conversationId: "conversation-id",
      cwd: "/fixture/workspace",
      status: "Completed",
      createdAt: 1,
      updatedAt: 2,
      userId: "must-not-leak",
      title: "must-not-leak",
    };
    const runCommand = async (command) => {
      if (command.endsWith("sqlite3")) {
        return { code: 0, stdout: JSON.stringify([{ value: JSON.stringify(sessionValue) }]), stderr: "" };
      }
      if (command.endsWith("file")) return { code: 0, stdout: "Mach-O 64-bit executable x86_64", stderr: "" };
      if (command.endsWith("sw_vers")) return { code: 0, stdout: "15.7", stderr: "" };
      throw new Error(`unexpected command: ${command}`);
    };
    const options = parseArgs([
      "--app-path", appPath,
      "--session-db", sessionDb,
      "--extension-data-root", dataRoot,
      "--extension-log-root", join(root, "missing-extension-logs"),
      "--app-log-root", join(root, "missing-app-logs"),
    ]);
    let receivedProfile = null;
    const result = await inspectWorkBuddyMacos(options, {
      runCommand,
      discoverDesktopApp: async ({ profile }) => {
        receivedProfile = profile;
        return {
          path: appPath,
          executable_path: executable,
          bundle_id: "com.tencent.workbuddy.mac",
          version: "5.5.3",
          source: "explicit",
          identity_verified: true,
        };
      },
      inspectProcess: async () => null,
      now: () => new Date("2026-09-19T08:00:00.000Z"),
    });
    assert.equal(result.status, "PASS");
    assert.equal(receivedProfile, WORKBUDDY_MACOS_APP_PROFILE);
    assert.equal(result.application.installation_variant, "workbuddy-macos-5.5.3-electron");
    assert.equal(result.readiness, "DISCOVERED_NOT_CONNECTED");
    assert.equal(result.process.running, false);
    assert.equal(result.cdp.reason, "workbuddy-not-running");
    assert.equal(result.native_sources.session_index.sessions.length, 1);
    assert.deepEqual(Object.keys(result.native_sources.session_index.sessions[0]).sort(), [
      "conversation_id",
      "created_at_ms",
      "cwd",
      "status",
      "updated_at_ms",
    ]);
    assert.equal(result.native_sources.history.message_file_count, 1);
    assert.equal(result.capabilities.prompt_send, false);
    assert.equal(result.capabilities.finalization, false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("WorkBuddy session query reports missing databases as unavailable", async () => {
  const result = await queryWorkBuddySessions("/definitely/missing/workbuddy.vscdb", {
    runCommand: async () => assert.fail("sqlite3 must not run for a missing database"),
  });
  assert.equal(result.status, "unavailable");
  assert.deepEqual(result.sessions, []);
});
