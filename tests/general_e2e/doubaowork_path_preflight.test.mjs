import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, writeFile, realpath, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { assessPathBudget, preflightDoubaoPaths } from "../../tools/report/e2e-shared/doubaowork/path-preflight.mjs";

test("Path budgets count UTF-8 bytes and the PATH_MAX terminating NUL", () => {
  assert.equal(assessPathBudget('/' + 'a'.repeat(255), { nameMax: 255, pathMax: 257 }).utf8_bytes, 256);
  assert.throws(() => assessPathBudget('/abc', { nameMax: 255, pathMax: 4 }), /PATH_MAX/);
  assert.throws(() => assessPathBudget('/' + 'a'.repeat(256), { nameMax: 255, pathMax: 1024 }), /NAME_MAX/);
  assert.throws(() => assessPathBudget('/中文 空格', { nameMax: 8, pathMax: 1024 }), /NAME_MAX/);
  for (const p of ['relative', '/bad\npath', '/bad\0path']) assert.throws(() => assessPathBudget(p, { nameMax: 255, pathMax: 1024 }), /UNSAFE/);
  assert.throws(() => assessPathBudget('/valid', { nameMax: 255, pathMax: Infinity }), /LIMIT_UNKNOWN/);
});

test("Preflight permits Chinese/spaces, checks future native paths and rejects symlinks before UI", async t => {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'doubao-path-')));
  t.after(() => rm(root, { recursive: true, force: true }));
  const workspace = join(root, '中文 空格'), promptFile = join(root, 'PROMPT.md'), nativeRoot = join(root, 'native');
  await mkdir(workspace); await mkdir(nativeRoot); await writeFile(promptFile, 'prompt');
  const config = { workspace, promptFile, nativeRoot, outputDir: join(root, 'control/not-created') };
  const options = { platform: 'darwin', readLimit: async name => name === 'NAME_MAX' ? 255 : 1024 };
  const result = await preflightDoubaoPaths(config, options);
  assert.equal(result.status, 'verified'); assert.equal(result.checks.length, 6);
  assert.ok(result.checks.some(c => c.role === 'native-session-path-reservation'));
  await symlink(workspace, join(root, 'alias'));
  await assert.rejects(preflightDoubaoPaths({ ...config, workspace: join(root, 'alias') }, options), /SYMLINK/);
  await assert.rejects(preflightDoubaoPaths({ ...config, outputDir: promptFile }, options), /CONTROL_ROOT/);
  await assert.rejects(preflightDoubaoPaths(config, { ...options, readLimit: async name => name === 'NAME_MAX' ? 255 : 200 }), /PATH_MAX/);
  await assert.rejects(preflightDoubaoPaths(config, { ...options, platform: 'win32' }), /MACOS/);
});
