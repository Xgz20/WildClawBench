import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import test from "node:test";
import { checkBrowserReadiness, evaluateBrowserReadiness } from "../../../scripts/browser-readiness.mjs";

const epoch = Date.parse("2026-10-09T02:00:00Z");
const at = (seconds) => new Date(epoch + seconds * 1000).toISOString();
const own = (tabs = []) => ({ browsers: [{ id: "2", type: "iab", metadata: { codexSessionId: "thread-1" }, tabs }] });
function ready() {
  return {
    task_id: "task-1", thread_id: "thread-1", started_at: at(0),
    discoveries: [{ started_at: at(0), finished_at: at(5), state: own() }],
    creation: { attempt_count: 1, success: true, tab_id: "1", started_at: at(5), finished_at: at(8) },
    verification: { finished_at: at(10), state: own([{ id: "1", url: "about:blank" }]) },
    readback: { finished_at: at(8), url: "about:blank", ax_state: "0 AXWebArea about:blank" },
  };
}
function emptyDiscoveries(count) {
  return [0, 7, 17].slice(0, count).map((second) => ({ started_at: at(second), finished_at: at(second + 5), state: { browsers: [] } }));
}
function evaluate(input, second = 11) { return evaluateBrowserReadiness(input, "thread-1", epoch + second * 1000); }

test("ready proof requires own tab, actual AX and bounded observation time", () => {
  const result = evaluate(ready());
  assert.equal(result.status, "READY");
  assert.equal(result.internal_info_timeout_changed, false);
  assert.equal(result.warmup_seconds, 60);
  assert.equal(result.browser_id, "2");
  assert.equal(result.verified_at, at(10));
});

test("empty inventories use two bounded backoffs then allow one official initialization", () => {
  for (const [count, delay] of [[1, 2], [2, 5]]) {
    const input = { ...ready(), discoveries: emptyDiscoveries(count), creation: null };
    const result = evaluate(input, count === 1 ? 5 : 12);
    assert.equal(result.status, "RETRY_DISCOVERY");
    assert.equal(result.retry_after_seconds, delay);
  }
  const input = { ...ready(), discoveries: emptyDiscoveries(3), creation: null };
  assert.equal(evaluate(input, 23).action, "CREATE_OWN_ABOUT_BLANK_ONCE");
  input.creation = { ...ready().creation, started_at: at(22), finished_at: at(25) };
  input.verification.finished_at = at(28);
  input.readback.finished_at = at(25);
  assert.equal(evaluate(input, 29).status, "READY");
  input.discoveries.push({ started_at: at(29), finished_at: at(34), state: own() });
  assert.throws(() => evaluate(input, 35), /1至3次/);
});

test("warmup deadline blocks empty, late creation and late page readback", () => {
  assert.equal(evaluate({ ...ready(), discoveries: emptyDiscoveries(1), creation: null }, 60).status, "BLOCKED");
  const creation = ready();
  creation.creation.finished_at = at(61);
  assert.equal(evaluate(creation, 62).reason, "warmup-window-expired");
  const readback = ready();
  readback.readback.finished_at = at(61);
  assert.equal(evaluate(readback, 62).reason, "warmup-window-expired");
  assert.equal(evaluate(ready(), 71).reason, "stale-health-proof");
});

test("foreign and ambiguous inventories fail closed", () => {
  const foreign = ready();
  foreign.discoveries[0].state.browsers[0].metadata.codexSessionId = "parent-thread";
  assert.throws(() => evaluate(foreign), /归属不匹配/);
  const ambiguous = ready();
  ambiguous.verification.state.browsers.push(own().browsers[0]);
  assert.throws(() => evaluate(ambiguous), /不唯一/);
  assert.throws(() => evaluate({ ...ready(), thread_id: "other" }), /thread_id 不匹配/);
});

test("creation failure, extra attempts and missing verification never permit site startup", () => {
  assert.equal(evaluate({ ...ready(), creation: { ...ready().creation, success: false } }).reason, "actual-creation-failed");
  assert.equal(evaluate({ ...ready(), discoveries: emptyDiscoveries(1), creation: { ...ready().creation, success: false } }).reason, "actual-creation-failed");
  assert.throws(() => evaluate({ ...ready(), creation: { ...ready().creation, attempt_count: 2 } }), /只能一次/);
  assert.equal(evaluate({ ...ready(), verification: null }).reason, "missing-ownership-verification");
  const changed = ready();
  changed.verification.state.browsers[0].id = "new-browser";
  assert.equal(evaluate(changed).reason, "browser-binding-changed");
});

