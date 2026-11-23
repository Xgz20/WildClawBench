// The SDK response itself is retained. Only the redundant desktop mirror may
// be absent immediately before an explicit compaction boundary.
export function verifyAssistantMirrors(assistants, mirrors, bytes, state) {
  const rows = bytes.toString('utf8').split('\n').map(line => line.trim() ? JSON.parse(line) : null);
  const gaps = [];
  let next = 0;
  const require = ok => { if (!ok) throw Error('ROLLOUT_ASSISTANT_MIRROR_CONFLICT'); };
  for (const assistant of assistants) {
    if (mirrors[next]?.content === assistant.content) { next += 1; continue; }
    const line = Number(assistant.source.raw_ref.split('#L')[1]);
    const row = rows[line - 1], payload = row?.payload;
    require(row?.type === 'response_item' && payload?.type === 'message' && payload.role === 'assistant'
      && typeof payload.id === 'string' && payload.id
      && payload.internal_chat_message_metadata_passthrough?.turn_id === state.session.turn_id);
    let boundary = line;
    while (rows[boundary]?.type === 'event_msg' && rows[boundary].payload?.type === 'token_count') boundary += 1;
    const compacted = rows[boundary], start = Date.parse(row.timestamp), end = Date.parse(compacted?.timestamp);
    require(compacted?.type === 'compacted' && typeof compacted.payload?.message === 'string'
      && Array.isArray(compacted.payload?.replacement_history) && Number.isFinite(start) && Number.isFinite(end)
      && end >= start);
    // Physical source adjacency, the bound turn and explicit compaction prove
    // this redundant-mirror gap. Compaction persistence latency is not a
    // content-identity test; retain longer delays as an explicit audit profile.
    const gap = { response_line: line, response_id: payload.id, compaction_line: boundary + 1,
      reason: 'Original SDK message retained; redundant UI mirror absent immediately before explicit compaction.' };
    if (end - start > 1000) {
      gap.profile = 'bound-sdk-adjacent-compaction-latency/v1';
      gap.persistence_delay_ms = end - start;
    }
    gaps.push(gap);
  }
  require(next === mirrors.length);
  return gaps;
}
