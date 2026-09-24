import { inspectMacGuiSession, assertMacGuiReady } from "../../vendor/e2e-shared/desktop-gui/macos.mjs";
import { readQwenTokenListener, sameQwenTokenProcess } from "./token-process.mjs";

export async function inspectLoopbackEndpoint(endpoint, overrides = {}) {
  const request = overrides.fetch ?? fetch;
  try {
    const expected = new URL(endpoint);
    if (expected.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(expected.hostname)) throw Error("invalid endpoint");
    const response = await request(`${expected.origin}/json/version`, { signal: AbortSignal.timeout(1500), redirect: "error" });
    if (!response.ok) return { ready: false, status: response.status, browser_identity_present: false };
    const payload = await response.json(), websocket = new URL(payload.webSocketDebuggerUrl);
    const verified = websocket.protocol === "ws:" && websocket.host === expected.host
      && /^\/devtools\/browser\/[A-Za-z0-9-]+$/u.test(websocket.pathname);
    return { ready: verified && Boolean(payload.Browser), status: response.status,
      browser_identity_present: Boolean(payload.Browser), websocket_verified: verified };
  } catch { return { ready: false, status: null, browser_identity_present: false, websocket_verified: false }; }
}

export async function inspectQwenExecutionEnvironment({ appPath, endpoint }, overrides = {}) {
  const result = { schema: "wildclawbench.qwenwork-execution-environment/v1", observed_at: new Date().toISOString(),
    app_path: appPath, endpoint, gui: await (overrides.inspectGui ?? inspectMacGuiSession)(),
    listener: null, cdp: { ready: false, websocket_verified: false }, verified: false, error: null,
    operations_performed: ["gui-console-lock-read"] };
  try {
    assertMacGuiReady(result.gui);
    result.operations_performed.push("exact-listener-token-switch-read");
    result.listener = await (overrides.inspectListener ?? readQwenTokenListener)({ appPath, port: Number(new URL(endpoint).port) });
    if (!result.listener) throw Error("QWENWORK_ENDPOINT_LISTENER_MISSING");
    result.operations_performed.push("loopback-cdp-status-read");
    result.cdp = await (overrides.inspectEndpoint ?? inspectLoopbackEndpoint)(endpoint);
    if (!result.cdp.ready || result.cdp.websocket_verified !== true) throw Error("QWENWORK_CDP_WEBSOCKET_UNVERIFIED");
    result.verified = true;
  } catch (error) { result.error = error.message; }
  return result;
}

export function assertQwenExecutionEnvironment(environment, expected = null) {
  assertMacGuiReady(environment?.gui);
  if (environment?.schema !== "wildclawbench.qwenwork-execution-environment/v1" || environment.verified !== true
      || environment.cdp?.ready !== true || environment.cdp?.websocket_verified !== true
      || !Number.isSafeInteger(environment.listener?.pid) || !environment.listener?.process_start_identity
      || !environment.listener?.command_sha256) throw Error("QWENWORK_EXECUTION_ENVIRONMENT_UNVERIFIED");
  if (expected && (environment.app_path !== expected.app_path || environment.endpoint !== expected.endpoint
      || !sameQwenTokenProcess(environment.listener, expected.listener))) throw Error("QWENWORK_EXECUTION_ENVIRONMENT_CHANGED");
  return environment;
}
