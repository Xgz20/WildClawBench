// OpenCode-native usage, scoped by verifyBinding; message and step-finish are
// duplicate projections, never separate charges. This module performs no I/O.
export const USAGE_PROFILE = 'loomy-opencode-recorded-usage/v1';
export const TOKEN_FIELDS = ['input_tokens', 'output_tokens', 'total_tokens',
  'cache_read_input_tokens', 'cache_creation_input_tokens', 'reasoning_output_tokens'];
const requireValue = (ok, code) => { if (!ok) throw Error(code); };
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
const same = (a, b) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));
const integer = value => Number.isSafeInteger(value) && value >= 0;

export function nativeUsage(binding) {
  const assistants = binding.messages.filter(row => row.parsed.role === 'assistant');
  const messages = new Map(binding.messages.map(row => [row.id, row]));
  requireValue(messages.size === binding.messages.length, 'LOOMY_USAGE_DUPLICATE_MESSAGE');
  const steps = new Map(), partIds = new Set();
  for (const row of binding.parts) {
    requireValue(!partIds.has(row.id), 'LOOMY_USAGE_DUPLICATE_PART'); partIds.add(row.id);
    if (row.parsed.type !== 'step-finish') continue;
    const message = messages.get(row.message_id);
    requireValue(message?.parsed.role === 'assistant' && message.session_id === row.session_id
      && !steps.has(row.message_id), 'LOOMY_USAGE_STEP_BINDING');
    if (message.parsed.tokens != null && row.parsed.tokens != null)
      requireValue(same(message.parsed.tokens, row.parsed.tokens), 'LOOMY_USAGE_PROJECTION_CONFLICT');
    steps.set(row.message_id, row);
  }
  const sums = Object.fromEntries(TOKEN_FIELDS.map(field => [field, 0]));
  const known = Object.fromEntries(TOKEN_FIELDS.map(field => [field, 0]));
  const missing = [], splitAnomalies = [], missingSteps = [];
  for (const row of assistants) {
    const step = steps.get(row.id);
    if (!step) missingSteps.push(row.id);
    const tokens = step?.parsed.tokens ?? row.parsed.tokens;
    const cache = tokens?.cache;
    // Empty initialized counters on aborted responses do not prove zero usage.
    if (!tokens || tokens.total == null || tokens.input == null || tokens.output == null
      || tokens.reasoning == null || cache?.read == null || cache?.write == null) {
      missing.push(row.id); continue;
    }
    requireValue([tokens.total, tokens.input, tokens.reasoning, cache.read, cache.write].every(integer)
      && Number.isSafeInteger(tokens.output), 'LOOMY_USAGE_INVALID_COUNTER');
    const output = tokens.output + tokens.reasoning;
    const input = tokens.input + cache.read + cache.write;
    requireValue(integer(output) && integer(input) && integer(input + output)
      && tokens.total === input + output, 'LOOMY_USAGE_TOTAL_CONFLICT');
    if (tokens.output < 0) {
      // The observed provider can split 32000 into -1 + 32001. Only the
      // reconciled combined output is admissible; never clamp the raw value.
      requireValue(row.parsed.finish === 'length', 'LOOMY_USAGE_NEGATIVE_OUTPUT_UNSUPPORTED');
      splitAnomalies.push({message_id: row.id, output: tokens.output,
        reasoning: tokens.reasoning, output_including_reasoning: output});
    }
    const values = {input_tokens: input, output_tokens: output, total_tokens: tokens.total,
      cache_read_input_tokens: cache.read, cache_creation_input_tokens: cache.write,
      reasoning_output_tokens: tokens.reasoning};
    for (const field of TOKEN_FIELDS) {
      // A reasoning split larger than combined output is not independently
      // reliable; its original value remains in the anomaly ledger.
      if (field === 'reasoning_output_tokens' && tokens.output < 0) continue;
      sums[field] += values[field]; known[field]++;
      requireValue(integer(sums[field]), 'LOOMY_USAGE_SUM_OVERFLOW');
    }
  }
  const coverage = {}, knownSubtotals = {}, usage = {};
  for (const field of TOKEN_FIELDS) {
    const complete = assistants.length > 0 && known[field] === assistants.length;
    coverage[field] = {known: known[field], total: assistants.length, unit: 'native-assistant-message'};
    usage[field] = {value: complete ? sums[field] : null,
      status: complete ? 'observed' : known[field] ? 'partial' : 'unavailable',
      basis: USAGE_PROFILE + '; one bound native usage per assistant; input includes cache; output includes reasoning; missing usage is not zero'};
    if (known[field] && !complete) knownSubtotals[field] = sums[field];
  }
  // Exactly the established OpenCode CLI definition: count native step-finish
  // records. It is not an HTTP-attempt counter or an assistant-message count.
  coverage.request_count = {known: steps.size, total: steps.size, unit: 'native-step-finish'};
  coverage.request_attempt_count = {known: 0, total: null, unit: 'http-attempt'};
  return {profile: USAGE_PROFILE, metrics: {usage, requests: {
    request_count: {value: steps.size, status: 'observed', basis: 'OpenCode CLI definition: unique bound native step-finish records; includes linked child sessions; excludes failures without step-finish and unobserved HTTP retries'},
    request_attempt_count: {value: null, status: 'unavailable', basis: 'HTTP attempt and retry counts are not exposed'} }},
    collection: {coverage, known_subtotals: knownSubtotals,
      warnings: ['LOOMY_REQUEST_COUNT_IS_STEP_FINISH_NOT_HTTP_ATTEMPTS',
        ...(missing.length ? ['LOOMY_NATIVE_USAGE_MISSING'] : []),
        ...(splitAnomalies.length ? ['LOOMY_OUTPUT_REASONING_SPLIT_ANOMALY'] : []),
        ...(missingSteps.length ? ['LOOMY_ASSISTANT_WITHOUT_STEP_FINISH'] : [])]},
    reconciliation: {assistant_message_count: assistants.length, step_finish_count: steps.size,
      messages_without_usage: missing, messages_without_step_finish: missingSteps,
      output_reasoning_split_anomalies: splitAnomalies, duplicate_projection_count: steps.size,
      all_present_source_totals_reconciled: true, zero_imputation_used: false}};
}
