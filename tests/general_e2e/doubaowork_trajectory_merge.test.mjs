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


test("Native Edit success reconciles only the exact path and diff-backed rendered result", () => {
  const facts = { kind: "edit_success", toolName: "Edit", filePath: "/a", replaceAll: false,
    userModified: false, unifiedDiff: "--- /a\n+++ /a\n@@ -1 +1 @@\n-old\n+new\n" };
  const local = [{ phase: "started", tool_call_id: "e", tool_name: "Edit", input: { file_path: "/a", old_string: "old", new_string: "new" } },
    { phase: "settled", tool_call_id: "e", tool_name: "Edit", output: { status: "success", content: "",
      structuredResultFacts: { localFileMutationV2: facts } } }];
  const trace = [{ kind: "assistant_tool_call", call_id: "e", tool_name: "Edit", arguments: local[0].input },
    { kind: "tool_result", call_id: "e", content: "The file /a has been updated successfully." }];
  assert.equal(mergeNativeToolTimeline(trace, local).order_verified, true);
  trace[1].content = "The file /other has been updated successfully.";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
  trace[1].content = "The file /a has been updated successfully.";
  local[1].output.structuredResultFacts.localFileMutationV2.unifiedDiff = "--- /b\n+++ /b\n";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
  local[1].output.structuredResultFacts.localFileMutationV2.unifiedDiff = "--- /a\n+++ /a\n";
  local[1].output.status = "error";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
});

test("Image Read bypass matches only exact path-bound successful native and model wrappers", () => {
  const path = "/workspace/render.jpg";
  const local = [{ phase: "started", tool_call_id: "image", tool_name: "Read", input: { file_path: path, thumbnail_size: "full" } },
    { phase: "settled", tool_call_id: "image", tool_name: "Read", output: { status: "success",
      content: `Read "${path}" as image for upload.`, structuredResultFacts: { localFileReadV2Bypass: { reason: "image" } } } }];
  const trace = [{ kind: "assistant_tool_call", call_id: "image", tool_name: "Read", arguments: { file_path: path } },
    { kind: "tool_result", call_id: "image", content: `Read media file ${path} (image). See the attachment in the multimodal content that follows.` }];
  assert.equal(mergeNativeToolTimeline(trace, local).order_verified, true);
  trace[1].content = `Read media file /other.jpg (image). See the attachment in the multimodal content that follows.`;
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
  trace[1].content = `Read media file ${path} (image). See the attachment in the multimodal content that follows.`;
  local[1].output.structuredResultFacts.localFileReadV2Bypass.reason = "unknown";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /TOOL_CONFLICT/);
  local[1].output.structuredResultFacts.localFileReadV2Bypass.reason = "image";
  local[1].output.content = "Read wrong image";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /TOOL_CONFLICT/);
});

test("Native Edit FILE_NOT_FOUND maps only the same failed call and cwd note", () => {
  const path = "/missing/page.html", cwd = "/workspace/task";
  const local = [{ phase: "started", tool_call_id: "missing", tool_name: "Edit", input: { file_path: path } },
    { phase: "settled", tool_call_id: "missing", tool_name: "Edit", output: { status: "error", content: "",
      structuredResultFacts: { localFileMutationV2: { kind: "failure", toolName: "Edit", error: { code: "FILE_NOT_FOUND",
        message: "File does not exist.", details: { cwd, filePath: path } } } } } }];
  const trace = [{ kind: "assistant_tool_call", call_id: "missing", tool_name: "Edit", arguments: { file_path: path } },
    { kind: "tool_result", call_id: "missing", content: `File does not exist. Note: your current working directory is ${cwd}.` }];
  assert.equal(mergeNativeToolTimeline(trace, local).order_verified, true);
  trace[1].content = "File does not exist. Note: your current working directory is /other.";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
  trace[1].content = `File does not exist. Note: your current working directory is ${cwd}.`;
  local[1].output.structuredResultFacts.localFileMutationV2.error.details.filePath = "/other";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
  local[1].output.structuredResultFacts.localFileMutationV2.error.details.filePath = path;
  local[1].output.status = "success";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
});

test("Native Write update maps only the exact successful diff-backed rendered path", () => {
  const path = "/workspace/page.html";
  const local = [{ phase: "started", tool_call_id: "update", tool_name: "Write", input: { file_path: path } },
    { phase: "settled", tool_call_id: "update", tool_name: "Write", output: { status: "success", content: "",
      structuredResultFacts: { localFileMutationV2: { kind: "write_success", toolName: "Write", type: "update", created: false,
        filePath: path, unifiedDiff: `--- ${path}\n+++ ${path}\n@@ -1 +1 @@\n-old\n+new\n` } } } }];
  const trace = [{ kind: "assistant_tool_call", call_id: "update", tool_name: "Write", arguments: { file_path: path } },
    { kind: "tool_result", call_id: "update", content: `The file ${path} has been updated successfully.` }];
  assert.equal(mergeNativeToolTimeline(trace, local).order_verified, true);
  trace[1].content = "The file /foreign has been updated successfully.";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
  trace[1].content = `The file ${path} has been updated successfully.`;
  local[1].output.structuredResultFacts.localFileMutationV2.unifiedDiff = "--- /foreign\n+++ /foreign\n";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
});

test("Native TaskOutput wrapper reconciles only identical task ID, success and stdout bytes", () => {
  const taskId = "11111111-1111-4111-8111-111111111111", stdout = "line one\nline two";
  const local = [{ phase: "started", tool_call_id: "task-output", tool_name: "TaskOutput", input: { task_id: taskId, block: true, timeout: 1000 } },
    { phase: "settled", tool_call_id: "task-output", tool_name: "TaskOutput", output: { status: "success",
      content: `Shell task '${taskId}' is completed.exit code 0. stdout: ${stdout}` } }];
  const trace = [{ kind: "assistant_tool_call", call_id: "task-output", tool_name: "TaskOutput", arguments: local[0].input },
    { kind: "tool_result", call_id: "task-output", content: `Task ${taskId} has finished with final status completed, exit code 0. The result has been consumed; do not query the same task_id again.\nstdout:\n${stdout}` }];
  assert.equal(mergeNativeToolTimeline(trace, local).order_verified, true);
  trace[1].content += "\nextra";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
  trace[1].content = `Task ${taskId} has finished with final status completed, exit code 0. The result has been consumed; do not query the same task_id again.\nstdout:\n${stdout}`;
  local[1].output.status = "error";
  assert.throws(() => mergeNativeToolTimeline(trace, local), /RESULT_CONFLICT/);
});
