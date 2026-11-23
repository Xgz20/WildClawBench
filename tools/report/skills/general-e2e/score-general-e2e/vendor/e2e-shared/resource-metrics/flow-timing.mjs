// Both endpoints are observations on the evaluator host. Never subtract a
// provider/server completion timestamp from a local dispatch timestamp.
export const FLOW_TIMING_PROFILE = "prompt-send-to-controller-terminal/v1";
export const FLOW_TIMING_BASIS = `${FLOW_TIMING_PROFILE}: Prompt dispatch start to controller terminal observation on the same host; excludes pre-send preparation, scoring and reporting; includes dispatch, queue and observer waits`;

export function flowTiming(sentAt, observedAt) {
  const valid = value => typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/u.test(value) && Number.isFinite(Date.parse(value));
  const duration = valid(sentAt) && valid(observedAt) ? (Date.parse(observedAt) - Date.parse(sentAt)) / 1000 : null;
  const value = duration !== null && duration >= 0 ? duration : null;
  return { value, status: value === null ? "unavailable" : "observed", basis: FLOW_TIMING_BASIS };
}

export function nativeDurationSeconds(milliseconds) {
  return Number.isSafeInteger(milliseconds) && milliseconds >= 0 ? milliseconds / 1000 : null;
}
