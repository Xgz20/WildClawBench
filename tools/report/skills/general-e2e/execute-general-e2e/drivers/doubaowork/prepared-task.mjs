import { createHash } from "node:crypto";
import { lstat, readFile } from "node:fs/promises";
import { isAbsolute, resolve, relative, join, sep, parse } from "node:path";

const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const inside = (root, path) => {
  const rel = relative(root, path);
  return rel && rel !== ".." && !rel.startsWith(`..${sep}`) && !isAbsolute(rel);
};

async function ordinaryChain(path, kind) {
  let current = parse(path).root;
  for (const part of path.slice(current.length).split(sep).filter(Boolean)) {
    current = join(current, part);
    const st = await lstat(current);
    if (st.isSymbolicLink() || (current !== path && !st.isDirectory())) {
      throw new Error("DOUBAOWORK_PREPARED_PATH_UNSAFE");
    }
    if (current === path && !(kind === "file" ? st.isFile() : st.isDirectory())) {
      throw new Error("DOUBAOWORK_PREPARED_PATH_TYPE_INVALID");
    }
  }
}

export async function validateGeneralTask({ unitRoot, taskId, expectedPermission = "current" }) {
  if (!isAbsolute(unitRoot || "") || !/^[A-Za-z0-9][A-Za-z0-9_-]+$/u.test(taskId || "")) {
    throw new Error("DOUBAOWORK_GENERAL_INPUT_INVALID");
  }
  unitRoot = resolve(unitRoot);
  const manifestPath = join(unitRoot, "manifest.json");
  await ordinaryChain(manifestPath, "file");
  const manifestBytes = await readFile(manifestPath);
  const manifest = JSON.parse(manifestBytes);
  if (manifest.schema_id !== "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
      || manifest.manifest_kind !== "execution" || manifest.unit?.harness?.id !== "doubaowork"
      || !/^macos(?:-[a-z0-9-]+)?$/u.test(manifest.unit.harness.platform || "")) {
    throw new Error("DOUBAOWORK_GENERAL_MANIFEST_INVALID");
  }
  const tasks = manifest.tasks?.filter(t => t.task_id === taskId);
  if (tasks?.length !== 1) throw new Error("DOUBAOWORK_GENERAL_TASK_AMBIGUOUS");
  const task = tasks[0], taskRoot = join(unitRoot, "execution", "tasks", taskId);
  const resolveMember = value => {
    if (typeof value !== "string" || isAbsolute(value) || value.includes("\\") || value.split("/").some(x => !x || x === "." || x === "..")) {
      throw new Error("DOUBAOWORK_GENERAL_MEMBER_UNSAFE");
    }
    const result = resolve(unitRoot, value);
    if (!inside(taskRoot, result)) throw new Error("DOUBAOWORK_GENERAL_MEMBER_OUTSIDE_TASK");
    return result;
  };
  const promptFile = resolveMember(task.prompt?.path);
  const candidateWorkspace = resolveMember(task.workspace?.path);
  await ordinaryChain(promptFile, "file");
  await ordinaryChain(candidateWorkspace, "directory");
  const promptBytes = await readFile(promptFile), prompt = promptBytes.toString("utf8");
  if (!prompt.trim() || sha(promptBytes) !== task.prompt.sent_sha256) throw new Error("DOUBAOWORK_GENERAL_PROMPT_DRIFT");
  const requestedModel = manifest.unit.model?.requested_id;
  if (typeof requestedModel !== "string" || !requestedModel.trim()) throw new Error("DOUBAOWORK_GENERAL_MODEL_MISSING");
  return {
    scene: "general", unitRoot, taskRoot, workspace: candidateWorkspace, candidateWorkspace, captureNativeTools: true, captureNativeLifecycle: true,
    promptFile, prompt, promptSha256: sha(promptBytes), promptBytes: promptBytes.length,
    manifestPath, manifestSha256: sha(manifestBytes), batchId: manifest.batch_id,
    taskId, taskName: task.task_name ?? null, requestedModel,
    requestedPermissionMode: expectedPermission, expectedAppVersion: manifest.unit.harness.version,
    frozenIdentity: {
      scene: "general", unit_root: unitRoot, batch_id: manifest.batch_id,
      unit_id: manifest.unit.unit_id, task_id: taskId, dataset: manifest.dataset,
      manifest_sha256: sha(manifestBytes), candidate_workspace: candidateWorkspace,
      native_tool_capture_policy: "doubaowork-local-tool-debug-sink/v1",
      native_lifecycle_capture_policy: "doubaowork-native-checkpoint-lifecycle/v1",
    },
  };
}

export async function validateGeneralResume(state, config) {
  const frozen = config.frozenIdentity;
  if (state.scene !== "general" || JSON.stringify(state.prepared) !== JSON.stringify(frozen)
      || state.prompt.sha256 !== config.promptSha256 || state.workspace !== config.workspace
      || state.requested.model !== config.requestedModel
      || state.requested.permission_mode !== config.requestedPermissionMode) {
    throw new Error("DOUBAOWORK_GENERAL_RESUME_DRIFT");
  }
}
