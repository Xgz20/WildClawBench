#!/usr/bin/env node
import { publishAstronStudioQueueCollection } from "./lib/general-finalizer.mjs";

const [unitFlag, unitRoot, queueFlag, queueId, ...extra] = process.argv.slice(2);
const [failedFlag, failedQueueId, shaFlag, failedQueueSha256] = extra;
const previousValid = extra.length === 0 || (extra.length === 4
  && failedFlag === "--closed-failed-queue-id" && failedQueueId
  && shaFlag === "--closed-failed-queue-sha256" && failedQueueSha256);
if (unitFlag !== "--unit-root" || !unitRoot || queueFlag !== "--queue-id" || !queueId || !previousValid) {
  process.stderr.write("Usage: publish_astronstudio_queue_collection.mjs --unit-root ABS --queue-id ID "
    + "[--closed-failed-queue-id ID --closed-failed-queue-sha256 SHA]\n");
  process.exitCode = 2;
} else {
  try {
    const result = await publishAstronStudioQueueCollection({ unitRoot, queueId, failedQueueId, failedQueueSha256 });
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  } catch (error) {
    process.stderr.write(String(error.message) + "\n");
    process.exitCode = 1;
  }
}
