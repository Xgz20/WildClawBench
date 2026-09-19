import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
import { join, relative, resolve } from "node:path";
import { lstat, readdir, realpath, stat } from "node:fs/promises";

import {
  DEFAULT_APP_PATH,
  DEFAULT_BUNDLE_ID,
  parseLoopbackEndpoint,
  validateSessionId,
} from "./lib.mjs";

const execFile = promisify(execFileCallback);

async function run(command, args, overrides = {}) {
  if (overrides.run) return overrides.run(command, args);
  return execFile(command, args, { encoding: "utf8", maxBuffer: 4 * 1024 * 1024 });
}

export function defaultNativeRoots(userHome = homedir()) {
  const profileRoot = join(userHome, "Library", "Application Support", "DoubaoWork");
  return {
    profile_root: profileRoot,
    sessions_root: join(profileRoot, "Default", ".doubaowork", "agent_mode", "workspace", ".sessions"),
    logs_root: join(profileRoot, "sdk_storage", "log"),
  };
}

export async function readDoubaoWorkAppIdentity(appPath = DEFAULT_APP_PATH, overrides = {}) {
  if (process.platform !== "darwin" && !overrides.allowNonDarwin) {
    throw new Error("DoubaoWork 当前只实现 macOS 应用身份探针");
  }
  const absolute = resolve(appPath);
  const appInfo = await lstat(absolute);
  if (!appInfo.isDirectory() || appInfo.isSymbolicLink()) {
    throw new Error(`DoubaoWork app 不是普通 app 目录：${absolute}`);
  }
  const canonical = await realpath(absolute);
  const plistPath = join(canonical, "Contents", "Info.plist");
  const { stdout } = await run("/usr/bin/plutil", ["-convert", "json", "-o", "-", plistPath], overrides);
  const plist = JSON.parse(stdout);
  if (plist.CFBundleIdentifier !== DEFAULT_BUNDLE_ID) {
    throw new Error(`DoubaoWork Bundle ID 不匹配：${plist.CFBundleIdentifier ?? "<missing>"}`);
  }
  const executable = join(canonical, "Contents", "MacOS", plist.CFBundleExecutable || "DoubaoWork");
  const executableInfo = await lstat(executable);
  if (!executableInfo.isFile() || executableInfo.isSymbolicLink()) {
    throw new Error(`DoubaoWork 主程序不是普通文件：${executable}`);
  }
  return {
    app_path: canonical,
    bundle_id: plist.CFBundleIdentifier,
    version: plist.CFBundleShortVersionString ?? null,
    build: plist.CFBundleVersion ?? null,
    executable,
    browser_executable: join(
      canonical,
      "Contents",
      "Helpers",
      "DoubaoWork Browser.app",
      "Contents",
      "MacOS",
      "DoubaoWork Browser",
    ),
  };
}

export function parseLsofRecords(stdout) {
  const records = [];
  let current = null;
  for (const line of stdout.split(/\r?\n/)) {
    if (!line) continue;
    const field = line[0];
    const value = line.slice(1);
    if (field === "p") {
      if (current) records.push(current);
      current = { pid: Number(value), command_name: null, address: null };
    } else if (current && field === "c") {
      current.command_name = value;
    } else if (current && field === "n") {
      current.address = value;
    }
  }
  if (current) records.push(current);
  return records.filter((entry) => Number.isSafeInteger(entry.pid) && entry.pid > 0);
}

export async function inspectEndpointListener(endpointValue, appIdentity, overrides = {}) {
  const endpoint = parseLoopbackEndpoint(endpointValue);
  let stdout;
  try {
    ({ stdout } = await run(
      "/usr/sbin/lsof",
      ["-nP", "-Fpcn", `-iTCP:${endpoint.port}`, "-sTCP:LISTEN"],
      overrides,
    ));
  } catch (error) {
    if (error?.code === 1) return { endpoint: endpoint.origin, listeners: [], unique_expected_listener: false };
    throw error;
  }
  const listeners = [];
  for (const record of parseLsofRecords(stdout)) {
    const result = await run("/bin/ps", ["-p", String(record.pid), "-o", "command="], overrides);
    const command = result.stdout.trim();
    listeners.push({
      ...record,
      command,
      expected_app: command === appIdentity.browser_executable
        || command.startsWith(`${appIdentity.browser_executable} `),
      loopback: record.address?.startsWith("127.0.0.1:")
        || record.address?.startsWith("[::1]:")
        || record.address?.startsWith("localhost:"),
    });
  }
  const expected = listeners.filter((entry) => entry.expected_app && entry.loopback);
  return {
    endpoint: endpoint.origin,
    listeners,
    unique_expected_listener: listeners.length === 1 && expected.length === 1,
  };
}

