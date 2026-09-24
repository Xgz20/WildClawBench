import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeRuntimeMessages, normalizeRuntimePrompt } from "../../tools/report/e2e-shared/doubaowork/runtime-messages.mjs";
import { sha256Text, summarizePromptReadback } from "../../tools/report/e2e-shared/doubaowork/lib.mjs";
import { CANCELLATION_SCHEMA, TERMINAL_OBSERVATION_SCHEMA, verifyCancellationEvidence, verifyFailureEvidence } from "../../tools/report/e2e-shared/doubaowork/terminal-evidence.mjs";

function fixture() {
  const prompt = "Fix `project/example.py`.\n", id = "123456789", workspace = "/private/fixture/workspace";
  const config = { runtime_type: 2, client_option: { workspace }, agent_task_param: { workspace, runtime_type: 2 } };
  const user = { conversation_id: id, message_id: "100", user_type: 1, status: 1, final_status: { message: "Success" },
    ext: { general_task_param: JSON.stringify(config), conversation_init_option: JSON.stringify({ project_id: "123" }) },
    content_blocks_v2: [{ block_type: 10000, content: { text_block: { text: prompt } }, is_finish: true }] };
  const assistant = { conversation_id: id, message_id: "101", reply_id: "100", session_id: "native-request", user_type: 2,
    status: 1, stage: 4, final_status: { session: "Success" }, ext: { general_task_param: JSON.stringify(config), is_finish: "1" },
    content_blocks_v2: [{ block_type: 10000, is_finish: true, content: { text_block: { text: "Done." } } }],
    local_info: { query_send_timestamp: 1000, perf_mark_samples: [{ queryMessageId: "100", answerId: "101", taskId: "native-request", receiveTimestamp: 2000, marks: [{ evName: "task_finish" }] }] } };
  const snapshot = { schema: "wildclawbench.doubaowork-runtime-messages/v1", source: "native-im.useMessageStore.getState", conversation_id: id, maps: { messageMap: { 100: user, 101: assistant }, messageListStatusMap: { hasMore: false, inIniting: false, inLoadingMore: false } } };
  const p = summarizePromptReadback(prompt);
  const state = { session: { conversation_id: id }, prompt: { readback_sha256: p.sha256, readback_bytes: p.bytes }, workspace, client: { project_id_sha256: sha256Text("123") } };
  const seal = () => { snapshot.payload_sha256 = sha256Text(JSON.stringify({ conversation_id: id, maps: snapshot.maps })); return snapshot; };
  return { snapshot, state, seal, user, assistant, config };
}

test("Native Prompt, reply, local workspace and terminal form one verified identity", () => {
  const f = fixture(), n = normalizeRuntimeMessages(f.seal(), f.state);
  assert.equal(n.terminal, "completed");
  assert.equal(n.native_cwd, f.state.workspace);
  assert.equal(n.reply_message_id, "101");
  assert.equal(n.finished_at, "1970-01-01T00:00:02.000Z");
  assert.equal(n.agent_duration_seconds, null);
});

test("Native reader rejects hash, Prompt, reply, project and workspace mismatches", () => {
  const cases = [
    f => { f.snapshot.payload_sha256 = "a".repeat(64); },
    f => { f.user.content_blocks_v2[0].content.text_block.text = "other"; f.seal(); },
    f => { f.assistant.reply_id = "other"; f.seal(); },
    f => { f.user.ext.conversation_init_option = '{"project_id":"999"}'; f.seal(); },
    f => { f.config.agent_task_param.workspace = "/other/workspace"; f.assistant.ext.general_task_param = JSON.stringify(f.config); f.seal(); },
    f => { f.assistant.conversation_id = "999"; f.seal(); },
  ];
  for (const alter of cases) { const f = fixture(); f.seal(); alter(f); assert.throws(() => normalizeRuntimeMessages(f.snapshot, f.state), /DOUBAOWORK_/); }
});

test("A partial/unknown native finish never becomes success", () => {
  for (const alter of [a => a.final_status = {}, a => a.final_status.session = "Error", a => a.ext.is_finish = "0", a => a.content_blocks_v2[0].is_finish = false, a => a.stage = 3]) {
    const f = fixture(); alter(f.assistant);
    assert.equal(normalizeRuntimeMessages(f.seal(), f.state).terminal, "unverified");
  }
});

