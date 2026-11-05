import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { MOA_SOURCE_SHA256, validateMoaBackendProof } from './runtime-moa.mjs';
import { normalizeNativeToolEvents } from './runtime-tools.mjs';
const sha = value => createHash('sha256').update(value).digest('hex');
const check = (ok, code) => { if (!ok) throw Error('DOUBAOWORK_MOA_SDK_' + code); };
const run = promisify(execFile);
const allowedImageOrigin = parsed => parsed.protocol === 'https:' && !parsed.username && !parsed.password && !parsed.port
  && (/^p[0-9]+-flow-(?:imagex-)?sign\.byteimg\.com$/u.test(parsed.hostname)
    || ['aka.doubaocdn.com','ar5iv.labs.arxiv.org','arxiv.org'].includes(parsed.hostname));

// This is the original SDK-written model protocol, not a reconstruction from
// candidate files or UI text. Keep the unused legacy JS observer as evidence;
// its zero deliveries do not mean zero SDK tool calls.
export function verifyMoaSdkProtocol({ trajectoryBytes, assignmentProof, snapshot, journal, source }) {
  check(journal.scene === 'general' && journal.client.version === '2.35.15'
    && assignmentProof?.status === 'verified' && assignmentProof.source === 'native-main-assignment/v1'
    && assignmentProof.agent_id === source.agent_id && snapshot.profile_sha256 === MOA_SOURCE_SHA256,
  'PROFILE_UNBOUND');
  check(journal.send.dispatch_attempt_count === 1 && journal.session.prompt_readback.status === 'verified', 'SEND_UNBOUND');
  validateMoaBackendProof(snapshot.native_backend);
  normalizeNativeToolEvents(snapshot, { attemptId: journal.attempt_id, workspace: journal.workspace,
    agentId: journal.session.native_request_session_id, conversationId: journal.session.conversation_id,
    sentAt: journal.timing.sent_at, finishedAt: journal.native_observation.finished_at });
  check(snapshot.events.length === 0 && snapshot.ledger.length === 0 && snapshot.errors.length === 0,
    'MIXED_OR_INVALID_OBSERVER');
  check(sha(trajectoryBytes) === source.sha256 && source.kind === 'doubaowork-session-trajectory'
    && source.relative_path === `${journal.session.conversation_id}/agents/${source.agent_id}/system/trajectory.jsonl`
    && trajectoryBytes.at(-1) === 10, 'SOURCE_DRIFT');
  const calls = new Map(), attachments = [];
  const lines = new TextDecoder('utf-8', { fatal: true }).decode(trajectoryBytes).split(/\r?\n/u);
  for (const [i,line] of lines.entries()) {
    if (!line.trim()) continue;
    const row = JSON.parse(line);
    check(row.role === 'assistant' || row.role === 'tool', 'ROLE_UNSUPPORTED');
    if (row.role === 'assistant') {
      check(row.content == null || typeof row.content === 'string', 'ASSISTANT_CONTENT_UNSUPPORTED');
      check(row.tool_calls == null || Array.isArray(row.tool_calls), 'CALLS_UNSUPPORTED');
      for (const call of row.tool_calls || []) {
        check(typeof call.id === 'string' && call.id.length > 0 && call.id.length <= 256 && !calls.has(call.id)
          && call.type === 'function' && typeof call.function?.name === 'string'
          && call.function.name.length > 0 && call.function.arguments && typeof call.function.arguments === 'object'
          && !Array.isArray(call.function.arguments), 'CALL_INVALID');
        calls.set(call.id, { call_id: call.id, name: call.function.name, arguments: call.function.arguments,
          call_line: i + 1, result_line: null });
      }
    } else {
      const call = calls.get(row.tool_call_id);
      check(call && call.result_line === null && typeof row.content === 'string', 'RESULT_INVALID');
      call.result_line = i + 1;
      call.result_sha256 = sha(row.content);
      check(row.image_link_list == null || Array.isArray(row.image_link_list), 'MEDIA_UNSUPPORTED');
      for (const [n,url] of (row.image_link_list || []).entries()) {
        check(typeof url === 'string', 'MEDIA_UNSUPPORTED');
        const parsed = new URL(url);
        check(allowedImageOrigin(parsed), 'MEDIA_ORIGIN_UNVERIFIED');
        attachments.push({ call_id: call.call_id, result_line: i + 1, image_index: n, url, url_sha256: sha(url) });
      }
    }
  }
  check([...calls.values()].every(c => c.result_line !== null), 'MISSING_RESULT');
  return { profile: 'doubaowork-native-moa-sdk-model-protocol-2.35.15/v1', source_sha256: source.sha256,
    native_source: { kind: source.kind, relative_path: source.relative_path, agent_id: source.agent_id, sha256: source.sha256 },
    assignment_sha256: assignmentProof.assignment_sha256, agent_id: source.agent_id, calls: [...calls.values()], attachments,
    legacy_js_observer: { status: 'not-the-sdk-execution-route', observed_deliveries: 0 },
    scope: 'SDK-persisted model requests and tool results; no hidden internal tool activity is inferred' };
}