async function safeMetadata(pathValue) {
  try {
    const info = await lstat(pathValue);
    return {
      exists: true,
      is_file: info.isFile(),
      is_directory: info.isDirectory(),
      is_symbolic_link: info.isSymbolicLink(),
      size_bytes: info.isFile() ? info.size : null,
      modified_at: info.mtime.toISOString(),
    };
  } catch (error) {
    if (error?.code === "ENOENT") return { exists: false };
    throw error;
  }
}

async function requireOrdinaryDirectory(pathValue, label) {
  const info = await lstat(pathValue);
  if (!info.isDirectory() || info.isSymbolicLink()) {
    throw new Error(`${label} 不是普通目录或包含符号链接：${pathValue}`);
  }
  return info;
}

async function listLogMetadata(logsRoot) {
  const output = [];
  const roots = [logsRoot, join(logsRoot, "agent_infra"), join(logsRoot, "agent_infra", "shell_session_host")];
  for (const root of roots) {
    let entries;
    try {
      entries = await readdir(root, { withFileTypes: true });
    } catch (error) {
      if (error?.code === "ENOENT") continue;
      throw error;
    }
    for (const entry of entries) {
      if (!entry.isFile() || entry.isSymbolicLink()) continue;
      const absolute = join(root, entry.name);
      const info = await stat(absolute);
      output.push({
        relative_path: relative(logsRoot, absolute),
        size_bytes: info.size,
        modified_at: info.mtime.toISOString(),
        task_binding: "unbound",
      });
      if (output.length >= 128) return output;
    }
  }
  return output.sort((left, right) => left.relative_path.localeCompare(right.relative_path));
}

export async function discoverNativeSources({
  userHome = homedir(),
  sessionId = null,
  roots = defaultNativeRoots(userHome),
} = {}) {
  const report = {
    roots: {
      sessions: await safeMetadata(roots.sessions_root),
      logs: await safeMetadata(roots.logs_root),
    },
    requested_session_id: sessionId,
    session: null,
    logs: await listLogMetadata(roots.logs_root),
  };
  if (!sessionId) return report;
  validateSessionId(sessionId);
  const sessionRoot = join(roots.sessions_root, sessionId);
  const rootMetadata = await safeMetadata(sessionRoot);
  const trajectories = [];
  if (rootMetadata.exists && rootMetadata.is_directory && !rootMetadata.is_symbolic_link) {
    await requireOrdinaryDirectory(roots.sessions_root, "DoubaoWork sessions root");
    await requireOrdinaryDirectory(sessionRoot, "DoubaoWork session root");
    const agentsRoot = join(sessionRoot, "agents");
    let agents = [];
    try {
      await requireOrdinaryDirectory(agentsRoot, "DoubaoWork agents root");
      agents = await readdir(agentsRoot, { withFileTypes: true });
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    for (const agent of agents) {
      if (!agent.isDirectory() || agent.isSymbolicLink()) continue;
      const agentRoot = join(agentsRoot, agent.name);
      const systemRoot = join(agentRoot, "system");
      await requireOrdinaryDirectory(agentRoot, `DoubaoWork agent ${agent.name}`);
      try {
        await requireOrdinaryDirectory(systemRoot, `DoubaoWork agent ${agent.name} system`);
      } catch (error) {
        if (error?.code === "ENOENT") continue;
        throw error;
      }
      const trajectory = join(systemRoot, "trajectory.jsonl");
      const metadata = await safeMetadata(trajectory);
      if (metadata.exists && metadata.is_file && !metadata.is_symbolic_link) {
        trajectories.push({
          agent_id: agent.name,
          path: trajectory,
          relative_path: relative(roots.sessions_root, trajectory),
          size_bytes: metadata.size_bytes,
          modified_at: metadata.modified_at,
          path_chain_verified: true,
        });
      }
    }
  }
  report.session = {
    ...rootMetadata,
    directory_id: sessionId,
    trajectories: trajectories.sort((left, right) => left.relative_path.localeCompare(right.relative_path)),
    native_cwd: null,
    turn_id: null,
    terminal_status: null,
  };
  return report;
}

export async function listSessionDirectoryIds({
  userHome = homedir(),
  roots = defaultNativeRoots(userHome),
} = {}) {
  await requireOrdinaryDirectory(roots.sessions_root, "DoubaoWork sessions root");
  const entries = await readdir(roots.sessions_root, { withFileTypes: true });
  const sessionIds = [];
  for (const entry of entries) {
    if (!/^[0-9]{1,64}$/.test(entry.name) || !entry.isDirectory() || entry.isSymbolicLink()) continue;
    const sessionRoot = join(roots.sessions_root, entry.name);
    await requireOrdinaryDirectory(sessionRoot, `DoubaoWork session ${entry.name}`);
    sessionIds.push(entry.name);
  }
  return sessionIds.sort();
}
