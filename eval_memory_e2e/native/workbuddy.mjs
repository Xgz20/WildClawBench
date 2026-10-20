import { pathToFileURL } from "node:url";
import { execFileSync } from 'node:child_process';
import { inspectWorkBuddyMacos, parseArgs as probeDefaults } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/probe.mjs";
import { assertWorkBuddyNativeIdle } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/execute.mjs";
import { WorkBuddyCdpClient, discoverWorkBuddyMainTarget, readWorkBuddyUi, assertWorkBuddyUiIdle,
  createFreshWorkBuddyTask, selectWorkBuddyWorkspace, assertWorkBuddyUiConfiguration,
  fillWorkBuddyPrompt, dispatchWorkBuddyPrompt, readWorkBuddyPromptState } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs";
import { snapshotWorkBuddyRuntimeBaseline, selectWorkBuddyRuntimeBinding } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/runtime-binding.mjs";
import {connectWorkBuddyUnit,attestWorkBuddyUnit} from './workbuddy-unit.mjs';
import { context, sha, requestHash, readJson, saveState, artifact, withUiLock, requireGui,
  baseReply, bindReply, verifyConfig, stdinRequest } from "./common.mjs";

const ENDPOINT = "http://127.0.0.1:9229";
const CAPABILITIES = ["new", "continue"];

export function requestedModelReady(history, expected, verifiedUnit=false) {
  const actual=history.request.requestedModel?.name??(verifiedUnit?history.request.requestedModel?.id:undefined);
  if(actual===expected)return true;
  if(verifiedUnit&&expected==='xopglm52'&&actual==='custom-local:xopglm52')return true;
  if(!['success','failure'].includes(history.runtime_terminal.request_state))return false;
  throw Error('WORKBUDDY_REQUESTED_MODEL_MISMATCH');
}

async function connect(frozen = null, profile=null) {
  await requireGui();
  if(profile?.workbuddy_scope)return connectWorkBuddyUnit(profile,frozen);
  const report = await inspectWorkBuddyMacos({ ...probeDefaults([]), appPath: "/Applications/WorkBuddy.app", endpoint: ENDPOINT, timeoutMs: 3000 });
  if (report.status !== "PASS" || !report.process?.running || report.cdp?.status !== "observed") throw Error("WORKBUDDY_NATIVE_PREFLIGHT_FAILED");
  const target = await discoverWorkBuddyMainTarget(ENDPOINT, 3000);
  const client = await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl, 8000);
  try {
    const ui = await readWorkBuddyUi(client);
    const uid = await client.evaluate(`(async()=>{const p=await window.wb.account.profile();return p?.uid??null})()`);
    if (!uid) throw Error("WORKBUDDY_LOGGED_IN_ID_UNAVAILABLE");
    const config = { app_version: report.application.version, model_display: ui.model ?? frozen?.model_display,
      permissions: ui.permission ?? frozen?.permissions, underlying_model: null, account_fingerprint: sha(String(uid)) };
    verifyConfig(config, null);
    return { client, report, ui, config, config_basis: ui.model ? "visible_ui" : "recorded_pre_send_and_native_requested_model" };
  } catch (error) { client.close(); throw error; }
}