export function parseMacSystemHttpsProxy(text) {
  const value = key => text.match(new RegExp('^\\s*' + key + '\\s*:\\s*(.+)$', 'mu'))?.[1]?.trim();
  if (value('HTTPSEnable') !== '1') return null;
  const host = value('HTTPSProxy'), port = Number(value('HTTPSPort'));
  check(['127.0.0.1','localhost'].includes(host) && Number.isSafeInteger(port) && port > 0 && port <= 65535,
    'SYSTEM_PROXY_UNVERIFIED');
  return `http://${host}:${port}`;
}
async function readSystemProxy() {
  if (process.platform !== 'darwin') return null;
  const { stdout } = await run('/usr/sbin/scutil', ['--proxy'], { encoding: 'utf8', timeout: 5000 });
  return parseMacSystemHttpsProxy(stdout);
}
async function proxyResponse(url, proxy) {
  let captured;
  try {
    captured = await run('/usr/bin/curl', ['--silent','--show-error','--proto','=https','--max-time','30',
      '--max-filesize',String(16 * 1024 * 1024),'--proxy',proxy,'--dump-header','/dev/stderr','--output','-',url],
    { encoding: 'buffer', timeout: 35000, maxBuffer: 18 * 1024 * 1024 });
  } catch (error) { throw Error('DOUBAOWORK_MOA_SDK_MEDIA_PROXY_FETCH_FAILED:' + String(error.code)); }
  const sections = captured.stderr.toString('utf8').split(/\r?\n\r?\n/u).filter(s => /^HTTP\/[\d.]+ \d{3}/u.test(s));
  const header = sections.at(-1); check(header, 'MEDIA_PROXY_HEADERS_UNVERIFIED');
  const status = Number(header.match(/^HTTP\/[\d.]+ (\d{3})/u)[1]);
  const get = key => header.match(new RegExp('^' + key + ':\\s*(.+)$', 'imu'))?.[1]?.trim();
  return new Response(captured.stdout, { status, headers: Object.fromEntries(
    ['content-type','location'].map(k => [k,get(k)]).filter(([,v]) => v)) });
}

