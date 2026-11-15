// Recompute reporting resources from a sealed AgentCube execution. Never edits it.
import {createHash, randomUUID} from 'node:crypto';
import {readFile, writeFile, lstat, readdir, realpath, mkdir, copyFile, rename, rm} from 'node:fs/promises';
import {resolve, relative, dirname, join, isAbsolute, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {verifyAgentCubeNative} from './agentcube-native-binding.mjs';
import {analyzeRollout} from './astronstudio-rollout.mjs';

export const AGENTCUBE_RESOURCE_SCHEMA = 'wildclawbench.agentcube-resource-supplement/v1';
const requireValue = (ok, code) => {if (!ok) throw Error(code);};
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
const same = (a, b) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));
const json = value => JSON.stringify(value, null, 2) + '\n';
function child(root, name) {
  requireValue(typeof name === 'string' && name && !isAbsolute(name) && !name.includes('\\')
    && name.split('/').every(part => part && part !== '.' && part !== '..'), 'AGENTCUBE_RESOURCE_PATH');
  const path = resolve(root, name);
  requireValue(path.startsWith(resolve(root) + sep), 'AGENTCUBE_RESOURCE_ESCAPE');
  return path;
}
async function bytes(path) {
  const info = await lstat(path);
  requireValue(info.isFile() && !info.isSymbolicLink() && await realpath(path) === resolve(path), 'AGENTCUBE_RESOURCE_NOT_REGULAR');
  const data = await readFile(path), after = await lstat(path);
  requireValue(data.length === info.size && after.ino === info.ino && after.mtimeMs === info.mtimeMs, 'AGENTCUBE_RESOURCE_SOURCE_CHANGED');
  return data;
}
async function inventory(root) {
  const rows = [];
  async function walk(folder) {
    for (const entry of await readdir(folder, {withFileTypes:true})) {
      requireValue(!entry.isSymbolicLink(), 'AGENTCUBE_RESOURCE_SYMLINK');
      const path = join(folder, entry.name);
      if (entry.isDirectory()) await walk(path);
      else if (path !== join(root, 'supplement.json')) {
        const data = await bytes(path);
        rows.push({path:relative(root, path).split(sep).join('/'), size:data.length, sha256:sha(data)});
      }
    }
  }
  await walk(root);
  return rows.sort((a,b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
}
async function copyTree(source, target) {
  requireValue((await lstat(source)).isDirectory() && await realpath(source) === resolve(source), 'AGENTCUBE_RESOURCE_TRACE_ROOT');
  await mkdir(target);
  for (const entry of await readdir(source, {withFileTypes:true})) {
    requireValue(!entry.isSymbolicLink(), 'AGENTCUBE_RESOURCE_SYMLINK');
    const from = join(source, entry.name), to = join(target, entry.name);
    if (entry.isDirectory()) await copyTree(from, to);
    else {
      const original = await bytes(from);
      await copyFile(from, to);
      requireValue(sha(await bytes(to)) === sha(original), 'AGENTCUBE_RESOURCE_COPY_DRIFT');
    }
  }
}
async function compute(unitRoot, record, directory) {
  const indexBytes = await bytes(join(directory, 'trace/trace-index.json'));
  const index = JSON.parse(indexBytes), traceRoot = join(directory, 'trace');
  const proofBytes = await bytes(join(traceRoot, 'bindings/execution-proof.json'));
  const proof = JSON.parse(proofBytes), binding = index.binding_evidence?.filter(r => r.path === 'bindings/execution-proof.json');
  requireValue(binding?.length === 1 && binding[0].sha256 === sha(proofBytes)
    && binding[0].size === proofBytes.length, 'AGENTCUBE_RESOURCE_PROOF_BINDING');
  await verifyAgentCubeNative({unitRoot, traceRoot, index, stateBytes:proofBytes, record});
  const original = JSON.parse(await bytes(join(directory, 'original-resource-metrics.json')));
  requireValue(same(original.identity, record.identity) && original.collection.collector === 'agentcube-astudio-native', 'AGENTCUBE_RESOURCE_IDENTITY');
  const raw = await bytes(child(traceRoot, index.raw_trace[0].path));
  const analysis = analyzeRollout(raw, {phase:'COMPLETED', session:{...proof.native_binding.session, verified:true},
    prompt:{send_status:'sent', sha256:proof.native_binding.prompt_transport.native_message_sha256}});
  const metrics = structuredClone(original);
  for (const group of ['usage','requests']) {
    metrics.metrics[group] = analysis.metrics[group];
    for (const field of Object.keys(analysis.metrics[group])) metrics.collection.coverage[field] = analysis.collection.coverage[field];
  }
  metrics.collection.known_subtotals = Object.fromEntries(Object.entries(analysis.collection.known_subtotals)
    .filter(([field]) => Object.hasOwn(metrics.collection.coverage, field)));
  metrics.collection.native_usage_reconciliation = analysis.usage_reconciliation;
  metrics.collection.warnings = [...new Set([...(original.collection.warnings || []), ...analysis.collection.warnings])];
  if (analysis.usage_reconciliation.reconciled) metrics.collection.warnings = metrics.collection.warnings
    .filter(warning => warning !== 'report-usage-native-reconciliation-unavailable');
  metrics.collection.native_parser = {profile:'agentcube-bound-general-rollout/v1',
    entry_sha256:sha(await bytes(fileURLToPath(new URL('./astronstudio-rollout.mjs', import.meta.url)))),
    timing_helper_sha256:sha(await bytes(fileURLToPath(new URL('../resource-metrics/flow-timing.mjs', import.meta.url))))};
  return {metrics, tool_counts:analysis.tool_counts};
}
export async function verifyAgentCubeResourceSupplement({unitRoot, taskId, executionRecord}) {
  unitRoot = resolve(unitRoot);
  requireValue(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(taskId), 'AGENTCUBE_RESOURCE_TASK');
  const root = child(unitRoot, 'evidence/resource-supplements/' + taskId);
  const manifestBytes = await bytes(join(root, 'supplement.json')), manifest = JSON.parse(manifestBytes);
  const recordBytes = await bytes(executionRecord), record = JSON.parse(recordBytes);
  requireValue(manifest.schema_version === AGENTCUBE_RESOURCE_SCHEMA && manifest.score_changed === false
    && manifest.zero_imputation_used === false && record.identity.task_id === taskId
    && same(manifest.identity, record.identity) && manifest.execution_record_sha256 === sha(recordBytes), 'AGENTCUBE_RESOURCE_MANIFEST');
  requireValue(same(await inventory(root), manifest.artifacts), 'AGENTCUBE_RESOURCE_ARTIFACT_DRIFT');
  requireValue(sha(await bytes(join(root, 'original-execution-record.json'))) === sha(recordBytes)
    && sha(await bytes(child(unitRoot, record.resource_metrics_path))) === manifest.original_resource_sha256
    && sha(await bytes(join(root, 'original-resource-metrics.json'))) === manifest.original_resource_sha256
    && sha(await bytes(child(unitRoot, record.evidence.trace_index_path))) === manifest.original_trace_index_sha256
    && sha(await bytes(join(root, 'trace/trace-index.json'))) === manifest.original_trace_index_sha256, 'AGENTCUBE_RESOURCE_ORIGINAL_DRIFT');
  const computed = await compute(unitRoot, record, root);
  requireValue(same(computed.metrics, JSON.parse(await bytes(join(root, 'resource-metrics.json'))))
    && same(computed.tool_counts, JSON.parse(await bytes(join(root, 'tool-counts.json')))), 'AGENTCUBE_RESOURCE_RECOMPUTATION');
  const prefix = relative(unitRoot, root).split(sep).join('/');
  return {status:'PASS', identity:record.identity, manifest_sha256:sha(manifestBytes),
    metrics:{...computed.metrics, tool_counts:computed.tool_counts},
    trace_index_path:prefix + '/trace/trace-index.json', transcript_path:prefix + '/trace/transcript.jsonl'};
}
export async function createAgentCubeResourceSupplement({unitRoot, taskId, executionRecord}) {
  unitRoot = resolve(unitRoot);
  const recordBytes = await bytes(executionRecord), record = JSON.parse(recordBytes);
  taskId = taskId || record.identity.task_id;
  requireValue(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(taskId) && record.identity.task_id === taskId, 'AGENTCUBE_RESOURCE_TASK');
  const parent = child(unitRoot, 'evidence/resource-supplements'), target = join(parent, taskId);
  await mkdir(parent, {recursive:true});
  try {await lstat(target); throw Error('AGENTCUBE_RESOURCE_TARGET_EXISTS');} catch (error) {if (error.code !== 'ENOENT') throw error;}
  const stage = join(parent, '.' + taskId + '-' + randomUUID());
  await mkdir(stage);
  try {
    const resource = await bytes(child(unitRoot, record.resource_metrics_path));
    const index = child(unitRoot, record.evidence.trace_index_path);
    await copyTree(dirname(index), join(stage, 'trace'));
    await writeFile(join(stage, 'original-execution-record.json'), recordBytes, {flag:'wx'});
    await writeFile(join(stage, 'original-resource-metrics.json'), resource, {flag:'wx'});
    const computed = await compute(unitRoot, record, stage);
    await writeFile(join(stage, 'resource-metrics.json'), json(computed.metrics), {flag:'wx'});
    await writeFile(join(stage, 'tool-counts.json'), json(computed.tool_counts), {flag:'wx'});
    await writeFile(join(stage, 'supplement.json'), json({schema_version:AGENTCUBE_RESOURCE_SCHEMA,
      identity:record.identity, score_changed:false, zero_imputation_used:false,
      execution_record_sha256:sha(recordBytes), original_resource_sha256:sha(resource),
      original_trace_index_sha256:sha(await bytes(index)), artifacts:await inventory(stage)}), {flag:'wx'});
    await rename(stage, target);
  } catch (error) {await rm(stage, {recursive:true, force:true}); throw error;}
  return verifyAgentCubeResourceSupplement({unitRoot, taskId, executionRecord});
}
