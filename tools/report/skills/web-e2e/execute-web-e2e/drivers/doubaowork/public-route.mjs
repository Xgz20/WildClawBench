/** Single-task and bounded 1-3 slot Web routes; platform admission remains version-specific. */
export const DOUBAOWORK_WEB_ROUTE = Object.freeze({
  id: "doubaowork",
  display_name: "DoubaoWork",
  platform: "darwin",
  mode: "native-single-and-serial-batch",
  entrypoint: "run-doubaowork.sh",
  receipt_bridge: "./drivers/doubaowork/receipt-bridge.mjs",
  finalizer: "./drivers/doubaowork/finalizer.mjs",
  formal_execution_receipt: true,
  batch: true,
  run_slots: 1,
  max_run_slots: 3,
  metrics: {
    registered: true,
    profile: "doubaowork-macos-web-v1",
    preflight: ["probe", "native-session-identity", "finalizer", "receipt-bridge"],
  },
});

export function resolveDoubaoWorkWebRoute({ batch = false, formalReceipt = false } = {}) {
  if (batch && !DOUBAOWORK_WEB_ROUTE.batch) throw new Error("DoubaoWork batch 尚未开放");
  return DOUBAOWORK_WEB_ROUTE;
}
