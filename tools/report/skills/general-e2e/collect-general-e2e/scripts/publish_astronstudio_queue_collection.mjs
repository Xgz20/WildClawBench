#!/usr/bin/env node
import { publishAstronStudioQueueCollection } from "./lib/general-finalizer.mjs";

const [unitFlag, unitRoot, queueFlag, queueId, ...extra] = process.argv.slice(2);
if (unitFlag !== "--unit-root" || !unitRoot || queueFlag !== "--queue-id" || !queueId || extra.length) {
  process.stderr.write("Usage: publish_astronstudio_queue_collection.mjs --unit-root ABS --queue-id ID\n");
  process.exitCode = 2;
} else {
  try {
    const result = await publishAstronStudioQueueCollection({ unitRoot, queueId });
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  } catch (error) {
    process.stderr.write(String(error.message) + "\n");
    process.exitCode = 1;
  }
}
