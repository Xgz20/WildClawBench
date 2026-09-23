import { createHash } from "node:crypto";

// Admitted from QwenWorkCN 1.2.0 / SDK 1.0.46 source and a fresh nonzero
// macOS session. The process-level switch only exposes raw values; this exact
// identity plus response/turn reconciliation is required for normalization.
export const QWENWORK_MACOS_1_2_0_TOKEN_PROFILE = Object.freeze({
  id: "qwenwork-macos-1.2.0-qoder-cache-inclusive-v1",
  platform: "darwin",
  client_version: "1.2.0",
  sdk_name: "@ali/qodercn-agent-sdk-next",
  sdk_version: "1.0.46",
  transcript_version: "1.1.59",
  runtime_sha256: "8dc1dc0b107f37837cf76ef7e2be4f0dd2fdbd90ff8391a3f1f9e965e9f3fb02",
  input_includes_cache_read: true,
});

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}

export function qwenCanaryConfigDigest(config) {
  const copy = structuredClone(config);
  for (const key of ["config_digest", "resume", "recovery_probe", "managed_queue_id",
    "allowed_active_session_ids", "allowed_active_conversation_ids", "prepare_only"]) delete copy[key];
  if (copy.prompt) delete copy.prompt.content;
  return createHash("sha256").update(JSON.stringify(stable(copy))).digest("hex");
}

export function matchQwenTokenProfile(probe, transcriptRows) {
  const profile = QWENWORK_MACOS_1_2_0_TOKEN_PROFILE;
  const runtime = probe?.runtime?.identity || {};
  const versions = [...new Set((transcriptRows || [])
    .filter((row) => row?.type === "assistant")
    .map((row) => row.version).filter(Boolean))];
  if (probe?.app?.identity_verified !== true
      || probe.app?.bundle_id !== "cn.qwenwork.desktop.mac"
      || probe.app?.version !== profile.client_version
      || probe.app?.token_usage_exposure?.status !== "enabled"
      || !Number.isSafeInteger(probe.app?.token_usage_exposure?.listener_pid)
      || versions.length !== 1 || versions[0] !== profile.transcript_version) return null;
  for (const key of ["platform", "client_version", "sdk_name", "sdk_version", "runtime_sha256"]) {
    if (runtime[key] !== profile[key]) return null;
  }
  return profile;
}
