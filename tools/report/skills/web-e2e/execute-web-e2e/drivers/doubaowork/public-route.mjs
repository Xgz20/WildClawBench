/** Offline public route registration for the DoubaoWork development adapter. */
export const DOUBAOWORK_WEB_ROUTE = Object.freeze({
  id: "doubaowork",
  display_name: "DoubaoWork",
  platform: "darwin",
  mode: "development-canary",
  entrypoint: "run-doubaowork.sh",
  receipt_bridge: "./drivers/doubaowork/receipt-bridge.mjs",
  finalizer: "./drivers/doubaowork/finalizer.mjs",
  formal_execution_receipt: false,
  batch: false,
  metrics: {
    registered: true,
    profile: "doubaowork-macos-web-v1",
    preflight: ["probe", "native-session-identity", "finalizer", "receipt-bridge"],
  },
});

export function resolveDoubaoWorkWebRoute({ batch = false, formalReceipt = false } = {}) {
  if (batch || formalReceipt) {
    throw new Error("DoubaoWork 当前仅支持离线 development canary，禁止 batch 或正式 execution receipt");
  }
  return DOUBAOWORK_WEB_ROUTE;
}
