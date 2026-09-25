// Frozen Web batch peer admission. No runtime dependency on the General Skill.
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { lstat, readFile, realpath } from "node:fs/promises";
import { hostname } from "node:os";
import { join, resolve } from "node:path";
import { readWorkerLock } from "../../vendor/e2e-shared/doubaowork/controller.mjs";
const execFileAsync = promisify(execFile);
const sha = value => createHash("sha256").update(value).digest("hex");
export const isBoundNativeRequestId = value => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u.test(value || "");
async function ordinaryJson(file) {
  const info = await lstat(file);
  if (!info.isFile() || info.isSymbolicLink() || await realpath(file) !== resolve(file)) throw new Error("DOUBAOWORK_WEB_MANAGED_PEER_FILE_UNSAFE");
  return JSON.parse(await readFile(file, "utf8"));
}
async function startIdentity(pid) {
  try { const { stdout } = await execFileAsync("ps", ["-p", String(pid), "-o", "lstart="], { timeout: 3000 }); return stdout.trim(); }
  catch { return null; }
}

export function validateManagedPeers({ queue, ownTaskId, journals, manifestSha, runId, batchId }) {
  if (queue?.schema !== "wildclawbench.doubaowork-web-batch/v1" || queue.run_id !== runId
      || queue.manifest_sha256 !== manifestSha || !queue.tasks.some(t => t.task_id === ownTaskId)) throw new Error("DOUBAOWORK_WEB_PEER_QUEUE_MISMATCH");
  const peers = [], seen = new Set();
  for (const row of queue.tasks) {
    if (row.task_id === ownTaskId || row.phase !== "RUNNING") continue;
    const j = journals[row.task_id];
    if (!j || sha(j.attempt_id || "") !== row.attempt_id_sha256 || j.scene !== "web"
        || j.identity?.task_id !== row.task_id || j.identity?.batch_id !== batchId
        || j.client?.manifest_sha256 !== manifestSha || j.prepared?.mode !== "web-native-batch-task/v1"
        || j.prepared?.run_id !== runId || j.workspace !== row.task_root
        || j.send?.dispatch_attempt_count !== 1 || j.session?.prompt_readback?.status !== "verified"
        || !/^[0-9]{1,64}$/u.test(j.session?.conversation_id || "")
        || !isBoundNativeRequestId(j.session?.native_request_session_id)
        || queue.model && j.actual?.model !== queue.model
        || queue.client_version && j.client?.version !== queue.client_version) throw new Error("DOUBAOWORK_WEB_MANAGED_PEER_UNBOUND");
    const key = `${j.session.conversation_id}:${j.session.native_request_session_id}`;
    if (seen.has(key)) throw new Error("DOUBAOWORK_WEB_MANAGED_PEER_DUPLICATE");
    seen.add(key);
    peers.push({ conversation_id: j.session.conversation_id, native_request_session_id: j.session.native_request_session_id,
      workspace: j.workspace, task_id: row.task_id });
  }
  return { conversationIds: peers.map(x => x.conversation_id), sessionIds: peers.map(x => x.native_request_session_id), peers };
}

export async function managedPeerConversations(config, runId) {
  const root = join(config.harnessRoot, ".execute-web-e2e", "doubaowork-batch", runId);
  const owner = await readWorkerLock(join(root, ".doubaowork-driver.lock"));
  if (owner.host !== hostname() || owner.pid !== process.ppid
      || await startIdentity(owner.pid) !== owner.process_start_identity) throw new Error("DOUBAOWORK_WEB_PEER_OWNER_MISMATCH");
  const queue = await ordinaryJson(join(root, "state.json"));
  const journals = {};
  for (const row of queue.tasks.filter(t => t.task_id !== config.taskId && t.phase === "RUNNING")) {
    journals[row.task_id] = await ordinaryJson(join(root, "tasks", row.task_id, "automation_state.json"));
  }
  return validateManagedPeers({ queue, ownTaskId: config.taskId, journals, manifestSha: config.manifestSha256,
    runId, batchId: config.batchId });
}
