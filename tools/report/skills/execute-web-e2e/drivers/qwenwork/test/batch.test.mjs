import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const DRIVER_DIR = realpathSync(join(dirname(fileURLToPath(import.meta.url)), ".."));

test("QwenWork batch worker defaults to three background run slots and caps at eight", () => {
  const help = spawnSync(process.execPath, [join(DRIVER_DIR, "batch.mjs"), "--help"], { encoding: "utf8" });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /QwenWork Web E2E 后台并发队列 Worker/);
  assert.match(help.stdout, /--run-slots <1\.\.8>/);
  assert.match(help.stdout, /Agent 并发数，默认：3；UI 始终单路/);

  for (const [runSlots, expectedError] of [
    ["0", /--run-slots 必须是正数/],
    ["9", /--run-slots 必须是 1 到 8 的整数/],
    ["1.5", /--run-slots 必须是 1 到 8 的整数/],
  ]) {
    const invalid = spawnSync(process.execPath, [
      join(DRIVER_DIR, "batch.mjs"),
      "--harness-root", "/tmp/not-used",
      "--run-id", "test",
      "--task-id", "task-001",
      "--run-slots", runSlots,
    ], { encoding: "utf8" });
    assert.equal(invalid.status, 1);
    assert.match(invalid.stderr, expectedError);
  }
});
