#!/usr/bin/env node

import { discoverDesktopApp } from "./index.mjs";
import { BUILTIN_DESKTOP_APP_PROFILES } from "./profiles.mjs";

function usage() {
  return `Desktop application discovery

Usage:
  node cli.mjs --profile <astronstudio|workbuddy|qwenwork|codex> [options]

Options:
  --app-path <path>       Explicit installation path (highest priority)
  --endpoint <url>        Optional loopback CDP endpoint used to identify a running process
  --platform <name>       darwin or win32; defaults to the current platform
  --format <json|tsv>     Output format; defaults to json
  -h, --help              Show this help
`;
}

function parseArgs(argv) {
  const result = { profile: "", appPath: "", endpoint: null, platform: process.platform, format: "json", help: false };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === "-h" || item === "--help") result.help = true;
    else if (item === "--profile") result.profile = argv[++index] || "";
    else if (item === "--app-path") result.appPath = argv[++index] || "";
    else if (item === "--endpoint") result.endpoint = argv[++index] || null;
    else if (item === "--platform") result.platform = argv[++index] || "";
    else if (item === "--format") result.format = argv[++index] || "";
    else throw new Error(`unknown argument: ${item}`);
  }
  if (!result.help && !BUILTIN_DESKTOP_APP_PROFILES[result.profile]) {
    throw new Error("--profile must select astronstudio, workbuddy, qwenwork, or codex");
  }
  if (!new Set(["json", "tsv"]).has(result.format)) throw new Error("--format must be json or tsv");
  return result;
}

async function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    if (args.help) {
      process.stdout.write(usage());
      return;
    }
    const result = await discoverDesktopApp({
      profile: BUILTIN_DESKTOP_APP_PROFILES[args.profile],
      requestedPath: args.appPath,
      endpoint: args.endpoint,
      platform: args.platform,
    });
    if (args.format === "tsv") {
      process.stdout.write(`${result.path}\t${result.source}\t${result.executable_path || ""}\n`);
    } else {
      process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    }
  } catch (error) {
    const payload = {
      status: "FAIL",
      code: error?.code || "DISCOVERY_FAILED",
      error: error instanceof Error ? error.message : String(error),
      candidates_checked: Array.isArray(error?.candidatesChecked) ? error.candidatesChecked : [],
    };
    process.stderr.write(`${JSON.stringify(payload)}\n`);
    process.exitCode = 2;
  }
}

await main();
