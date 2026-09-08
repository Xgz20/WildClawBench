import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const DRIVER_DIR = realpathSync(join(dirname(fileURLToPath(import.meta.url)), ".."));

test("AstronStudio batch worker is serial and rejects unverified concurrency", () => {
  const help = spawnSync(process.execPath, [join(DRIVER_DIR, "batch.mjs"), "--help"], { encoding: "utf8" });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /AstronStudio Web E2E 串行队列 Worker/);
  assert.match(help.stdout, /--run-slots <1\.\.1>/);

  const invalid = spawnSync(process.execPath, [
    join(DRIVER_DIR, "batch.mjs"),
    "--harness-root", "/tmp/not-used",
    "--run-id", "test",
    "--task-id", "task-001",
    "--run-slots", "2",
  ], { encoding: "utf8" });
  assert.equal(invalid.status, 1);
  assert.match(invalid.stderr, /--run-slots 必须是 1 到 1 的整数/);
});
