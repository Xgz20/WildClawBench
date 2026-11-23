import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { lstat, mkdir, readFile, readdir, readlink, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';

export const FINAL_RECAPTURE_PROFILE = 'bound-terminal-final-recapture/v1';
export const FINAL_RECAPTURE_INPUT = 'wildclawbench.terminal-final-recapture-input/v1';
export const FINAL_RECAPTURE_BUNDLE = 'wildclawbench.terminal-final-recapture-bundle/v1';
const PREFIX = 'bindings/terminal-final-recapture/';
const ROLES = ['original_state', 'original_record', 'original_final', 'native_binding', 'native_turn',
  'native_messages', 'provider_rows', 'sdk', 'candidate_tree', 'authorization', 'authorization_review'];
const ensure = (ok, code) => { if (!ok) throw Error(code); };
export const recaptureSha = bytes => createHash('sha256').update(bytes).digest('hex');
export const requiresTerminalFinalRecapture = state => (state.history ?? []).some(row => row.event === 'TERMINAL_FINAL_RECAPTURE_ADOPTED' && row.profile === FINAL_RECAPTURE_PROFILE);
export function assertRecaptureDeclaration(state, index) {
  if (requiresTerminalFinalRecapture(state)) ensure(index.terminal_final_recapture_profile?.id === FINAL_RECAPTURE_PROFILE, 'RECAPTURE_PROFILE_REQUIRED');
}
const pretty = value => Buffer.from(JSON.stringify(value, null, 2) + '\n');
const ordered = value => value && typeof value === 'object'
  ? Array.isArray(value) ? value.map(ordered)
    : Object.fromEntries(Object.keys(value).sort().filter(k => value[k] !== undefined).map(k => [k, ordered(value[k])])) : value;
const canonical = value => JSON.stringify(ordered(value));
const same = (a, b) => canonical(a) === canonical(b);
const ref = (path, bytes) => ({ path, sha256: recaptureSha(bytes), size: bytes.length });
const json = bytes => JSON.parse(bytes.toString('utf8'));
const lines = bytes => bytes.toString('utf8').split('\n').filter(s => s.trim()).map(JSON.parse);
const inside = (root, path) => { const r = relative(resolve(root), resolve(path)); return r === '' || r !== '..' && !r.startsWith('../') && !isAbsolute(r); };
function safe(path) {
  ensure(typeof path === 'string' && path && !isAbsolute(path) && !path.includes('\\')
    && path.split('/').every(p => p && p !== '.' && p !== '..'), 'RECAPTURE_PATH_INVALID');
  return path;
}
async function artifact(root, row) {
  const path = resolve(root, safe(row?.path));
  ensure(inside(await realpath(root), await realpath(path)) && (await lstat(path)).isFile() && !(await lstat(path)).isSymbolicLink(), 'RECAPTURE_SOURCE_INVALID');
  const bytes = await readFile(path);
  ensure(bytes.length === row.size && recaptureSha(bytes) === row.sha256, 'RECAPTURE_SOURCE_SHA_MISMATCH');
  return bytes;
}
export async function recaptureCandidateTree(root) {
  const rows = [];
  async function visit(path, rel) {
    const info = await lstat(path), row = { path: rel, mode: info.mode & 0o7777 };
    if (info.isSymbolicLink()) row.kind = 'symlink', row.target = await readlink(path);
    else if (info.isDirectory()) {
      row.kind = 'directory'; rows.push(row);
      for (const name of (await readdir(path)).sort()) await visit(join(path, name), rel === '.' ? name : rel + '/' + name);
      return;
    } else {
      ensure(info.isFile(), 'RECAPTURE_CANDIDATE_TYPE_UNSUPPORTED');
      const hash = createHash('sha256'); for await (const bytes of createReadStream(path)) hash.update(bytes);
      Object.assign(row, { kind: 'file', size: info.size, sha256: hash.digest('hex') });
    }
    rows.push(row);
  }
  await visit(resolve(root), '.');
  return rows.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
}
export function validateTerminalFinalRecapture(data) {
  const s = data.originalState, session = s.session;
  ensure(['batch_id', 'unit_id', 'task_id', 'attempt_id'].every(k => typeof s.identity?.[k] === 'string' && s.identity[k]), 'RECAPTURE_IDENTITY_INVALID');
  ensure(s.phase === 'COMPLETED' && s.execution?.business_status === 'completed', 'RECAPTURE_NATIVE_TERMINAL_REQUIRED');
  ensure(session?.verified === true && session.native_status === 'completed', 'RECAPTURE_SESSION_UNVERIFIED');
  ensure(s.send?.dispatch_attempt_count === 1 && s.prompt?.send_status === 'sent', 'RECAPTURE_SEND_NOT_UNIQUE');
  ensure(recaptureSha(data.originalFinal) === s.evidence?.final_response_sha256, 'RECAPTURE_ORIGINAL_FINAL_SHA_MISMATCH');
  ensure(same(data.candidateBefore, data.candidateAfter), 'RECAPTURE_CANDIDATE_CHANGED');
  const mapping = s.client?.custom_model_binding;
  ensure(mapping?.native_binding_verified === true && mapping.reasoning_effort === 'high'
    && typeof mapping.config_id === 'string' && mapping.config_id && Number.isInteger(mapping.execution_revision) && mapping.execution_revision > 0
    && typeof mapping.configured_model_name === 'string' && mapping.configured_model_name, 'RECAPTURE_CUSTOM_MODEL_UNVERIFIED');
  const enc = value => Buffer.from(String(value)).toString('base64url');
  const model = `custom/${enc(mapping.config_id)}/${mapping.execution_revision}/${enc(mapping.configured_model_name)}`;
  const b = data.binding, turn = data.turn;
  ensure(b.thread_id === session.thread_id && b.latest_turn_id === session.turn_id && b.session_id === session.session_id
    && b.workspace_root === session.cwd && b.project_id === s.client.workspace_selection?.project_id, 'RECAPTURE_NATIVE_BINDING_MISMATCH');
  ensure(turn.thread_id === session.thread_id && turn.turn_id === session.turn_id && turn.state === 'completed' && turn.completed_at, 'RECAPTURE_NATIVE_TURN_MISMATCH');
  const sdk = data.sdk, metas = sdk.filter(r => r.type === 'session_meta').map(r => r.payload);
  ensure(metas.length === 1 && metas[0].id === session.session_id && metas[0].cwd === session.cwd, 'RECAPTURE_SDK_SESSION_MISMATCH');
  const contexts = sdk.filter(r => r.type === 'turn_context').map(r => r.payload);
  ensure(contexts.length && contexts.every(c => c.turn_id === session.turn_id && c.cwd === session.cwd && c.model === model && c.effort === 'high'), 'RECAPTURE_SDK_CONTEXT_MISMATCH');
  const markers = type => sdk.map((r, i) => ({ ...r, line: i + 1 })).filter(r => r.type === 'event_msg' && r.payload?.type === type);
  const starts = markers('task_started'), ends = markers('task_complete'), users = markers('user_message');
  ensure(starts.length === 1 && ends.length === 1 && starts[0].line < ends[0].line
    && starts[0].payload.turn_id === session.turn_id && ends[0].payload.turn_id === session.turn_id, 'RECAPTURE_SDK_BOUNDARY_MISMATCH');
  ensure(users.length === 1 && recaptureSha(Buffer.from(users[0].payload.message)) === s.prompt.sha256, 'RECAPTURE_SDK_PROMPT_MISMATCH');
  const messages = sdk.map((r, i) => ({ ...r.payload, line: i + 1, envelope: r.type })).filter(r => r.envelope === 'response_item' && r.type === 'message' && r.role === 'assistant');
  ensure(messages.length && messages.every(r => starts[0].line < r.line && r.line < ends[0].line), 'RECAPTURE_SDK_MESSAGE_RANGE_INVALID');
  const text = r => {
    ensure(r.content?.length === 1 && r.content[0].type === 'output_text' && typeof r.content[0].text === 'string', 'RECAPTURE_SDK_TEXT_SHAPE_UNSUPPORTED');
    return r.content[0].text;
  };
  const final = messages.at(-1), finalText = text(final);
  ensure(finalText.trim() && ends[0].payload.last_agent_message === finalText, 'RECAPTURE_SDK_FINAL_DISAGREEMENT');
  ensure(!sdk.slice(final.line, ends[0].line - 1).some(r => r.type === 'response_item' && ['function_call', 'custom_tool_call', 'tool_search_call'].includes(r.payload?.type)), 'RECAPTURE_SDK_TOOL_AFTER_FINAL');
  ensure(turn.assistant_message_id === 'assistant:' + final.id, 'RECAPTURE_FINAL_MESSAGE_ID_MISMATCH');
  const native = data.messages;
  ensure(native.length && native.every(r => r.thread_id === session.thread_id && r.turn_id === session.turn_id && r.role === 'assistant'), 'RECAPTURE_PROJECTION_SCOPE_MISMATCH');
  const selected = native.filter(r => r.message_id === turn.assistant_message_id);
  ensure(selected.length === 1 && selected[0].is_streaming === 0 && selected[0].text === finalText, 'RECAPTURE_PROJECTION_FINAL_DISAGREEMENT');
  const earlier = messages.slice(0, -1).filter(r => Buffer.from(text(r) + '\n').equals(data.originalFinal));
  ensure(earlier.length === 1, 'RECAPTURE_ORIGINAL_NOT_UNIQUE_EARLIER_MESSAGE');
  const oldNative = native.filter(r => r.message_id === 'assistant:' + earlier[0].id);
  ensure(oldNative.length === 1 && oldNative[0].is_streaming === 0 && Buffer.from(oldNative[0].text + '\n').equals(data.originalFinal), 'RECAPTURE_ORIGINAL_NOT_EARLIER_NATIVE_MESSAGE');
  const providers = data.provider;
  ensure(providers.length && providers.every(r => r.thread_id === session.thread_id && r.turn_id === session.turn_id), 'RECAPTURE_PROVIDER_SCOPE_MISMATCH');
  const completed = providers.filter(r => r.event_type === 'turn.completed');
  ensure(completed.length === 1, 'RECAPTURE_PROVIDER_TERMINAL_AMBIGUOUS');
  const terminal = JSON.parse(completed[0].event_json);
  ensure(terminal.threadId === session.thread_id && terminal.turnId === session.turn_id && terminal.payload?.state === 'completed', 'RECAPTURE_PROVIDER_TERMINAL_MISMATCH');
  const items = providers.filter(r => r.event_type === 'item.completed' && JSON.parse(r.event_json).itemId === final.id);
  ensure(items.length === 1, 'RECAPTURE_PROVIDER_FINAL_AMBIGUOUS');
  const itemRow = items[0], event = JSON.parse(itemRow.event_json), payload = event.payload, item = payload?.data?.item;
  ensure(itemRow.lifecycle_generation && itemRow.lifecycle_generation === completed[0].lifecycle_generation, 'RECAPTURE_PROVIDER_LIFECYCLE_MISMATCH');
  ensure(event.threadId === session.thread_id && event.turnId === session.turn_id && payload.itemType === 'assistant_message'
    && payload.status === 'completed' && item?.type === 'agentMessage' && item.id === final.id && item.text === finalText, 'RECAPTURE_PROVIDER_FINAL_DISAGREEMENT');
  ensure(payload.data.threadId === session.session_id && payload.data.turnId === session.turn_id, 'RECAPTURE_PROVIDER_SDK_BINDING_MISMATCH');
  ensure(itemRow.sequence < completed[0].sequence, 'RECAPTURE_PROVIDER_ORDER_INVALID');
  const finalBytes = Buffer.from(finalText + '\n');
  ensure(!finalBytes.equals(data.originalFinal), 'RECAPTURE_NO_DIFFERENCE');
  return { profile: FINAL_RECAPTURE_PROFILE, identity: s.identity,
    old_final_sha256: recaptureSha(data.originalFinal), new_final_sha256: recaptureSha(finalBytes),
    old_sdk_message_id: earlier[0].id, old_sdk_line: earlier[0].line,
    final_sdk_message_id: final.id, final_sdk_line: final.line, sdk_complete_line: ends[0].line,
    provider_final_sequence: itemRow.sequence, provider_final_event_id: itemRow.event_id,
    provider_completed_sequence: completed[0].sequence, candidate_unchanged: true, resend_count: 0,
    finalBytes, finalProviderEvent: event };
}
async function loadInput(root, bytes, candidateRoot) {
  const input = json(bytes);
  ensure(input.schema_version === FINAL_RECAPTURE_INPUT && input.profile === FINAL_RECAPTURE_PROFILE
    && Number.isFinite(Date.parse(input.created_at)) && same(Object.keys(input.sources ?? {}).sort(), [...ROLES].sort()), 'RECAPTURE_INPUT_INVALID');
  ensure(ROLES.every(role => input.sources[role]?.path?.startsWith('inputs/'))
    && new Set(ROLES.map(role => input.sources[role].path)).size === ROLES.length, 'RECAPTURE_INPUT_PATH_SCOPE_INVALID');
  const sources = {};
  for (const role of ROLES) sources[role] = await artifact(root, input.sources[role]);
  const auth = json(sources.authorization);
  ensure(auth.status === 'GRANTED' && auth.profile === FINAL_RECAPTURE_PROFILE && typeof auth.source === 'string' && auth.source
    && typeof auth.scope === 'string' && auth.scope && auth.review_sha256 === recaptureSha(sources.authorization_review), 'RECAPTURE_AUTHORIZATION_INVALID');
  const originalState = json(sources.original_state), candidateBefore = json(sources.candidate_tree);
  const originalRecord = json(sources.original_record);
  ensure(same(originalRecord.identity, originalState.identity), 'RECAPTURE_ORIGINAL_RECORD_IDENTITY_MISMATCH');
  const proof = validateTerminalFinalRecapture({ originalState, originalFinal: sources.original_final,
    binding: json(sources.native_binding), turn: json(sources.native_turn), messages: json(sources.native_messages),
    provider: lines(sources.provider_rows), sdk: lines(sources.sdk), candidateBefore,
    candidateAfter: candidateRoot ? await recaptureCandidateTree(candidateRoot) : candidateBefore });
  return { input, sources, originalState, proof };
}
function derivedState(loaded, finalRelative, inputBytes) {
  const state = structuredClone(loaded.originalState);
  state.evidence = { ...state.evidence, final_response_path: safe(finalRelative), final_response_sha256: loaded.proof.new_final_sha256 };
  state.history = [...(state.history ?? []), { at: loaded.input.created_at, phase: state.phase,
    event: 'TERMINAL_FINAL_RECAPTURE_ADOPTED', profile: FINAL_RECAPTURE_PROFILE,
    input_manifest_sha256: recaptureSha(inputBytes), original_state_sha256: recaptureSha(loaded.sources.original_state),
    original_final_sha256: loaded.proof.old_final_sha256, authorization_sha256: recaptureSha(loaded.sources.authorization) }];
  return state;
}
export async function prepareTerminalFinalRecapture({ inputManifest, outputDir }) {
  const bytes = await readFile(inputManifest), inputRoot = dirname(resolve(inputManifest));
  const preliminary = await loadInput(inputRoot, bytes);
  const root = await realpath(resolve(preliminary.originalState.task_root, '../../..')), workspace = await realpath(preliminary.originalState.candidate_workspace);
  const output = join(await realpath(dirname(resolve(outputDir))), basename(outputDir));
  ensure(inside(root, output) && output !== root && !inside(workspace, output), 'RECAPTURE_OUTPUT_SCOPE_INVALID');
  const loaded = await loadInput(inputRoot, bytes, workspace);
  const finalRelative = relative(root, join(output, 'final-response.md')).split('\\').join('/');
  const state = derivedState(loaded, finalRelative, bytes), stateBytes = pretty(state);
  const { finalBytes, finalProviderEvent, ...proof } = loaded.proof;
  const manifest = { schema_version: FINAL_RECAPTURE_BUNDLE, profile: FINAL_RECAPTURE_PROFILE,
    identity: state.identity, session: state.session, input_manifest: ref('input-manifest.json', bytes),
    derived_state: ref('automation-state.json', stateBytes), final_response: ref('final-response.md', finalBytes),
    final_response_relative_path: finalRelative, proof };
  await mkdir(output, { recursive: false });
  for (const role of ROLES) {
    const path = join(output, safe(loaded.input.sources[role].path));
    await mkdir(dirname(path), { recursive: true }); await writeFile(path, loaded.sources[role], { flag: 'wx' });
  }
  await writeFile(join(output, 'input-manifest.json'), bytes, { flag: 'wx' });
  await writeFile(join(output, 'automation-state.json'), stateBytes, { flag: 'wx' });
  await writeFile(join(output, 'final-response.md'), finalBytes, { flag: 'wx' });
  await writeFile(join(output, 'recapture-manifest.json'), pretty(manifest), { flag: 'wx' });
  return { status: 'PASS', state_file: join(output, 'automation-state.json'), manifest: join(output, 'recapture-manifest.json'), proof };
}
export async function readTerminalFinalRecapture(path, state, stateBytes, { candidateRoot = null } = {}) {
  const manifestBytes = await readFile(path), manifest = json(manifestBytes), root = dirname(resolve(path));
  ensure(manifest.schema_version === FINAL_RECAPTURE_BUNDLE && manifest.profile === FINAL_RECAPTURE_PROFILE
    && same(manifest.identity, state.identity) && same(manifest.session, state.session), 'RECAPTURE_BUNDLE_IDENTITY_MISMATCH');
  ensure(manifest.derived_state.sha256 === recaptureSha(stateBytes) && manifest.derived_state.size === stateBytes.length, 'RECAPTURE_DERIVED_STATE_SHA_MISMATCH');
  const inputBytes = await artifact(root, manifest.input_manifest), loaded = await loadInput(root, inputBytes, candidateRoot);
  const expected = derivedState(loaded, manifest.final_response_relative_path, inputBytes);
  ensure(same(state, expected), 'RECAPTURE_DERIVATION_MISMATCH');
  const finalBytes = await artifact(root, manifest.final_response);
  ensure(finalBytes.equals(loaded.proof.finalBytes) && state.evidence.final_response_sha256 === recaptureSha(finalBytes), 'RECAPTURE_FINAL_SHA_MISMATCH');
  const { finalBytes: ignored, finalProviderEvent, ...proof } = loaded.proof;
  ensure(same(manifest.proof, proof), 'RECAPTURE_PROOF_MISMATCH');
  const artifacts = [{ path: PREFIX + 'recapture-manifest.json', bytes: manifestBytes },
    { path: PREFIX + manifest.input_manifest.path, bytes: inputBytes },
    { path: PREFIX + manifest.derived_state.path, bytes: stateBytes },
    { path: PREFIX + manifest.final_response.path, bytes: finalBytes },
    ...ROLES.map(role => ({ path: PREFIX + loaded.input.sources[role].path, bytes: loaded.sources[role] }))];
  ensure(new Set(artifacts.map(a => a.path)).size === artifacts.length, 'RECAPTURE_BINDING_PATH_DUPLICATE');
  return { proof, finalProviderEvent, sdk_sha256: recaptureSha(loaded.sources.sdk), binding_artifacts: artifacts };
}
export function assertRecaptureArchiveSources(bundle, sdkBytes, providerRows) {
  ensure(sdkBytes && recaptureSha(sdkBytes) === bundle.sdk_sha256, 'RECAPTURE_ARCHIVED_SDK_MISMATCH');
  const rows = providerRows.filter(r => r.sequence === bundle.proof.provider_final_sequence && r.event_id === bundle.proof.provider_final_event_id);
  ensure(rows.length === 1 && same(rows[0].event ?? JSON.parse(rows[0].event_json), bundle.finalProviderEvent), 'RECAPTURE_ARCHIVED_PROVIDER_MISMATCH');
}
export async function verifyArchivedTerminalFinalRecapture(index, state, stateBytes, root, { candidateRoot = null } = {}) {
  ensure(index.terminal_final_recapture_profile?.id === FINAL_RECAPTURE_PROFILE
    && index.canonical_source_policy?.id === 'bound-native-sdk-canonical/v1' && !index.native_provider_log_profile, 'RECAPTURE_ARCHIVE_PROFILE_INVALID');
  const binding = (index.binding_evidence ?? []).filter(r => r.path === PREFIX + 'recapture-manifest.json');
  ensure(binding.length === 1, 'RECAPTURE_ARCHIVED_MANIFEST_MISSING');
  await artifact(root, binding[0]);
  const bundle = await readTerminalFinalRecapture(join(root, binding[0].path), state, stateBytes, { candidateRoot });
  const declared = new Map((index.binding_evidence ?? []).map(r => [r.path, r]));
  for (const row of bundle.binding_artifacts) {
    const original = declared.get(row.path); ensure(original && original.sha256 === recaptureSha(row.bytes) && original.size === row.bytes.length, 'RECAPTURE_BINDING_CLOSURE_MISMATCH');
    await artifact(root, original);
  }
  const sdk = index.raw_trace.find(r => r.path === 'raw/astronstudio-rollout.jsonl');
  const provider = index.raw_trace.find(r => r.path === 'raw/astronstudio-provider-events.jsonl');
  ensure(sdk && provider, 'RECAPTURE_ARCHIVED_RAW_MISSING');
  assertRecaptureArchiveSources(bundle, await artifact(root, sdk), lines(await artifact(root, provider)));
  return bundle.proof;
}
