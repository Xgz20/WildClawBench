import { createHash } from "node:crypto";
import { lstat, readFile } from "node:fs/promises";
import { join } from "node:path";

// This is historical evidence only. The installed 1.0.6 client is not allowed
// to inherit the 1.0.5 result merely because the SDK and runtime hash match.
export const QWENWORK_MACOS_1_0_5_PROFILE = Object.freeze({
  id: "qwenwork-macos-1.0.5-qoder-cache-inclusive-v1",
  platform: "darwin",
  client_version: "1.0.5",
  sdk_name: "@ali/qodercn-agent-sdk-next",
  sdk_version: "1.0.28",
  transcript_version: "1.1.32",
  runtime_sha256: "e86620b7e772d1f536ba15beea8c3059bf6075dffb478aceaa8cad328a879c28",
  input_includes_cache_read: true,
});

export const QWENWORK_GENERAL_PROFILES = Object.freeze([
  QWENWORK_MACOS_1_0_5_PROFILE,
]);

export function matchQwenWorkRuntimeProfile(identity) {
  if (!identity || typeof identity !== "object") return null;
  const matched = QWENWORK_GENERAL_PROFILES.find((profile) => Object.entries(profile)
    .filter(([key]) => !new Set(["id", "input_includes_cache_read"]).has(key))
    .every(([key, expected]) => identity[key] === expected));
  return matched?.id || null;
}

async function regularFile(path, maximumBytes) {
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink() || info.size > maximumBytes) {
    throw new Error(`QWENWORK_RUNTIME_FILE_INVALID: ${path}`);
  }
  return info;
}

export async function inspectQwenWorkRuntimeIdentity({
  appPath,
  clientVersion,
  transcriptVersions = [],
  platform = process.platform,
}) {
  const uniqueVersions = [...new Set(transcriptVersions.filter((value) => typeof value === "string" && value))];
  const identity = {
    platform,
    client_version: clientVersion || null,
    transcript_version: uniqueVersions.length === 1 ? uniqueVersions[0] : null,
    sdk_name: null,
    sdk_version: null,
    runtime_sha256: null,
  };
  if (!appPath || platform !== "darwin") return identity;

  const sdkRoot = join(
    appPath,
    "Contents",
    "Resources",
    "app.asar.unpacked",
    "node_modules",
    "@qoder-ai",
    "qoder-agent-sdk",
  );
  const packagePath = join(sdkRoot, "package.json");
  const runtimePath = join(sdkRoot, "dist", "_worker", "qoder-worker-runtime.obf.mjs");
  await regularFile(packagePath, 1024 * 1024);
  const runtimeInfo = await regularFile(runtimePath, 64 * 1024 * 1024);
  const [packageBytes, runtimeBytes] = await Promise.all([
    readFile(packagePath),
    readFile(runtimePath),
  ]);
  const packageJson = JSON.parse(packageBytes.toString("utf8"));
  return {
    ...identity,
    sdk_name: typeof packageJson.name === "string" ? packageJson.name : null,
    sdk_version: typeof packageJson.version === "string" ? packageJson.version : null,
    runtime_size: runtimeInfo.size,
    runtime_sha256: createHash("sha256").update(runtimeBytes).digest("hex"),
  };
}
