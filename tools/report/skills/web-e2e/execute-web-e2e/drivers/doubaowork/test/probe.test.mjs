import assert from "node:assert/strict";
import { test } from "node:test";

import { runProbe } from "../probe.mjs";

function fakePage(url) {
  return {
    url: () => url,
    setDefaultTimeout: () => {},
    evaluate: async () => ({
      url,
      title_length: 11,
      ready_state: "complete",
      body_text_length: 100,
      content_editable_count: 1,
      textarea_count: 0,
      main_count: 1,
      dialog_count: 0,
      send_button_count: 1,
      project_folder_item_count: 1,
    }),
  };
}

test("probe 只读核验应用、监听者和唯一 chat target", async () => {
  let browserClosed = false;
  const page = fakePage("chrome://doubaowork-chat/chat/12345678901234567");
  const report = await runProbe({
    endpoint: "http://127.0.0.1:9260",
    appPath: "/Applications/DoubaoWork.app",
    outputDir: "/private/evidence",
    captureSensitiveArtifacts: false,
  }, {
    readAppIdentity: async () => ({
      app_path: "/Applications/DoubaoWork.app",
      bundle_id: "com.work.pc.doubao",
      version: "2.28.12",
      build: "2.28.12",
      browser_executable: "/Applications/DoubaoWork.app/Contents/Helpers/DoubaoWork Browser.app/Contents/MacOS/DoubaoWork Browser",
    }),
    inspectListener: async () => ({ endpoint: "http://127.0.0.1:9260", listeners: [{}], unique_expected_listener: true }),
    fetchJson: async (url) => url.endsWith("/json/version")
      ? { Browser: "Chrome/147", "Protocol-Version": "1.3" }
      : [{ type: "page", url: "doubaowork://doubaowork-chat/chat/12345678901234567" }],
    connect: async () => ({
      contexts: () => [{ pages: () => [page] }],
      close: async () => { browserClosed = true; },
    }),
    discoverNativeSources: async () => ({ roots: {}, logs: [] }),
  });
  assert.equal(report.status, "passed");
  assert.equal(report.read_only, true);
  assert.equal(report.actions_performed.includes("click"), false);
  assert.equal(report.page.url.includes("12345678901234567"), false);
  assert.equal(report.discovery_targets.length, 1);
  assert.equal(JSON.stringify(report.discovery_targets).includes("12345678901234567"), false);
  assert.equal(browserClosed, true);
});

test("probe 在监听者身份不唯一时失败关闭且不连接页面", async () => {
  let connected = false;
  const report = await runProbe({
    endpoint: "http://127.0.0.1:9260",
    appPath: "/Applications/DoubaoWork.app",
    outputDir: "/private/evidence",
    captureSensitiveArtifacts: false,
  }, {
    readAppIdentity: async () => ({
      app_path: "/Applications/DoubaoWork.app",
      bundle_id: "com.work.pc.doubao",
      version: "2.28.12",
      build: "2.28.12",
      browser_executable: "/Applications/DoubaoWork Browser",
    }),
    inspectListener: async () => ({ endpoint: "http://127.0.0.1:9260", listeners: [{}, {}], unique_expected_listener: false }),
    connect: async () => { connected = true; },
  });
  assert.equal(report.status, "failed");
  assert.equal(connected, false);
  assert.match(report.errors[0], /监听者/);
});
