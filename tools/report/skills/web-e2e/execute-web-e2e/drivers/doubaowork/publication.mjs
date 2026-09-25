import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, realpath, writeFile, rename } from "node:fs/promises";
import { dirname, join, resolve, sep } from "node:path";
import { readRegular } from "../../vendor/e2e-shared/doubaowork/bound-evidence.mjs";
import { snapshotTree } from "../workbuddy/lib.mjs";
const sha = b => createHash("sha256").update(b).digest("hex");
const json = v => Buffer.from(`${JSON.stringify(v, null, 2)}\n`);
async function existing(path) { try { return await readRegular(path); } catch (e) { if (e.code !== "ENOENT") throw e; return null; } }

// Resume publication of exactly the already frozen bytes; never repeat cleanup or dispatch.
export async function publishFrozenTransaction(outputDir) {
  const transaction = JSON.parse(await readRegular(join(outputDir, "formal-transaction.json")));
  if (transaction.schema !== "wildclawbench.doubaowork-web-publication/v1") throw new Error("DOUBAOWORK_WEB_TRANSACTION_SCHEMA");
  const root = transaction.harness_root;
  if (await realpath(root) !== root || !outputDir.startsWith(root + sep)) throw new Error("DOUBAOWORK_WEB_TRANSACTION_ROOT");
  const scoped = path => { const target = resolve(root, path); if (!target.startsWith(root + sep)) throw new Error("DOUBAOWORK_WEB_TRANSACTION_PATH"); return target; };
  for (const row of transaction.prerequisites) if (sha(await readRegular(scoped(row.path))) !== row.sha256) throw new Error("DOUBAOWORK_WEB_TRANSACTION_INPUT_DRIFT");
  const check = await snapshotTree(scoped(transaction.candidate_path));
  if (check.sha256 !== transaction.candidate_sha256 || check.forbidden_directories.length) throw new Error("DOUBAOWORK_WEB_TRANSACTION_CANDIDATE_DRIFT");
  // Verify the complete transaction before publishing any file, including after a crash.
  for (const row of transaction.files) {
    if (sha(await readRegular(scoped(row.staged_path))) !== row.sha256) throw new Error("DOUBAOWORK_WEB_TRANSACTION_STAGING_DRIFT");
    const prior = await existing(scoped(row.path));
    if (prior && sha(prior) !== row.sha256 && sha(prior) !== row.previous_sha256) throw new Error("DOUBAOWORK_WEB_TRANSACTION_TARGET_CONFLICT");
  }
  for (const row of transaction.files) {
    const target = scoped(row.path), bytes = await readRegular(scoped(row.staged_path));
    const prior = await existing(target);
    if (prior && sha(prior) === row.sha256) continue;
    await mkdir(dirname(target), { recursive: true });
    if (await realpath(dirname(target)) !== dirname(target)) throw new Error("DOUBAOWORK_WEB_TRANSACTION_SYMLINK");
    if (!prior) await writeFile(target, bytes, { flag: "wx", mode: 0o600 });
    else {
      if (sha(prior) !== row.previous_sha256) throw new Error("DOUBAOWORK_WEB_TRANSACTION_TARGET_CONFLICT");
      const tmp = join(dirname(target), `.publication-${randomUUID()}`);
      await writeFile(tmp, bytes, { flag: "wx", mode: 0o600 });
      if (sha(await readRegular(target)) !== row.previous_sha256) throw new Error("DOUBAOWORK_WEB_TRANSACTION_TARGET_DRIFT");
      await rename(tmp, target);
    }
  }
  const finalCheck = await snapshotTree(scoped(transaction.candidate_path));
  if (finalCheck.sha256 !== transaction.candidate_sha256 || finalCheck.forbidden_directories.length) throw new Error("DOUBAOWORK_WEB_TRANSACTION_CANDIDATE_DRIFT");
  const marker = { attempt_id: transaction.attempt_id, manifest_sha256: transaction.manifest_sha256,
    candidate_sha256: transaction.candidate_sha256, files: [...transaction.prerequisites, ...transaction.files.map(({ path, sha256 }) => ({ path, sha256 }))] };
  await writeFile(join(outputDir, "formal-publication.json"), json(marker), { flag: "wx", mode: 0o600 });
  return marker;
}
