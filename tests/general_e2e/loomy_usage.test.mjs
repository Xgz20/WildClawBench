import test from 'node:test';
import assert from 'node:assert/strict';
import { nativeUsage } from '../../tools/report/e2e-shared/loomy/metrics.mjs';

function fixture(tokens = {total: 135, input: 80, output: 7, reasoning: 3, cache: {read: 40, write: 5}}) {
  return {messages: [{id: 'msg', session_id: 'root', parsed: {role: 'assistant', finish: 'stop', tokens}}],
    parts: [{id: 'part', message_id: 'msg', session_id: 'root', parsed: {type: 'step-finish', tokens: structuredClone(tokens)}}]};
}
test('OpenCode native projections count once, normalize cache and fold reasoning', () => {
  const value = nativeUsage(fixture());
  assert.equal(value.metrics.requests.request_count.value, 1);
  assert.equal(value.metrics.usage.input_tokens.value, 125);
  assert.equal(value.metrics.usage.output_tokens.value, 10);
  assert.equal(value.metrics.usage.total_tokens.value, 135);
  assert.equal(value.metrics.usage.cache_read_input_tokens.value, 40);
  assert.equal(value.metrics.usage.cache_creation_input_tokens.value, 5);
  assert.equal(value.metrics.usage.reasoning_output_tokens.value, 3);
  assert.equal(value.metrics.requests.request_attempt_count.value, null);
  assert.deepEqual(value.collection.known_subtotals, {});
});
test('missing initialized usage remains partial and does not become observed zero', () => {
  const binding = fixture();
  binding.messages.push({id: 'aborted', session_id: 'root', parsed: {role: 'assistant',
    tokens: {input: 0, output: 0, reasoning: 0, cache: {read: 0, write: 0}}, error: {name: 'MessageAbortedError'}}});
  const value = nativeUsage(binding);
  assert.equal(value.metrics.usage.total_tokens.value, null);
  assert.equal(value.collection.known_subtotals.total_tokens, 135);
  assert.deepEqual(value.collection.coverage.total_tokens, {known: 1, total: 2, unit: 'native-assistant-message'});
  assert.equal(value.metrics.requests.request_count.value, 1);
  assert.deepEqual(value.reconciliation.messages_without_step_finish, ['aborted']);
});
test('the exact recorded zero with a total counter is distinct from missing usage', () => {
  const value = nativeUsage(fixture({total: 0, input: 0, output: 0, reasoning: 0, cache: {read: 0, write: 0}}));
  assert.equal(value.metrics.usage.total_tokens.value, 0);
  assert.equal(value.metrics.usage.total_tokens.status, 'observed');
});
test('length-final negative split preserves reconciled output without clamping or asserting reasoning', () => {
  const binding = fixture({total: 32115, input: 80, output: -3, reasoning: 32003, cache: {read: 30, write: 5}});
  binding.messages[0].parsed.finish = 'length';
  const before = structuredClone(binding), value = nativeUsage(binding);
  assert.equal(value.metrics.usage.output_tokens.value, 32000);
  assert.equal(value.metrics.usage.total_tokens.value, 32115);
  assert.equal(value.metrics.usage.reasoning_output_tokens.value, null);
  assert.equal(value.reconciliation.output_reasoning_split_anomalies[0].output, -3);
  assert.deepEqual(binding, before);
});
test('scoped child responses are counted without adding the duplicate message projection', () => {
  const parent = fixture(), child = fixture();
  child.messages[0].id = 'child-msg'; child.messages[0].session_id = 'child';
  Object.assign(child.parts[0], {id: 'child-part', message_id: 'child-msg', session_id: 'child'});
  const value = nativeUsage({messages: [...parent.messages, ...child.messages], parts: [...parent.parts, ...child.parts]});
  assert.equal(value.metrics.requests.request_count.value, 2);
  assert.equal(value.metrics.usage.total_tokens.value, 270);
});
test('conflicting projections and repeated steps are rejected', () => {
  const conflict = fixture(); conflict.parts[0].parsed.tokens.input++;
  assert.throws(() => nativeUsage(conflict), /PROJECTION_CONFLICT/);
  const repeated = fixture(); repeated.parts.push({...repeated.parts[0], id: 'second'});
  assert.throws(() => nativeUsage(repeated), /STEP_BINDING/);
  const foreign = fixture(); foreign.parts[0].session_id = 'foreign';
  assert.throws(() => nativeUsage(foreign), /STEP_BINDING/);
});
test('inconsistent totals and unobserved negative shapes do not silently enter reports', () => {
  const conflict = fixture(); conflict.messages[0].parsed.tokens.total++;
  conflict.parts[0].parsed.tokens = structuredClone(conflict.messages[0].parsed.tokens);
  assert.throws(() => nativeUsage(conflict), /TOTAL_CONFLICT/);
  const negative = fixture({total: 135, input: 80, output: -1, reasoning: 11, cache: {read: 40, write: 5}});
  assert.throws(() => nativeUsage(negative), /NEGATIVE_OUTPUT_UNSUPPORTED/);
});
