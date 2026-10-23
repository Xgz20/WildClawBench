import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { validateTerminalFinalRecapture, prepareTerminalFinalRecapture, readTerminalFinalRecapture,
  recaptureCandidateTree, assertRecaptureArchiveSources } from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-terminal-final-recapture.mjs';
import { recaptureFixture, writeRecaptureInput, digest, pretty } from './fixtures/terminal-final-recapture.mjs';
const finalProvider = d => d.provider.find(r => r.event_type === 'item.completed' && JSON.parse(r.event_json).itemId === 'final');
const changeFinal = (d, change) => { const row = finalProvider(d), e = JSON.parse(row.event_json); change(e); row.event_json = JSON.stringify(e); };
test('unique earlier frozen commentary is recaptured only from three matching completed sources', () => {
  const data = recaptureFixture(), original = JSON.stringify(data.originalState), proof = validateTerminalFinalRecapture(data);
  assert.equal(proof.finalBytes.toString(), 'Done.\n'); assert.equal(proof.old_sdk_message_id, 'old');
  assert.equal(proof.final_sdk_message_id, 'final'); assert.equal(proof.resend_count, 0);
  assert.equal(JSON.stringify(data.originalState), original);
});
for (const [name, change, error] of [
  ['native not terminal', d => { d.originalState.phase = 'RUNNING'; }, 'NATIVE_TERMINAL'],
  ['unverified session', d => { d.originalState.session.verified = false; }, 'SESSION_UNVERIFIED'],
  ['duplicate dispatch', d => { d.originalState.send.dispatch_attempt_count = 2; }, 'SEND_NOT_UNIQUE'],
  ['original digest', d => { d.originalFinal = Buffer.from('other'); }, 'ORIGINAL_FINAL_SHA'],
  ['candidate mutation', d => { d.candidateAfter.push({ path: 'unexpected' }); }, 'CANDIDATE_CHANGED'],
  ['model not verified', d => { d.originalState.client.custom_model_binding.native_binding_verified = false; }, 'CUSTOM_MODEL'],
  ['project changed', d => { d.binding.project_id = 'other'; }, 'NATIVE_BINDING'],
  ['workspace changed', d => { d.binding.workspace_root = 'other'; }, 'NATIVE_BINDING'],
  ['session changed', d => { d.binding.session_id = 'other'; }, 'NATIVE_BINDING'],
  ['native turn not complete', d => { d.turn.state = 'running'; }, 'NATIVE_TURN'],
  ['native final id changed', d => { d.turn.assistant_message_id = 'assistant:other'; }, 'FINAL_MESSAGE_ID'],
  ['SDK session changed', d => { d.sdk[0].payload.id = 'other'; }, 'SDK_SESSION'],
  ['SDK model changed', d => { d.sdk[2].payload.model = 'other'; }, 'SDK_CONTEXT'],
  ['SDK high changed', d => { d.sdk[2].payload.effort = 'medium'; }, 'SDK_CONTEXT'],
  ['SDK turn changed', d => { d.sdk[2].payload.turn_id = 'other'; }, 'SDK_CONTEXT'],
  ['SDK prompt changed', d => { d.sdk[3].payload.message = 'other'; }, 'SDK_PROMPT'],
  ['SDK last reply changed', d => { d.sdk.at(-1).payload.last_agent_message = 'other'; }, 'SDK_FINAL'],
  ['native projection changed', d => { d.messages.at(-1).text = 'other'; }, 'PROJECTION_FINAL'],
  ['foreign projected message', d => { d.messages[0].turn_id = 'other'; }, 'PROJECTION_SCOPE'],
  ['unknown old final', d => { d.sdk.find(r => r.payload?.id === 'old').payload.content[0].text = 'other'; }, 'ORIGINAL_NOT_UNIQUE'],
  ['provider scope changed', d => { d.provider[0].thread_id = 'other'; }, 'PROVIDER_SCOPE'],
  ['provider lifecycle changed', d => { finalProvider(d).lifecycle_generation = 'other'; }, 'PROVIDER_LIFECYCLE'],
  ['provider final changed', d => changeFinal(d, e => { e.payload.data.item.text = 'other'; }), 'PROVIDER_FINAL'],
  ['provider SDK session changed', d => changeFinal(d, e => { e.payload.data.threadId = 'other'; }), 'PROVIDER_SDK_BINDING'],
  ['provider final duplicated', d => { d.provider.push(structuredClone(finalProvider(d))); }, 'PROVIDER_FINAL_AMBIGUOUS'],
]) test('reject ' + name, () => { const data = recaptureFixture(); change(data); assert.throws(() => validateTerminalFinalRecapture(data), new RegExp(error)); });
test('explicit preparation preserves originals, binds authorization and rechecks derivation plus candidate', async () => {
  const root = await mkdtemp(join(tmpdir(), 'terminal-recapture-'));
  try {
    const taskRoot = join(root, 'execution/tasks/task'), workspace = join(taskRoot, 'workspace');
    await mkdir(workspace, { recursive: true }); await writeFile(join(workspace, 'answer'), 'candidate');
    const data = recaptureFixture(); data.originalState.task_root = taskRoot; data.originalState.candidate_workspace = workspace;
    data.originalState.session.cwd = workspace; data.binding.workspace_root = workspace; data.sdk[0].payload.cwd = workspace; data.sdk[2].payload.cwd = workspace;
    data.candidateBefore = data.candidateAfter = await recaptureCandidateTree(workspace);
    const input = await writeRecaptureInput(join(root, 'input'), data), output = join(root, 'recapture');
    const result = await prepareTerminalFinalRecapture({ inputManifest: input, outputDir: output });
    const stateBytes = await readFile(result.state_file), state = JSON.parse(stateBytes);
    assert.equal(state.identity.attempt_id, data.originalState.identity.attempt_id);
    assert.equal(data.originalState.evidence.final_response_sha256, JSON.parse(await readFile(join(output, 'inputs/original_state.json'))).evidence.final_response_sha256);
    const bundle = await readTerminalFinalRecapture(result.manifest, state, stateBytes, { candidateRoot: workspace });
    assert.equal(bundle.binding_artifacts.length, 15);
    assertRecaptureArchiveSources(bundle, await readFile(join(output, 'inputs/sdk.json')),
      data.provider.map(row => ({ ...row, event: JSON.parse(row.event_json) })));
    assert.throws(() => assertRecaptureArchiveSources(bundle, Buffer.from('other'), []), /ARCHIVED_SDK/);
    const manifestBytes = await readFile(result.manifest), changedManifest = JSON.parse(manifestBytes);
    const changedState = structuredClone(state); changedState.execution.duration_seconds = 12345;
    const changedBytes = pretty(changedState);
    Object.assign(changedManifest.derived_state, { sha256: digest(changedBytes), size: changedBytes.length });
    await writeFile(result.manifest, pretty(changedManifest));
    await assert.rejects(readTerminalFinalRecapture(result.manifest, changedState, changedBytes), /DERIVATION_MISMATCH/);
    await writeFile(result.manifest, manifestBytes);
    await writeFile(join(workspace, 'answer'), 'changed');
    await assert.rejects(readTerminalFinalRecapture(result.manifest, state, stateBytes, { candidateRoot: workspace }), /CANDIDATE_CHANGED/);
    await assert.rejects(prepareTerminalFinalRecapture({ inputManifest: input, outputDir: output }), /CANDIDATE_CHANGED|EEXIST/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
for (const kind of ['unapproved', 'review-drift', 'foreign-record', 'duplicate-source-path', 'source-symlink', 'candidate-output']) {
  test('bundle fails closed: ' + kind, async () => {
    const root = await mkdtemp(join(tmpdir(), 'terminal-recapture-negative-'));
    try {
      const taskRoot = join(root, 'execution/tasks/task'), workspace = join(taskRoot, 'workspace');
      await mkdir(workspace, { recursive: true });
      const data = recaptureFixture(); Object.assign(data.originalState, { task_root: taskRoot, candidate_workspace: workspace });
      data.originalState.session.cwd = workspace; data.binding.workspace_root = workspace;
      data.sdk[0].payload.cwd = workspace; data.sdk[2].payload.cwd = workspace;
      data.candidateBefore = data.candidateAfter = await recaptureCandidateTree(workspace);
      const inputRoot = join(root, 'input'), path = await writeRecaptureInput(inputRoot, data), manifest = JSON.parse(await readFile(path));
      async function change(role, update) {
        const row = manifest.sources[role], bytes = pretty(update(JSON.parse(await readFile(join(inputRoot, row.path)))));
        await writeFile(join(inputRoot, row.path), bytes); Object.assign(row, { sha256: digest(bytes), size: bytes.length });
      }
      let expected;
      if (kind === 'unapproved') { await change('authorization', v => ({ ...v, status: 'PENDING' })); expected = /AUTHORIZATION_INVALID/; }
      if (kind === 'review-drift') { await change('authorization', v => ({ ...v, review_sha256: '0'.repeat(64) })); expected = /AUTHORIZATION_INVALID/; }
      if (kind === 'foreign-record') { await change('original_record', v => ({ identity: { ...v.identity, task_id: 'foreign' } })); expected = /ORIGINAL_RECORD_IDENTITY/; }
      if (kind === 'duplicate-source-path') { manifest.sources.sdk.path = manifest.sources.original_state.path; expected = /INPUT_PATH_SCOPE/; }
      if (kind === 'source-symlink') { const target = join(inputRoot, manifest.sources.sdk.path); await rm(target); await symlink(join(inputRoot, manifest.sources.authorization_review.path), target); expected = /SOURCE_INVALID/; }
      if (kind === 'candidate-output') expected = /OUTPUT_SCOPE/;
      await writeFile(path, pretty(manifest));
      await assert.rejects(prepareTerminalFinalRecapture({ inputManifest: path,
        outputDir: kind === 'candidate-output' ? join(workspace, 'recapture') : join(root, 'output') }), expected);
    } finally { await rm(root, { recursive: true, force: true }); }
  });
}
