import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { classifySharedWriters, parseOpenFiles, parseProcesses } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/workbuddy/shared-writers.mjs";
const hash = x => createHash("sha256").update(x).digest("hex");
function fixture() {
  const app = "/Applications/WorkBuddy.app", root = app + "/Contents/MacOS/Electron --remote-debugging-port=9229";
  const processText = `100 1 Mon Nov  2 10:28:50 2026 ${root}\n110 100 Mon Nov  2 10:29:00 2026 ${app}/Contents/MacOS/bridge\n120 110 Mon Nov  2 10:30:00 2026 ${app}/Contents/Resources/app.asar.unpacked/node_modules/@tencent/tencent-docs-ai-engine/bin/darwin-arm64/editor_sdk --port 39099\n200 1 Mon Nov  2 10:30:00 2026 /foreign/editor_sdk\n`;
  const before = parseProcesses(processText), probe = { application: { path: app, bundle_id: "com.tencent.workbuddy.mac", identity_verified: true },
    process: { pid: 100, command: root, started_at: "2026-11-02T10:28:50.000Z" } };
  return { probe, workspace: "/evaluation/task/workspace", before, after: parseProcesses(processText),
    handles: parseOpenFiles("p120\nf14\nau\nn/evaluation/task/workspace/input.xlsx\n") };
}
test("only a stable app-owned shared native editor with a mutable handle requests deferred finalization", () => {
  const f = fixture(), result = classifySharedWriters(f);
  assert.equal(result.status, "DEFER_FINALIZATION_UNTIL_HARNESS_SHUTDOWN");
  assert.equal(result.shared_mutable_handles[0].owner.pid, 120);
  assert.equal(result.workspace_or_processes_modified, false);
  f.handles[0].access = "r";
  assert.equal(classifySharedWriters(f).status, "NO_SHARED_MUTABLE_WORKSPACE_HANDLES");
  f.handles[0].access = null;
  assert.equal(classifySharedWriters(f).status, "NEEDS_ATTENTION_UNKNOWN_WRITER");
});
test("foreign writers are preserved as unknown and never considered safe to stop", () => {
  const f = fixture(); f.handles[0].pid = 200;
  const result = classifySharedWriters(f);
  assert.equal(result.status, "NEEDS_ATTENTION_UNKNOWN_WRITER");
  assert.equal(result.shared_mutable_handles.length, 0);
});
test("PID reuse and changed app ownership fail closed", () => {
  const f = fixture(); f.after.get(120).command_sha256 = hash("reused");
  assert.throws(() => classifySharedWriters(f), /PID_CHANGED/u);
  const g = fixture(); g.after.get(100).started_at = "changed";
  assert.throws(() => classifySharedWriters(g), /APP_IDENTITY_CHANGED/u);
});
test("malformed lsof fields and paths outside the exact Workspace are rejected", () => {
  assert.throws(() => parseOpenFiles("f14\nau\nn/x\n"), /LSOF_ORDER/u);
  const f = fixture(); f.handles[0].path = "/evaluation/task/workspace-other/input.xlsx";
  assert.throws(() => classifySharedWriters(f), /OUTSIDE_WORKSPACE/u);
});
