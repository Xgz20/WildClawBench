#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SUBMISSION_SCHEMA = "wildclawbench.web-e2e-submission/v1";
const SCORE_SCHEMA = "wildclawbench.web-e2e-task-score/v1";
const SECRET_NAMES = new Set([".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json", "secrets.json", "my_api.json"]);
const SECRET_SUFFIXES = [".pem", ".key", ".p12", ".pfx"];
const FORBIDDEN_DIR_NAMES = new Set(["node_modules", ".git"]);

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`参数格式错误: ${key ?? ""}`);
    result[key.slice(2)] = value;
  }
  return result;
}

function loadJson(filename) {
  const value = JSON.parse(fs.readFileSync(filename, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error(`JSON 顶层必须是对象: ${filename}`);
  return value;
}

function auditTree(root) {
  if (!fs.existsSync(root)) return { files: [], forbiddenDirectories: [] };
  const files = [];
  const forbiddenDirectories = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const filename = path.join(root, entry.name);
    if (entry.isDirectory()) {
      if (FORBIDDEN_DIR_NAMES.has(entry.name)) forbiddenDirectories.push(filename);
      else {
        const nested = auditTree(filename);
        files.push(...nested.files);
        forbiddenDirectories.push(...nested.forbiddenDirectories);
      }
    } else if (entry.isFile()) files.push(filename);
  }
  return { files, forbiddenDirectories };
}

export function buildSubmission(packageRoot) {
  const manifest = loadJson(path.join(packageRoot, "manifest.json"));
  const entries = manifest.tasks ?? [];
  if (entries.length === 0) throw new Error("manifest.tasks 为空");
  const tasks = [];
  for (const entry of entries) {
    const scorePath = path.join(packageRoot, "score", "tasks", entry.task_id, "private-scoring", "task_score.json");
    if (!fs.existsSync(scorePath)) throw new Error(`缺少 task_score.json: ${entry.task_id}`);
    const score = loadJson(scorePath);
    if (score.schema_version !== SCORE_SCHEMA) throw new Error(`task_score schema 不兼容: ${entry.task_id}`);
    if (score.identity?.batch_id !== manifest.batch_id || score.identity?.task_id !== entry.task_id) {
      throw new Error(`task_score 身份与 manifest 不一致: ${entry.task_id}`);
    }
    if (score.execution?.status === "pending") throw new Error(`执行状态仍为 pending: ${entry.task_id}`);
    const scoringDir = path.dirname(scorePath);
    for (const criterion of score.evaluation?.criteria ?? []) {
      for (const evidence of criterion.evidence ?? []) {
        const raw = String(evidence?.path ?? "");
        const parts = raw.split(/[\\/]+/);
        if (!raw || path.isAbsolute(raw) || parts.includes("..") || parts[0] !== "evidence") {
          throw new Error(`评分证据必须位于 private-scoring/evidence 下: ${entry.task_id}: ${raw}`);
        }
        if (!fs.existsSync(path.join(scoringDir, ...parts))) throw new Error(`评分证据文件不存在: ${entry.task_id}: ${raw}`);
      }
    }
    tasks.push(score);
  }
  const harnessIds = new Set(tasks.map((task) => String(task.identity?.harness?.id ?? "")));
  const modelIds = new Set(tasks.map((task) => String(task.identity?.model?.id ?? "")));
  if (harnessIds.size !== 1 || modelIds.size !== 1) throw new Error("一个回传包只能包含一个 model@harness");
  const harnessId = [...harnessIds][0];
  const modelId = [...modelIds][0];
  if (!harnessId) throw new Error("回传前必须填写 harness.id");

  const audit = auditTree(packageRoot);
  const sensitive = [];
  for (const filename of audit.files) {
    const name = path.basename(filename).toLowerCase();
    if (SECRET_NAMES.has(name) || name.startsWith(".env.") || SECRET_SUFFIXES.some((suffix) => name.endsWith(suffix))) {
      sensitive.push(path.relative(packageRoot, filename).split(path.sep).join("/"));
    }
  }
  if (sensitive.length) throw new Error(`回传目录包含敏感文件，打包前必须处理: ${sensitive.join(", ")}`);
  if (audit.forbiddenDirectories.length) {
    const relative = audit.forbiddenDirectories.map((filename) => path.relative(packageRoot, filename).split(path.sep).join("/"));
    throw new Error(`回传目录包含不应打包的目录，请先删除: ${relative.join(", ")}`);
  }
  return {
    schema_version: SUBMISSION_SCHEMA,
    batch_id: manifest.batch_id,
    source_revision: manifest.source_revision ?? null,
    created_at: new Date().toISOString(),
    unit: {
      model_id: modelId || null,
      model_display_name: tasks[0].identity?.model?.display_name || modelId || null,
      harness_id: harnessId,
      harness_display_name: tasks[0].identity?.harness?.display_name || harnessId,
    },
    task_ids: entries.map((item) => item.task_id),
    tasks,
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args["package-root"]) throw new Error("必须提供 --package-root");
  const packageRoot = path.resolve(args["package-root"]);
  const output = path.resolve(args.output || path.join(packageRoot, "submission.json"));
  fs.writeFileSync(output, `${JSON.stringify(buildSubmission(packageRoot), null, 2)}\n`, "utf8");
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
