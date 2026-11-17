import {createHash} from 'node:crypto';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u;
const hash = value => createHash('sha256').update(value).digest('hex');
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const keys = (value, allowed) => object(value) && Object.keys(value).every(key => allowed.includes(key));
const text = value => typeof value === 'string' && value.length > 0;
const requestKeys = ['requestId','routeId','modelSource','requestedModel','effectiveModel',
  'responseId','requestKind','status','usage'];
const usageKeys = ['inputTokens','outputTokens','totalTokens','cachedInputTokens',
  'reasoningOutputTokens','cacheCreationInputTokens'];

// Structured one-shot calls have no conversation/session projection. Late
// gateway accounting updates can recreate their ledger after the call closed.
// This verifies accounting closure only; it never completes a candidate task.
export function closedStructuredGatewayLedger(ledger, rows, anchors) {
  try {
    if (!ledger.thread_id?.startsWith('structured-') || !uuid.test(ledger.thread_id.slice(11))
        || !uuid.test(ledger.turn_id) || !Number.isSafeInteger(ledger.first_sequence)
        || ledger.first_sequence <= 0 || !Array.isArray(rows) || rows.length < 3
        || !anchors || ['threads','sessions','runtime','pending'].some(key => anchors[key] !== 0)) return null;
    const updated = Date.parse(ledger.updated_at);
    if (!Number.isFinite(updated) || rows[0].sequence !== ledger.first_sequence) return null;
    const requests = new Map(), evidence = [];
    let lastSequence = 0, lastCreated = -Infinity, lastPersisted = -Infinity;
    let providerThread, account, closedAt = null;
    for (const [index, row] of rows.entries()) {
      const e = JSON.parse(row.event_json), p = e.payload, raw = e.raw?.payload;
      const created = Date.parse(e.createdAt), persisted = Date.parse(row.persisted_at);
      if (row.thread_id !== ledger.thread_id || row.turn_id !== ledger.turn_id
          || row.lifecycle_generation !== null || row.event_type !== 'turn.gateway-usage.updated'
          || !Number.isSafeInteger(row.sequence) || row.sequence <= lastSequence
          || !Number.isFinite(created) || !Number.isFinite(persisted) || created < lastCreated
          || persisted < created || persisted < lastPersisted || persisted > updated
          || !keys(e, ['modelSource','modelUsageSource','eventId','provider','threadId','createdAt',
            'turnId','providerRefs','raw','type','payload'])
          || e.type !== row.event_type || e.eventId !== row.event_id || !uuid.test(e.eventId)
          || e.threadId !== ledger.thread_id || e.turnId !== ledger.turn_id || e.provider !== 'acode'
          || e.modelSource !== 'builtin' || e.modelUsageSource !== 'gateway'
          || !uuid.test(e.providerRefs?.providerThreadId) || e.providerRefs.providerTurnId !== ledger.turn_id
          || !keys(e.providerRefs, ['providerThreadId','providerTurnId'])
          || !keys(e.raw, ['source','method','payload']) || e.raw.source !== 'acode'
          || e.raw.method !== row.event_type
          || !keys(p, ['billingAccountId','complete','requests'])
          || !keys(raw, ['billingAccountId','complete','requests'])
          || !text(p.billingAccountId) || raw.billingAccountId !== p.billingAccountId
          || typeof p.complete !== 'boolean' || raw.complete !== p.complete
          || !Array.isArray(p.requests) || !Array.isArray(raw.requests)
          || p.requests.length !== raw.requests.length) return null;
      providerThread ??= e.providerRefs.providerThreadId;
      account ??= p.billingAccountId;
      if (providerThread !== e.providerRefs.providerThreadId || account !== p.billingAccountId) return null;
      if (p.complete) {
        if (index !== rows.length - 1 || p.requests.length || !requests.size
            || [...requests.values()].some(request => request.state !== 'completed')) return null;
        closedAt = e.createdAt;
      } else {
        if (!p.requests.length) return null;
        const seen = new Set();
        for (const request of p.requests) {
          if (!keys(request, requestKeys) || !uuid.test(request.requestId)
              || seen.has(request.requestId) || request.modelSource !== 'builtin'
              || !text(request.routeId) || !text(request.requestedModel)
              || !['started','completed'].includes(request.status)) return null;
          seen.add(request.requestId);
          const originals = raw.requests.filter(item => item.requestId === request.requestId);
          if (originals.length !== 1 || !keys(originals[0], requestKeys)
              || ['requestId','routeId','modelSource','requestedModel','effectiveModel',
              'responseId','requestKind','status'].some(key => originals[0][key] !== request[key])) return null;
          const previous = requests.get(request.requestId);
          if (request.status === 'started') {
            if (previous || request.responseId || request.usage || request.requestKind || request.effectiveModel) return null;
            requests.set(request.requestId, {state:'started', route:request.routeId, model:request.requestedModel});
          } else {
            if (!previous || previous.state !== 'started' || previous.route !== request.routeId
                || previous.model !== request.requestedModel || !text(request.effectiveModel)
                || !text(request.responseId) || request.requestKind !== 'turn'
                || !keys(request.usage, usageKeys) || !keys(originals[0].usage, usageKeys)
                || !Number.isSafeInteger(request.usage.inputTokens) || !Number.isSafeInteger(request.usage.outputTokens)
                || Object.keys(request.usage).some(key => originals[0].usage[key] !== request.usage[key])
                || Object.values(request.usage).some(value => !Number.isSafeInteger(value) || value < 0)
                || Object.values(originals[0].usage).some(value => !Number.isSafeInteger(value) || value < 0)) return null;
            requests.set(request.requestId, {...previous, state:'completed'});
          }
        }
      }
      lastSequence = row.sequence; lastCreated = created; lastPersisted = persisted;
      evidence.push({sequence:row.sequence, event_id:row.event_id, persisted_at:row.persisted_at,
        event_sha256:hash(row.event_json)});
    }
    if (!closedAt) return null;
    return {profile:'closed-structured-gateway-ledger/v1', thread_id:ledger.thread_id,
      turn_id:ledger.turn_id, provider_session_id:providerThread, completed_at:closedAt,
      request_count:requests.size, ledger:{...ledger}, evidence,
      accounting_only:true, candidate_terminal_inferred:false, native_rows_modified:false};
  } catch { return null; }
}
