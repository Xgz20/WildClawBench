import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  cp,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import { collectQwenWorkEvidence } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/collector.mjs";
import { assessQwenMetadataCoverage } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/metadata-gate.mjs";
import { normalizeQwenNativeTrace } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/native-normalizer.mjs";

const FIXTURES = new URL("./fixtures/qwenwork/", import.meta.url);
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const identity = {
  batch_id: "batch-qwen-collector",
  unit_id: "unit-qwen-collector",
  task_id: "task-qwen-collector",
  attempt_id: "attempt-qwen-collector",
};

test("redacted binding fixture stays on the QwenWork provenance schema", async () => {
  const binding = JSON.parse(await readFile(new URL("session-binding-redacted.json", FIXTURES), "utf8"));
  assert.equal(binding.schema_version, "wildclawbench.general-e2e-qwenwork-session-binding/v1");
  assert.equal(binding.terminal_observation.trusted_terminal, true);
  assert.equal(binding.terminal_observation.active_stream, false);
});

async function copyFixture(name, target) {
  await cp(new URL(name, FIXTURES), target);
}

async function createFixture({ mutateBinding = null, mutateSegment = null } = {}) {
  const root = await mkdtemp(join(tmpdir(), "qwenwork-collector-"));
  const unitRoot = join(root, "unit");
  const workspace = join(unitRoot, "workspace");
  const traceRoot = join(root, ".qwenworkcn");
  const projectRoot = join(traceRoot, "projects");
  const segmentRoot = join(traceRoot, "logs", "sessions", "workspace-fixture", "session-fixture-001", "segments");
  await mkdir(workspace, { recursive: true });
  await mkdir(projectRoot, { recursive: true });
  await mkdir(segmentRoot, { recursive: true });
  const promptPath = join(unitRoot, "prompt.md");
  const prompt = Buffer.from("[REDACTED_USER_PROMPT]", "utf8");
  await writeFile(promptPath, prompt);
  const transcriptPath = join(projectRoot, "session-fixture-001.jsonl");
  const transcript = Buffer.from(
    (await readFile(new URL("transcript-redacted.jsonl", FIXTURES), "utf8"))
      .replaceAll("/private/tmp/qwenwork-general-fixture/workspace", workspace),
    "utf8",
  );
  const segmentPath = join(segmentRoot, "0001.jsonl");
  let segment = (await readFile(new URL("segments-redacted.jsonl", FIXTURES), "utf8"))
    .replaceAll("/private/tmp/qwenwork-general-fixture/workspace", workspace);
  if (mutateSegment) segment = mutateSegment(segment);
  await writeFile(transcriptPath, transcript);
  await writeFile(segmentPath, segment);
  const canonicalTranscriptPath = await realpath(transcriptPath);

  const terminalObservation = {
    trusted_terminal: true,
    target_session_verified: true,
    active_stream: false,
    stop_confirmed: true,
    conflicts: [],
  };
  const state = {
    schema_version: "wildclawbench.general-e2e-execution-state/v1",
    driver: { id: "qwenwork-macos-general", version: "0.2.0", harness: "qwenwork", platform: "macos" },
    identity,
    dataset: { id: "dataset-qwen-fixture", digest: "d".repeat(64) },
    phase: "COMPLETED",
    task_root: unitRoot,
    candidate_workspace: workspace,
    prompt: {
      path: promptPath,
      sha256: sha256(prompt),
      send_status: "sent",
      sent_at: "2026-09-17T03:00:01.000Z",
    },
    send: { dispatch_attempt_count: 1 },
    execution: {
      business_status: "completed",
      started_at: "2026-09-17T03:00:01.000Z",
      finished_at: "2026-09-17T03:00:06.000Z",
      duration_seconds: 5,
    },
    session: {
      thread_id: null,
      turn_id: null,
      session_id: "session-fixture-001",
      cwd: workspace,
      verified: true,
      binding_evidence: [],
    },
    extensions: {
      qwenwork: {
        local_project_id: "project-fixture-001",
        terminal_observation: terminalObservation,
      },
    },
  };
  const binding = {
    schema_version: "wildclawbench.general-e2e-qwenwork-session-binding/v1",
    identity,
    prompt_sha256: state.prompt.sha256,
    workspace,
    local_project_id: "project-fixture-001",
    conversation_id: "conversation-fixture-001",
    sub_chat_id: "sub-chat-fixture-001",
    session_id: "session-fixture-001",
    terminal_observation: terminalObservation,
  };
  const bindingPath = join(unitRoot, "evidence", "qwenwork", "session-binding.json");
  await mkdir(join(unitRoot, "evidence", "qwenwork"), { recursive: true });
  if (mutateBinding) mutateBinding(binding);
  const bindingBytes = Buffer.from(`${JSON.stringify(binding, null, 2)}\n`, "utf8");
  await writeFile(bindingPath, bindingBytes);
  const canonicalBindingPath = await realpath(bindingPath);
  state.session.binding_evidence = [{
    path: canonicalBindingPath,
    sha256: sha256(bindingBytes),
    size: bindingBytes.length,
  }];
  const journal = {
    schema_version: "wildclawbench.general-e2e-qwenwork-attempt-journal/v1",
    identity,
    phase: "COMPLETED",
    execution_state: state,
    send: { dispatch_attempt_count: 1 },
    session: {
      session_id: "session-fixture-001",
      cwd: workspace,
      prompt_evidence: {
        transcript_path: canonicalTranscriptPath,
        transcript_sha256: sha256(transcript),
        transcript_size: transcript.length,
      },
    },
  };
  const journalPath = join(unitRoot, "qwenwork-attempt-journal.json");
  await writeFile(journalPath, `${JSON.stringify(journal, null, 2)}\n`);
  return { root, unitRoot, traceRoot, journalPath, state };
}

