import { lstat, readFile, realpath } from "node:fs/promises";
import { hostname } from "node:os";
import { join, resolve } from "node:path";

async function ordinaryJson(path) {
  const st = await lstat(path);
  if (!st.isFile() || st.isSymbolicLink() || await realpath(path) !== resolve(path)) throw new Error("DOUBAOWORK_MANAGED_QUEUE_PATH_UNSAFE");
  return JSON.parse(await readFile(path, "utf8"));
}

export async function managedPeerConversations(config, queueId) {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/u.test(queueId)) throw new Error("DOUBAOWORK_MANAGED_QUEUE_ID_INVALID");
  const root = join(config.unitRoot, ".general-e2e/queues/doubaowork", queueId);
  const owner = await ordinaryJson(join(root, ".doubaowork-driver.lock"));
  if (owner.host !== hostname() || owner.pid !== process.ppid || !owner.instance_id) throw new Error("DOUBAOWORK_MANAGED_QUEUE_OWNER_MISMATCH");
  const queue = await ordinaryJson(join(root, "queue.json"));
  if (queue.schema !== "wildclawbench.doubaowork-general-queue/v1" || queue.config.unit_root !== config.unitRoot
      || queue.config.queue_id !== queueId || queue.config.manifest_sha256 !== config.manifestSha256
      || !queue.tasks.some(t => t.task_id === config.taskId)) throw new Error("DOUBAOWORK_MANAGED_QUEUE_BINDING_MISMATCH");
  const ids = [], sessions = [], peers = [];
  for (const row of queue.tasks) {
    if (row.task_id === config.taskId || !["RUNNING", "DISPATCHING", "NEEDS_ATTENTION"].includes(row.phase)) continue;
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]+$/u.test(row.task_id)) throw new Error("DOUBAOWORK_MANAGED_PEER_TASK_INVALID");
    const journal = await ordinaryJson(join(config.unitRoot, ".general-e2e/execution", row.task_id, "doubaowork/automation_state.json"));
    if (journal.attempt_id !== row.attempt_id || journal.scene !== "general" || journal.identity.task_id !== row.task_id
        || journal.client.manifest_sha256 !== config.manifestSha256 || journal.prepared.managed_queue_id !== queueId
        || journal.send.dispatch_attempt_count !== 1 || journal.session.prompt_readback.status !== "verified"
        || !/^[0-9]{1,64}$/u.test(journal.session.conversation_id || "")) throw new Error("DOUBAOWORK_MANAGED_PEER_UNBOUND");
    ids.push(journal.session.conversation_id);
    peers.push({ conversation_id: journal.session.conversation_id, workspace: journal.workspace,
      native_request_session_id: journal.session.native_request_session_id ?? null });
    if (journal.session.native_request_session_id) sessions.push(journal.session.native_request_session_id);
  }
  if (new Set(ids).size !== ids.length) throw new Error("DOUBAOWORK_MANAGED_PEER_DUPLICATE");
  return { conversationIds: ids, sessionIds: sessions, peers };
}
