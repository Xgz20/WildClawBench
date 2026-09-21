#!/usr/bin/env node
import { mkdir, mkdtemp, rename, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { artifact, jsonBytes } from "../../vendor/e2e-shared/workbuddy-jsonl-metrics/index.mjs";
import { applyWorkBuddyTiming, timingSupplementInput, verifyTimingSupplement } from "../../vendor/e2e-shared/workbuddy-jsonl-metrics/timing.mjs";

export async function supplementWorkBuddyTiming({ unitRoot, executionRecord }) {
  const input = await timingSupplementInput(unitRoot, executionRecord);
  const taskId = input.original.record.identity.task_id;
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(taskId)) throw new Error("TASK_ID_INVALID");
  const createdAt = new Date().toISOString();
  const bytes = jsonBytes(applyWorkBuddyTiming(input.base, input.binding, input.sources, createdAt));
  const parent = join(unitRoot, "evidence/timing-supplements"), target = join(parent, taskId);
  await mkdir(parent, { recursive: true });
  const stage = await mkdtemp(join(parent, ".stage-"));
  try {
    await writeFile(join(stage, "resource-metrics.json"), bytes, { flag: "wx", mode: 0o600 });
    await writeFile(join(stage, "supplement.json"), jsonBytes({ ...input.manifest, created_at: createdAt,
      resource: artifact("resource-metrics.json", bytes) }), { flag: "wx", mode: 0o600 });
    await mkdir(target);
    try { await rename(stage, target); } catch (error) { await rm(target, { recursive: true }); throw error; }
  } finally { await rm(stage, { recursive: true, force: true }); }
  return verifyTimingSupplement(unitRoot, taskId, executionRecord);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), options = {};
  const flags = { "--unit-root": "unitRoot", "--execution-record": "executionRecord" };
  if (args.includes("--help")) console.log("Usage: --unit-root UNIT --execution-record FROZEN_RECORD");
  else {
    for (let i = 0; i < args.length; i += 2) {
      if (!flags[args[i]] || !args[i + 1]) throw new Error("INVALID_ARGUMENTS");
      options[flags[args[i]]] = args[i + 1];
    }
    console.log(JSON.stringify(await supplementWorkBuddyTiming(options)));
  }
}
