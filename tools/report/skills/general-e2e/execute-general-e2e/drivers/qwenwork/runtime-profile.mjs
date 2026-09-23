import { createHash } from "node:crypto";
import { lstat, readFile } from "node:fs/promises";
import { join } from "node:path";
import { inspectQwenProjectEncoding } from "./path-preflight.mjs";

export const QWENWORK_DRIVER_MACOS_1_0_5_PROFILE = Object.freeze({
  id: "qwenwork-macos-1.0.5-qoder-cache-inclusive-v1",
  platform: "darwin",
  client_version: "1.0.5",
  sdk_name: "@ali/qodercn-agent-sdk-next",
  sdk_version: "1.0.28",
  transcript_version: "1.1.32",
  runtime_sha256: "e86620b7e772d1f536ba15beea8c3059bf6075dffb478aceaa8cad328a879c28",
  input_includes_cache_read: true,
});

export const QWENWORK_DRIVER_PROFILES = Object.freeze([
  QWENWORK_DRIVER_MACOS_1_0_5_PROFILE,
]);

export function matchDriverRuntimeProfile(identity) {
  if (!identity || typeof identity !== "object") return null;
  const matched = QWENWORK_DRIVER_PROFILES.find((profile) => Object.entries(profile)
    .filter(([key]) => !new Set(["id", "input_includes_cache_read"]).has(key))
    .every(([key, expected]) => identity[key] === expected));
  return matched?.id || null;
}

async function readRegular(path, maximumBytes) {
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink() || info.size > maximumBytes) {
    throw new Error(`QWENWORK_RUNTIME_FILE_INVALID: ${path}`);
  }
  return { info, bytes: await readFile(path) };
}

export async function inspectDriverRuntimeIdentity({
  appPath,
  clientVersion,
  transcriptVersions = [],
  platform = process.platform,
}) {
  const versions = [...new Set(transcriptVersions.filter((value) => typeof value === "string" && value))];
  const base = {
    platform,
    client_version: clientVersion || null,
    transcript_version: versions.length === 1 ? versions[0] : null,
    sdk_name: null,
    sdk_version: null,
    runtime_size: null,
    runtime_sha256: null,
  };
  if (!appPath || platform !== "darwin") return base;
  const sdkRoot = join(
    appPath,
    "Contents",
    "Resources",
    "app.asar.unpacked",
    "node_modules",
    "@qoder-ai",
    "qoder-agent-sdk",
  );
  const [packageFile, runtimeFile] = await Promise.all([
    readRegular(join(sdkRoot, "package.json"), 1024 * 1024),
    readRegular(join(sdkRoot, "dist", "_worker", "qoder-worker-runtime.obf.mjs"), 64 * 1024 * 1024),
  ]);
  const packageJson = JSON.parse(packageFile.bytes.toString("utf8"));
  return {
    ...base,
    sdk_name: typeof packageJson.name === "string" ? packageJson.name : null,
    sdk_version: typeof packageJson.version === "string" ? packageJson.version : null,
    runtime_size: runtimeFile.info.size,
    runtime_sha256: createHash("sha256").update(runtimeFile.bytes).digest("hex"),
    path_encoding: inspectQwenProjectEncoding(runtimeFile.bytes.toString("utf8")),
  };
}
