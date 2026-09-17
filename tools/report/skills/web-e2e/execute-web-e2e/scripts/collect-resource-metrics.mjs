#!/usr/bin/env node
import { readFile, writeFile, realpath } from "node:fs/promises";
import { dirname, relative, resolve, isAbsolute, sep } from "node:path";
import { captureResourceMetrics } from "../drivers/metrics/capture.mjs";

// 历史结果只导出旁路 JSON，不改 execution_record、评分包、回执或候选哈希。
const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i];
  if (!["--state", "--workspace", "--harness", "--session-db", "--output"].includes(key) || !process.argv[i + 1]) throw new Error("非法参数");
  if (args[key.slice(2)] !== undefined) throw new Error("重复参数");
  args[key.slice(2)] = process.argv[i + 1];
}
for (const key of ["state", "workspace", "harness", "output"]) if (!args[key]) throw new Error(`缺少 --${key}`);
const state = JSON.parse(await readFile(args.state, "utf8"));
if (state.driver?.id !== args.harness) throw new Error("Harness 与状态身份不一致");
const workspace = await realpath(args.workspace);
const output = resolve(args.output);
const outputParent = await realpath(dirname(output));
const inside = relative(workspace, outputParent);
if (inside === "" || (inside !== ".." && !inside.startsWith(`..${sep}`) && !isAbsolute(inside))) {
  throw new Error("旁路输出不能写入执行题目目录；请使用独立审计目录");
}
const result = await captureResourceMetrics({ workspace: args.workspace, sessionDb: args["session-db"] }, state, args.harness);
await writeFile(args.output, `${JSON.stringify(result, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
console.log(JSON.stringify({ output: args.output, warnings: result.collection.warnings }));
