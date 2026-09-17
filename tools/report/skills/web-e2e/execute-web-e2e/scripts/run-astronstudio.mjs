#!/usr/bin/env node

import { access } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const driverDir = resolve(scriptDir, "../drivers/astronstudio");

async function main(argv) {
  const passthrough = new Set(["--probe", "--help", "-h"]);
  if (argv.length === 0) {
    console.error("用法: run-astronstudio.cmd <单题目录> [选项]");
    console.error("预检: run-astronstudio.cmd --probe [选项]");
    return 2;
  }
  const { main: runDriver } = await import(pathToFileURL(join(driverDir, "driver.mjs")).href);
  if (passthrough.has(argv[0])) return runDriver(argv);
  try {
    await access(join(driverDir, "node_modules", "playwright-core"));
  } catch {
    console.error("尚未安装依赖，请先在 execute-web-e2e\\drivers\\astronstudio 目录执行 npm ci");
    return 2;
  }
  const [taskRoot, ...rest] = argv;
  return runDriver(["--workspace", taskRoot, ...rest]);
}

const exitCode = await main(process.argv.slice(2));
process.exitCode = exitCode;
setImmediate(() => process.exit(exitCode));
