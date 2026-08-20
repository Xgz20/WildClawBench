#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`参数格式错误: ${key ?? ""}`);
    }
    result[key.slice(2)] = value;
  }
  return result;
}

function loadJson(filename) {
  const value = JSON.parse(fs.readFileSync(filename, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`JSON 顶层必须是对象: ${filename}`);
  }
  return value;
}

export function buildScoreInput(contract) {
  return {
    evaluation_status: "completed",
    evaluation_error: null,
    site_url: "http://127.0.0.1:4173",
    browser: { name: "", viewport: "" },
    criteria: (contract.criteria ?? []).map((item) => ({
      key: item.key,
      score: null,
      reason: "",
      actions: [],
      evidence: [],
    })),
    aesthetic_score: null,
    aesthetic_reason: null,
    scorer: { agent: "", model: "", session_id: "" },
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args["task-contract"] || !args.output) {
    throw new Error("必须提供 --task-contract 和 --output");
  }
  const output = path.resolve(args.output);
  if (fs.existsSync(output)) {
    throw new Error(`拒绝覆盖已有评分输入: ${output}`);
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(
    output,
    `${JSON.stringify(buildScoreInput(loadJson(args["task-contract"])), null, 2)}\n`,
    "utf8",
  );
  process.stdout.write(`PASS: ${output}\n`);
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`FAIL: ${error.message}\n`);
    process.exitCode = 2;
  }
}
