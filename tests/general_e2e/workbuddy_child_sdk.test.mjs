import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { artifact, jsonBytes } from "../../tools/report/e2e-shared/workbuddy-jsonl-metrics/index.mjs";
import { bindChildSdk, childSdkProof, discoverChildSdk, verifyChildSdkArchive, CHILD_SDK_PROOF } from "../../tools/report/e2e-shared/workbuddy-jsonl-metrics/children.mjs";

function fixture() {
  const identity = { batch_id: "batch", unit_id: "unit", task_id: "task", attempt_id: "attempt" };
  const session = { thread_id: null, session_id: "parent-session", turn_id: "parent-request", cwd: "/fixture/workspace", verified: true };
  const args = { description: "Read fixture", prompt: "Read and validate the synthetic fixture.", subagent_type: "sheet-agent" };
  const tool = { type: "tool", title: "Agent", toolCallId: "call_parent", status: "completed", rawInput: args,
    _meta: { "codebuddy.ai/toolName": "Agent", "codebuddy.ai/isSubagent": true,
      "codebuddy.ai/description": args.description, "codebuddy.ai/subagentType": "sheet-agent",
      "codebuddy.ai/requestId": session.turn_id, "codebuddy.ai/conversationRequestId": session.turn_id,
      "codebuddy.ai/modelRequestId": "response-parent", "codebuddy.ai/llmMessageId": "response-parent" } };
  const snapshot = { conversation: { id: session.session_id, state: "idle", hasActiveChildAgents: false, space: { cwd: session.cwd } },
    request: { id: session.turn_id, state: "completed", timestamp: 50, completedAt: 1000, assistantMessage: { state: "completed", content: [tool] } } };
  const primary = [
    { type: "file-history-snapshot", value: "not a model event" },
    { id: "parent-call", type: "function_call", name: "Agent", callId: "call_parent", timestamp: 100,
      arguments: JSON.stringify(args), providerData: { messageId: "response-parent" } },
    { id: "parent-return", type: "function_call_result", name: "Agent", callId: "call_parent", timestamp: 900, status: "completed" },
  ];
  const row = value => ({ sessionId: "child-session", cwd: session.cwd,
    providerData: { conversationRequestId: "child-request", agent: "sheet-agent" },
    _meta: { baggage: `codebuddy.session_id=${session.session_id},codebuddy.conversation_request_id=${session.turn_id}` }, ...value });
  const child = [
    row({ id: "child-user", type: "message", role: "user", timestamp: 101, content: [{ type: "input_text", text: args.prompt }],
      providerData: { conversationRequestId: "child-request", rootRequestId: session.turn_id, agent: "sheet-agent" } }),
    row({ id: "child-call", type: "function_call", name: "Read", callId: "call_child", timestamp: 200, arguments: "{}" }),
    row({ id: "child-result", type: "function_call_result", name: "Read", callId: "call_child", timestamp: 300,
      status: "completed", output: { type: "text", text: "Actual native fixture result." } }),
    row({ id: "child-final", type: "message", role: "assistant", timestamp: 400, status: "completed", content: "Done." }),
  ];
  const bytes = rows => Buffer.from(rows.map(x => JSON.stringify(x)).join("\n") + "\n");
  const sources = () => [{ name: "agent-fixture.jsonl", bytes: bytes(child), attachments: [
    { name: "agent-fixture/tool-results/call_child.txt", bytes: Buffer.from("Original native output.\n") },
    { name: "agent-fixture/tool-results/call_child-render.txt", bytes: Buffer.from("Separate native rendering.\n") },
  ] }];
  return { identity, session, snapshot, tool, args, primary, child, bytes, sources,
    bind() { return bindChildSdk(bytes(primary), snapshot, session, sources()); } };
}

test("child evidence retains independent identities, auxiliary bytes and primary scope", () => {
  const f = fixture(), before = f.bytes(f.primary), child = f.bytes(f.child), result = f.bind()[0];
  assert.equal(result.parent_tool_call_id, "call_parent");
  assert.equal(result.session_id, "child-session");
  assert.equal(result.transcript_status, "complete");
  assert.equal(result.observed_tool_call_count, 1);
  assert.equal(result.auxiliary_tool_results.length, 2);
  assert.equal(result.token_usage_scope, "not-included-in-primary-resource-metrics");
  assert.deepEqual(before, f.bytes(f.primary)); assert.deepEqual(child, f.bytes(f.child));
});

