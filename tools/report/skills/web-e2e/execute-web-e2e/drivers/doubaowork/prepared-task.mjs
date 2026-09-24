import { createHash } from "node:crypto";
import { lstat, readdir, readFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, resolve } from "node:path";
import { sha256Text } from "./lib.mjs";
const FORBIDDEN_WORKSPACE_NAMES = new Set([".git", "eval", "gt", "private-scoring"]);
const sha256Buffer = value => createHash("sha256").update(value).digest("hex");
async function requireOrdinary(pathValue, type, label) {
  const info = await lstat(pathValue);
  const matches = type === "file" ? info.isFile() : info.isDirectory();
  if (!matches || info.isSymbolicLink()) {
    throw new Error(`${label} 不是普通${type === "file" ? "文件" : "目录"}：${pathValue}`);
  }
  return info;
}

async function inspectWorkspaceTree(root, relative = "") {
  const current = relative ? join(root, relative) : root;
  const entries = await readdir(current, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isSymbolicLink()) throw new Error(`workspace 禁止符号链接：${join(relative, entry.name)}`);
    if (FORBIDDEN_WORKSPACE_NAMES.has(entry.name)) {
      throw new Error(`workspace 包含禁止目录：${join(relative, entry.name)}`);
    }
    if (entry.isDirectory()) await inspectWorkspaceTree(root, join(relative, entry.name));
  }
}

export async function validatePreparedTaskRoot(taskRootValue) {
  if (typeof taskRootValue !== "string" || !taskRootValue.trim()) {
    throw new Error("--task-root 必填，且必须是 prepared execution 单题根目录的绝对路径");
  }
  if (!isAbsolute(taskRootValue)) throw new Error("task root 必须是绝对路径");
  const taskRoot = resolve(taskRootValue);
  await requireOrdinary(taskRoot, "directory", "单题根目录");
  const promptFile = join(taskRoot, "PROMPT.md");
  const candidateWorkspace = join(taskRoot, "workspace");
  await requireOrdinary(promptFile, "file", "PROMPT.md");
  await requireOrdinary(candidateWorkspace, "directory", "workspace");
  await inspectWorkspaceTree(candidateWorkspace);
  const prompt = await readFile(promptFile, "utf8");
  if (!prompt.trim()) throw new Error("PROMPT.md 不能为空");

  const harnessRoot = dirname(dirname(dirname(taskRoot)));
  const manifestPath = join(harnessRoot, "manifest.json");
  await requireOrdinary(manifestPath, "file", "Harness manifest");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  if (manifest.schema_version !== "wildclawbench.web-e2e-batch/v3") {
    throw new Error(`manifest schema_version 不受支持：${manifest.schema_version ?? "<missing>"}`);
  }
  if (manifest.harness?.id !== "doubaowork") {
    throw new Error(`manifest harness 必须是 doubaowork，实际为 ${manifest.harness?.id ?? "<missing>"}`);
  }
  const taskId = basename(taskRoot);
  const task = manifest.tasks?.find((item) => item.task_id === taskId);
  if (!task) throw new Error(`manifest 未声明当前 task：${taskId}`);
  if (resolve(harnessRoot, task.execution_dir) !== taskRoot
      || resolve(harnessRoot, task.prompt_file) !== promptFile) {
    throw new Error("manifest 中 execution_dir 或 prompt_file 与当前单题不一致");
  }
  return {
    taskRoot,
    workspace: taskRoot,
    candidateWorkspace,
    promptFile,
    prompt,
    promptSha256: sha256Text(prompt),
    promptBytes: Buffer.byteLength(prompt),
    manifestPath,
    manifestSha256: sha256Buffer(await readFile(manifestPath)),
    batchId: manifest.batch_id,
    taskId,
    taskName: task.task_name ?? null,
    taskSha256: task.task_sha256 ?? null,
  };
}
