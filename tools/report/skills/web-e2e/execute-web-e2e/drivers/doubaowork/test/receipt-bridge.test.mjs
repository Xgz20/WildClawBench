import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  mapDoubaoAssessmentToWebReceiptBridge,
  RECEIPT_BRIDGE_SCHEMA,
} from "../receipt-bridge.mjs";

async function fixture(name) {
  const path = new URL(`./fixtures/${name}`, import.meta.url);
  return JSON.parse(await readFile(path, "utf8"));
}

test("ready assessment maps to Web vocabulary while retaining unverified native fields", async () => {
  const assessment = await fixture("receipt-bridge-ready.json");
  const result = mapDoubaoAssessmentToWebReceiptBridge({
    assessment,
    taskId: "task-finalizer",
    batchId: "batch-finalizer",
    attemptId: "attempt-finalizer",
    model: { id: "fixture-model", display_name: "Fixture Model" },
  });

  assert.equal(result.schema, RECEIPT_BRIDGE_SCHEMA);
  assert.equal(result.status, "READY_FOR_WEB_RECEIPT");
  assert.equal(result.formal_execution_receipt_allowed, true);
  assert.equal(result.public_mapping.automation_phase, "SUCCEEDED");
  assert.equal(result.public_mapping.execution_status, "completed");
  assert.equal(result.public_mapping.terminal.status, "unverified");
  assert.equal(result.public_mapping.terminal.verified, false);
  assert.equal(result.public_mapping.workspace_binding.status, "unverified");
  assert.equal(result.public_mapping.workspace_binding.verified, false);
  assert.equal(result.integrity.native_terminal_verified, false);
  assert.equal(result.integrity.native_cwd_verified, false);
});

test("missing native identity stays NEEDS_ATTENTION and cannot map to completed", async () => {
  const assessment = await fixture("receipt-bridge-native-identity-mismatch.json");
  const result = mapDoubaoAssessmentToWebReceiptBridge({ assessment });

  assert.equal(result.status, "NEEDS_ATTENTION");
  assert.equal(result.formal_execution_receipt_allowed, false);
  assert.equal(result.public_mapping.automation_phase, "NEEDS_ATTENTION");
  assert.equal(result.public_mapping.execution_status, "pending");
  assert.ok(result.reasons.includes("NATIVE_EVIDENCE_IDENTITY_MISMATCH"));
  assert.ok(result.reasons.includes("DOUBAO_RECEIPT_BRIDGE_GATE_FAILED"));
});
