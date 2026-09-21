#!/usr/bin/env node
import { mkdir, mkdtemp, rename, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { VERSION, SUPPLEMENT_SCHEMA, originalResources, discoverJsonl, parseBoundJsonl,
  supplementalMetrics, artifact, jsonBytes, safeRead, verifySupplement, equal } from "../../vendor/e2e-shared/workbuddy-jsonl-metrics/index.mjs";

export async function supplementWorkBuddyResources({ unitRoot, executionRecord, nativeProjectsRoot = join(homedir(), ".workbuddy/projects") }) {
  const original = await originalResources(unitRoot, executionRecord);
  const { record } = original;
  const native = await discoverJsonl(nativeProjectsRoot, record.session.session_id);
  if (!native) throw new Error("WORKBUDDY_JSONL_MISSING");
  const parsed = parseBoundJsonl(native.bytes, { snapshot: original.snapshot, session: record.session, promptSha256: record.prompt.sha256 });
  const source = artifact("native.jsonl", native.bytes);
  const createdAt = new Date().toISOString();
  const resourceBytes = jsonBytes(supplementalMetrics(original, parsed, source, createdAt));
  const receiptPath = join(unitRoot, "receipts/collect-evidence-receipt.json");
  const receiptBytes = await safeRead(unitRoot, receiptPath);
  const receipt = JSON.parse(receiptBytes);
  if (receipt.status !== "completed" || receipt.stage !== "collect-evidence"
      || !equal(receipt.scope, { batch_id: record.identity.batch_id, unit_id: record.identity.unit_id })
      || !receipt.artifacts.some(x => x.path === original.execution.path && x.sha256 === original.execution.sha256)) {
    throw new Error("WORKBUDDY_SUPPLEMENT_COLLECT_RECEIPT_MISMATCH");
  }
  const parent = join(unitRoot, "evidence/resource-supplements");
  const target = join(parent, record.identity.task_id);
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(record.identity.task_id)) throw new Error("TASK_ID_INVALID");
  await mkdir(parent, { recursive: true });
  const stage = await mkdtemp(join(parent, ".stage-"));
  try {
    await writeFile(join(stage, "native.jsonl"), native.bytes, { mode: 0o600, flag: "wx" });
    await writeFile(join(stage, "resource-metrics.json"), resourceBytes, { mode: 0o600, flag: "wx" });
    await writeFile(join(stage, "supplement.json"), jsonBytes({
      schema_version: SUPPLEMENT_SCHEMA, collector_version: VERSION, created_at: createdAt,
      resource_path_base: "unit",
      identity: record.identity, dataset: record.dataset,
      base_execution: original.execution, base_resource: original.resource,
      base_collect_receipt: artifact("receipts/collect-evidence-receipt.json", receiptBytes),
      native: source, resource: artifact("resource-metrics.json", resourceBytes),
    }), { mode: 0o600, flag: "wx" });
    // mkdir reserves the final name; an existing supplement never gets overwritten.
    await mkdir(target);
    try { await rename(stage, target); } catch (error) { await rm(target, { recursive: true }); throw error; }
  } finally { await rm(stage, { recursive: true, force: true }); }
  return verifySupplement(unitRoot, record.identity.task_id, executionRecord);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), options = {};
  const flags = { "--unit-root": "unitRoot", "--execution-record": "executionRecord", "--native-projects-root": "nativeProjectsRoot" };
  if (args.includes("--help")) console.log("Usage: --unit-root UNIT --execution-record FROZEN_RECORD [--native-projects-root ~/.workbuddy/projects]");
  else {
    for (let i = 0; i < args.length; i += 2) {
      if (!flags[args[i]] || !args[i + 1]) throw new Error("INVALID_ARGUMENTS");
      options[flags[args[i]]] = args[i + 1];
    }
    console.log(JSON.stringify(await supplementWorkBuddyResources(options)));
  }
}
