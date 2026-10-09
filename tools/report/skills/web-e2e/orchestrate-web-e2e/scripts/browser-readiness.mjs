#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

export const BROWSER_READINESS_SCHEMA = "wildclawbench.web-e2e-browser-readiness/v1";
export const BROWSER_WARMUP_SECONDS = 60;
export const MAX_BROWSER_DISCOVERIES = 3;

function time(value, name) {
  const parsed = typeof value === "string" ? Date.parse(value) : NaN;
  if (!Number.isFinite(parsed)) throw new Error(`${name} 必须是有效时间`);
  return parsed;
}

function ownBrowser(state, threadId) {
  if (!Array.isArray(state?.browsers)) throw new Error("必须保存原始 Browser 清单");
  const iabs = state.browsers.filter((browser) => browser.type === "iab");
  if (iabs.some((browser) => browser.metadata?.codexSessionId !== threadId)) {
    throw new Error("Browser 会话归属不匹配，禁止借用其他会话");
  }
  if (iabs.length > 1) throw new Error("本会话 iab 不唯一");
  if (iabs[0] && (typeof iabs[0].id !== "string" || !iabs[0].id)) throw new Error("Browser 缺少唯一 ID");
  return iabs[0] || null;
}

export function evaluateBrowserReadiness(input, threadId, now = Date.now()) {
  if (!threadId || input.thread_id !== threadId) throw new Error("健康记录 thread_id 不匹配");
  const started = time(input.started_at, "started_at");
  const discoveries = input.discoveries;
  if (!Array.isArray(discoveries) || discoveries.length < 1 || discoveries.length > MAX_BROWSER_DISCOVERIES) {
    throw new Error("发现记录必须为1至3次，禁止无限重试");
  }
  const deadline = started + BROWSER_WARMUP_SECONDS * 1000;
  let lastEnd = started;
  let browser = null;
  for (const [index, observation] of discoveries.entries()) {
    const begin = time(observation.started_at, "发现 started_at");
    const end = time(observation.finished_at, "发现 finished_at");
    if (begin < lastEnd || end < begin || end > now) throw new Error("发现记录时间顺序错误");
    if (index && !browser && begin < lastEnd + (index === 1 ? 2000 : 5000)) throw new Error("发现复查未遵守退避时间");
    lastEnd = end;
    browser = ownBrowser(observation.state, threadId);
  }
  const result = { schema_version: BROWSER_READINESS_SCHEMA, thread_id: threadId,
    started_at: input.started_at, deadline_at: new Date(deadline).toISOString(),
    warmup_seconds: BROWSER_WARMUP_SECONDS, discovery_count: discoveries.length,
    max_discoveries: MAX_BROWSER_DISCOVERIES, internal_info_timeout_changed: false };
  const blocked = (reason) => ({ ...result, status: "BLOCKED", reason, action: "STOP_SCORING_INFRASTRUCTURE" });
  if (!browser && !input.creation) {
    if (now >= deadline) return blocked("warmup-window-expired");
    if (discoveries.length < MAX_BROWSER_DISCOVERIES) {
      return { ...result, status: "RETRY_DISCOVERY", action: "DISCOVER_OWN_BROWSER",
        retry_after_seconds: discoveries.length === 1 ? 2 : 5 };
    }
  }
  if (!input.creation) {
    return now >= deadline ? blocked("warmup-window-expired")
      : { ...result, status: "CHECKING", action: "CREATE_OWN_ABOUT_BLANK_ONCE" };
  }
  const creation = input.creation;
  if (creation.attempt_count !== 1) throw new Error("实际创建必须且只能一次");
  const creationBegin = time(creation.started_at, "创建 started_at");
  const creationEnd = time(creation.finished_at, "创建 finished_at");
  if (creationBegin < lastEnd || creationEnd < creationBegin || creationEnd > now) throw new Error("创建时间顺序错误");
  if (creationEnd > deadline) return blocked("warmup-window-expired");
  if (creation.success !== true) return blocked("actual-creation-failed");
  if (!browser && discoveries.length !== MAX_BROWSER_DISCOVERIES) throw new Error("空清单必须先完成有界发现复查");
  if (typeof creation.tab_id !== "string" || !creation.tab_id) throw new Error("缺少实际创建返回的 tab_id");
  const verification = input.verification;
  if (!verification) return blocked("missing-ownership-verification");
  const verifiedAt = time(verification.finished_at, "复查 finished_at");
  if (verifiedAt < creationEnd || verifiedAt > now) throw new Error("复查时间顺序错误");
  if (verifiedAt > deadline) return blocked("warmup-window-expired");
  const verified = ownBrowser(verification.state, threadId);
  if (!verified || (browser && verified.id !== browser.id)) return blocked("browser-binding-changed");
  const tabs = verified.tabs?.filter((tab) => tab.id === creation.tab_id || tab.providerTabId === creation.tab_id) || [];
  if (tabs.length !== 1 || tabs[0].url !== "about:blank") return blocked("created-tab-not-uniquely-bound");
  if (input.readback?.url !== "about:blank" || typeof input.readback.ax_state !== "string"
    || !input.readback.ax_state.includes("AXWebArea about:blank")) return blocked("missing-actual-page-readback");
  const readAt = time(input.readback.finished_at, "页面回读 finished_at");
  // createBrowserTab already returns actual AX state; a later read is also valid.
  if (readAt < creationEnd || readAt > now) throw new Error("页面回读时间顺序错误");
  const proofAt = Math.max(verifiedAt, readAt);
  if (proofAt > deadline) return blocked("warmup-window-expired");
  if (now - proofAt > BROWSER_WARMUP_SECONDS * 1000) return blocked("stale-health-proof");
  return { ...result, status: "READY", action: "START_MANAGED_SITE", browser_id: verified.id,
    tab_id: creation.tab_id, metadata: verified.metadata, verified_at: new Date(proofAt).toISOString() };
}

