import assert from "node:assert/strict";
import test from "node:test";

import { runWorkBuddyOfflinePreflight } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/preflight.mjs";

test("WorkBuddy脱仓包离线预检能解析共享清理组件、source gate和CB-B输入", async () => {
  const result = await runWorkBuddyOfflinePreflight();
  assert.equal(result.status, "PASS");
  assert.equal(result.side_effects, "none");
  assert.equal(result.cb_b_input.cleanup_hook, "workbuddy-macos-task-processes");
  assert.equal(result.checks.filter((item) => item.status === "pass").length, result.checks.length);
});

test("WorkBuddy脱仓包缺少共享清理组件时预检失败关闭", async () => {
  const result = await runWorkBuddyOfflinePreflight({ skillRoot: "/tmp/absent-workbuddy-general-e2e" });
  assert.equal(result.status, "FAIL");
  assert.ok(result.checks.some((item) => item.name.includes("task-process-cleanup") && item.status === "fail"));
});

