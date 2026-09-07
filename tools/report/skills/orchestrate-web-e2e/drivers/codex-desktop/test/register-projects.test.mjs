import assert from "node:assert/strict";
import test from "node:test";

import {
  assertLoopbackEndpoint,
  choosePageInventory,
  pageRank,
  parseArgs,
} from "../register-projects.mjs";

test("parseArgs accepts probe and repeated project paths", () => {
  const args = parseArgs([
    "--project", "/tmp/a",
    "--project", "/tmp/b",
    "--renderer-bridge",
    "--endpoint", "http://localhost:9230",
  ]);
  assert.deepEqual(args.projects, ["/tmp/a", "/tmp/b"]);
  assert.equal(args.rendererBridge, true);
  assert.equal(args.endpoint, "http://localhost:9230");
});

test("registrar only accepts loopback HTTP endpoints", () => {
  assert.equal(assertLoopbackEndpoint("http://127.0.0.1:9230").hostname, "127.0.0.1");
  assert.throws(() => assertLoopbackEndpoint("https://127.0.0.1:9230"), /只允许本机/);
  assert.throws(() => assertLoopbackEndpoint("http://192.0.2.1:9230"), /只允许本机/);
});

test("Codex app page outranks browser and DevTools pages", () => {
  assert.ok(pageRank({ title: "Codex", url: "app://-/" }) > pageRank({ title: "Browser", url: "https://example.com" }));
  assert.ok(pageRank({ title: "ChatGPT", url: "app://-/index.html" }) > pageRank({ title: "ChatGPT", url: "app://-/index.html?initialRoute=%2Favatar-overlay" }));
  assert.ok(pageRank({ title: "DevTools", url: "devtools://devtools" }) < 0);
  const selected = choosePageInventory([
    { index: 0, title: "Example", url: "https://example.com" },
    { index: 1, title: "Codex", url: "app://-/" },
  ]);
  assert.equal(selected.index, 1);
});

test("multiple equal app pages require an exact URL", () => {
  const pages = [
    { index: 0, title: "Codex", url: "app://-/one" },
    { index: 1, title: "Codex", url: "app://-/two" },
  ];
  assert.throws(() => choosePageInventory(pages), /多个同等候选/);
  assert.equal(choosePageInventory(pages, "app://-/two").index, 1);
});
