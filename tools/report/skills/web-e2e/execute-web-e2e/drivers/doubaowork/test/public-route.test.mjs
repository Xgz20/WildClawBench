import test from "node:test";
import assert from "node:assert/strict";
import { DOUBAOWORK_WEB_ROUTE, resolveDoubaoWorkWebRoute } from "../public-route.mjs";

test("public route registers metrics and consumes the existing bridge", () => {
  assert.equal(DOUBAOWORK_WEB_ROUTE.id, "doubaowork");
  assert.equal(DOUBAOWORK_WEB_ROUTE.metrics.registered, true);
  assert.equal(DOUBAOWORK_WEB_ROUTE.receipt_bridge, "./drivers/doubaowork/receipt-bridge.mjs");
  assert.equal(resolveDoubaoWorkWebRoute().formal_execution_receipt, false);
});

test("public route rejects batch and formal receipt paths", () => {
  assert.throws(() => resolveDoubaoWorkWebRoute({ batch: true }), /禁止 batch/);
  assert.throws(() => resolveDoubaoWorkWebRoute({ formalReceipt: true }), /正式 execution receipt/);
});
