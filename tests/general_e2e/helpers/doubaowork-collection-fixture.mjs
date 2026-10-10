import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, readFile, writeFile, realpath, rm } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL, fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { DISPATCHER_PROFILE, DISPATCHER_SOURCE_SHA256 } from '../../../tools/report/e2e-shared/doubaowork/runtime-dispatcher.mjs';

// Synthetic native discovery; execute the real reader, collector and projection.
export async function fixture(t) {
  const REPO = fileURLToPath(new URL('../../../', import.meta.url));
  const OUT = await realpath(await mkdtemp(join(tmpdir(), 'doubao-collection-contract-')));
  t.after(() => rm(OUT, { recursive: true, force: true }));
  const sha = x => createHash('sha256').update(x).digest('hex');
  async function put(path, value) {
    const bytes = Buffer.isBuffer(value) ? value : Buffer.from(JSON.stringify(value, null, 2) + '\n');
    await mkdir(dirname(path), { recursive: true }); await writeFile(path, bytes);
    return { file: path.split('/').at(-1), sha256: sha(bytes), size_bytes: bytes.length };
  }

  // The real bound reader and collector run against synthetic native discovery.
  // The platform/parser adapter is mocked; integrity, normalization, collection,
  // timeline merging, and record projection are the repository implementations.
  const unitPath = join(OUT, `fixture-unit-${Date.now()}`);
  const unit = await realpath(await mkdir(unitPath, { recursive: true }).then(() => unitPath));
  const workspace = join(unit, 'execution/tasks/task-probe/workspace');
  await mkdir(workspace, { recursive: true });
  const prompt = 'fixture prompt';
  const promptPath = join(unit, 'execution/tasks/task-probe/prompt.md');
  await writeFile(promptPath, prompt);
  const control = join(unit, '.general-e2e/execution/task-probe/doubaowork');
  const config = { runtime_type: 2, client_option: { workspace }, agent_task_param: { workspace, runtime_type: 2 } };
  const user = { conversation_id: '123456789', message_id: '100', user_type: 1, status: 1,
    final_status: { message: 'Success' }, ext: { general_task_param: JSON.stringify(config), conversation_init_option: '{"project_id":"123"}' },
    content_blocks_v2: [{ block_type: 10000, content: { text_block: { text: prompt } }, is_finish: true }] };
  const assistant = { conversation_id: '123456789', message_id: '101', reply_id: '100', session_id: 'native-request', user_type: 2,
    status: 1, stage: 4, final_status: { session: 'Success' }, ext: { general_task_param: JSON.stringify(config), is_finish: '1' },
    content_blocks_v2: [{ block_type: 10000, is_finish: true, content: { text_block: { text: 'Done.' } } }],
    local_info: { query_send_timestamp: 1000, perf_mark_samples: [{ queryMessageId: '100', answerId: '101', taskId: 'native-request', receiveTimestamp: 2000, marks: [{ evName: 'task_finish' }] }] } };
  const runtime = { schema: 'wildclawbench.doubaowork-runtime-messages/v1', source: 'native-im.useMessageStore.getState', conversation_id: '123456789',
    maps: { messageMap: { 100: user, 101: assistant }, messageListStatusMap: { hasMore: false, inIniting: false, inLoadingMore: false } } };
  const seal = r => { r.payload_sha256 = sha(JSON.stringify({ conversation_id: r.conversation_id, maps: r.maps })); return r; };
  const manifest = { manifest_kind: 'execution', batch_id: 'offline-probe', dataset: { id: 'fixture', digest: 'd'.repeat(64) },
    unit: { unit_id: 'doubao-fixture', harness: { id: 'doubaowork', platform: 'darwin' }, model: { requested_id: 'fixture-model', reasoning_effort: 'high' } },
    tasks: [{ task_id: 'task-probe', prompt: { path: 'execution/tasks/task-probe/prompt.md', sent_sha256: sha(prompt) }, workspace: { path: 'execution/tasks/task-probe/workspace' } }] };
  const manifestProof = await put(join(unit, 'manifest.json'), manifest);
  const journal = { scene: 'general', attempt_id: 'attempt-fixture', identity: { batch_id: 'offline-probe', task_id: 'task-probe' }, prepared: { unit_id: 'doubao-fixture' }, workspace,
    client: { version: '2.31.10', project_id_sha256: sha('123'), manifest_sha256: manifestProof.sha256 }, actual: { model: 'fixture-model' },
    session: { conversation_id: '123456789', native_request_session_id: 'native-request', prompt_readback: { status: 'verified' } },
    prompt: { file: promptPath, sha256: sha(prompt), readback_sha256: sha(prompt), readback_bytes: Buffer.byteLength(prompt) },
    send: { dispatch_attempt_count: 1 }, timing: { sent_at: new Date(1000).toISOString() }, native_observation: {} };
  journal.native_observation.artifact = await put(join(control, 'runtime.json'), seal(runtime));
  journal.native_observation.final_reply = await put(join(control, 'final.txt'), Buffer.from('Done.'));
  const trajectoryPath = join(OUT, 'native-fixture/trajectory.jsonl');
  const trajectoryBytes = Buffer.from(JSON.stringify({ role: 'user', content: prompt }) + '\n');
  await put(trajectoryPath, trajectoryBytes);
  const trajectoryEvents = [{ kind: 'user_message', content: prompt, source: { file: 'raw/trajectory.jsonl', line: 1 } }];
  const source = { relative_path: 'trajectory.jsonl', sha256: sha(trajectoryBytes), size_bytes: trajectoryBytes.length };
  const cache = new Map();
  async function synthetic(id, namespace) {
    if (!cache.has(id)) {
      const names = Object.keys(namespace);
      cache.set(id, new vm.SyntheticModule(names, function () { for (const key of names) this.setExport(key, namespace[key]); }, { identifier: id }));
    }
    return cache.get(id);
  }
  async function link(specifier, parent) {
    if (specifier.startsWith('node:')) return synthetic(specifier, await import(specifier));
    const path = resolve(dirname(parent.identifier), specifier);
    if (path.endsWith('/bound-evidence.mjs')) return bound;
    const actual = await import(pathToFileURL(path).href);
    if (path.endsWith('/platform.mjs')) return synthetic(path, { ...actual,
      discoverNativeSources: async () => ({ session: { exists: true, trajectories: [{}] } }),
      defaultNativeRoots: () => ({ sessions_root: dirname(trajectoryPath) }) });
    if (path.endsWith('/native-evidence.mjs')) return synthetic(path, { ...actual,
      buildNativeEvidence: async () => ({ trace: { sources: [source], events: structuredClone(trajectoryEvents), warnings: [] } }) });
    return synthetic(path, actual);
  }
  async function sourceModule(path, suffix = '') {
    const mod = new vm.SourceTextModule(await readFile(path, 'utf8') + suffix, { identifier: path, initializeImportMeta(meta) { meta.url = pathToFileURL(path).href; } });
    await mod.link(link); await mod.evaluate(); return mod;
  }
  const bound = await sourceModule(join(REPO, 'tools/report/e2e-shared/doubaowork/bound-evidence.mjs'));
  const collect = await sourceModule(join(REPO, 'tools/report/skills/general-e2e/collect-general-e2e/drivers/doubaowork/collector.mjs'));
  const finalizer = await sourceModule(join(REPO, 'tools/report/skills/general-e2e/collect-general-e2e/scripts/lib/general-finalizer.mjs'), '\nexport { buildExecutionRecord };\n');

  const event = { phase: 'started', tool_call_id: 'call-1', tool_name: 'Bash', input: { command: 'pwd' },
    instance_id: 'sandbox', native_cwd: workspace, native_agent_id: 'native-request', conversation_id: '123456789', observed_at: new Date(1000).toISOString() };
  const result = { status: 'success', content: 'ok' };
  const row = { toolCallId: 'call-1', toolName: 'Bash', instanceId: 'sandbox', sseIdentity: { agentId: 'native-request' }, uploadState: 'uploaded', cachedAtMs: 1500, result };
  const snapshot = { schema: 'wildclawbench.doubaowork-native-tool-events/v1', profile: DISPATCHER_PROFILE, profile_sha256: DISPATCHER_SOURCE_SHA256,
    attempt_id: journal.attempt_id, workspace, native_agent_id: 'native-request', installed_at: new Date(0).toISOString(), collected_at: new Date(3000).toISOString(),
    events: [event, { ...event, phase: 'settled', observed_at: new Date(1500).toISOString(), input: undefined, output: result }], ledger: [row],
    ledger_samples: [{ row, observed_at_ms: 2000 }], contexts: [], errors: [], overflow: false, unknown_context_events: 0, ledger_at_capacity: false,
    ledger_retention_ms: 1800000, ledger_capacity: 1000, ledger_observation_policy: 'uploaded-ledger-observed-within-native-ttl/v1' };
  journal.native_tool_observer = { profile_sha256: DISPATCHER_SOURCE_SHA256 };
  journal.native_observation.native_tools_artifact = await put(join(control, 'tools.json'), snapshot);

  const journalFile = join(control, 'journal.json');
  await put(journalFile, journal);
  const outputRoot = join(unit, '.general-e2e/collection/task-probe/probe-1');
  return { unit, workspace, control, journal, journalFile, runtime, snapshot, manifest, outputRoot,
    trajectoryPath, trajectoryBytes, source,
    writeArtifact: put, seal,
    readBound: options => bound.namespace.readBoundNativeEvidence({ journalFile, journal, ...options }),
    collect: async () => { await put(journalFile, journal); return collect.namespace.collectDoubaoGeneral({ unitRoot: unit, journalFile, outputRoot }); },
    project: (index, state, resource) => finalizer.namespace.buildExecutionRecord({ manifest, state,
      traceBundle: { index, traceArtifacts: [] }, resource: { value: resource }, finalResponse: { sha256: sha('Done.') },
      candidateArtifact: { expected_sha256: 'c'.repeat(64), frozen_at: new Date(3000).toISOString(), candidate: { path: 'evidence/candidate' } }, evidenceRootRelative: 'evidence' }),
  };
}
