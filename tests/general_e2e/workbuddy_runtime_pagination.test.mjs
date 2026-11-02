import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import { getWorkBuddyRuntimeConversation } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/runtime-binding.mjs";

function client(conversation) {
  return { evaluate: expression => vm.runInNewContext(expression, {
    window: { wb: { conversations: { get: async () => conversation } } },
    setTimeout,
  }) };
}
function view(requests, hasOlder = false, historyReady = true) {
  return { requests, entries: [], totalRequests: requests.length, hasOlder, historyReady };
}
const recent = { id: "recent", timestamp: 2000 };
const older = { id: "older", timestamp: 1000 };

test("WorkBuddy clears a native continuation only through an empty older page and fresh full view", async () => {
  let continuation = true;
  const queries = [];
  const result = await getWorkBuddyRuntimeConversation(client({
    info: { id: "conversation" },
    requestEntries: async query => {
      queries.push(query);
      if (query) { assert.equal(query.beforeRequestId, recent.id); continuation = false; return view([]); }
      return view([recent], continuation);
    },
  }), "conversation");
  assert.equal(queries.length, 3);
  assert.equal(result.requestEntries.hasOlder, false);
  assert.equal(result.requestEntries.requests[0].id, recent.id);
  assert.equal(result.history_pages.length, 2);
  assert.equal(result.history_pages[0].result.hasOlder, true);
  assert.equal(result.history_pages[1].result.requests.length, 0);
});

test("WorkBuddy loads real older requests without dropping extra user turns", async () => {
  let loaded = false;
  const result = await getWorkBuddyRuntimeConversation(client({
    info: { id: "conversation" },
    requestEntries: async query => {
      if (query) { loaded = true; return view([older]); }
      return view(loaded ? [recent, older] : [recent], !loaded);
    },
  }), "conversation");
  assert.deepEqual(Array.from(result.requestEntries.requests, r => r.id), ["recent", "older"]);
  assert.equal(result.requestEntries.totalRequests, 2);
});

test("WorkBuddy does not accept a stalled continuation", async () => {
  await assert.rejects(getWorkBuddyRuntimeConversation(client({
    requestEntries: async () => view([recent], true),
  }), "conversation"), /PAGINATION_STALLED/);
});

test("WorkBuddy preloads an unready history without changing its terminal flags", async () => {
  let loaded = false;
  const result = await getWorkBuddyRuntimeConversation(client({
    preload() { loaded = true; },
    requestEntries: async () => view(loaded ? [recent] : [], false, loaded),
  }), "conversation");
  assert.equal(result.requestEntries.historyReady, true);
  assert.equal(result.history_pages[0].result.historyReady, false);
});

test("WorkBuddy rejects a continuation without a valid native cursor", async () => {
  await assert.rejects(getWorkBuddyRuntimeConversation(client({
    requestEntries: async () => view([{ id: "../bad", timestamp: 2000 }], true),
  }), "conversation"), /CURSOR_INVALID/);
});