test("the exact empty-description projection uses full SDK arguments without filling the runtime", () => {
  const f = fixture(); f.tool.rawInput = { description: {} };
  assert.equal(f.bind()[0].argument_binding, "runtime-empty-description-sdk-full-arguments/v1");
  assert.deepEqual(f.tool.rawInput, { description: {} });
  f.tool._meta["codebuddy.ai/modelRequestId"] = "foreign-response";
  assert.throws(() => f.bind(), /PARENT_ARGUMENTS_MISMATCH/);
});

test("native incomplete or absent results remain partial and are never synthesized", () => {
  const f = fixture(); f.child[2].status = "incomplete";
  const result = f.bind()[0]; assert.equal(result.transcript_status, "partial");
  assert.deepEqual(result.incomplete_result_call_ids, ["call_child"]);
  assert.equal(f.child[2].status, "incomplete");
  f.child.splice(2, 1);
  assert.deepEqual(f.bind()[0].missing_result_call_ids, ["call_child"]);
});

test("foreign scope, altered prompts, unmatched auxiliary files and unknown result states fail closed", () => {
  const mutations = [
    f => { f.child[0].providerData.rootRequestId = "foreign"; },
    f => { f.child[1].sessionId = "foreign"; },
    f => { f.child[2].cwd = "/foreign"; },
    f => { f.child[1]._meta.baggage = "codebuddy.session_id=foreign,codebuddy.conversation_request_id=parent-request"; },
    f => { f.child[0].content[0].text += "Changed."; },
    f => { f.child[1].timestamp = 99; },
    f => { f.child[2].timestamp = 1001; },
    f => { f.child[2].callId = "foreign-call"; },
    f => { f.child[2].status = "unknown-state"; },
    f => { f.child.push({ ...f.child[0], id: "extra-user" }); },
    f => { f.child.push({ ...f.child[1], arguments: "changed" }); },
    f => { f.snapshot.conversation.hasActiveChildAgents = true; },
    f => { f.tool.rawInput = { description: {}, prompt: {} }; },
  ];
  for (const mutate of mutations) { const f = fixture(); mutate(f); assert.throws(() => f.bind(), /WORKBUDDY_CHILD_SDK_/); }
  const f = fixture(), source = f.sources(); source[0].attachments[0].name = "agent-fixture/tool-results/call_foreign.txt";
  assert.throws(() => bindChildSdk(f.bytes(f.primary), f.snapshot, f.session, source), /AUXILIARY_CALL_UNBOUND/);
});

test("ambiguous same-prompt parent calls cannot be linked by nearest-time guessing", () => {
  const f = fixture(); f.snapshot.request.assistantMessage.content.push({ ...f.tool, toolCallId: "call_other" });
  f.primary.push({ ...f.primary[1], id: "other-parent-call", callId: "call_other" },
    { ...f.primary[2], id: "other-parent-return", callId: "call_other" });
  assert.throws(() => f.bind(), /PARENT_CALL_AMBIGUOUS/);
});

async function archive(root, f, options = {}) {
  const primaryRef = artifact("raw/workbuddy-session.jsonl", f.bytes(f.primary));
  const runtimeBytes = jsonBytes({ source_kind: "workbuddy-runtime-api", identity: f.identity,
    conversation_id: f.session.session_id, request_id: f.session.turn_id, workspace: f.session.cwd,
    runtime_snapshot: f.snapshot });
  const runtimeRef = artifact("raw/runtime.json", runtimeBytes);
  const sources = f.sources();
  const proof = childSdkProof(f.identity, f.session, runtimeRef, primaryRef, f.bytes(f.primary), f.snapshot, sources, options);
  const files = [{ ref: primaryRef, bytes: f.bytes(f.primary) }, { ref: runtimeRef, bytes: runtimeBytes }];
  for (const source of sources) for (const item of [{ name: source.name, bytes: source.bytes }, ...source.attachments])
    files.push({ ref: artifact("raw/workbuddy-subagents/" + item.name, item.bytes), bytes: item.bytes });
  const proofBytes = jsonBytes(proof), proofRef = artifact(CHILD_SDK_PROOF, proofBytes);
  for (const item of [...files, { ref: proofRef, bytes: proofBytes }]) {
    const path = join(root, item.ref.path); await mkdir(dirname(path), { recursive: true }); await writeFile(path, item.bytes);
  }
  return { raw_trace: files.map(x => x.ref), binding_evidence: [proofRef] };
}

