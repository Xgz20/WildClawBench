import { chromium } from "playwright-core";
import { pathToFileURL } from "node:url";
import { runProbe as sharedProbe, main as sharedMain } from "../../vendor/e2e-shared/doubaowork/probe.mjs";
const connect = (...args) => chromium.connectOverCDP(...args);
export const runProbe = (config, overrides = {}) => sharedProbe(config, { connect, ...overrides });
export const main = argv => sharedMain(argv, { connect });
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
