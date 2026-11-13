#!/usr/bin/env node
import { isEntrypoint } from '../../vendor/e2e-shared/loomy/index.mjs';
import { resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { collectTask } from '../../vendor/e2e-shared/loomy/collection.mjs';
export { collectTask };
export async function main(argv = process.argv.slice(2)) {
  const { values: args } = parseArgs({ args: argv, options: {
    'unit-root': { type: 'string' }, 'task-id': { type: 'string' }, 'run-config': { type: 'string' },
    'output-root': { type: 'string' }, help: { type: 'boolean' },
  } });
  if (args.help) { console.log('Loomy General 只读原生证据采集\nnode drivers/loomy/collector.mjs --unit-root ABS --task-id ID --run-config ABS [--output-root NEW_DIR]\n采集不发送 Prompt、不改候选、不判分；输出 trace-index v2、标准转录和资源来源。'); return; }
  if (!args['unit-root'] || !args['task-id'] || !args['run-config']) throw Error('LOOMY_COLLECT_INPUT_REQUIRED');
  console.log(JSON.stringify(await collectTask({ unitRoot: args['unit-root'], taskId: args['task-id'],
    runConfig: args['run-config'], outputRoot: args['output-root'] }), null, 2));
}
if (await isEntrypoint(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
