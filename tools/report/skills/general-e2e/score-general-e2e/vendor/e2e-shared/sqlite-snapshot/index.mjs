import { execFile } from "node:child_process";
import { constants } from "node:fs";
import { copyFile, link, mkdtemp, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";

const executeFile = promisify(execFile);
export const COMPONENT_VERSION = "1.0.0";

export function configureSnapshotReader(database) {
  // Connection-local tuning only. mmap is capped by SQLite when unsupported;
  // virtual mapping does not reserve 2 GiB of physical memory per reader.
  database.exec("PRAGMA cache_size=-65536; PRAGMA mmap_size=2147483648;");
}

// Every caller supplies a fresh snapshot path and still validates SQLite/WAL.
// Node's FICLONE flag can fall back to a full copy on macOS. Native cp -c
// performs APFS cloning; publish its private staging inode without overwrite.
export async function copySnapshotFile(source, destination, overrides = {}) {
  const target = resolve(destination);
  const copy = overrides.copyFile || copyFile;
  if ((overrides.platform || process.platform) === "darwin") {
    const stage = await mkdtemp(join(dirname(target), ".sqlite-clone-"));
    try {
      const clone = overrides.clone || ((input, output) => executeFile(
        "/bin/cp", ["-c", resolve(input), output],
        { timeout: 10_000, maxBuffer: 64 * 1024 },
      ));
      await clone(source, join(stage, "snapshot"));
      await link(join(stage, "snapshot"), target);
      return { method: "macos-apfs-clone" };
    } catch (error) {
      if (error?.code === "EEXIST") throw error;
      // Unsupported filesystem, unavailable native command, or an interrupted
      // clone may use the original copy path. Never remove a caller's target.
    } finally {
      await rm(stage, { recursive: true, force: true });
    }
  }
  await copy(source, target, constants.COPYFILE_EXCL | constants.COPYFILE_FICLONE);
  return { method: "node-copyfile-ficlone-fallback" };
}
