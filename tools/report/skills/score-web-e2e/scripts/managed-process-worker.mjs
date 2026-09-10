#!/usr/bin/env node

import { execFileSync, spawn } from "node:child_process";

function parseArgs(argv) {
  if (argv[0] !== "--service-id" || !/^[a-f0-9-]{36}$/iu.test(argv[1] || "")) {
    throw new Error("managed process worker 缺少有效 service id");
  }
  const separator = argv.indexOf("--", 2);
  if (separator < 0 || separator === argv.length - 1) throw new Error("managed process worker 缺少服务命令");
  return { serviceId: argv[1], command: argv.slice(separator + 1) };
}

const { command } = parseArgs(process.argv.slice(2));
let executable = command[0];
if (process.platform === "win32" && !/[\\/]/u.test(executable)) {
  try {
    executable = execFileSync("where.exe", [executable], { encoding: "utf8" })
      .split(/\r?\n/u)
      .map((value) => value.trim())
      .find(Boolean) || executable;
  } catch {
    // 让 spawn 返回原始 ENOENT，日志会保留用户请求的命令。
  }
}
const needsWindowsShell = process.platform === "win32" && /\.(?:cmd|bat)$/iu.test(executable);
const child = spawn(executable, command.slice(1), {
  cwd: process.cwd(),
  env: process.env,
  shell: needsWindowsShell,
  stdio: "inherit",
});

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.once(signal, () => {
    if (!child.killed) child.kill(signal);
  });
}

child.once("error", (error) => {
  process.stderr.write(`managed process worker 启动失败：${error.message}\n`);
  process.exitCode = 2;
});
child.once("exit", (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 2);
});
