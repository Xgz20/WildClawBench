#!/usr/bin/env node

import { copyFile } from "node:fs/promises";
import { constants } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const COPY_MODE = constants.COPYFILE_FICLONE;
const execFileAsync = promisify(execFile);

async function copyOne(source, destination) {
  if (process.platform === "darwin") {
    try {
      await execFileAsync("/bin/cp", ["-c", source, destination]);
      return;
    } catch {
      // Fall through to the portable Node copy. This can consume real disk
      // space, so the caller's bounded timeout remains the final guard.
    }
  }
  await copyFile(source, destination, COPY_MODE);
}

async function copyIfPresent(source, destination) {
  try {
    await copyOne(source, destination);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

const [source, destination] = process.argv.slice(2);
if (!source || !destination) {
  console.error("usage: sqlite-snapshot-copy.mjs <source> <destination>");
  process.exitCode = 2;
} else {
  try {
    await copyOne(source, destination);
    await copyIfPresent(`${source}-wal`, `${destination}-wal`);
    await copyIfPresent(`${source}-shm`, `${destination}-shm`);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
