// Read every reserved native slot. A first-completion group wait is not a full
// concurrency snapshot, and an old cursor is not proof that a judge is active.
export async function collectNativeSnapshots(waitThreads, targets) {
  if (typeof waitThreads !== 'function' || !Array.isArray(targets) || !targets.length) throw Error('NATIVE_SNAPSHOT_INPUT_INVALID');
  if (new Set(targets.map(t => `${t.hostId}/${t.threadId}`)).size !== targets.length) throw Error('NATIVE_SNAPSHOT_DUPLICATE_TARGET');
  const settled = await Promise.allSettled(targets.map(async target => {
    if (!target.threadId || !target.hostId) throw Error('NATIVE_SNAPSHOT_IDENTITY_REQUIRED');
    // Deliberately omit afterCursor: this is a fresh bounded state snapshot.
    const raw = await waitThreads({ targets: [{threadId:target.threadId, hostId:target.hostId}], timeoutMs:0 });
    if (raw.isError) throw Error('NATIVE_SNAPSHOT_TOOL_ERROR');
    const content = raw.content?.find(c => c.type === 'text');
    const value = content ? JSON.parse(content.text) : raw;
    if (value.errors?.length) throw Error('NATIVE_SNAPSHOT_TARGET_ERROR');
    if (!Array.isArray(value.polls) || value.polls.length !== 1) throw Error('NATIVE_SNAPSHOT_INCOMPLETE');
    const poll = value.polls[0];
    if (poll.thread?.id !== target.threadId || poll.thread?.hostId !== target.hostId || !poll.cursor || !poll.latestTurn?.status) throw Error('NATIVE_SNAPSHOT_BINDING_INVALID');
    return { target, raw, poll, timedOut: value.timedOut === true };
  }));
  const failed = settled.find(r => r.status === 'rejected');
  if (failed) throw failed.reason;
  return settled.map(r => r.value);
}
