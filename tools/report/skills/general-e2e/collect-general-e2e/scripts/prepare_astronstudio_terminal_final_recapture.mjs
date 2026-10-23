#!/usr/bin/env node
import { isAbsolute } from 'node:path';
import { prepareTerminalFinalRecapture } from '../vendor/e2e-shared/general-resource-supplements/astronstudio-terminal-final-recapture.mjs';
const args = process.argv.slice(2);
if (args.includes('--help')) {
  console.log('Explicit authorized recapture: --input-manifest ABS --output-dir ABS. Never sends, grades, overwrites original state, or changes a candidate.');
} else {
  const options = {};
  for (let i = 0; i < args.length; i += 2) {
    const key = { '--input-manifest': 'inputManifest', '--output-dir': 'outputDir' }[args[i]];
    if (!key || !args[i + 1] || !isAbsolute(args[i + 1])) throw Error('RECAPTURE_ABSOLUTE_ARGUMENTS_REQUIRED');
    options[key] = args[i + 1];
  }
  if (!options.inputManifest || !options.outputDir) throw Error('RECAPTURE_ABSOLUTE_ARGUMENTS_REQUIRED');
  prepareTerminalFinalRecapture(options).then(result => console.log(JSON.stringify(result, null, 2)))
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
