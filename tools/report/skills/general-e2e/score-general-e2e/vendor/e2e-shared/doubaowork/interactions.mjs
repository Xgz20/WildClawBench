import { sha256Text } from "./lib.mjs";

export function summarizePendingConfirmations(facts, conversationId) {
  const pending = facts.filter(row => row.pending_confirmation === true);
  const valid = row => typeof row.id === "string" && /^[0-9]{1,64}$/u.test(row.id);
  const ids = [...new Set(pending.filter(valid).map(row => row.id))];
  return { conversation_ids: ids, count: ids.length, unknown_count: pending.filter(row => !valid(row)).length,
    bound_pending: ids.includes(conversationId) };
}

// Native file-access confirmation uses scene 2 and action types 1010/1011.
// Retain the history even when the card was resolved before the next UI poll;
// it cannot silently become a zero-human-intervention automatic execution.
export function inspectNativeAuthorizationHistory(snapshot, nativeRequestId) {
  if (typeof nativeRequestId !== "string" || !nativeRequestId
      || snapshot?.schema !== "wildclawbench.doubaowork-runtime-messages/v1"
      || snapshot.source !== "native-im.useMessageStore.getState"
      || snapshot.payload_sha256 !== sha256Text(JSON.stringify({ conversation_id: snapshot.conversation_id, maps: snapshot.maps }))) {
    throw new Error("DOUBAOWORK_INTERACTION_SOURCE_INVALID");
  }
  const rows = [];
  for (const name of ["messageMap", "localMessageMap"]) {
    for (const message of Object.values(snapshot.maps[name] || {})) {
      if (message.user_type !== 2) continue;
      for (const [index, block] of (message.content_blocks_v2 || []).entries()) {
        const q = block.content?.quick_reply_block;
        if (!Array.isArray(q?.items) || !q.items.some(item => [1010, 1011].includes(item.action_type))) continue;
        if (block.block_type !== 10080 || q.scene !== 2) throw new Error("DOUBAOWORK_AUTHORIZATION_PROFILE_UNVERIFIED");
        for (const item of q.items.filter(item => [1010, 1011].includes(item.action_type))) {
          let value; try { value = JSON.parse(item.schema_payload); } catch { throw new Error("DOUBAOWORK_AUTHORIZATION_PAYLOAD_INVALID"); }
          if (typeof value.tool_call_id !== "string" || !value.tool_call_id || value.agent_id !== nativeRequestId) throw new Error("DOUBAOWORK_AUTHORIZATION_SCOPE_MISMATCH");
          rows.push({ source_map: name, block_index: index, scene: q.scene, status: q.status,
            block_finished: block.is_finish === true, action_type: item.action_type,
            native_request_id_sha256: sha256Text(value.agent_id), tool_call_id_sha256: sha256Text(value.tool_call_id) });
        }
      }
    }
  }
  return rows;
}
