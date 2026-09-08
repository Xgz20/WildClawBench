import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const DRIVER_DIR = realpathSync(join(dirname(fileURLToPath(import.meta.url)), ".."));

test("AstronStudio batch worker defaults to three background slots with a maximum of eight", () => {
  const help = spawnSync(process.execPath, [join(DRIVER_DIR, "batch.mjs"), "--help"], { encoding: "utf8" });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /AstronStudio Web E2E 后台并发队列 Worker/);
  assert.match(help.stdout, /--run-slots <1\.\.8>/);
  assert.match(help.stdout, /默认：3/);

  const invalid = spawnSync(process.execPath, [
    join(DRIVER_DIR, "batch.mjs"),
    "--harness-root", "/tmp/not-used",
    "--run-id", "test",
    "--task-id", "task-001",
    "--run-slots", "9",
  ], { encoding: "utf8" });
  assert.equal(invalid.status, 1);
  assert.match(invalid.stderr, /--run-slots 必须是 1 到 8 的整数/);
});
