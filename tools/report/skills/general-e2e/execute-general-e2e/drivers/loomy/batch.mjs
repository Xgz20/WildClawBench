#!/usr/bin/env node
import { isEntrypoint } from '../../vendor/e2e-shared/loomy/index.mjs';
import { resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { runBatch } from '../../vendor/e2e-shared/loomy/batch.mjs';
export { runBatch };

export async function main(argv = process.argv.slice(2)) {
  const { values: args } = parseArgs({ args: argv, options: {
    'unit-root': { type: 'string' }, 'run-config': { type: 'string' }, 'queue-id': { type: 'string' },
    'run-slots': { type: 'string' }, resume: { type: 'boolean' }, 'continue-on-terminal-failure': { type: 'boolean' },
    help: { type: 'boolean' },
    'source-repair-manifest': { type: 'string' },
    'retry-pre-send-task-id': { type: 'string', multiple: true },
  } });
  if (args.help) {
    console.log('Loomy General E2E macOS 持久化队列\nnode drivers/loomy/batch.mjs --unit-root ABS --run-config ABS --queue-id ID [--run-slots 1..3] [--resume]\n默认单槽；UI 发送始终串行。冻结题序/输入/参数，未知发送不重发，无任务级 deadline。');
    return;
  }
  if (!args['unit-root'] || !args['run-config'] || !args['queue-id']) throw Error('LOOMY_QUEUE_INPUT_REQUIRED');
  const result = await runBatch({ unitRoot: args['unit-root'], runConfig: args['run-config'], queueId: args['queue-id'],
    runSlots: args['run-slots'] ? Number(args['run-slots']) : 1, resume: args.resume,
    sourceRepairManifest: args['source-repair-manifest'],
    retryPreSendTaskIds: args['retry-pre-send-task-id'] || [],
    continueOnTerminalFailure: args['continue-on-terminal-failure'] });
  console.log(JSON.stringify(result, null, 2));
  if (result.phase === 'NEEDS_ATTENTION') process.exitCode = 3;
}
if (await isEntrypoint(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
