#!/usr/bin/env node
import { spawn } from "node:child_process";
import { realpathSync } from "node:fs";
import { mkdir, realpath, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_ENDPOINT = "http://127.0.0.1:9230";
const DEFAULT_BUNDLE_ID = "com.openai.codex";
const DRIVER_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_HELPER = join(DRIVER_DIR, "select-folder.swift");

export function usage() {
  return `Codex Desktop 项目注册器

用法：
  node register-projects.mjs --probe [--endpoint http://127.0.0.1:9230]
  node register-projects.mjs --project <绝对目录> [--endpoint URL] [--output JSON]

选项：
  --probe                         只读探测 CDP 页面和项目入口
  --project <目录>                要注册为 Codex Desktop 项目的评分目录；可重复
  --renderer-bridge               显式使用 Desktop 私有 renderer bridge 注册，跳过文件选择器
  --endpoint <URL>                Codex Desktop 本机 CDP 地址
  --page-url <URL>                多窗口时精确指定主页面 URL
  --bundle-id <ID>                macOS 应用 bundle id
  --app-path <路径>               Codex Desktop 应用路径
  --timeout-seconds <秒>          单步超时，默认 15
  --output <JSON>                 注册证据输出文件
`;
}

export function parseArgs(argv) {
  const args = {
    probe: false,
    rendererBridge: false,
    projects: [],
    endpoint: DEFAULT_ENDPOINT,
    pageUrl: "",
    bundleId: DEFAULT_BUNDLE_ID,
    appPath: "/Applications/ChatGPT.app",
    timeoutSeconds: 15,
    output: "",
    help: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--probe") args.probe = true;
    else if (token === "--renderer-bridge") args.rendererBridge = true;
    else if (token === "--project") args.projects.push(argv[++index] || "");
    else if (token === "--endpoint") args.endpoint = argv[++index] || "";
    else if (token === "--page-url") args.pageUrl = argv[++index] || "";
    else if (token === "--bundle-id") args.bundleId = argv[++index] || "";
    else if (token === "--app-path") args.appPath = argv[++index] || "";
    else if (token === "--timeout-seconds") args.timeoutSeconds = Number(argv[++index]);
    else if (token === "--output") args.output = argv[++index] || "";
    else if (token === "--help" || token === "-h") args.help = true;
    else throw new Error(`未知参数：${token}`);
  }
  if (!Number.isFinite(args.timeoutSeconds) || args.timeoutSeconds <= 0) throw new Error("--timeout-seconds 必须为正数");
  if (!args.probe && !args.help && !args.projects.length) throw new Error("必须提供 --project，或使用 --probe");
  if (args.projects.some((project) => !project)) throw new Error("--project 不能为空");
  return args;
}

export function assertLoopbackEndpoint(endpoint) {
  const url = new URL(endpoint);
  if (url.protocol !== "http:" || !new Set(["127.0.0.1", "localhost", "[::1]"]).has(url.hostname)) {
    throw new Error(`只允许本机 HTTP CDP 地址：${endpoint}`);
  }
  return url;
}

export function pageRank({ title, url }) {
  if (/devtools:/i.test(url)) return -1000;
  let score = 0;
  if (/^app:\/\//i.test(url)) score += 100;
  if (/codex|chatgpt/i.test(title)) score += 40;
  if (/initialRoute=.*avatar-overlay/i.test(url)) score -= 50;
  if (/settings|browser/i.test(title)) score -= 10;
  return score;
}

export function choosePageInventory(inventory, exactUrl = "") {
  if (exactUrl) {
    const matches = inventory.filter((entry) => entry.url === exactUrl);
    if (matches.length !== 1) throw new Error(`--page-url 必须唯一匹配，实际 ${matches.length} 个`);
    return matches[0];
  }
  const ranked = inventory.map((entry) => ({ ...entry, rank: pageRank(entry) })).sort((a, b) => b.rank - a.rank);
  if (!ranked.length || ranked[0].rank <= 0) throw new Error("CDP 中没有可识别的 Codex Desktop 主页面");
  if (ranked[1]?.rank === ranked[0].rank) throw new Error("存在多个同等候选 Codex 页面，请使用 --page-url 精确指定");
  return ranked[0];
}

async function endpointReady(endpoint) {
  const base = assertLoopbackEndpoint(endpoint);
  const response = await fetch(new URL("/json/version", base), { signal: AbortSignal.timeout(3000) }).catch(() => null);
  return Boolean(response?.ok);
}

async function visible(locator) {
  const count = await locator.count();
  const result = [];
  for (let index = 0; index < count; index += 1) {
    const item = locator.nth(index);
    if (await item.isVisible().catch(() => false)) result.push(item);
  }
  return result;
}

async function uniqueVisible(locators, label) {
  const matches = [];
  for (const locator of locators) matches.push(...await visible(locator));
  if (matches.length !== 1) throw new Error(`${label} 必须唯一可见，实际 ${matches.length} 个`);
  return matches[0];
}

async function dismissStaleProjectDialog(page, timeout) {
  const dialogs = await visible(page.getByRole("dialog"));
  if (!dialogs.length) return;
  if (dialogs.length !== 1) {
    throw new Error("Codex Desktop 存在未知对话框，拒绝继续注册项目");
  }
  const dialogText = await dialogs[0].innerText();
  if (/将设备连接到此 Mac|Connect (?:a )?device to this Mac/i.test(dialogText)) {
    const later = dialogs[0].getByRole("button", { name: /^(稍后|Not now|Maybe later)$/i });
    if (await later.count() !== 1) throw new Error("Desktop 设备连接引导缺少唯一的稍后按钮");
    await later.click({ timeout, noWaitAfter: true });
    await dialogs[0].waitFor({ state: "hidden", timeout });
    return;
  }
  if (!/创建项目|Create project/i.test(dialogText)) {
    throw new Error("Codex Desktop 存在未知对话框，拒绝继续注册项目");
  }
  const cancel = dialogs[0].getByRole("button", { name: /^(Cancel|取消)$/i });
  if (await cancel.count() !== 1) throw new Error("已有创建项目对话框无法安全关闭");
  await cancel.click({ timeout, noWaitAfter: true });
  await dialogs[0].waitFor({ state: "hidden", timeout });
}

async function beginProjectRegistration(page, timeout) {
  const openPattern = /^(Open folder|打开文件夹)$/i;
  const direct = await Promise.all([
    visible(page.getByRole("button", { name: openPattern })),
    visible(page.getByRole("menuitem", { name: openPattern })),
  ]);
  const directMatches = direct.flat();
  if (directMatches.length === 1) {
    await directMatches[0].click({ timeout, noWaitAfter: true });
    return { method: "direct-open-folder", finalize: false };
  }
  if (directMatches.length > 1) throw new Error(`打开文件夹入口不唯一，实际 ${directMatches.length} 个`);

  const createPattern = /^(Add new project|添加新项目)$/i;
  const createMatches = await visible(page.getByRole("button", { name: createPattern }));
  if (createMatches.length > 1) throw new Error(`添加新项目入口不唯一，实际 ${createMatches.length} 个`);
  if (createMatches.length === 1) {
    // 新版 Desktop 的侧栏收缩层可能覆盖图标命中区域；该定位器已经按唯一
    // aria-label 锁定按钮，force 只绕过装饰层的 pointer-events 拦截。
    await createMatches[0].click({ timeout, noWaitAfter: true, force: true });
    const dialog = page.getByRole("dialog");
    await dialog.waitFor({ state: "visible", timeout });
    const local = dialog.getByRole("radio", { name: /^(Local|本地)(\s|$)/i });
    if (await local.count() !== 1) throw new Error("创建项目对话框缺少唯一的本地项目选项");
    if (await local.getAttribute("aria-checked") !== "true") await local.click({ timeout, noWaitAfter: true });
    await dialog.getByRole("button", { name: /^(Next|下一步)$/i }).click({ timeout, noWaitAfter: true });
    const staleSources = dialog.getByRole("button", { name: /^(Remove|移除)\s+/i });
    while (await staleSources.count()) {
      await staleSources.first().click({ timeout, noWaitAfter: true });
    }
    const sourceFolder = await uniqueVisible([
      dialog.getByRole("button", { name: /^(Select source folder|选择源文件夹)$/i }),
      dialog.getByRole("button", { name: /^(Add folder|添加文件夹)$/i }),
    ], "源文件夹选择入口");
    await sourceFolder.click({ timeout, noWaitAfter: true, force: true });
    return { method: "create-local-project-dialog", finalize: true };
  }

  const addPattern = /^(Add project|添加项目|New project|新建项目|Open project|打开项目)$/i;
  const trigger = await uniqueVisible([
    page.getByRole("button", { name: addPattern }),
    page.getByRole("menuitem", { name: addPattern }),
  ], "添加项目入口");
  await trigger.click({ timeout, noWaitAfter: true });
  const open = await uniqueVisible([
    page.getByRole("button", { name: openPattern }),
    page.getByRole("menuitem", { name: openPattern }),
  ], "打开文件夹菜单项");
  await open.click({ timeout, noWaitAfter: true });
  return { method: "add-project-then-open-folder", finalize: false };
}

async function registerWithRendererBridge(page, project) {
  const available = await page.evaluate(
    () => typeof window.electronBridge?.sendMessageFromView === "function",
  );
  if (!available) throw new Error("Codex Desktop 未暴露 renderer bridge，不能使用 --renderer-bridge");
  await page.evaluate(async (root) => {
    await window.electronBridge.sendMessageFromView({
      type: "electron-add-new-workspace-root-option",
      root,
    });
  }, project);
  return {
    method: "renderer-bridge",
    finalize: false,
    nativeSelection: { folder: project, method: "renderer-bridge", status: "registered" },
  };
}

async function finalizeProjectRegistration(page, project, timeout) {
  const dialog = page.getByRole("dialog");
  await dialog.waitFor({ state: "visible", timeout });
  const sourceBasename = project.split("/").at(-1);
  const selectedSources = dialog.getByRole("button", { name: /^(Remove|移除)\s+/i });
  if (await selectedSources.count() !== 1 || !(await selectedSources.first().getAttribute("aria-label"))?.endsWith(sourceBasename)) {
    throw new Error(`创建项目对话框未回读到目标源文件夹：${sourceBasename}`);
  }
  const nameInput = dialog.getByRole("textbox", { name: /^(Project name|项目名称)$/i });
  if (await nameInput.count() !== 1) throw new Error("创建项目对话框缺少唯一的项目名称输入框");
  if (!(await nameInput.inputValue()).trim()) await nameInput.fill(sourceBasename, { timeout });
  const create = dialog.getByRole("button", { name: /^(Create project|创建项目)$/i });
  await create.waitFor({ state: "visible", timeout });
  if (!(await create.isEnabled())) throw new Error("选择源文件夹后创建项目按钮仍不可用");
  await create.click({ timeout, noWaitAfter: true });
  await dialog.waitFor({ state: "hidden", timeout });
}

function runHelper(helper, bundleId, project, timeoutSeconds) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn("/usr/bin/xcrun", ["swift", helper, bundleId, project, String(timeoutSeconds)], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", rejectPromise);
    child.once("exit", (code) => {
      if (code === 0) resolvePromise(JSON.parse(stdout));
      else rejectPromise(new Error(stderr.trim() || `文件夹选择 helper 退出码 ${code}`));
    });
  });
}