test("Native Broken requires a bound acknowledged Stop and quiet runtime before cancellation admission", () => {
  const f = fixture(), at = ms => new Date(ms).toISOString();
  f.state.client.version = "2.31.3"; f.state.attempt_id = "attempt"; f.state.timing = { sent_at: at(1000) };
  f.snapshot.observed_at = at(2000);
  const before = structuredClone(f.seal());
  before.maps.messageMap[101].final_status = {};
  before.maps.messageMap[101].ext.is_finish = "0";
  before.maps.messageMap[101].stage = 1;
  before.payload_sha256 = sha256Text(JSON.stringify({ conversation_id: before.conversation_id, maps: before.maps }));
  f.assistant.final_status = { message: "Broken", session: "Broken" };
  f.assistant.status = 3; f.assistant.stage = 1; f.assistant.content_blocks_v2[0].is_finish = false;
  f.snapshot.observed_at = at(5000);
  const native = normalizeRuntimeMessages(f.seal(), f.state);
  assert.equal(native.terminal, "interrupted"); assert.equal(native.finished_at, null); assert.equal(native.agent_duration_seconds, null);
  assert.equal(native.final_text, null);
  f.state.cancellation = { requested_at: at(3000), click_started_at: at(3500), click_returned_at: at(4000),
    click_attempt_count: 1, conversation_id: "123456789", user_message_id: "100", native_request_session_id: "native-request" };
  const intent = { schema: CANCELLATION_SCHEMA, operation: "click-bound-native-stop", selector: "chat_input_local_break_button",
    attempt_id: "attempt", workspace: f.state.workspace, requested_at: at(3000), runtime: before,
    frontend: { initialized: true, active: [{ session_id: "native-request", conversation_ids: ["123456789"] }] } };
  const observation = { schema: TERMINAL_OBSERVATION_SCHEMA, attempt_id: "attempt", workspace: f.state.workspace,
    conversation_id: "123456789", native_request_session_id: "native-request", observed_at: at(6000),
    native_payload_sha256: f.snapshot.payload_sha256, frontend: { initialized: true, active: [] },
    background: { initialized: true, active: [] }, stop_control_count: 0, pending: false };
  const args = { state: f.state, native, runtime: f.snapshot, intent, observation };
  assert.equal(verifyCancellationEvidence(args).cancellation_confirmed, true);
  for (const mutate of [x => x.state.cancellation.click_returned_at = null,
    x => x.state.cancellation.native_request_session_id = "other", x => x.intent.attempt_id = "other",
    x => x.observation.background.active.push({}), x => x.observation.frontend.active.push({}),
    x => x.observation.native_payload_sha256 = "other", x => x.observation.pending = true,
    x => x.observation.observed_at = at(3000)]) {
    const bad = structuredClone(args); mutate(bad); assert.throws(() => verifyCancellationEvidence(bad), /CANCELLATION_/);
  }
  f.state.client.version = "unknown";
  assert.equal(normalizeRuntimeMessages(f.seal(), f.state).terminal, "unverified");
});

test("2.31.6 transport Error is provisional until its exact native request is quiet", () => {
  const f = fixture(), at = ms => new Date(ms).toISOString();
  f.state.client.version = "2.31.6"; f.state.attempt_id = "attempt"; f.state.timing = { sent_at: at(1000) };
  f.snapshot.observed_at = at(5000);
  Object.assign(f.assistant, { status: 4, stage: 1, final_status: { message: "Error", session: "Error" },
    error_details: { has_error: true, error_code: 710020702, error_message: "Failed to fetch" } });
  delete f.assistant.ext.is_finish;
  f.assistant.content_blocks_v2[0].is_finish = false;
  const native = normalizeRuntimeMessages(f.seal(), f.state);
  assert.equal(native.terminal, "failed"); assert.equal(native.finished_at, null);
  assert.equal(native.agent_duration_seconds, null); assert.equal(native.final_text, null);
  assert.equal(native.raw_terminal.error_code, 710020702);
  const observation = { schema: TERMINAL_OBSERVATION_SCHEMA, attempt_id: "attempt", workspace: f.state.workspace,
    conversation_id: native.conversation_id, native_request_session_id: native.native_request_session_id,
    observed_at: at(6000), native_payload_sha256: f.snapshot.payload_sha256,
    frontend: { initialized: true, active: [] }, background: { initialized: true, active: [] },
    stop_control_count: 0, pending: false };
  const args = { state: f.state, native, runtime: f.snapshot, observation };
  assert.equal(verifyFailureEvidence(args).business_status, "infrastructure_error");
  for (const mutate of [x => x.observation.frontend.active.push({}), x => x.observation.background.active.push({}),
    x => x.observation.native_request_session_id = "other", x => x.observation.native_payload_sha256 = "other",
    x => x.observation.pending = true, x => x.observation.observed_at = at(4000)]) {
    const bad = structuredClone(args); mutate(bad); assert.throws(() => verifyFailureEvidence(bad), /FAILURE_/);
  }
  for (const mutate of [x => x.assistant.error_details.error_code = 1, x => x.assistant.error_details.has_error = false,
    x => x.assistant.final_status.session = "PanicError", x => x.assistant.stage = 4,
    x => x.state.client.version = "unknown"]) {
    const bad = fixture(); bad.state.client.version = "2.31.6";
    Object.assign(bad.assistant, { status: 4, stage: 1, final_status: { message: "Error", session: "Error" },
      error_details: { has_error: true, error_code: 710020702 } });
    mutate(bad); assert.equal(normalizeRuntimeMessages(bad.seal(), bad.state).terminal, "unverified");
  }
});

