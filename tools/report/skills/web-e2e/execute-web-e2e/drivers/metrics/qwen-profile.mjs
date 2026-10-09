import { createHash } from "node:crypto";
import { lstat, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";

// 只有源码公式与真实非零会话都已核对的组合才能归一化；环境开关不是证据。
export const QWEN_PROFILE = Object.freeze({
  id: "qwenwork-1.0.5-qoder-cache-inclusive-v1",
  platform: "darwin",
  client_version: "1.0.5",
  sdk_name: "@ali/qodercn-agent-sdk-next",
  sdk_version: "1.0.28",
  transcript_version: "1.1.32",
  runtime_sha256: "e86620b7e772d1f536ba15beea8c3059bf6075dffb478aceaa8cad328a879c28",
});

export const QWEN_WINDOWS_PROFILE = Object.freeze({
  ...QWEN_PROFILE,
  platform: "win32",
  client_version: "1.0.5.0",
});

export const QWEN_WINDOWS_1_0_6_PROFILE = Object.freeze({
  ...QWEN_PROFILE,
  id: "qwenwork-1.0.6-qoder-cache-inclusive-v1",
  platform: "win32",
  client_version: "1.0.6.0",
});

// macOS 1.2.5: runtime formula and bound nonzero Web sessions were audited
// independently. Do not match future client versions by SDK/hash alone.
export const QWEN_MACOS_1_2_5_PROFILE = Object.freeze({
  id: "qwenwork-macos-1.2.5-qoder-cache-inclusive-v1",
  platform: "darwin",
  client_version: "1.2.5",
  sdk_name: "@ali/qodercn-agent-sdk-next",
  sdk_version: "1.0.46",
  transcript_version: "1.1.59",
  runtime_sha256: "8dc1dc0b107f37837cf76ef7e2be4f0dd2fdbd90ff8391a3f1f9e965e9f3fb02",
});

export const QWEN_PROFILES = Object.freeze([
  QWEN_PROFILE,
  QWEN_WINDOWS_PROFILE,
  QWEN_WINDOWS_1_0_6_PROFILE,
  QWEN_MACOS_1_2_5_PROFILE,
]);

export function verifiedQwenProfile(identity) {
  const matched = identity && QWEN_PROFILES.find(profile => Object.entries(profile)
    .filter(([key]) => key !== "id").every(([key, value]) => identity[key] === value));
  return matched?.id ?? null;
}

export async function inspectQwenRuntime(appPath, clientVersion, transcript, platform = process.platform) {
  const versions = [...new Set(transcript.filter(r => r.type === "assistant").map(r => r.version))];
  const identity = { platform, client_version: clientVersion || null,
    transcript_version: versions.length === 1 ? versions[0] ?? null : null };
  try {
    if (!appPath) return identity;
    const resources = platform === "darwin" ? join(appPath, "Contents", "Resources") : join(dirname(appPath), "resources");
    const sdk = join(resources, "app.asar.unpacked", "node_modules", "@qoder-ai", "qoder-agent-sdk");
    const runtime = join(sdk, "dist", "_worker", "qoder-worker-runtime.obf.mjs");
    for (const [file, limit] of [[runtime, 64 * 1024 * 1024], [join(sdk, "package.json"), 1024 * 1024]]) {
      const info = await lstat(file);
      if (!info.isFile() || info.isSymbolicLink() || info.size > limit) return identity;
    }
    const pkg = JSON.parse(await readFile(join(sdk, "package.json"), "utf8"));
    identity.sdk_name = pkg.name;
    identity.sdk_version = pkg.version;
    identity.runtime_sha256 = createHash("sha256").update(await readFile(runtime)).digest("hex");
  } catch { /* 应用升级/移除不能影响请求数等仍可采集的指标。 */ }
  return identity;
}
