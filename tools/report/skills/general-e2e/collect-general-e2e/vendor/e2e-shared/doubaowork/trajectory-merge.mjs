import { canonicalNativePayload, deduplicateTrajectoryEvents } from "./native-evidence.mjs";

const equal = (a, b) => JSON.stringify(canonicalNativePayload(a)) === JSON.stringify(canonicalNativePayload(b));
function inputMatches(event, native, result) {
  if (equal(event.arguments, native.input)) return true;
  // The persisted model call can omit the protocol's image thumbnail hint.
  // Admit only this observed difference for an actually returned text Read;
  // both original payloads remain archived, all other arguments must match.
  if (event.tool_name !== "Read" || event.arguments?.thumbnail_size !== undefined
      || native.input?.thumbnail_size !== "full") return false;
  const text = result.output?.structuredResultFacts?.localFileReadV2?.kind === "text";
  const image = result.output?.status === "success"
    && result.output?.structuredResultFacts?.localFileReadV2Bypass?.reason === "image"
    && typeof native.input.file_path === "string"
    && result.output.content === `Read "${native.input.file_path}" as image for upload.`;
  if (!text && !image) return false;
  const { thumbnail_size, ...rest } = native.input;
  return equal(event.arguments, rest);
}

/** Use only explicit native order edges and observed-before bounds. If two
 * events remain incomparable, do not choose an arbitrary topological order. */
export function mergeObservedToolTimeline(snapshots, local) {
  const union = deduplicateTrajectoryEvents(snapshots.flatMap(s => s.events)).events;
  const toolEvents = union.filter(e => ["assistant_tool_call", "tool_result"].includes(e.kind));
  // Reuse exact payload reconciliation; this result is not an ordering proof.
  mergeNativeToolTimeline(toolEvents, local);
  const localIds = new Set(local.map(e => e.tool_call_id));
  const keyFor = e => `${e.kind === "assistant_tool_call" ? "started" : "settled"}:${e.call_id}`;
  const expected = new Set([...toolEvents.map(keyFor), ...local.map(e => `${e.phase}:${e.tool_call_id}`)]);
  // A complete native model transcript already defines its request/result
  // order. The client's serialized execution of parallel requests is another
  // ordering; forcing both onto one list would manufacture a false conflict.
  for (const snapshot of [...snapshots].reverse()) {
    const events = deduplicateTrajectoryEvents(snapshot.events).events;
    const tools = events.filter(e => ["assistant_tool_call", "tool_result"].includes(e.kind));
    const present = new Set(tools.map(keyFor));
    if (present.size !== expected.size || [...expected].some(k => !present.has(k))) continue;
    const calls = new Set(), settled = new Set(); let valid = true;
    for (const e of tools) {
      if (e.kind === "assistant_tool_call") { if (calls.has(e.call_id)) valid = false; calls.add(e.call_id); }
      else { if (!calls.has(e.call_id) || settled.has(e.call_id)) valid = false; settled.add(e.call_id); }
    }
    if (!valid || calls.size !== settled.size) continue;
    const dispatch = new Map(local.map(e => [`${e.phase}:${e.tool_call_id}`, e]));
    return { order_verified: true, basis: "complete-native-model-transcript-order; local execution times retained separately",
      entries: events.map(event => ({ source: "trajectory", event, native_canonical: true, execution_event: dispatch.get(keyFor(event)) })) };
  }
  if (toolEvents.every(e => localIds.has(e.call_id))) return mergeNativeToolTimeline(toolEvents, local);
  const nodes = new Map(local.map(e => [`${e.phase}:${e.tool_call_id}`, { source: "local", event: e }]));
  for (const e of toolEvents) if (!localIds.has(e.call_id)) nodes.set(keyFor(e), { source: "trajectory", event: e });
  const edges = new Map([...nodes.keys()].map(k => [k, new Set()]));
  const edge = (a, b) => { if (a !== b) { if (!nodes.has(a) || !nodes.has(b)) throw new Error("DOUBAOWORK_TIMELINE_NODE_MISSING"); edges.get(a).add(b); } };
  for (let i = 1; i < local.length; i++) edge(`${local[i - 1].phase}:${local[i - 1].tool_call_id}`, `${local[i].phase}:${local[i].tool_call_id}`);
  for (const s of snapshots) {
    const at = s.captured_at === null ? null : Date.parse(s.captured_at);
    if (at !== null && !Number.isFinite(at)) throw new Error("DOUBAOWORK_TIMELINE_OBSERVATION_TIME_INVALID");
    const events = deduplicateTrajectoryEvents(s.events).events.filter(e => ["assistant_tool_call", "tool_result"].includes(e.kind));
    for (let i = 1; i < events.length; i++) edge(keyFor(events[i - 1]), keyFor(events[i]));
    if (at !== null) for (const e of events.filter(e => !localIds.has(e.call_id))) {
      const later = local.find(l => Date.parse(l.observed_at) > at);
      if (later) edge(keyFor(e), `${later.phase}:${later.tool_call_id}`);
    }
  }
  for (const e of toolEvents.filter(e => !localIds.has(e.call_id) && e.kind === "assistant_tool_call")) edge(keyFor(e), `settled:${e.call_id}`);
  const degree = new Map([...nodes.keys()].map(k => [k, 0]));
  for (const targets of edges.values()) for (const b of targets) degree.set(b, degree.get(b) + 1);
  const entries = [];
  while (degree.size) {
    const ready = [...degree.keys()].filter(k => degree.get(k) === 0);
    if (ready.length !== 1) return { order_verified: false, basis: ready.length ? "native-order-incomparable" : "native-order-conflict",
      entries: [...local.map(event => ({ source: "local", event })), ...toolEvents.filter(e => !localIds.has(e.call_id)).map(event => ({ source: "trajectory", event }))] };
    const key = ready[0]; entries.push(nodes.get(key)); degree.delete(key);
    for (const b of edges.get(key)) degree.set(b, degree.get(b) - 1);
  }
  return { order_verified: true, basis: "unique-native-order+same-host-observation-upper-bounds", entries };
}

