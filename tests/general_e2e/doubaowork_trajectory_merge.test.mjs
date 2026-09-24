import assert from "node:assert/strict";
import { test } from "node:test";
import { mergeNativeToolTimeline, mergeObservedToolTimeline } from "../../tools/report/e2e-shared/doubaowork/trajectory-merge.mjs";

const local = id => [{ phase: "started", tool_call_id: id, tool_name: "Bash", input: { command: id } },
  { phase: "settled", tool_call_id: id, tool_name: "Bash", output: { content: `result-${id}` } }];
const trace = (id, tool = "Bash") => [{ kind: "assistant_tool_call", call_id: id, tool_name: tool, arguments: { command: id } },
  { kind: "tool_result", call_id: id, content: `result-${id}` }];

test("A captured native fragment plus an observed-before bound uniquely orders a rolling remote tool", () => {
  const l = [...local("a"), ...local("b"), ...local("c")].map((e, i) => ({ ...e, observed_at: new Date((i + 1) * 1000).toISOString() }));
  const fragment = [...trace("b"), ...trace("r", "calculator")];
  const r = mergeObservedToolTimeline([{ events: fragment, captured_at: new Date(4500).toISOString() }], l);
  assert.equal(r.order_verified, true);
  assert.deepEqual(r.entries.map(e => e.event.call_id || e.event.tool_call_id), ["a", "a", "b", "b", "r", "r", "c", "c"]);
  assert.equal(mergeObservedToolTimeline([{ events: fragment, captured_at: null }], l).order_verified, false);
  assert.equal(mergeObservedToolTimeline([{ events: fragment, captured_at: new Date(7000).toISOString() }], l).order_verified, false);
  assert.throws(() => mergeObservedToolTimeline([{ events: fragment, captured_at: "bad" }], l), /TIME_INVALID/);
});

test("Complete native request groups retain model-visible order separately from serial local execution", () => {
  const a = trace("a"), b = trace("b"), remote = trace("r", "calculator");
  const native = [a[0], b[0], a[1], b[1], ...remote];
  const l = [...local("a"), ...local("b")];
  const result = mergeObservedToolTimeline([{ events: native, captured_at: null }], l);
  assert.equal(result.order_verified, true); assert.match(result.basis, /complete-native-model/);
  assert.deepEqual(result.entries.map(e => e.event.call_id), ["a", "b", "a", "b", "r", "r"]);
  assert.equal(result.entries[0].native_canonical, true);
  assert.equal(result.entries[0].execution_event.phase, "started");
  // A missing local call cannot be hidden by selecting a convenient snapshot.
  assert.equal(mergeObservedToolTimeline([{ events: native, captured_at: null }], [...l, ...local("missing")]).order_verified, false);
});

test("A matching native transcript prefix anchors remote events before the local tail", () => {
  const t = [...trace("a"), ...trace("r", "calculator"), ...trace("b")];
  const result = mergeNativeToolTimeline(t, [...local("a"), ...local("b"), ...local("c")]);
  assert.equal(result.order_verified, true); assert.equal(result.shared_call_count, 2);
  assert.deepEqual(result.entries.map(e => e.event.call_id || e.event.tool_call_id), ["a", "a", "r", "r", "b", "b", "c", "c"]);
  assert.equal(result.entries[0].local.phase, "started");
});

test("Missing local prefixes, unclosed anchors, or remote-only tails stay unordered", () => {
  for (const [t, l] of [
    [[...trace("r", "calculator")], local("a")],
    [[...trace("b"), ...trace("r", "calculator")], [...local("a"), ...local("b"), ...local("c")]],
    [[...trace("a"), ...trace("r", "calculator")], [...local("a"), ...local("c")]],
    [[trace("a")[0], ...trace("r", "calculator")], local("a")],
  ]) assert.equal(mergeNativeToolTimeline(t, l).order_verified, false);
});

test("A rolling local-only trajectory cannot downgrade the complete native local order", () => {
  const r = mergeNativeToolTimeline(trace("b"), [...local("a"), ...local("b"), ...local("c")]);
  assert.equal(r.order_verified, true);
  assert.deepEqual(r.entries.map(e => e.event.tool_call_id), ["a", "a", "b", "b", "c", "c"]);
});

test("Shared call input and rendered results must agree with captured protocol payloads", () => {
  const t = trace("a");t[0].arguments.command = "other";
  assert.throws(() => mergeNativeToolTimeline(t, local("a")), /TOOL_CONFLICT/);
  const r = trace("a");r[1].content = "different result";
  assert.throws(() => mergeNativeToolTimeline(r, local("a")), /RESULT_CONFLICT/);
  const read = [{ phase: "started", tool_call_id: "a", tool_name: "Read", input: { file_path: "/a" } },
    { phase: "settled", tool_call_id: "a", tool_name: "Read", output: { content: "", structuredResultFacts: {
      localFileReadV2: { kind: "text", body: "line", offset: 1, returnedLineCount: 1, totalLines: 1, truncated: false } } } }];
  const rendered = [{ kind: "assistant_tool_call", call_id: "a", tool_name: "Read", arguments: { file_path: "/a" } },
    { kind: "tool_result", call_id: "a", content: "line\n\n[End of file.]" }];
  assert.equal(mergeNativeToolTimeline(rendered, read).order_verified, true);
  read[0].input.thumbnail_size = "full";
  assert.equal(mergeNativeToolTimeline(rendered, read).order_verified, true);
  read[0].input.limit = 200;
  assert.throws(() => mergeNativeToolTimeline(rendered, read), /TOOL_CONFLICT/);
  delete read[0].input.limit;
  read[1].output.structuredResultFacts.localFileReadV2.truncated = true;
  assert.throws(() => mergeNativeToolTimeline(rendered, read), /RESULT_CONFLICT/);
});

test("Native Write create facts reconcile only the exact successful rendered result", () => {
  const l = [{ phase: "started", tool_call_id: "w", tool_name: "Write", input: { file_path: "/a" } },
    { phase: "settled", tool_call_id: "w", tool_name: "Write", output: { status: "success", content: "", structuredResultFacts: {
      localFileMutationV2: { kind: "write_success", toolName: "Write", type: "create", created: true, filePath: "/a" } } } }];
  const t = [{ kind: "assistant_tool_call", call_id: "w", tool_name: "Write", arguments: { file_path: "/a" } },
    { kind: "tool_result", call_id: "w", content: "File created successfully at: /a" }];
  assert.equal(mergeNativeToolTimeline(t, l).order_verified, true);
  t[1].content = "File created successfully at: /other";
  assert.throws(() => mergeNativeToolTimeline(t, l), /RESULT_CONFLICT/);
});
