#!/usr/bin/env node

import { copyFile } from "node:fs/promises";

async function copyIfPresent(source, destination) {
  try {
    await copyFile(source, destination);
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
    await copyFile(source, destination);
    await copyIfPresent(`${source}-wal`, `${destination}-wal`);
    await copyIfPresent(`${source}-shm`, `${destination}-shm`);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
