import assert from "node:assert/strict";
import test from "node:test";
import { choosePageInventory } from "../register-projects.mjs";

test("task-titled main window outranks a Page prewarm window", () => {
  const pages = [
    { index: 0, title: "ChatGPT", url: "app://-/detached-window.html?initialRoute=%2Fdetached-window" },
    { index: 1, title: "ChatGPT", url: "app://-/index.html?initialRoute=%2Fspace%2Flocal-page-9f48da39%3Fwindow%3Dpage%26prewarm%3D1" },
    { index: 2, title: "DoubaoWork macOS E2E 集成", url: "app://-/index.html" },
  ];
  assert.equal(choosePageInventory(pages).index, 2);
  assert.equal(choosePageInventory(pages, pages[1].url).index, 1);
  assert.throws(() => choosePageInventory([...pages, { ...pages[2], index: 3 }]), /多个同等候选/);
  assert.throws(() => choosePageInventory([...pages, { ...pages[2], index: 3 }], pages[2].url), /必须唯一匹配/);
});

test("detached windows and Browser cannot displace the main app window", () => {
  assert.equal(choosePageInventory([
    { index: 0, title: "Browser", url: "https://example.com" },
    { index: 1, title: "ChatGPT", url: "app://-/index.html?initialRoute=%2Favatar-overlay" },
    { index: 2, title: "执行通用端到端评测", url: "app://-/index.html" },
    { index: 3, title: "DevTools", url: "devtools://devtools" },
  ]).index, 2);
});
