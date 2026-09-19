import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";

import { discoverDesktopApp } from "../../tools/report/e2e-shared/desktop-app-discovery/index.mjs";
import { BUILTIN_DESKTOP_APP_PROFILES, DOUBAOWORK_APP_PROFILE } from "../../tools/report/e2e-shared/desktop-app-discovery/profiles.mjs";

async function withInstall(callback) {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-discovery-"));
  const app = join(root, "custom location", "DoubaoWork.app");
  try {
    for (const path of DOUBAOWORK_APP_PROFILE.macos.requiredRelativePaths) {
      await mkdir(dirname(join(app, path)), { recursive: true });
      await writeFile(join(app, path), "fixture");
    }
    await callback(await realpath(app));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

function dependencies(bundleId = "com.work.pc.doubao") {
  return {
    runCommand: async (_command, args) => {
      if (args.includes("Print :CFBundleIdentifier")) return { code: 0, stdout: bundleId };
      if (args.includes("Print :CFBundleShortVersionString")) return { code: 0, stdout: "2.28.12" };
      return { code: 1, stdout: "" };
    },
  };
}

test("DoubaoWork discovers a native macOS bundle without app.asar", async () => {
  await withInstall(async (app) => {
    assert.equal(BUILTIN_DESKTOP_APP_PROFILES.doubaowork, DOUBAOWORK_APP_PROFILE);
    const result = await discoverDesktopApp({
      profile: DOUBAOWORK_APP_PROFILE, requestedPath: app, platform: "darwin",
    }, dependencies());
    assert.equal(result.identity_verified, true);
    assert.equal(result.path, app);
    assert.equal(result.executable_path, join(app, "Contents/MacOS/DoubaoWork"));
    assert.equal(result.bundle_id, "com.work.pc.doubao");
    assert.equal(result.component_version, "1.2.0");
  });
});

test("DoubaoWork rejects a wrong bundle or missing browser helper", async () => {
  await withInstall(async (app) => {
    const options = { profile: DOUBAOWORK_APP_PROFILE, requestedPath: app, platform: "darwin" };
    await assert.rejects(discoverDesktopApp(options, dependencies("example.other.app")));
    await rm(join(app, "Contents/Helpers/DoubaoWork Browser.app"), { recursive: true });
    await assert.rejects(discoverDesktopApp(options, dependencies()));
  });
});

test("the macOS DoubaoWork profile does not claim Windows discovery", async () => {
  await assert.rejects(
    discoverDesktopApp({ profile: DOUBAOWORK_APP_PROFILE, platform: "win32" }),
    (error) => error.code === "PROFILE_PLATFORM_UNSUPPORTED",
  );
});