function resultMatches(native, content, start) {
  if (typeof native.output?.content === "string" && native.output.content === content) return true;
  const mutation = native.output?.structuredResultFacts?.localFileMutationV2;
  if (native.tool_name === "Write" && native.output.status === "success" && mutation?.kind === "write_success"
      && mutation.toolName === "Write" && mutation.type === "create" && mutation.created === true
      && typeof mutation.filePath === "string" && `File created successfully at: ${mutation.filePath}` === content) return true;
  // 2.31.6 serializes a successful local Edit as a fixed model-visible
  // sentence while the local result ledger retains the diff and exact path.
  // Require the same call ID (checked by the caller), success, tool identity,
  // path, diff header and rendered sentence; other shapes stay conflicting.
  if (native.tool_name === "Edit" && native.output?.status === "success"
      && mutation?.kind === "edit_success" && mutation.toolName === "Edit"
      && mutation.userModified === false && mutation.replaceAll === false
      && typeof mutation.filePath === "string"
      && typeof mutation.unifiedDiff === "string"
      && mutation.unifiedDiff.startsWith(`--- ${mutation.filePath}\n+++ ${mutation.filePath}\n`)
      && content === `The file ${mutation.filePath} has been updated successfully.`) return true;
  // Native image Read bypasses the text reader. Match only the bound input
  // path and the two exact successful protocol wrappers. Raw multimodal bytes
  // remain archived; the normalized result content is explicitly partial.
  const image = native.output?.structuredResultFacts?.localFileReadV2Bypass;
  const imagePath = start?.input?.file_path;
  if (native.tool_name === "Read" && native.output?.status === "success" && image?.reason === "image"
      && typeof imagePath === "string"
      && native.output.content === `Read "${imagePath}" as image for upload.`
      && content === `Read media file ${imagePath} (image). See the attachment in the multimodal content that follows.`) return true;
  const failure = native.output?.structuredResultFacts?.localFileMutationV2;
  const error = failure?.error, details = error?.details;
  if (native.tool_name === "Edit" && native.output?.status === "error" && native.output.content === ""
      && failure?.kind === "failure" && failure.toolName === "Edit"
      && error?.code === "FILE_NOT_FOUND" && error.message === "File does not exist."
      && typeof details?.cwd === "string" && details.cwd.startsWith("/")
      && details.filePath === start?.input?.file_path
      && content === `File does not exist. Note: your current working directory is ${details.cwd}.`) return true;
  if (native.tool_name === "Write" && native.output?.status === "success"
      && mutation?.kind === "write_success" && mutation.toolName === "Write"
      && mutation.type === "update" && mutation.created === false
      && typeof mutation.filePath === "string"
      && typeof mutation.unifiedDiff === "string"
      && mutation.unifiedDiff.startsWith(`--- ${mutation.filePath}\n+++ ${mutation.filePath}\n`)
      && content === `The file ${mutation.filePath} has been updated successfully.`) return true;
  if (native.tool_name === "TaskOutput" && native.output?.status === "success"
      && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u.test(start?.input?.task_id || "")) {
    const taskId = start.input.task_id;
    const nativePrefix = `Shell task '${taskId}' is completed.exit code 0. stdout: `;
    const modelPrefix = `Task ${taskId} has finished with final status completed, exit code 0. The result has been consumed; do not query the same task_id again.\nstdout:\n`;
    if (typeof native.output.content === "string" && native.output.content.startsWith(nativePrefix)
        && content === modelPrefix + native.output.content.slice(nativePrefix.length)) return true;
  }
  const read = native.output?.structuredResultFacts?.localFileReadV2;
  // Native Read v2 renders this footer only for an untruncated text EOF.
  return native.tool_name === "Read" && read?.kind === "text" && read.truncated === false
    && Number.isInteger(read.offset) && Number.isInteger(read.returnedLineCount) && Number.isInteger(read.totalLines)
    && read.offset + read.returnedLineCount - 1 >= read.totalLines
    && typeof read.body === "string" && `${read.body}\n\n[End of file.]` === content;
}