function containedFile(root, relativeName) {
  if (path.isAbsolute(relativeName) || relativeName.split(/[\\/]/).includes("..")) throw new Error("输入必须在本题 evidence 中");
  const segments = relativeName.split(/[\\/]/);
  if (segments[0] !== "private-scoring" || segments[1] !== "evidence") throw new Error("输入必须在本题 evidence 中");
  let current = root;
  for (const segment of segments) {
    current = path.join(current, segment);
    if (!segment || fs.lstatSync(current).isSymbolicLink()) throw new Error("禁止符号链接或空路径");
  }
  if (!fs.statSync(current).isFile() || fs.statSync(current).size > 262144) throw new Error("输入不是有界普通文件");
  return current;
}

export function checkBrowserReadiness(taskRoot, inputFile, threadId, now = Date.now()) {
  const root = fs.realpathSync(taskRoot);
  const file = containedFile(root, inputFile);
  const input = JSON.parse(fs.readFileSync(file, "utf8"));
  const contractFile = path.join(root, "private-scoring", "task_contract.json");
  if (fs.lstatSync(contractFile).isSymbolicLink() || !fs.statSync(contractFile).isFile()
    || fs.statSync(contractFile).size > 262144) throw new Error("task contract 必须为有界普通文件");
  const contract = JSON.parse(fs.readFileSync(contractFile, "utf8"));
  if (!contract.identity?.task_id || input.task_id !== contract.identity.task_id) throw new Error("健康记录 task_id 不匹配");
  const result = evaluateBrowserReadiness(input, threadId, now);
  const output = path.join(root, "private-scoring", "evidence", "browser-readiness.json");
  if (file === output) throw new Error("输入不能覆盖健康结果记录");
  const outputStat = (() => { try { return fs.lstatSync(output); } catch (error) { if (error.code === "ENOENT") return null; throw error; } })();
  if (outputStat && (outputStat.isSymbolicLink() || !outputStat.isFile())) {
    throw new Error("健康结果目标必须为普通文件");
  }
  const temporary = `${output}.${randomUUID()}.tmp`;
  try {
    fs.writeFileSync(temporary, `${JSON.stringify({ ...result, observations: input }, null, 2)}\n`, { mode: 0o600, flag: "wx" });
    fs.renameSync(temporary, output);
  } finally { fs.rmSync(temporary, { force: true }); }
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = {};
    for (let i = 2; i < process.argv.length; i += 2) {
      const key = process.argv[i];
      if (!["--task-root", "--input", "--thread-id"].includes(key) || !process.argv[i + 1]) throw new Error("参数不完整或不支持");
      args[key] = process.argv[i + 1];
    }
    if (!args["--task-root"] || !args["--input"] || !args["--thread-id"]) throw new Error("需要 task-root/input/thread-id");
    const result = checkBrowserReadiness(args["--task-root"], args["--input"], args["--thread-id"]);
    console.log(JSON.stringify(result));
    if (result.status === "BLOCKED") process.exitCode = 2;
  } catch (error) { console.error(`FAIL: ${error.message}`); process.exitCode = 2; }
}
