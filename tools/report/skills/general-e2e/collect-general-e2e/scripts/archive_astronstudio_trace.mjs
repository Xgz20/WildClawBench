#!/usr/bin/env node
import { realpathSync } from "node:fs";
import { readFile, realpath, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { basename, dirname, join, resolve } from "node:path";
import { archiveAstronStudioTrace as archiveTrace, main as runArchiveCli }
  from "../vendor/e2e-shared/general-resource-supplements/archive_astronstudio_trace.mjs";
import { createCleanupGuard } from "../vendor/e2e-shared/astronstudio-runtime/guard.mjs";
import { appendFrameworkEvent } from "../vendor/e2e-shared/astronstudio-runtime/diagnostics.mjs";
export * from "../vendor/e2e-shared/general-resource-supplements/archive_astronstudio_trace.mjs";

export async function assertLiveArchiveAllowed({ stateFile, state, stateDatabase }, overrides = {}) {
  if (!state.run_config?.path) return;
  let config;
  try {
    config = JSON.parse(await readFile(state.run_config.path, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return; // Portable archive using a separately supplied database.
    throw error;
  }
  const configured = config.state_database?.path;
  if (!configured) return;
  if (resolve(configured) !== resolve(stateDatabase)) {
    const [source, target] = await Promise.all([
      stat(configured).catch(error => { if (error.code === "ENOENT") return null; throw error; }),
      stat(stateDatabase),
    ]);
    if (!source || source.dev !== target.dev || source.ino !== target.ino) return;
    // Preserve the original pathname for native state/WAL identity binding.
    if (await realpath(configured) !== await realpath(stateDatabase)) {
      throw Error("ASTUDIO_LIVE_ARCHIVE_REQUIRES_CONFIGURED_DATABASE_PATH");
    }
  }
  let taskRoot = dirname(await realpath(stateFile));
  while (dirname(taskRoot) !== taskRoot &&
      !(basename(taskRoot) === state.identity.task_id && basename(dirname(taskRoot)) === "execution")) {
    taskRoot = dirname(taskRoot);
  }
  const execution = dirname(taskRoot);
  const control = dirname(execution);
  if (basename(execution) !== "execution" || basename(control) !== ".general-e2e"
      || basename(taskRoot) !== state.identity.task_id) {
    throw Error("ASTUDIO_LIVE_ARCHIVE_REQUIRES_UNIT_EXECUTION_STATE");
  }
  const unitRoot = dirname(control);
  const guard = createCleanupGuard({ unitRoot, state, querySafety: overrides.querySafety });
  const proof = await guard();
  await appendFrameworkEvent(join(control, "diagnostics", "framework-events.jsonl"), {
    caller: "archive_astronstudio_trace", event: "archive.native-idle-verified",
    identity: state.identity, snapshot_sha256: proof.snapshot_sha256,
  });
}

export async function archiveAstronStudioTrace(options, overrides = {}) {
  return archiveTrace(options, {
    ...overrides,
    assertArchiveAllowed: async input => {
      await assertLiveArchiveAllowed(input, overrides);
      await overrides.assertArchiveAllowed?.(input);
    },
  });
}

export async function main() {
  return runArchiveCli({ assertArchiveAllowed: assertLiveArchiveAllowed });
}

if (process.argv[1] && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url))) {
  main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
