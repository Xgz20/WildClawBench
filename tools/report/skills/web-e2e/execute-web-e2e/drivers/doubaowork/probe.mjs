import { mkdir, writeFile } from "node:fs/promises";
import { resolve, join } from "node:path";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

import {
  DEFAULT_APP_PATH,
  DEFAULT_ENDPOINT,
  PROBE_SCHEMA,
  parseLoopbackEndpoint,
  isDoubaoWorkChatTarget,
  selectUniqueChatTarget,
  summarizeTarget,
} from "./lib.mjs";
import {
  discoverNativeSources,
  inspectEndpointListener,
  readDoubaoWorkAppIdentity,
} from "./platform.mjs";

async function fetchJson(url, timeout = 5_000) {
  const response = await fetch(url, { signal: AbortSignal.timeout(timeout) });
  if (!response.ok) throw new Error(`${url} 返回 HTTP ${response.status}`);
  return response.json();
}

export async function runProbe(config, overrides = {}) {
  const endpoint = parseLoopbackEndpoint(config.endpoint);
  const report = {
    schema: PROBE_SCHEMA,
    observed_at: new Date().toISOString(),
    read_only: true,
    actions_performed: [],
    endpoint: endpoint.origin,
    checks: {},
    errors: [],
  };
  let browser;
  try {
    const readAppIdentity = overrides.readAppIdentity ?? readDoubaoWorkAppIdentity;
    const app = await readAppIdentity(config.appPath, overrides.platform);
    report.app = {
      app_path: app.app_path,
      bundle_id: app.bundle_id,
      version: app.version,
      build: app.build,
    };
    report.checks.app_identity = true;
    report.actions_performed.push("read-app-identity");

    const inspectListener = overrides.inspectListener ?? inspectEndpointListener;
    const listener = await inspectListener(endpoint.origin, app, overrides.platform);
    report.listener = listener;
    if (!listener.unique_expected_listener) {
      throw new Error("CDP 端口监听者不是唯一且可核验的 DoubaoWork Browser 进程");
    }
    report.checks.listener_identity = true;
    report.actions_performed.push("read-listener");

    const version = await (overrides.fetchJson ?? fetchJson)(`${endpoint.origin}/json/version`);
    report.browser_version = version.Browser ?? null;
    report.protocol_version = version["Protocol-Version"] ?? null;
    report.checks.version_endpoint = true;
    report.actions_performed.push("read-cdp-version");

    const discoveryTargets = await (overrides.fetchJson ?? fetchJson)(`${endpoint.origin}/json/list`);
    report.discovery_targets = discoveryTargets.filter(isDoubaoWorkChatTarget).map(summarizeTarget);
    const discoveryTarget = selectUniqueChatTarget(discoveryTargets);
    report.discovery_target = summarizeTarget(discoveryTarget);
    report.checks.unique_discovery_target = true;
    report.actions_performed.push("read-cdp-targets");

    const connect = overrides.connect ?? ((...args) => chromium.connectOverCDP(...args));
    browser = await connect(endpoint.origin, { timeout: 10_000 });
    report.checks.playwright_connect = true;
    const pages = browser.contexts().flatMap((context) => context.pages());
    const page = selectUniqueChatTarget(pages.map((item) => ({ url: item.url(), page: item }))).page;
    page.setDefaultTimeout(10_000);
    report.playwright_target = summarizeTarget({ url: page.url(), type: "page" });
    report.checks.unique_playwright_target = true;
    report.page = await page.evaluate(() => ({
      url: location.href,
      title_length: document.title.length,
      ready_state: document.readyState,
      body_text_length: document.body?.innerText?.length ?? 0,
      content_editable_count: document.querySelectorAll('[contenteditable="true"]').length,
      textarea_count: document.querySelectorAll("textarea").length,
      main_count: document.querySelectorAll('main,[role="main"]').length,
      dialog_count: document.querySelectorAll('[role="dialog"]').length,
      send_button_count: document.querySelectorAll('[data-testid="chat_input_send_button"]').length,
      project_folder_item_count: document.querySelectorAll('[data-testid="project-shared-project-folder-item"]').length,
    }));
    const pageUrl = new URL(report.page.url);
    report.page.url = `${pageUrl.protocol}//${pageUrl.hostname}${pageUrl.pathname.replace(/[0-9]+/g, "<SESSION_ID>")}`;
    report.checks.dom_read = true;
    report.actions_performed.push("read-dom-summary");

    if (config.captureSensitiveArtifacts) {
      await writeFile(join(config.outputDir, "chat-aria.txt"), await page.locator("body").ariaSnapshot());
      const cdp = await page.context().newCDPSession(page);
      try {
        const capture = await cdp.send("Page.captureScreenshot", { format: "png" });
        await writeFile(join(config.outputDir, "chat.png"), Buffer.from(capture.data, "base64"));
      } finally {
        await cdp.detach();
      }
      report.sensitive_artifacts = ["chat-aria.txt", "chat.png"];
      report.checks.optional_sensitive_capture = true;
      report.actions_performed.push("capture-sensitive-artifacts");
    }

    const conversationHash = report.playwright_target.conversation_id_sha256;
    const discoverSources = overrides.discoverNativeSources ?? discoverNativeSources;
    const sessions = await discoverSources();
    report.native_sources = {
      roots: sessions.roots,
      log_file_count: sessions.logs.length,
      session_binding: "not-attempted-without-raw-conversation-id",
      conversation_id_sha256: conversationHash,
    };
    report.checks.native_source_roots = true;
    report.actions_performed.push("read-native-source-metadata");
    report.status = "passed";
  } catch (error) {
    report.status = "failed";
    report.errors.push(error instanceof Error ? error.message : String(error));
  } finally {
    if (browser) await browser.close();
  }
  return report;
}

export async function main(argv = process.argv.slice(2)) {
  const { values } = parseArgs({
    args: argv,
    options: {
      endpoint: { type: "string", default: DEFAULT_ENDPOINT },
      "app-path": { type: "string", default: DEFAULT_APP_PATH },
      "output-dir": { type: "string" },
      "capture-sensitive-artifacts": { type: "boolean", default: false },
    },
  });
  if (!values["output-dir"]) throw new Error("--output-dir 必填，且应位于仓库外私有证据目录");
  const outputDir = resolve(values["output-dir"]);
  await mkdir(outputDir, { recursive: true });
  const report = await runProbe({
    endpoint: values.endpoint,
    appPath: values["app-path"],
    outputDir,
    captureSensitiveArtifacts: values["capture-sensitive-artifacts"],
  });
  await writeFile(join(outputDir, "probe.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (report.status !== "passed") process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