test("QwenWork collector emits CB-B v2 trace and null usage coverage without promoting completed", async () => {
  const fixture = await createFixture();
  try {
    const [unitRoot, journalFile, clientTraceRoot] = await Promise.all([
      realpath(fixture.unitRoot),
      realpath(fixture.journalPath),
      realpath(fixture.traceRoot),
    ]);
    const outputRoot = join(await realpath(fixture.unitRoot), ".general-e2e", "collection", "attempt-qwen-collector");
    const result = await collectQwenWorkEvidence({
      unitRoot,
      journalFile,
      clientTraceRoot,
      outputRoot,
      redacted: true,
      collectedAt: "2026-09-17T03:00:10.000Z",
    });
    assert.equal(result.trace.schema_id, "urn:wildclawbench:schema:general-e2e:trace-index:v2");
    assert.equal(result.trace.session.session_id, "session-fixture-001");
    assert.equal(result.trace.session.thread_id, null);
    assert.deepEqual(result.trace.completeness, { status: "complete", omitted_event_count: 0, missing: [] });
    assert.equal(result.resource.metrics.usage.input_tokens.value, null);
    assert.equal(result.resource.metrics.usage.input_tokens.status, "unavailable");
    assert.deepEqual(result.resource.collection.coverage.input_tokens, { known: 0, total: 2, unit: "model_response" });
    assert.equal(result.trace.metadata_coverage.readiness.ready_for_collect, true);
    assert.deepEqual(result.trace.metadata_coverage.segments.session_id, {
      known: 0, total: 15, missing: 15, mismatched: 0,
    });
    assert.deepEqual(result.trace.metadata_coverage.segments.cwd, {
      known: 2, total: 15, missing: 13, mismatched: 0,
    });
    const toolResult = result.trace.calls[0];
    assert.equal(toolResult.result_sequence != null, true);
    const transcript = (await readFile(result.trace_index, "utf8")).trim();
    assert.match(transcript, /"schema_id": "urn:wildclawbench:schema:general-e2e:trace-index:v2"/u);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("metadata gate reports partial segment identity without inferring missing values", () => {
  const result = assessQwenMetadataCoverage({
    state: { session: { session_id: "session-fixture-001", cwd: "/fixture/workspace" } },
    transcriptRows: [
      { sessionId: "session-fixture-001", cwd: "/fixture/workspace" },
      { sessionId: "session-fixture-001", cwd: "/fixture/workspace" },
    ],
    segmentRows: [
      { data: { project_root: "/fixture/workspace", target_dir: "/fixture/workspace" } },
      { session_id: "session-fixture-001", data: { project_root: "/fixture/workspace" } },
    ],
    segmentDirectoryBound: true,
  });
  assert.equal(result.readiness.ready_for_collect, true);
  assert.deepEqual(result.segments.session_id, {
    known: 1, total: 2, missing: 1, mismatched: 0,
  });
  assert.deepEqual(result.segments.cwd, {
    known: 2, total: 2, missing: 0, mismatched: 0,
  });
  assert.deepEqual(result.claims_withheld, [
    "per-row-segment-session_id_when_missing",
    "per-row-segment-cwd_when_missing",
    "terminal_state_from_metadata_only",
    "usage_from_metadata_only",
  ]);
});

test("metadata gate blocks missing transcript metadata and relative or mismatched segment cwd", () => {
  const missingTranscript = assessQwenMetadataCoverage({
    state: { session: { session_id: "session-fixture-001", cwd: "/fixture/workspace" } },
    transcriptRows: [
      { sessionId: "session-fixture-001", cwd: "/fixture/workspace" },
      { cwd: "/fixture/workspace" },
    ],
    segmentRows: [{ data: { project_root: "/fixture/workspace" } }],
    segmentDirectoryBound: true,
  });
  assert.deepEqual(missingTranscript.readiness.blockers, ["transcript_session_id_missing"]);

  const badSegment = assessQwenMetadataCoverage({
    state: { session: { session_id: "session-fixture-001", cwd: "/fixture/workspace" } },
    transcriptRows: [{ sessionId: "session-fixture-001", cwd: "/fixture/workspace" }],
    segmentRows: [{ session_id: "session-fixture-001", data: { project_root: "relative/workspace" } }],
    segmentDirectoryBound: true,
  });
  assert.deepEqual(badSegment.readiness.blockers, ["segment_cwd_mismatch", "segment_cwd_unverified"]);
});

test("tool execution status completed remains unknown when no shell outcome proves success", () => {
  const normalized = normalizeQwenNativeTrace({
    identity,
    transcriptRows: [
      { __raw_path: "raw/transcript.jsonl", __raw_line: 1, type: "user", timestamp: "2026-09-17T03:00:00Z", sessionId: "session-fixture-001", cwd: "/fixture", message: { content: [{ type: "text", text: "prompt" }] } },
      { __raw_path: "raw/transcript.jsonl", __raw_line: 2, type: "assistant", timestamp: "2026-09-17T03:00:01Z", sessionId: "session-fixture-001", cwd: "/fixture", message: { content: [{ type: "tool_use", id: "call-1", name: "Bash", input: {} }] } },
      { __raw_path: "raw/transcript.jsonl", __raw_line: 3, type: "user", timestamp: "2026-09-17T03:00:02Z", sessionId: "session-fixture-001", cwd: "/fixture", message: { content: [{ type: "tool_result", tool_use_id: "call-1", content: "done" }] } },
    ],
    segmentRows: [
      { __raw_path: "raw/segments/0001.jsonl", __raw_line: 1, type: "tool.execution.finished", tool_call_id: "call-1", data: { status: "completed" } },
    ],
  });
  assert.equal(normalized.events.find((event) => event.type === "tool_result").tool.status, "unknown");
});

test("collector rejects binding identity and segment workspace provenance drift", async () => {
  const badBinding = await createFixture({ mutateBinding: (binding) => { binding.session_id = "other-session"; } });
  const badBindingPaths = await Promise.all([
    realpath(badBinding.unitRoot), realpath(badBinding.journalPath), realpath(badBinding.traceRoot),
  ]);
  await assert.rejects(
    collectQwenWorkEvidence({
      unitRoot: badBindingPaths[0],
      journalFile: badBindingPaths[1],
      clientTraceRoot: badBindingPaths[2],
      outputRoot: join(await realpath(badBinding.unitRoot), ".general-e2e", "collection", "bad-binding"),
    }),
    /BINDING_SESSION_MISMATCH/u,
  );
  await rm(badBinding.root, { recursive: true, force: true });

  const badSegment = await createFixture({
    mutateSegment: (segment) => segment.replace(/\/workspace/gu, "/other-workspace"),
  });
  const badSegmentPaths = await Promise.all([
    realpath(badSegment.unitRoot), realpath(badSegment.journalPath), realpath(badSegment.traceRoot),
  ]);
  await assert.rejects(
    collectQwenWorkEvidence({
      unitRoot: badSegmentPaths[0],
      journalFile: badSegmentPaths[1],
      clientTraceRoot: badSegmentPaths[2],
      outputRoot: join(await realpath(badSegment.unitRoot), ".general-e2e", "collection", "bad-segment"),
    }),
    /METADATA_GATE_BLOCKED: segment_cwd_mismatch/u,
  );
  await rm(badSegment.root, { recursive: true, force: true });
});
