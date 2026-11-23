// These observations deliberately do not supply canonical token/request usage.
// A context-window snapshot and a subscription display are different measures.
export function inspectNativeResourceObservations(runtime, native) {
  const messages = Object.values(runtime.maps?.messageMap || {});
  const matches = messages.filter(m => m.message_id === native.reply_message_id && m.conversation_id === native.conversation_id);
  if (matches.length !== 1) throw new Error("DOUBAOWORK_RESOURCE_MESSAGE_AMBIGUOUS");
  const extra = matches[0].ext || {};
  const parse = key => { if (extra[key] === undefined) return null; try { return JSON.parse(extra[key]); } catch { return { parse_error: true }; } };
  const occupancy = parse("context_window_usage"), commerce = parse("commerce_usage_data_v1");
  const tokenKeys = new Set(["input_tokens", "prompt_tokens", "output_tokens", "completion_tokens", "total_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens"]);
  const candidates = [];
  const visit = (value, path, depth = 0) => {
    if (depth > 8 || !value || typeof value !== "object") return;
    for (const [key, item] of Object.entries(value)) {
      if (tokenKeys.has(key) && (typeof item === "number" || typeof item === "string" && /^\d+$/u.test(item))) candidates.push({ path: `${path}.${key}`, value: item });
      if (item && typeof item === "object") visit(item, `${path}.${key}`, depth + 1);
    }
  };
  for (const [key, value] of Object.entries(extra)) {
    if (!/usage|token_count|accounting/i.test(key) || /fetch|access|auth/i.test(key)) continue;
    visit(typeof value === "string" ? parse(key) : value, `assistant.ext.${key}`);
  }
  return {
    schema: "wildclawbench.doubaowork-resource-observations/v1",
    conversation_id: native.conversation_id, reply_message_id: native.reply_message_id,
    context_window: occupancy ? { status: "native-display-only", source: "assistant.ext.context_window_usage", value: occupancy,
      cumulative_consumption: false, usable_as_input_or_total_tokens: false } : { status: "unavailable" },
    subscription: commerce ? { status: "native-display-only", source: "assistant.ext.commerce_usage_data_v1",
      label: commerce.summary?.label ?? null, display_value: commerce.summary?.value ?? null,
      items: Array.isArray(commerce.items) ? commerce.items.map(i => ({ label: i.label, display_value: i.value })) : [],
      unit: null, usable_as_currency_or_tokens: false } : { status: "unavailable" },
    token_accounting: { status: "unavailable", candidates, reason: candidates.length ? "Candidate fields need a verified per-request accounting profile" : "No per-request token accounting found in this bound message" },
    model_requests: { status: "unavailable", reason: "A frontend task/SSE connection is not a provider model request; no native per-model-request ledger is exposed by this reader" },
  };
}
