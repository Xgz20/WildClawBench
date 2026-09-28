#!/usr/bin/env node
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { main } from "../vendor/e2e-shared/general-resource-supplements/index.mjs";
export * from "../vendor/e2e-shared/general-resource-supplements/index.mjs";
if (process.argv[1] && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url))) main().catch(e => { console.error(e.message); process.exitCode = 1; });
