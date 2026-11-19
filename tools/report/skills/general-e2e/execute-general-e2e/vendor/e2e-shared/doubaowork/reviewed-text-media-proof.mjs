// Verify the exact native replies and account for every original SDK call.
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {normalizeRuntimeMessages} from './runtime-messages.mjs';
import {recountArchivedTools} from './tool-counts.mjs';

const sha = b => createHash('sha256').update(b).digest('hex');
const check = (valid, code) => { if (!valid) throw Error('TEXT_MEDIA_PROOF: ' + code); };

const [root, stateFile] = process.argv.slice(2);
const read = async name => JSON.parse(await readFile(resolve(root, name)));
const execution = JSON.parse(await readFile(stateFile));
const index = await read('trace-index.json');
const journal = await read('bindings/dispatch-journal.json');
const runtime = await read('raw/runtime-messages.json');
const protocol = await read('raw/native-moa-sdk-protocol.json');
const native = normalizeRuntimeMessages(runtime, journal);
check(index.completeness.status === 'partial' && index.completeness.omitted_event_count === 0, 'partial scope');
check(journal.send.dispatch_attempt_count === 1 && native.terminal === 'completed'
  && native.native_cwd === execution.session.cwd && native.conversation_id === execution.session.session_id
  && native.reply_message_id === execution.session.turn_id && native.prompt.sha256 === execution.prompt.sha256, 'native binding');
const transcript = (await readFile(resolve(root, index.transcript.path), 'utf8')).split(/\r?\n/u)
  .filter(line => line.trim()).map(JSON.parse);
const users = transcript.filter(e => e.type === 'user_message');
const finals = transcript.filter(e => e.type === 'assistant_message');
check(users.length === 1 && sha(users[0].content) === execution.prompt.sha256
  && finals.at(-1)?.content === native.final_text, 'transcript prompt and final');
const final = await readFile(resolve(root, 'final-response-bound.txt'), 'utf8');
check(final === native.final_text || final === native.final_text + '\n', 'collected final');

const counts = await recountArchivedTools({stateFile, traceIndex: resolve(root, 'trace-index.json')});
check(counts.status === 'complete' && counts.total === protocol.calls.length && counts.additional_calls === 0, 'call accounting');
const missing = protocol.attachments.filter(a => a.status === 'unavailable').map(a => ({
  reason: a.reason, call_id: a.call_id, result_line: a.result_line, image_index: a.image_index,
  url_sha256: a.url_sha256, proof_sha256: a.sha256,
}));
check(missing.length > 0, 'missing media set');
process.stdout.write(JSON.stringify({native_sdk_sha256: protocol.source_sha256, native_call_count: counts.total,
  available_media_count: protocol.attachments.length - missing.length, missing_media: missing,
  native_final_sha256: sha(native.final_text), native_tool_results_recounted: true}));