test("Multiple turns and regens fail closed; unrelated finish timestamps are not consumed", () => {
  const f = fixture(); f.snapshot.maps.messageMap[102] = { ...f.assistant, message_id: "102" };
  assert.throws(() => normalizeRuntimeMessages(f.seal(), f.state), /TURN_AMBIGUOUS/);
  delete f.snapshot.maps.messageMap[102]; f.assistant.local_info.perf_mark_samples[0].answerId = "other";
  assert.equal(normalizeRuntimeMessages(f.seal(), f.state).finished_at, null);
});

test("Acknowledged input binds a running turn without fabricating assistant completion or cwd", () => {
  const f = fixture(); delete f.snapshot.maps.messageMap[101];
  const n = normalizeRuntimePrompt(f.seal(), f.state);
  assert.equal(n.terminal, "unverified"); assert.equal(n.native_cwd, null);
  assert.equal(n.user_message_id, "100");
  assert.throws(() => normalizeRuntimeMessages(f.snapshot, f.state), /TURN_AMBIGUOUS/);
  f.user.final_status.message = "Pending";
  assert.throws(() => normalizeRuntimePrompt(f.seal(), f.state), /UNACKNOWLEDGED/);
});

function historyFixture() {
  const f = fixture(), id = "9bfef3f2-a2a3-45f3-9504-2f119e119e2c";
  delete f.assistant.session_id; delete f.assistant.stage;
  f.assistant.local_info = { from: "Api" };
  f.user.ext.reply_unique_key = id; f.assistant.ext.reply_unique_key = id;
  f.user.create_time = "1";
  f.assistant.ext.finish_reason_chat = "succeed:completion";
  f.assistant.ext.finish_time_ms = "4000";
  f.assistant.final_status.message = "Success";
  f.assistant.content_blocks_v2.push({ block_type: 10091, is_finish: true,
    content: { elapsed_block: { start_time_s: "1", end_time_s: "3" }, pc_event_block: "" } });
  return f;
}

test("Persisted native reply keeps its request identity, completion source and numeric-string interval", () => {
  const f = historyFixture(), n = normalizeRuntimeMessages(f.seal(), f.state);
  assert.equal(n.terminal, "completed"); assert.equal(n.native_request_session_id, f.user.ext.reply_unique_key);
  assert.equal(n.finished_at, "1970-01-01T00:00:04.000Z"); assert.equal(n.agent_duration_seconds, 2);
  assert.equal(n.raw_terminal.stage, null); assert.match(n.sources.finished_at, /finish_time_ms/);
  assert.equal(normalizeRuntimePrompt(f.snapshot, f.state).native_request_session_id, n.native_request_session_id);
});

test("Historical format does not waive request binding, API provenance, success or timestamp checks", () => {
  for (const alter of [f => { f.assistant.ext.reply_unique_key = "other"; },
    f => { f.state.session.native_request_session_id = "other"; },
    f => { f.assistant.ext.finish_time_ms = "500"; }]) {
    const f = historyFixture(); alter(f); assert.throws(() => normalizeRuntimeMessages(f.seal(), f.state), /DOUBAOWORK_/);
  }
  for (const alter of [f => { f.assistant.local_info.from = "unknown"; },
    f => { f.assistant.ext.finish_reason_chat = "cancelled"; },
    f => { f.assistant.stage = 3; }, f => { f.assistant.final_status.message = "Error"; }]) {
    const f = historyFixture(); alter(f); assert.equal(normalizeRuntimeMessages(f.seal(), f.state).terminal, "unverified");
  }
  const f = historyFixture(); f.assistant.ext.finish_time_ms = "4e3";
  assert.equal(normalizeRuntimeMessages(f.seal(), f.state).finished_at, null);
});
