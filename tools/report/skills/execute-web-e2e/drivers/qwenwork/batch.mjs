#!/usr/bin/env node

import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

process.env.WCB_WEB_E2E_BATCH_PROFILE = "qwenwork";

const { main } = await import("../workbuddy/batch.mjs");

const isEntrypoint = process.argv[1]
  && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  const exitCode = await main(process.argv.slice(2));
  process.exitCode = exitCode;
  setImmediate(() => process.exit(exitCode));
}
