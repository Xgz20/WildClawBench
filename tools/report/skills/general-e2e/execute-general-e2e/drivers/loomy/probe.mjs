#!/usr/bin/env node
import { isEntrypoint } from '../../vendor/e2e-shared/loomy/index.mjs';
import { writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { jsonBytes, probe } from '../../vendor/e2e-shared/loomy/index.mjs';

export async function main(argv = process.argv.slice(2)) {
  const { values: args } = parseArgs({ args: argv, options: {
    output: { type: 'string' }, 'config-output': { type: 'string' }, 'cache-root': { type: 'string' },
    'app-path': { type: 'string' }, database: { type: 'string' }, python: { type: 'string' },
    'archived-failure-record': { type: 'string', multiple: true }, help: { type: 'boolean' },
  } });
  if (args.help) {
    console.log('Loomy macOS arm64 只读探针\nnode drivers/loomy/probe.mjs --output NEW.json --config-output NEW-config.json [--app-path /Applications/Loomy.app] [--python python3] [--archived-failure-record ABS/EXECUTION-RECORD.json ...]\n只读取应用、原生 UI、会话索引和运行状态；不启动客户端、不改模型/权限、不发送 Prompt。');
    return;
  }
  if (!args.output || !args['config-output']) throw Error('LOOMY_PROBE_OUTPUT_PATHS_REQUIRED');
  const result = await probe({ appPath: args['app-path'], database: args.database,
    cacheRoot: args['cache-root'] || resolve(dirname(args.output), '.loomy-ax-cache'), python: args.python || 'python3',
    archivedFailureRecords: args['archived-failure-record'] || [] });
  await writeFile(args.output, jsonBytes(result), { flag: 'wx', mode: 0o600 });
  await writeFile(args['config-output'], jsonBytes(result.config), { flag: 'wx', mode: 0o600 });
  console.log(JSON.stringify({ status: result.status, output: resolve(args.output), config: resolve(args['config-output']),
    version: result.config.client.version, configuration: result.config.configuration }));
}
if (await isEntrypoint(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
