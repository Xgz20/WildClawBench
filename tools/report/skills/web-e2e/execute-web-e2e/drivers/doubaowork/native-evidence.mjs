// Shared source: tools/report/e2e-shared/doubaowork/native-evidence.mjs
export * from "../../vendor/e2e-shared/doubaowork/native-evidence.mjs";
import { main } from "../../vendor/e2e-shared/doubaowork/native-evidence.mjs";
import { pathToFileURL } from "node:url";
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}