async function observe(ctx, request, live, state) {
  const { client, config } = live;
  verifyConfig(config, state.config);
  let selected;
  try { selected = await selectWorkBuddyRuntimeBinding({ client, workspace: request.workspace,
    baseline: state.baseline, boundConversationId: state.native?.session_id ?? state.boundConversationId ?? null,
    boundRequestId: state.native?.turn_id ?? null, promptSha256: request.prompt_sha256 }); }
  catch (error) {
    if (!String(error.message).includes("WORKBUDDY_RUNTIME_HISTORY_INCOMPLETE")) throw error;
    return bindReply(ctx, request, { ...baseReply(request, config), status: "active", reason: "等待原生历史加载；不重发已登记的操作。" },
      { history_status: "not_ready", prompt_binding_status: "unverified_intent_only", config_basis: live.config_basis });
  }
  const reply = baseReply(request, config);
  if (!selected.binding) {
    if (selected.ambiguous) throw Error("WORKBUDDY_NATIVE_BINDING_AMBIGUOUS");
    return bindReply(ctx, request, { ...reply, status: "active", reason: "等待原操作的原生接受证据；不会重新发送。" },
      { prompt_binding_status: "unverified_intent_only", baseline: state.baseline });
  }
  const binding = selected.binding;
  const history = binding.history;
  state.native = { session_id: history.binding.conversation_id, turn_id: history.binding.request_id, cwd: binding.session_snapshot.cwd };
  if (state.native.cwd !== request.workspace || history.prompt.sha256 !== request.prompt_sha256) throw Error("WORKBUDDY_NATIVE_PROMPT_OR_CWD_MISMATCH");
  reply.native = state.native;
  const terminal = history.runtime_terminal;
  if(!requestedModelReady(history,state.config.model_display,live.scoped===true)) {
    await saveState(ctx,state);
    return bindReply(ctx,request,{...reply,status:'active',reason:'等待原生请求的模型元数据完整；不重发。'},
      {native_terminal:terminal,prompt_binding_status:'verified',requested_model_metadata_status:'pending'});
  }
  if ([terminal.request_state, terminal.user_message_state, terminal.assistant_message_state].includes("failure")) {
    await saveState(ctx, state);
    return bindReply(ctx, request, { ...reply, status: "infrastructure_error", reason: "原生请求异常终态，保留实际状态和消息，不计能力零分。" },
      { runtime_snapshot: binding.runtime_snapshot, native_terminal: terminal, prompt_binding_status: "verified",
        native_request:history.request });
  }
  if (terminal.request_state !== "success" || terminal.user_message_state !== "success" || terminal.assistant_message_state !== "success") {
    await saveState(ctx, state);
    return bindReply(ctx, request, { ...reply, status: "active", reason: "原生请求仍在执行。" },
      { runtime_snapshot: binding.runtime_snapshot, native_terminal: terminal, prompt_binding_status: "verified" });
  }
  state.firstTerminalObservedAt ??= Date.now();
  await saveState(ctx, state);
  const seconds = Math.max(0, (Date.now() - state.firstTerminalObservedAt) / 1000);
  if (seconds < request.memory_wait_seconds) return bindReply(ctx, request,
    { ...reply, status: "active", reason: "主请求已结束，等待冻结的记忆观察窗；后台写入状态不可观测。" },
    { runtime_snapshot: binding.runtime_snapshot, native_terminal: terminal, prompt_binding_status: "verified" });
  reply.status = "completed";
  reply.memory_observation = { status: "unobservable", wait_seconds: seconds };
  reply.final_response = await artifact(ctx, "response", history.final_response ?? "");
  reply.trace = await artifact(ctx, "trace", { source_kind: "workbuddy-runtime-api", native: state.native,
    selected_request_id: state.native.turn_id, conversation_id: state.native.session_id, request: history.request });
  return bindReply(ctx, request, reply, { runtime_snapshot: binding.runtime_snapshot,
    native_terminal: terminal, prompt_binding_status: "verified", memory_observation: reply.memory_observation });
}

