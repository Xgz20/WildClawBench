import test from "node:test";
import assert from "node:assert/strict";
import { flowTiming, nativeDurationSeconds } from "../tools/report/e2e-shared/resource-metrics/flow-timing.mjs";
import { parseAstron } from "../tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/parsers.mjs";
import { analyzeRollout } from "../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout.mjs";
import { createHash } from "node:crypto";

test("本机发送至终态支持时区与毫秒，不给缺失、倒序或伪时间补零", () => {
  assert.equal(flowTiming("2026-10-12T08:00:00+08:00", "2026-10-12T00:00:03.125Z").value, 3.125);
  assert.equal(flowTiming("2026-10-12T00:00:00Z", "2026-10-12T00:00:00Z").value, 0);
  for (const start of [null, undefined, "", 0, "bad"]) assert.equal(flowTiming(start, "2026-10-12T00:00:00Z").value, null);
  assert.equal(flowTiming("2026-10-12T00:00:01Z", "2026-10-12T00:00:00Z").status, "unavailable");
});
test("原生任务耗时只接受真实非负整数毫秒", () => {
  assert.equal(nativeDurationSeconds(0), 0);
  assert.equal(nativeDurationSeconds(12345), 12.345);
  for (const value of [null, undefined, "12345", -1, NaN, Infinity, 0.5]) assert.equal(nativeDurationSeconds(value), null);
});
test("AstronStudio Web 和 General profile 2 使用同一 payload.duration_ms，不依赖日志时间差", () => {
  const prompt = "timing fixture";
  const row = (type, payload, timestamp = "2026-10-12T00:00:00Z") => ({ type, payload, timestamp });
  const rows = [row("session_meta", {id:"session",cwd:"/fixture"}),
    row("event_msg", {type:"task_started",turn_id:"turn"}),
    row("event_msg", {type:"user_message",message:prompt}),
    row("response_item", {type:"message",role:"user",content:[{type:"input_text",text:prompt}]}),
    row("event_msg", {type:"task_complete",turn_id:"turn",duration_ms:7234}, "2026-10-12T00:01:00Z")];
  const state = {phase:"COMPLETED",session:{session_id:"session",turn_id:"turn",cwd:"/fixture",verified:true},prompt:{send_status:"sent",sha256:createHash("sha256").update(prompt).digest("hex")}};
  const general = analyzeRollout(Buffer.from(rows.map(JSON.stringify).join("\n")), state);
  const web = parseAstron(rows, "turn");
  assert.equal(general.metrics.timing.agent_duration_seconds.value, 7.234);
  assert.equal(web.execution.agent_duration_seconds, 7.234);
  delete rows.at(-1).payload.duration_ms;
  assert.equal(analyzeRollout(Buffer.from(rows.map(JSON.stringify).join("\n")), state).metrics.timing.agent_duration_seconds.value, null);
  assert.equal(parseAstron(rows, "turn").execution.agent_duration_seconds, null);
});
