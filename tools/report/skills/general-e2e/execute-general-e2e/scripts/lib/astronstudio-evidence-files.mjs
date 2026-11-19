import { randomUUID } from "node:crypto";
import { constants } from "node:fs";
import { open, rename, rm } from "node:fs/promises";
import { dirname } from "node:path";

export async function readEvidenceJson(path) {
  let file;
  try {
    file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
    const info = await file.stat();
    if (!info.isFile() || info.size > 16 * 1024 * 1024) throw Error("ASTUDIO_EVIDENCE_JSON_SIZE");
    return JSON.parse(await file.readFile("utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  } finally {
    await file?.close();
  }
}

export async function syncEvidenceDirectory(path) {
  const handle = await open(path, "r");
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}

export async function writeEvidenceBytes(path, bytes) {
  const handle = await open(path, "wx", 0o600);
  try {
    await handle.writeFile(bytes);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

export async function writeEvidenceJson(path, value) {
  const temporary = path + "." + randomUUID() + ".tmp";
  try {
    await writeEvidenceBytes(temporary, JSON.stringify(value, null, 2) + "\n");
    await rename(temporary, path);
    await syncEvidenceDirectory(dirname(path));
  } finally {
    await rm(temporary, { force: true });
  }
}

export function evidenceClock(now = Date.now()) {
  return { at: new Date(now).toISOString(), monotonic_ns: process.hrtime.bigint().toString() };
}