test("offline replay checks lineage as well as hashes and includes every output sidecar", async () => {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-child-archive-"));
  try {
    const f = fixture(), index = await archive(root, f);
    assert.equal((await verifyChildSdkArchive(root, index, f.identity, f.session)).children.length, 1);
    const child = index.raw_trace.find(x => x.path.endsWith("agent-fixture.jsonl"));
    const changed = structuredClone(f.child); changed[0].content[0].text = "Foreign task";
    const changedBytes = f.bytes(changed); await writeFile(join(root, child.path), changedBytes);
    Object.assign(child, artifact(child.path, changedBytes));
    const proofPath = join(root, CHILD_SDK_PROOF), proof = JSON.parse(await readFile(proofPath, "utf8"));
    proof.children[0].raw = { ...child };
    const bytes = jsonBytes(proof); await writeFile(proofPath, bytes);
    index.binding_evidence[0] = artifact(CHILD_SDK_PROOF, bytes);
    await assert.rejects(() => verifyChildSdkArchive(root, index, f.identity, f.session), /PARENT_CALL_AMBIGUOUS_OR_MISSING/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("discovery accepts only bound native layout and rejects linked output symlinks", async () => {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-child-discovery-"));
  try {
    const f = fixture(), native = { path: join(root, "parent-session.jsonl"), bytes: f.bytes(f.primary) };
    const dir = join(root, "parent-session/subagents"), source = f.sources()[0];
    await mkdir(dir, { recursive: true }); await writeFile(join(dir, source.name), source.bytes);
    for (const item of source.attachments) { const p = join(dir, item.name); await mkdir(dirname(p), { recursive: true }); await writeFile(p, item.bytes); }
    const result = await discoverChildSdk(native, f.snapshot, f.session); assert.equal(result[0].attachments.length, 2);
    const p = join(dir, source.attachments[0].name); await rm(p); await symlink(native.path, p);
    await assert.rejects(() => discoverChildSdk(native, f.snapshot, f.session), /UNSAFE_AUXILIARY/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("a child before the SDK recording time binds to its actual native dispatch without timestamp tolerance", () => {
  const f = fixture(); f.primary[1].timestamp = 103;
  f.tool._meta["codebuddy.ai/toolExecutionStarted"] = true;
  f.tool._meta["codebuddy.ai/toolExecutionStartedAt"] = 100;
  const result = f.bind()[0];
  assert.equal(result.first_timestamp, 101);
  assert.deepEqual(result.parent_time_binding, { profile: "native-tool-execution-start/v1",
    source: "runtime.toolExecutionStartedAt", sdk_call_recorded_at: 103,
    native_execution_started_at: 100, effective_lower_bound: 100, primary_completed_at: 1000 });
  assert.throws(() => bindChildSdk(f.bytes(f.primary), f.snapshot, f.session, f.sources(),
    { timeProfile: "sdk-record-timestamp/v1" }), /EVENT_TIME_OUTSIDE_PARENT/);
  f.tool._meta["codebuddy.ai/toolExecutionStartedAt"] = 102;
  assert.throws(() => f.bind(), /EVENT_TIME_OUTSIDE_PARENT/);
  for (const value of [49, 1001, "100"]) {
    f.tool._meta["codebuddy.ai/toolExecutionStartedAt"] = value;
    assert.throws(() => f.bind(), /NATIVE_START_UNBOUND/);
  }
});

test("old SDK-timestamp proofs replay unchanged and unknown time profiles fail closed", async () => {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-child-legacy-time-"));
  try {
    const f = fixture(), index = await archive(root, f, { timeProfile: "sdk-record-timestamp/v1" });
    const proof = await verifyChildSdkArchive(root, index, f.identity, f.session);
    assert.equal(proof.binding_time_profile, undefined);
    assert.equal(proof.children[0].parent_time_binding, undefined);
    assert.throws(() => bindChildSdk(f.bytes(f.primary), f.snapshot, f.session, f.sources(),
      { timeProfile: "unknown-time-profile/v1" }), /TIME_PROFILE_UNSUPPORTED/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("exact native local-agent session metadata is preserved with its filename alias", () => {
  const f = fixture();
  const meta = { id: "native-session-metadata", type: "session-meta", sessionId: "agent-fixture", timestamp: 250,
    meta: { "codebuddy.ai/hostKind": "unopted", "codebuddy.ai/agentRuntime": "local-agent" } };
  f.child.splice(2, 0, meta);
  const before = f.bytes(f.child), result = f.bind()[0];
  assert.deepEqual(result.session_metadata_records, [{ id: meta.id, timestamp: 250,
    session_alias: "agent-fixture", profile: "native-local-agent-session-meta/v1" }]);
  assert.equal(result.observed_tool_call_count, 1);
  assert.equal(result.transcript_status, "complete");
  assert.deepEqual(before, f.bytes(f.child));
});

test("metadata cannot hide another user message, foreign session, unknown runtime or out-of-bound time", () => {
  for (const mutate of [
    row => { row.role = "user"; row.content = "unbound input"; },
    row => { row.sessionId = "agent-foreign"; },
    row => { row.meta["codebuddy.ai/agentRuntime"] = "foreign-runtime"; },
    row => { row.timestamp = 1001; },
    row => { row.providerData = { conversationRequestId: "foreign" }; },
  ]) {
    const f = fixture(), row = { id: "native-meta", type: "session-meta", sessionId: "agent-fixture", timestamp: 250,
      meta: { "codebuddy.ai/hostKind": "unopted", "codebuddy.ai/agentRuntime": "local-agent" } };
    mutate(row);f.child.splice(2, 0, row);assert.throws(() => f.bind(), /SESSION_META_UNBOUND/);
  }
});

test("generated MCP output files require an exact absolute-path reference in a native tool result", () => {
  const f = fixture(), name = "mcp-sheetagent-run_command-1794065902594-707bf7.txt";
  const path = "/native/sdk/agent-fixture/tool-results/" + name;
  f.child[1].name = f.child[2].name = "mcp__sheetagent__run_command";
  f.child[2].output.text = "Full output saved to: " + path;
  const sources = f.sources(); sources[0].attachments = [{ name: "agent-fixture/tool-results/" + name,
    source_path: path, bytes: Buffer.from("Original native MCP output.") }];
  const result = bindChildSdk(f.bytes(f.primary), f.snapshot, f.session, sources)[0];
  assert.equal(result.auxiliary_tool_results[0].call_id, "call_child");
  assert.deepEqual(result.auxiliary_tool_results[0].native_result_references,
    [{ event_id: "child-result", call_id: "call_child", tool_name: "mcp__sheetagent__run_command", path_fields: ["output"] }]);
  f.child[2].output.text = "Filename only: " + name;
  sources[0].bytes = f.bytes(f.child);
  assert.throws(() => bindChildSdk(f.bytes(f.primary), f.snapshot, f.session, sources), /MCP_OUTPUT_REFERENCE_MISSING/);
  f.child[3].content = "Assistant claims: " + path;
  sources[0].bytes = f.bytes(f.child);
  assert.throws(() => bindChildSdk(f.bytes(f.primary), f.snapshot, f.session, sources), /MCP_OUTPUT_REFERENCE_MISSING/);
});

test("generated MCP path bindings replay offline without following the original absolute path", async () => {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-child-mcp-path-"));
  try {
    const f = fixture(), name = "mcp-sheetagent-run_command-1794065902594-707bf7.txt";
    const path = "/original/native/agent-fixture/tool-results/" + name;
    f.child[1].name = f.child[2].name = "mcp__sheetagent__run_command";
    f.child[2].output.text = "Full output saved to: " + path;
    f.sources = () => [{ name: "agent-fixture.jsonl", bytes: f.bytes(f.child), attachments: [
      { name: "agent-fixture/tool-results/" + name, source_path: path, bytes: Buffer.from("Frozen output.") },
    ] }];
    const index = await archive(root, f), proof = await verifyChildSdkArchive(root, index, f.identity, f.session);
    assert.equal(proof.children[0].auxiliary_tool_results[0].native_source_path, path);
    assert.equal(proof.children[0].auxiliary_tool_results[0].native_result_references[0].event_id, "child-result");
  } finally { await rm(root, { recursive: true, force: true }); }
});
