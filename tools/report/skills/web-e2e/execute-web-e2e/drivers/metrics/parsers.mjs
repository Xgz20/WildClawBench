// Web adapter: preserve the published Web metric schema while the parsing
// mechanism comes from the versioned scenario-neutral component.
import {
  TOKEN_KEYS,
  createNativeResourceMetricParsers,
} from "../../vendor/e2e-shared/resource-metrics/native-parsers.mjs";
import { verifiedQwenProfile } from "./qwen-profile.mjs";

export const VERSION = "1.1.3";
export { TOKEN_KEYS };

const parsers = createNativeResourceMetricParsers({
  schemaVersion: "wildclawbench.web-e2e-resource-collection/v1",
  version: VERSION,
  scope: "primary-task",
  excludedScope: [
    "unobserved-http-retries",
    "unlinked-child-agents",
    "client-background-services",
  ],
  resolveQwenProfile: verifiedQwenProfile,
});

export const {
  count,
  elapsed,
  empty,
  setMetric,
  parseWorkBuddy,
  parseAstron,
  parseQwen,
} = parsers;

/**
 * DoubaoWork exposes a trajectory with tool/message evidence but no verified
 * usage, request, duration, native cwd, or terminal fields. Keep those values
 * null and publish only the deduplicated tool known subtotal plus coverage.
 * The caller must have already resolved one explicit conversation/session ID;
 * this parser never searches unbound logs or infers a total from UI text.
 */
export function parseDoubao(nativeEvidence) {
  const result = empty("NATIVE_USAGE_UNAVAILABLE");
  result.collection.warnings = [];
  const resources = nativeEvidence?.resources ?? {};
  const tools = resources.tools ?? {};
  const knownSubtotal = Number.isSafeInteger(tools.known_subtotal) && tools.known_subtotal >= 0
    ? tools.known_subtotal
    : (Number.isSafeInteger(tools.call_count) && tools.call_count >= 0 ? tools.call_count : null);
  const callStatus = knownSubtotal == null
    ? "unavailable"
    : (tools.status === "observed" ? "observed" : "partial");
  setMetric(
    result,
    "tools",
    "call_count",
    knownSubtotal,
    callStatus,
    "explicit session trajectory; deduplicated known subtotal, not a complete turn total",
  );
  if (knownSubtotal != null && callStatus !== "observed") {
    result.collection.known_subtotals = { call_count: knownSubtotal };
  }
  result.collection.sources = Array.isArray(nativeEvidence?.trace?.sources)
    ? nativeEvidence.trace.sources.map((source) => ({ ...source }))
    : [];
  result.collection.session_id = nativeEvidence?.identity?.session_directory_id
    ?? nativeEvidence?.identity?.conversation_id
    ?? null;
  result.collection.native_capabilities = nativeEvidence?.native_capabilities ?? null;
  result.collection.native_terminal_status = nativeEvidence?.terminal?.status ?? "unverified";
  result.collection.native_workspace_binding = nativeEvidence?.identity?.workspace_binding ?? null;
  result.collection.tool_coverage = tools.coverage ?? { numerator: null, denominator: null };
  result.collection.trace_completeness = nativeEvidence?.trace?.completeness ?? "unknown";
  result.collection.warnings.push("NATIVE_USAGE_UNAVAILABLE");
  result.collection.warnings.push("NATIVE_TERMINAL_UNAVAILABLE");
  result.collection.warnings.push("NATIVE_CWD_UNAVAILABLE");
  if (callStatus === "partial" || result.collection.tool_coverage?.denominator == null) {
    result.collection.warnings.push("PARTIAL_TOOL_COVERAGE");
  }
  return result;
}