export async function fetchMoaSdkAttachments(protocol, { disableSystemProxy = false } = {}) {
  const output = [];
  if (!protocol.attachments.length) return output;
  const proxy = disableSystemProxy ? null : await readSystemProxy();
  for (const item of protocol.attachments) {
    let url = item.url, response; const redirects = [];
    for (let hops = 0; hops < 5; hops += 1) {
      check(allowedImageOrigin(new URL(url)), 'MEDIA_ORIGIN_UNVERIFIED');
      response = proxy ? await proxyResponse(url, proxy)
        : await fetch(url, { redirect: 'manual', signal: AbortSignal.timeout(20000) });
      if (![301,302,303,307,308].includes(response.status)) break;
      const location = response.headers.get('location'); check(location, 'MEDIA_REDIRECT_UNVERIFIED');
      const target = new URL(location, url); check(allowedImageOrigin(target), 'MEDIA_REDIRECT_UNVERIFIED');
      redirects.push({ from_sha256: sha(url), to_sha256: sha(target.href), status: response.status });
      await response.body?.cancel(); url = target.href;
    }
    check(response.status === 200, 'MEDIA_FETCH_FAILED');
    const mime = (response.headers.get('content-type') || '').split(';')[0];
    check(['image/png','image/jpeg','image/webp','image/gif'].includes(mime), 'MEDIA_TYPE_UNVERIFIED');
    const reader = response.body.getReader(), chunks = []; let size = 0;
    try {
      while (true) { const { done, value } = await reader.read(); if (done) break;
        size += value.length; check(size <= 16 * 1024 * 1024, 'MEDIA_TOO_LARGE'); chunks.push(Buffer.from(value)); }
    } catch (error) { await reader.cancel().catch(() => {}); throw error; }
    finally { reader.releaseLock(); }
    const bytes = Buffer.concat(chunks), png = bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])),
      jpeg = bytes[0] === 255 && bytes[1] === 216, webp = bytes.subarray(0,4).toString() === 'RIFF' && bytes.subarray(8,12).toString() === 'WEBP',
      gif = ['GIF87a','GIF89a'].includes(bytes.subarray(0,6).toString());
    check(mime === 'image/png' && png || mime === 'image/jpeg' && jpeg || mime === 'image/webp' && webp || mime === 'image/gif' && gif, 'MEDIA_BYTES_UNVERIFIED');
    const ext = mime === 'image/jpeg' ? 'jpg' : mime.split('/')[1], digest = sha(bytes);
    output.push({ ...item, url: undefined, bytes, path: `raw/native-tool-attachments/${digest}.${ext}`,
      sha256: digest, size: bytes.length, mime_type: mime, redirects,
      transport: proxy ? { profile: 'existing-macos-loopback-https-proxy/v1', endpoint_sha256: sha(proxy) } : { profile: 'node-fetch-https/v1' },
      retrieved_at: new Date().toISOString() });
  }
  return output;
}

export function countMoaSdkTools(protocol, transcript, index) {
  const normalized = transcript.filter(e => e.type === 'tool_call'), results = transcript.filter(e => e.type === 'tool_result');
  check(normalized.length === protocol.calls.length && index.calls.length === normalized.length, 'NORMALIZED_CALL_SET');
  const byTool = {}, catalog = [];
  for (const c of protocol.calls) {
    const calls = normalized.filter(e => e.tool.call_id === c.call_id), matches = results.filter(e => e.tool.call_id === c.call_id);
    check(calls.length === 1 && matches.length === 1 && calls[0].tool.name === c.name
      && JSON.stringify(calls[0].tool.arguments) === JSON.stringify(c.arguments)
      && typeof matches[0].tool.result === 'string' && sha(matches[0].tool.result) === c.result_sha256, 'NORMALIZED_CALL_DRIFT');
    byTool[c.name] = (byTool[c.name] || 0) + 1;
    catalog.push({ id_namespace: 'native-moa-sdk-tool-call', native_id: c.call_id, tool_name: c.name,
      source_ref: `trace/raw/trajectory.jsonl#L${c.call_line}`, result_ref: `trace/raw/trajectory.jsonl#L${c.result_line}` });
  }
  return { status: 'complete', basis: protocol.scope, total: protocol.calls.length,
    by_tool: Object.fromEntries(Object.entries(byTool).sort()), catalog,
    original_normalized_count: normalized.length, additional_calls: 0,
    legacy_js_observer: protocol.legacy_js_observer, original_process_trace_status: index.completeness.status };
}
