import { normalizeRuntimePrompt } from "./runtime-messages.mjs";

export const CANCELLATION_SCHEMA = "wildclawbench.doubaowork-cancellation-intent/v1";
export const TERMINAL_OBSERVATION_SCHEMA = "wildclawbench.doubaowork-terminal-observation/v1";

export function hasCancellationRequest(state, native) {
  const request = state.cancellation;
  return native?.terminal === "interrupted" && request?.click_attempt_count === 1
    && Number.isFinite(Date.parse(request.click_returned_at))
    && request.native_request_session_id === native.native_request_session_id
    && request.conversation_id === native.conversation_id
    && request.user_message_id === native.user_message_id;
}

export function verifyCancellationEvidence({ state, native, runtime, intent, observation }) {
  if (!hasCancellationRequest(state, native)) throw new Error("DOUBAOWORK_CANCELLATION_REQUEST_UNVERIFIED");
  const request = state.cancellation;
  const acknowledged = normalizeRuntimePrompt(intent?.runtime, state);
  const wasTerminal = Object.values(intent.runtime.maps.messageMap || {}).some(message => message.user_type === 2
    && (message.ext?.is_finish === "1" || ["Success", "Broken", "Error", "ExpectError", "PanicError", "CancelError"].includes(message.final_status?.session)));
  if (intent.schema !== CANCELLATION_SCHEMA || intent.operation !== "click-bound-native-stop"
      || wasTerminal
      || intent.attempt_id !== state.attempt_id || intent.workspace !== state.workspace
      || intent.selector !== "chat_input_local_break_button"
      || intent.requested_at !== request.requested_at
      || !Number.isFinite(Date.parse(intent.runtime.observed_at))
      || Date.parse(intent.runtime.observed_at) < Date.parse(state.timing.sent_at)
      || Date.parse(intent.runtime.observed_at) > Date.parse(intent.requested_at)
      || acknowledged.user_message_id !== native.user_message_id
      || acknowledged.native_request_session_id !== native.native_request_session_id
      || intent.frontend?.initialized !== true || intent.frontend.active?.length !== 1
      || intent.frontend.active[0].session_id !== native.native_request_session_id
      || !intent.frontend.active[0].conversation_ids?.includes(native.conversation_id)) {
    throw new Error("DOUBAOWORK_CANCELLATION_INTENT_BINDING_INVALID");
  }
  const times = [state.timing.sent_at, request.requested_at, request.click_started_at,
    request.click_returned_at, runtime.observed_at, observation?.observed_at].map(Date.parse);
  if (times.some(t => !Number.isFinite(t)) || times.some((t, i) => i > 0 && t < times[i - 1])
      || times.at(-1) > Date.now()
      || observation.schema !== TERMINAL_OBSERVATION_SCHEMA
      || observation.attempt_id !== state.attempt_id || observation.workspace !== state.workspace
      || observation.conversation_id !== native.conversation_id
      || observation.native_request_session_id !== native.native_request_session_id
      || observation.native_payload_sha256 !== runtime.payload_sha256
      || observation.frontend?.initialized !== true || observation.frontend.active?.length !== 0
      || observation.background?.initialized !== true || observation.background.active?.length !== 0
      || observation.stop_control_count !== 0 || observation.pending !== false) {
    throw new Error("DOUBAOWORK_CANCELLATION_TERMINAL_NOT_QUIET");
  }
  return { verified: true, business_status: "cancelled", cancellation_confirmed: true,
    observed_at: observation.observed_at, native_finished_at: native.finished_at,
    source: "native-im-live.Broken+bound-stop-click+native-frontend-and-tool-idle" };
}

export function verifyFailureEvidence({ state, native, runtime, observation }) {
  if (native.terminal !== "failed" || state.client.version !== "2.31.6"
      || native.raw_terminal?.profile !== "native-im-live/v1"
      || native.raw_terminal.error_code !== 710020702) throw new Error("DOUBAOWORK_FAILURE_PROFILE_UNVERIFIED");
  const times = [state.timing.sent_at, runtime.observed_at, observation?.observed_at].map(Date.parse);
  if (times.some(t => !Number.isFinite(t)) || times.some((t, i) => i > 0 && t < times[i - 1])
      || times.at(-1) > Date.now()
      || observation.schema !== TERMINAL_OBSERVATION_SCHEMA
      || observation.attempt_id !== state.attempt_id || observation.workspace !== state.workspace
      || observation.conversation_id !== native.conversation_id
      || observation.native_request_session_id !== native.native_request_session_id
      || observation.native_payload_sha256 !== runtime.payload_sha256
      || observation.frontend?.initialized !== true || observation.frontend.active?.length !== 0
      || observation.background?.initialized !== true || observation.background.active?.length !== 0
      || observation.stop_control_count !== 0 || observation.pending !== false) {
    throw new Error("DOUBAOWORK_FAILURE_TERMINAL_NOT_QUIET");
  }
  return { verified: true, business_status: "infrastructure_error", observed_at: observation.observed_at,
    native_finished_at: native.finished_at, source: "native-im-live.Error.710020702+native-frontend-and-tool-idle" };
}
