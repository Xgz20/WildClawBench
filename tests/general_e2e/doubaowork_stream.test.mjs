import assert from "node:assert/strict";
import { test } from "node:test";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
import { installRuntimeStreamObserver, collectRuntimeStream } from "../../tools/report/e2e-shared/doubaowork/runtime-stream.mjs";

function fixture(fetch, fallback = false) {
  const api = { fetch }, chunks = [];
  const window = { "@flow-web/desktop:stable": chunks, fetch };
  if (fallback) Object.defineProperty(api, "fetch", { get: () => window.fetch, set: v => { window.fetch = v; } });
  const require = () => ({ le: () => fallback ? undefined : api.fetch, iv: ({ fetch }) => { if (fallback) throw new Error("must preserve undefined SDK override"); api.fetch = fetch; } });
  require.m = { 190005: function () { return "baseURL fetch"; } };
  chunks.push = item => { Array.prototype.push.call(chunks, item); item[2](require); };
  const context = vm.createContext({ window, crypto: webcrypto, TextDecoder });
  return { api, page: { evaluate: (fn, arg) => { context.argument = arg; return vm.runInContext(`(${fn.toString()})(argument)`, context); } } };
}

const config = { attemptId: "attempt-a", prompt: "Fixture `prompt`.", workspace: "/private/fixture" };
const request = { method: "POST", body: JSON.stringify({ prompt: config.prompt, cwd: config.workspace }) };

test("Response observer preserves request and original response, and restores its own wrapper", async () => {
  const response = new Response('data: {"event":"done"}\n\n'); let seen;
  const original = async (...args) => { seen = args; return response; };
  const f = fixture(original);
  await installRuntimeStreamObserver(f.page, config);
  const actual = await f.api.fetch("https://fixture.invalid/completion", request);
  assert.equal(actual, response); assert.equal(seen[1], request);
  assert.equal(await actual.text(), 'data: {"event":"done"}\n\n');
  let capture;
  for (let i = 0; i < 100; i++) {
    capture = await collectRuntimeStream(f.page, config.attemptId);
    if (!capture.active) break;
    await new Promise(r => setTimeout(r, 5));
  }
  assert.equal(capture.status, "captured"); assert.equal(capture.requests.length, 1);
  assert.equal(capture.requests[0].text, 'data: {"event":"done"}\n\n');
  await collectRuntimeStream(f.page, config.attemptId, { restore: true });
  assert.equal(f.api.fetch, original);
});

test("Unrelated requests, unsupported response objects and wrong attempt IDs do not fabricate streams", async () => {
  const response = { status: 200 }, original = async () => response, f = fixture(original);
  await installRuntimeStreamObserver(f.page, config);
  await f.api.fetch("https://fixture.invalid/unrelated", { body: "different prompt" });
  assert.equal((await collectRuntimeStream(f.page, config.attemptId)).requests.length, 0);
  assert.equal(await f.api.fetch("https://fixture.invalid/completion", request), response);
  const r = await collectRuntimeStream(f.page, config.attemptId);
  assert.equal(r.status, "partial"); assert.equal(r.requests[0].error, "RESPONSE_CLONE_UNAVAILABLE");
  await assert.rejects(async () => collectRuntimeStream(f.page, "other"), /ATTEMPT_MISMATCH/);
  await assert.rejects(async () => installRuntimeStreamObserver(f.page, config), /ALREADY_EXISTS/);
  await collectRuntimeStream(f.page, config.attemptId, { restore: true });
  assert.equal(f.api.fetch, original);
});

test("Original fetch failure propagates unchanged", async () => {
  const expected = new Error("original failure"), original = async () => { throw expected; }, f = fixture(original);
  await installRuntimeStreamObserver(f.page, config);
  await assert.rejects(f.api.fetch("https://fixture.invalid/completion", request), e => e === expected);
  await collectRuntimeStream(f.page, config.attemptId, { restore: true });
  assert.equal(f.api.fetch, original);
});

test("Global fallback capture preserves an undefined SDK override and nested JSON prompts", async () => {
  const original = async () => new Response("data: done\n\n"), f = fixture(original, true);
  const installed = await installRuntimeStreamObserver(f.page, config);
  assert.equal(installed.fetch_binding, "global-fetch-fallback");
  const response = await f.api.fetch("https://fixture.invalid/completion", { body: JSON.stringify({ content: JSON.stringify({ text: config.prompt }), options: { workspace: config.workspace } }) });
  await response.text();
  let capture;
  for (let i = 0; i < 100; i++) {
    capture = await collectRuntimeStream(f.page, config.attemptId);
    if (!capture.active) break;
    await new Promise(r => setTimeout(r, 5));
  }
  assert.equal(capture.status, "captured");
  await collectRuntimeStream(f.page, config.attemptId, { restore: true });
  assert.equal(f.api.fetch, original);
});