/** Keep the native model-visible trajectory prefix, then append a proven local
 * tail. A union without a common completed-call boundary remains unordered. */
export function mergeNativeToolTimeline(trajectory, local) {
  const starts = new Map(local.filter(e => e.phase === "started").map(e => [e.tool_call_id, e]));
  const results = new Map(local.filter(e => e.phase === "settled").map(e => [e.tool_call_id, e]));
  const shared = new Set(), sharedResults = new Set();
  const remote = trajectory.filter(e => e.kind === "assistant_tool_call" && !starts.has(e.call_id));
  for (const e of trajectory) {
    if (!starts.has(e.call_id)) continue;
    if (e.kind === "assistant_tool_call") {
      const n = starts.get(e.call_id);
      if (e.tool_name !== n.tool_name || !inputMatches(e, n, results.get(e.call_id))) throw new Error("DOUBAOWORK_CROSS_SOURCE_TOOL_CONFLICT");
      shared.add(e.call_id);
    } else if (e.kind === "tool_result") {
      const n = results.get(e.call_id);
      if (!n || !resultMatches(n, e.content, starts.get(e.call_id))) throw new Error("DOUBAOWORK_CROSS_SOURCE_RESULT_CONFLICT");
      sharedResults.add(e.call_id);
    }
  }
  if (!remote.length && local.length) return {
    order_verified: true, basis: "bound-local-event-order; trajectory has no additional tools",
    shared_call_count: shared.size, entries: local.map(event => ({ source: "local", event })),
  };
  const tail = local.filter(e => !shared.has(e.tool_call_id));
  const boundary = local.reduce((last, e, i) => shared.has(e.tool_call_id) ? i : last, -1);
  const prefixClosed = shared.size === sharedResults.size && [...shared].every(id => sharedResults.has(id))
    && local.slice(0, boundary + 1).every(e => shared.has(e.tool_call_id));
  const toolEvents = trajectory.filter(e => ["assistant_tool_call", "tool_result"].includes(e.kind));
  const last = toolEvents.at(-1);
  const tailAnchored = !tail.length || (!remote.length && !shared.size)
    || last?.kind === "tool_result" && sharedResults.has(last.call_id);
  const verified = prefixClosed && tailAnchored;
  if (!verified) return {
    order_verified: false, basis: "unordered-union; no complete shared prefix boundary",
    entries: [...local.map(event => ({ source: "local", event })),
      ...trajectory.filter(e => !starts.has(e.call_id)).map(event => ({ source: "trajectory", event }))],
  };
  return {
    order_verified: true, basis: "native-model-transcript-prefix+bound-local-event-tail",
    shared_call_count: shared.size,
    entries: [...trajectory.map(event => ({ source: "trajectory", event,
      local: event.kind === "assistant_tool_call" ? starts.get(event.call_id)
        : event.kind === "tool_result" ? results.get(event.call_id) : undefined })),
    ...tail.map(event => ({ source: "local", event }))],
  };
}
