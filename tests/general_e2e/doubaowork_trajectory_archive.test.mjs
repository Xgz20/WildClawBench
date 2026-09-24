import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, writeFile, readFile, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { captureTrajectoryVersion } from "../../tools/report/e2e-shared/doubaowork/trajectory-archive.mjs";

test("Rolling files are retained as separate bound, immutable observations", async t => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "doubao-archive-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = join(root, "123/agents/main/system/trajectory.jsonl");await mkdir(join(root, "123/agents/main/system"), { recursive: true });
  const options = { outputRoot: join(root, "archive"), sourceRoot: root,
    discovery: { session: { trajectories: [{ path: source, agent_id: "main" }] } },
    journal: { attempt_id: "attempt", workspace: join(root, "workspace"), session: { conversation_id: "123" }, send: { dispatch_attempt_count: 1 } } };
  const first = '{"role":"user","content":"exact prompt"}\n';await writeFile(source, first);
  let index = await captureTrajectoryVersion(options);assert.equal(index.snapshots.length, 1);
  const original = join(options.outputRoot, index.snapshots[0].file);
  index = await captureTrajectoryVersion(options);assert.equal(index.snapshots.length, 1);
  await writeFile(source, first + '{"role":"assistant","content":"later"}\n');
  index = await captureTrajectoryVersion(options);assert.equal(index.snapshots.length, 2);
  assert.equal(await readFile(original, "utf8"), first);
  assert.ok(Date.parse(index.snapshots[1].captured_at) >= Date.parse(index.snapshots[0].captured_at));
  await assert.rejects(captureTrajectoryVersion({ ...options, journal: { ...options.journal, attempt_id: "other" } }), /IDENTITY_DRIFT/);
  await writeFile(source, '{"role":');assert.equal(await captureTrajectoryVersion(options), null);
});
