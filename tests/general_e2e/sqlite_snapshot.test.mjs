import assert from "node:assert/strict";
import { copyFile, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { copySnapshotFile, configureSnapshotReader } from "../../tools/report/e2e-shared/sqlite-snapshot/index.mjs";

async function fixture(run) {
  const root = await mkdtemp(join(tmpdir(), "wcb-snapshot-test-"));
  try {
    const source = join(root, "source");
    const target = join(root, "snapshot");
    await writeFile(source, "frozen database bytes");
    await run({ root, source, target });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

test("native clone publishes an independent, exact snapshot", async () => fixture(async ({ root, source, target }) => {
  const result = await copySnapshotFile(source, target, { platform: "darwin", clone: copyFile });
  assert.equal(result.method, "macos-apfs-clone");
  await writeFile(source, "later live database bytes");
  assert.equal(await readFile(target, "utf8"), "frozen database bytes");
  assert.deepEqual((await readdir(root)).sort(), ["snapshot", "source"]);
}));

test("partial native clone failure leaves no staging bytes in fallback", async () => fixture(async ({ root, source, target }) => {
  const result = await copySnapshotFile(source, target, {
    platform: "darwin",
    clone: async (_input, output) => {
      await writeFile(output, "partial bytes");
      throw Object.assign(new Error("unsupported filesystem"), { code: "ENOTSUP" });
    },
  });
  assert.equal(result.method, "node-copyfile-ficlone-fallback");
  assert.equal(await readFile(target, "utf8"), await readFile(source, "utf8"));
  assert.deepEqual((await readdir(root)).sort(), ["snapshot", "source"]);
}));

test("native clone cannot overwrite a preexisting snapshot", async () => fixture(async ({ root, source, target }) => {
  await writeFile(target, "existing evidence");
  await assert.rejects(copySnapshotFile(source, target, { platform: "darwin", clone: copyFile }), { code: "EEXIST" });
  assert.equal(await readFile(target, "utf8"), "existing evidence");
  assert.deepEqual((await readdir(root)).sort(), ["snapshot", "source"]);
}));

test("snapshot appearing during cloning is preserved", async () => fixture(async ({ source, target }) => {
  await assert.rejects(copySnapshotFile(source, target, {
    platform: "darwin",
    clone: async (input, output) => {
      await copyFile(input, output);
      await writeFile(target, "concurrent evidence");
    },
  }), { code: "EEXIST" });
  assert.equal(await readFile(target, "utf8"), "concurrent evidence");
}));

test("other platforms do not invoke macOS commands", async () => fixture(async ({ source, target }) => {
  const result = await copySnapshotFile(source, target, { platform: "linux", clone: () => assert.fail("unexpected native command") });
  assert.equal(result.method, "node-copyfile-ficlone-fallback");
  assert.equal(await readFile(target, "utf8"), "frozen database bytes");
}));

test("fallback cannot overwrite a preexisting snapshot", async () => fixture(async ({ source, target }) => {
  await writeFile(target, "existing evidence");
  await assert.rejects(copySnapshotFile(source, target, { platform: "linux" }), { code: "EEXIST" });
  assert.equal(await readFile(target, "utf8"), "existing evidence");
}));

test("missing WAL preserves ENOENT without manufacturing a file", async () => fixture(async ({ root, target }) => {
  await assert.rejects(copySnapshotFile(join(root, "missing-wal"), target, { platform: "darwin", clone: copyFile }), { code: "ENOENT" });
  assert.deepEqual(await readdir(root), ["source"]);
}));

test("real macOS APFS snapshot survives subsequent source writes", { skip: process.platform !== "darwin" }, async () => fixture(async ({ source, target }) => {
  const result = await copySnapshotFile(source, target);
  assert.equal(result.method, "macos-apfs-clone");
  await writeFile(source, "new bytes");
  assert.equal(await readFile(target, "utf8"), "frozen database bytes");
}));

test("reader tuning preserves complete integrity checks and read-only enforcement", async () => fixture(async ({ source, target }) => {
  const { DatabaseSync } = await import("node:sqlite");
  await rm(source);
  const writer = new DatabaseSync(source);
  writer.exec("CREATE TABLE values_table(value TEXT); INSERT INTO values_table VALUES ('evidence');");
  writer.close();
  await copySnapshotFile(source, target);
  const reader = new DatabaseSync(target, { readOnly: true });
  try {
    configureSnapshotReader(reader);
    assert.equal(reader.prepare("PRAGMA quick_check;").get().quick_check, "ok");
    assert.equal(reader.prepare("SELECT value FROM values_table;").get().value, "evidence");
    assert.throws(() => reader.exec("INSERT INTO values_table VALUES ('mutation');"), /readonly/iu);
  } finally {
    reader.close();
  }
}));