export async function runWorkBuddy(request) {
  const ctx = await context(request, "WorkBuddy");
  let state;
  try { state = await readJson(ctx.stateFile); } catch (error) { if (error.code !== "ENOENT") throw error; }
  const profile=ctx.manifest.profiles.WorkBuddy;
  const live = await connect(state?.config ?? request.expected_config,profile);
  try {
    verifyConfig(live.config, request.expected_config);
    if (state && state.requestHash !== requestHash(request)) throw Error("WORKBUDDY_MEMORY_REQUEST_DRIFT");
    if (request.action === "prepare_namespace") {
      if (request.required_capabilities.some(capability => !CAPABILITIES.includes(capability))) {
        return bindReply(ctx, request, { ...baseReply(request, live.config), status: "needs_attention", reason: "该任务链需要尚未验收的原生能力，例如客户端重启。" });
      }
      assertWorkBuddyNativeIdle(live.report); assertWorkBuddyUiIdle(live.ui);
      const baseline = await snapshotWorkBuddyRuntimeBaseline(live.client, request.workspace);
      if (baseline.conversations.length) throw Error("WORKBUDDY_TEST_NAMESPACE_NOT_FRESH");
      if (!state) await saveState(ctx, { requestHash: requestHash(request), phase: "namespace_prepared", config: live.config, baseline });
      return bindReply(ctx, request, { ...baseReply(request, live.config), status: "completed", background_settled: true,
        admission: { account_policy: "current_signed_in_account", test_scope_only: true, precondition_verified: true,
          capabilities: CAPABILITIES, isolation: live.scoped?'verified_namespace':"shared_account_cold_first",
          precondition_scope: live.scoped?'case_repeat_os_memory_unit':"new_experiment_and_fresh_local_workspace_only", global_memory_reset_verified: false,
          ...(live.scoped?{unit_id:profile.workbuddy_scope.unit_id,case_repeat_behavior_isolation_verified:false}:{}) } },
        { general_probe: live.report, namespace_baseline: baseline, account_identity_method: "window.wb.account.profile.uid -> sha256" });
    }
    if (state) {
      if (request.transport_action !== "observe") throw Error("WORKBUDDY_DUPLICATE_NATIVE_DISPATCH");
      return await observe(ctx, request, live, state);
    }
    if (request.transport_action === "observe") throw Error("WORKBUDDY_NATIVE_ACCEPTANCE_UNKNOWN: no Driver state; never redispatch");
    return await withUiLock(ctx, request, async () => {
      execFileSync('/usr/bin/open',['-a','/Applications/WorkBuddy.app']);
      const closed=await live.client.evaluate(`(()=>{const visible=e=>!!e.getClientRects().length;
        const modals=[...document.querySelectorAll('.settings-modal')].filter(visible);
        if(!modals.length)return false;
        if(modals.length!==1||!modals[0].querySelector('.memory-settings-panel'))throw Error('WORKBUDDY_FOREIGN_SETTINGS_DIALOG');
        const buttons=[...modals[0].querySelectorAll('button.settings-modal__close[aria-label="Close settings"]')].filter(visible);
        if(buttons.length!==1)throw Error('WORKBUDDY_MEMORY_SETTINGS_CLOSE_AMBIGUOUS');buttons[0].click();return true})()`);
      if(closed&&await live.client.evaluate(`Boolean([...document.querySelectorAll('.settings-modal')].find(e=>e.getClientRects().length))`))throw Error('WORKBUDDY_MEMORY_SETTINGS_STILL_OPEN');
      assertWorkBuddyNativeIdle(live.report); assertWorkBuddyUiIdle(await readWorkBuddyUi(live.client));
      const baseline = await snapshotWorkBuddyRuntimeBaseline(live.client, request.workspace);
      if (request.session_action === "new") {
        await createFreshWorkBuddyTask(live.client, 15000);
        await selectWorkBuddyWorkspace(live.client, request.workspace, 15000);
      } else if (request.session_action === "continue") {
        const ui = await readWorkBuddyUi(live.client);
        if (!request.previous_native || ui.selected_conversation_id !== request.previous_native.session_id) throw Error("WORKBUDDY_CONTINUATION_ROUTE_CHANGED");
      } else throw Error("WORKBUDDY_RESTART_NOT_ADMITTED");
      const ui = await readWorkBuddyUi(live.client);
      assertWorkBuddyUiConfiguration(ui, { workspace: request.workspace, model: live.config.model_display, permission: live.config.permissions });
      state = { requestHash: requestHash(request), phase: "prepared", config: live.config, baseline,
        boundConversationId: request.session_action === "continue" ? request.previous_native.session_id : null };
      await saveState(ctx, state);
      await fillWorkBuddyPrompt(live.client, request.prompt, 15000);
      await requireGui();
      assertWorkBuddyUiConfiguration(await readWorkBuddyUi(live.client), { workspace: request.workspace,
        model: live.config.model_display, permission: live.config.permissions });
      const input = await readWorkBuddyPromptState(live.client);
      state.prompt_input_evidence = input;
      state.phase = "invoking";
      if(live.scoped){ctx.memoryBoundary=attestWorkBuddyUnit(profile);await artifact(ctx,'os-boundary-before-press',ctx.memoryBoundary)}
      await saveState(ctx, state);
      await dispatchWorkBuddyPrompt(live.client, 15000);
      state.phase = "invoked";
      await saveState(ctx, state);
      return observe(ctx, request, live, state);
    });
  } finally { live.client.close(); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { process.stdout.write(JSON.stringify(await runWorkBuddy(await stdinRequest())) + "\n"); }
  catch (error) { process.stderr.write(String(error.stack || error) + "\n"); process.exitCode = 2; }
}