test("unbound tabs or missing actual AX fail, other browser types cannot supply proof", () => {
  const duplicate = ready();
  duplicate.verification.state.browsers[0].tabs.push({ id: "1", url: "about:blank" });
  assert.equal(evaluate(duplicate).reason, "created-tab-not-uniquely-bound");
  const missing = ready();
  missing.readback.ax_state = "Browser is available";
  assert.equal(evaluate(missing).reason, "missing-actual-page-readback");
  const other = ready();
  other.verification.state.browsers[0].type = "chrome";
  assert.equal(evaluate(other).reason, "browser-binding-changed");
});

test("invalid time, reversed ordering and skipped backoffs are rejected", () => {
  assert.throws(() => evaluate({ ...ready(), started_at: "invalid" }), /有效时间/);
  assert.throws(() => evaluate(ready(), 4), /时间顺序错误/);
  const reversed = ready();
  reversed.creation.started_at = at(4);
  assert.throws(() => evaluate(reversed), /创建时间顺序错误/);
  const fast = { ...ready(), discoveries: emptyDiscoveries(2), creation: null };
  fast.discoveries[1].started_at = at(6);
  assert.throws(() => evaluate(fast, 13), /退避时间/);
});

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "web-browser-readiness-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, "private-scoring/evidence"), { recursive: true });
  fs.writeFileSync(path.join(root, "private-scoring/task_contract.json"), JSON.stringify({ identity: { task_id: "task-1" } }));
  const relative = "private-scoring/evidence/input.json";
  fs.writeFileSync(path.join(root, relative), JSON.stringify(ready()));
  return { root, relative, check: () => checkBrowserReadiness(root, relative, "thread-1", epoch + 11000) };
}

test("CLI helper writes atomic private evidence and preserves its input", (t) => {
  const f = fixture(t);
  const before = fs.readFileSync(path.join(f.root, f.relative));
  assert.equal(f.check().status, "READY");
  const output = path.join(f.root, "private-scoring/evidence/browser-readiness.json");
  assert.deepEqual(JSON.parse(fs.readFileSync(output)).observations, ready());
  assert.equal(fs.statSync(output).mode & 0o777, 0o600);
  assert.deepEqual(fs.readFileSync(path.join(f.root, f.relative)), before);
  assert.deepEqual(fs.readdirSync(path.dirname(output)).sort(), ["browser-readiness.json", "input.json"]);
  assert.equal(f.check().status, "READY");
});

test("helper rejects task mismatch, traversal, oversized input and overwriting result", (t) => {
  const f = fixture(t);
  for (const input of ["../input.json", path.join(f.root, f.relative), "workspace/input.json"]) {
    assert.throws(() => checkBrowserReadiness(f.root, input, "thread-1"), /本题 evidence/);
  }
  fs.writeFileSync(path.join(f.root, f.relative), JSON.stringify({ ...ready(), task_id: "other" }));
  assert.throws(f.check, /task_id 不匹配/);
  fs.writeFileSync(path.join(f.root, f.relative), " ".repeat(262145));
  assert.throws(f.check, /有界普通文件/);
  fs.writeFileSync(path.join(f.root, f.relative), JSON.stringify(ready()));
  f.check();
  const relative = "private-scoring/evidence/browser-readiness.json";
  fs.writeFileSync(path.join(f.root, relative), JSON.stringify(ready()));
  assert.throws(() => checkBrowserReadiness(f.root, relative, "thread-1", epoch + 11000), /输入不能覆盖/);
});

test("helper rejects input, contract, directory and dangling output symlinks", (t) => {
  for (const kind of ["input", "contract", "directory", "output"]) {
    const f = fixture(t);
    const target = kind === "input" ? path.join(f.root, f.relative)
      : kind === "contract" ? path.join(f.root, "private-scoring/task_contract.json")
      : kind === "directory" ? path.join(f.root, "private-scoring/evidence")
      : path.join(f.root, "private-scoring/evidence/browser-readiness.json");
    fs.rmSync(target, { recursive: true, force: true });
    fs.symlinkSync(path.join(f.root, "missing"), target);
    assert.throws(f.check, /符号链接|有界普通文件|普通文件/);
    assert.equal(fs.existsSync(path.join(f.root, "missing")), false);
  }
});
