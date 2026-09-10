#!/usr/bin/env node

import { access } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const driverDir = resolve(scriptDir, "../drivers/astronstudio");

async function main(argv) {
  if (argv.length === 0) {
    console.error("用法: run-astronstudio-batch.cmd <Harness 根目录> --run-id <ID> --task-id <ID> [--task-id <ID> ...] [选项]");
    return 2;
  }
  const { main: runBatch } = await import(join(driverDir, "batch.mjs"));
  if (new Set(["--help", "-h"]).has(argv[0])) return runBatch(argv);
  try {
    await access(join(driverDir, "node_modules", "playwright-core"));
  } catch {
    console.error("尚未安装依赖，请先在 execute-web-e2e\\drivers\\astronstudio 目录执行 npm ci");
    return 2;
  }
  const [harnessRoot, ...rest] = argv;
  return runBatch(["--harness-root", harnessRoot, ...rest]);
}

const exitCode = await main(process.argv.slice(2));
process.exitCode = exitCode;
