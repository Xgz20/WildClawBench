#!/usr/bin/env node
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { access } from "node:fs/promises";
import { resolveDoubaoWorkWebRoute } from "../drivers/doubaowork/public-route.mjs";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const driverDir = resolve(scriptDir, "../drivers/doubaowork");
const argv = process.argv.slice(2);
if (argv.length === 0) {
  console.error("用法: run-doubaowork.sh <prepared 单题目录> --output-dir <仓库外目录> [选项]");
  console.error("预检: run-doubaowork.sh --probe [选项]");
  process.exitCode = 2;
} else {
  resolveDoubaoWorkWebRoute({ batch: argv.includes("--batch"), formalReceipt: argv.includes("--formal-receipt") });
  if (argv[0] === "--probe") {
    const { main: runProbe } = await import(pathToFileURL(join(driverDir, "probe.mjs")).href);
    process.exitCode = await runProbe(argv.slice(1));
  } else {
    const { main: runDriver } = await import(pathToFileURL(join(driverDir, "driver.mjs")).href);
    try { await access(join(driverDir, "node_modules", "playwright-core")); }
    catch { console.error("尚未安装依赖，请先在 execute-web-e2e/drivers/doubaowork 目录执行 npm ci"); process.exitCode = 2; }
    if (process.exitCode !== 2) process.exitCode = await runDriver(["--task-root", argv[0], ...argv.slice(1)]);
  }
}
