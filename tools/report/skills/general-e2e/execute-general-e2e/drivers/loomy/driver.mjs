#!/usr/bin/env node
import { isEntrypoint } from '../../vendor/e2e-shared/loomy/index.mjs';
import { resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { executeTask } from '../../vendor/e2e-shared/loomy/execution.mjs';
export { executeTask };

export async function main(argv = process.argv.slice(2)) {
  const { values: args } = parseArgs({ args: argv, options: {
    'unit-root': { type: 'string' }, 'task-id': { type: 'string' }, 'run-config': { type: 'string' },
    resume: { type: 'boolean' }, 'detach-after-submit': { type: 'boolean' }, 'observe-once': { type: 'boolean' },
    'poll-interval-ms': { type: 'string' }, 'identity-timeout-ms': { type: 'string' }, help: { type: 'boolean' },
    'source-repair-manifest': { type: 'string' },
    'retry-pre-send-failure': { type: 'boolean' },
  } });
  if (args.help) {
    console.log('Loomy General E2E macOS 单题执行\nnode drivers/loomy/driver.mjs --unit-root ABS --task-id ID --run-config ABS [--detach-after-submit]\n恢复：原参数加 --resume [--observe-once]。恢复只观察原 attempt，绝不重发。\nUI/身份绑定超时不构成被测任务 deadline。');
    return;
  }
  if (!args['unit-root'] || !args['task-id'] || !args['run-config']) throw Error('LOOMY_EXECUTION_INPUT_REQUIRED');
  if (args['observe-once'] && (!args.resume || args['detach-after-submit'])) throw Error('LOOMY_OBSERVE_ONCE_REQUIRES_RESUME');
  for (const key of ['poll-interval-ms', 'identity-timeout-ms']) if (args[key] && (!Number.isSafeInteger(Number(args[key])) || Number(args[key]) <= 0)) throw Error('LOOMY_INVALID_INTERVAL:' + key);
  const result = await executeTask({ unitRoot: args['unit-root'], taskId: args['task-id'], runConfig: args['run-config'],
    resume: args.resume, detachAfterSubmit: args['detach-after-submit'], observeOnce: args['observe-once'],
    sourceRepairManifest: args['source-repair-manifest'],
    retryPreSendFailure: args['retry-pre-send-failure'],
    pollIntervalMs: args['poll-interval-ms'] ? Number(args['poll-interval-ms']) : undefined,
    identityTimeoutMs: args['identity-timeout-ms'] ? Number(args['identity-timeout-ms']) : undefined });
  console.log(JSON.stringify(result, null, 2));
  if (result.state.phase === 'NEEDS_ATTENTION') process.exitCode = 3;
}
if (await isEntrypoint(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