function appVersion(appPath) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn("/usr/libexec/PlistBuddy", ["-c", "Print :CFBundleShortVersionString", join(appPath, "Contents", "Info.plist")], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", rejectPromise);
    child.once("exit", (code) => code === 0
      ? resolvePromise(stdout.trim())
      : rejectPromise(new Error(stderr.trim() || `无法读取 Codex Desktop 版本：${appPath}`)));
  });
}

async function inspectPages(browser) {
  const entries = [];
  for (const context of browser.contexts()) {
    for (const page of context.pages()) entries.push({ page, title: await page.title().catch(() => ""), url: page.url() });
  }
  return entries;
}

async function writeOutput(filename, value) {
  if (!filename) return;
  const target = resolve(filename);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export async function run(args) {
  if (!(await endpointReady(args.endpoint))) {
    throw new Error(`Codex Desktop 未开放本机 CDP：${args.endpoint}。请在启动控制任务前以 --remote-debugging-address=127.0.0.1 和 --remote-debugging-port 启动 Desktop`);
  }
  const { chromium } = await import("playwright-core");
  const browser = await chromium.connectOverCDP(args.endpoint);
  try {
    const pages = await inspectPages(browser);
    const inventory = pages.map(({ title, url }, index) => ({ index, title, url }));
    const selected = choosePageInventory(inventory, args.pageUrl);
    const page = pages[selected.index].page;
    page.setDefaultTimeout(args.timeoutSeconds * 1000);
    const result = {
      schema_version: "wildclawbench.codex-project-registration/v1",
      endpoint: args.endpoint,
      desktop_version: await appVersion(args.appPath),
      desktop_page: { title: selected.title, url: selected.url },
      probed_at: new Date().toISOString(),
      projects: [],
    };
    if (args.probe) {
      result.status = "PROBED";
      result.pages = inventory;
      await writeOutput(args.output, result);
      return result;
    }

    for (const rawProject of args.projects) {
      if (!isAbsolute(rawProject)) throw new Error(`--project 必须为绝对路径：${rawProject}`);
      const project = await realpath(rawProject);
      await page.bringToFront();
      await dismissStaleProjectDialog(page, args.timeoutSeconds * 1000);
      const registration = args.rendererBridge
        ? await registerWithRendererBridge(page, project)
        : await beginProjectRegistration(page, args.timeoutSeconds * 1000);
      const nativeSelection = registration.nativeSelection ?? await runHelper(
        DEFAULT_HELPER,
        args.bundleId,
        project,
        args.timeoutSeconds,
      );
      if (registration.finalize) await finalizeProjectRegistration(page, project, args.timeoutSeconds * 1000);
      await page.waitForTimeout(1000);
      const evidenceDir = args.output ? dirname(resolve(args.output)) : "";
      let screenshot = null;
      if (evidenceDir) {
        await mkdir(evidenceDir, { recursive: true });
        screenshot = join(evidenceDir, `${project.split("/").at(-1)}-registered.png`);
        await page.screenshot({ path: screenshot });
      }
      result.projects.push({ requested_path: rawProject, canonical_path: project, ui_method: registration.method, native_selection: nativeSelection, screenshot });
    }
    result.status = args.rendererBridge
      ? "RENDERER_BRIDGE_REGISTRATION_COMPLETED"
      : "UI_REGISTRATION_COMPLETED";
    result.completed_at = new Date().toISOString();
    await writeOutput(args.output, result);
    return result;
  } finally {
    // connectOverCDP 返回的是已连接 Browser；Playwright 的公开 close() 在该
    // 场景只断开自动化连接，不退出用户正在运行的 Codex Desktop。
    await browser.close();
  }
}

async function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    if (args.help) {
      process.stdout.write(usage());
      return;
    }
    const result = await run(args);
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`FAIL: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
  }
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
