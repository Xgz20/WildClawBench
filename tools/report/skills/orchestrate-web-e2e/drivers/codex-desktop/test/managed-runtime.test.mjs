import assert from "node:assert/strict";
import test from "node:test";

import { adoptWindowsStartingServiceIdentity } from "../../../../score-web-e2e/scripts/managed_runtime.mjs";

function startingService() {
  return {
    status: "STARTING",
    pid: 26964,
    pgid: null,
    process_started_at_text: null,
    command: ["D:\\Tools\\nodejs\\node.exe", "serve_static.mjs"],
    service_id: "8166b395-53b9-4333-b8b7-a150ae53930f",
    process_group_mode: "windows-process-tree",
  };
}

test("adopts an exact Windows STARTING worker identity after an interrupted probe", () => {
  const service = startingService();
  const adopted = adoptWindowsStartingServiceIdentity(service, {
    pid: 26964,
    pgid: 26964,
    started_at_text: "2026-09-10T23:39:16.319141+08:00",
    command: "D:\\Tools\\nodejs\\node.exe C:\\skills\\managed-process-worker.mjs --service-id 8166b395-53b9-4333-b8b7-a150ae53930f -- D:\\Tools\\nodejs\\node.exe serve_static.mjs",
    process_group_mode: "windows-process-tree",
  }, { processWrapperFile: "C:\\skills\\managed-process-worker.mjs" });

  assert.equal(adopted, true);
  assert.equal(service.pgid, 26964);
  assert.equal(service.process_started_at_text, "2026-09-10T23:39:16.319141+08:00");
});

test("rejects a Windows STARTING process whose service id does not match", () => {
  const service = startingService();
  const adopted = adoptWindowsStartingServiceIdentity(service, {
    pid: 26964,
    pgid: 26964,
    started_at_text: "2026-09-10T23:39:16.319141+08:00",
    command: "D:\\Tools\\nodejs\\node.exe C:\\skills\\managed-process-worker.mjs --service-id 00000000-0000-0000-0000-000000000000 -- D:\\Tools\\nodejs\\node.exe serve_static.mjs",
    process_group_mode: "windows-process-tree",
  }, { processWrapperFile: "C:\\skills\\managed-process-worker.mjs" });

  assert.equal(adopted, false);
  assert.equal(service.pgid, null);
  assert.equal(service.process_started_at_text, null);
});
