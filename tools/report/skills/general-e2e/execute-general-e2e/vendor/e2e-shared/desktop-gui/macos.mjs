import { execFile } from "node:child_process";
import { stat } from "node:fs/promises";
import { promisify } from "node:util";

export const COMPONENT_VERSION = "1.0.0";
const execute = promisify(execFile);

async function readRegistry() {
  const { stdout } = await execute("/usr/sbin/ioreg", ["-a", "-n", "Root", "-d", "1"], { timeout: 5000, maxBuffer: 4 * 1024 * 1024 });
  return new Promise((resolve, reject) => {
    const child = execFile("/usr/bin/plutil", ["-convert", "json", "-o", "-", "-"],
      { timeout: 5000, maxBuffer: 4 * 1024 * 1024 }, (error, json) => {
        if (error) reject(error);
        else { try { resolve(JSON.parse(json)); } catch (e) { reject(e); } }
      });
    child.stdin.on("error", () => {});
    child.stdin.end(stdout);
  });
}

export async function inspectMacGuiSession(overrides = {}) {
  const report = { schema: "wildclawbench.macos-gui-session/v1", observed_at: new Date().toISOString(),
    source: "ioreg.IOConsoleLocked+IOConsoleUsers+dev-console-uid", screen_locked: null,
    console_session_verified: false, unlocked: false, error: null };
  try {
    if ((overrides.platform ?? process.platform) !== "darwin") throw Error("GUI_PLATFORM_UNSUPPORTED");
    const [registry, consoleUid] = await Promise.all([
      (overrides.readRegistry ?? readRegistry)(),
      (overrides.readConsoleUid ?? (async () => (await stat("/dev/console")).uid))(),
    ]);
    const uid = overrides.effectiveUid ?? process.getuid();
    const root = Array.isArray(registry) ? registry.length === 1 ? registry[0] : null : registry;
    if (root?.IORegistryEntryName !== "Root" || typeof root.IOConsoleLocked !== "boolean") throw Error("GUI_LOCK_STATE_UNKNOWN");
    report.screen_locked = root.IOConsoleLocked;
    const users = root.IOConsoleUsers;
    if (!Array.isArray(users)) throw Error("GUI_CONSOLE_SESSION_UNKNOWN");
    const active = users.filter(row => row.kCGSSessionOnConsoleKey === true);
    if (active.length !== 1 || active[0].kCGSessionLoginDoneKey !== true
        || !Number.isSafeInteger(uid) || uid <= 0 || consoleUid !== uid
        || active[0].kCGSSessionUserIDKey !== uid) throw Error("GUI_CONSOLE_SESSION_NOT_OWNED");
    report.console_session_verified = true;
    report.unlocked = report.screen_locked === false;
  } catch (error) {
    report.error = /^GUI_[A-Z_]+$/u.test(error.message) ? error.message : "GUI_INSPECTION_FAILED";
  }
  return report;
}

export function assertMacGuiReady(report) {
  if (report?.schema !== "wildclawbench.macos-gui-session/v1" || report.screen_locked !== false
      || report.console_session_verified !== true || report.unlocked !== true || report.error) {
    throw new Error("MACOS_GUI_LOCKED_OR_UNVERIFIED");
  }
}
