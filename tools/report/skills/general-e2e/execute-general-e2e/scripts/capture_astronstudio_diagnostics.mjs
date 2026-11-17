#!/usr/bin/env node
import {captureStandaloneDiagnostics} from "../vendor/e2e-shared/astronstudio-runtime/diagnostics.mjs";
const args=process.argv.slice(2),options={};
if(args.includes("--help")) {
  process.stdout.write("Read-only AStudio diagnostics: --unit-root ABS --state-file ABS --output-dir NEW_ABS [--reason TEXT]\n");
} else {
  const keys={"--unit-root":"unitRoot","--state-file":"stateFile","--output-dir":"outputDir","--reason":"reason"};
  for(let i=0;i<args.length;i+=2) {
    if(!keys[args[i]]||!args[i+1])throw Error("Invalid diagnostics argument");
    options[keys[args[i]]]=args[i+1];
  }
  if(!options.unitRoot||!options.stateFile||!options.outputDir)throw Error("Missing diagnostics paths");
  process.stdout.write(JSON.stringify(await captureStandaloneDiagnostics(options),null,2)+"\n");
}
