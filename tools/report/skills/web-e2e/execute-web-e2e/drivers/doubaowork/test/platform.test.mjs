import assert from "node:assert/strict";
import { mkdtemp, mkdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  defaultNativeRoots,
  discoverNativeSources,
  parseLsofRecords,
} from "../platform.mjs";

test("解析 lsof 字段记录并保留监听进程身份", () => {
  const records = parseLsofRecords("p3505\ncDoubaoWork Browser\nn127.0.0.1:9260\n");
  assert.deepEqual(records, [{ pid: 3505, command_name: "DoubaoWork Browser", address: "127.0.0.1:9260" }]);
});

test("原生 source discovery 只匹配显式 session 和普通 trajectory 文件", async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-native-"));
  context.after(async () => {
    const { rm } = await import("node:fs/promises");
    await rm(root, { recursive: true, force: true });
  });
  const roots = defaultNativeRoots(root);
  const trajectory = join(roots.sessions_root, "12345678901234567", "agents", "agent_fixture", "system", "trajectory.jsonl");
  await mkdir(join(trajectory, ".."), { recursive: true });
  await writeFile(trajectory, "{\"role\":\"user\",\"content\":\"fixture\"}\n");
  const escaped = join(root, "escaped.jsonl");
  await writeFile(escaped, "{}\n");
  await mkdir(join(roots.sessions_root, "12345678901234567", "agents", "agent_link", "system"), { recursive: true });
  await symlink(escaped, join(roots.sessions_root, "12345678901234567", "agents", "agent_link", "system", "trajectory.jsonl"));
  await mkdir(join(roots.logs_root, "agent_infra"), { recursive: true });
  await writeFile(join(roots.logs_root, "agent_infra", "agent_infra_fixture.log"), "fixture\n");

  const discovery = await discoverNativeSources({
    userHome: root,
    sessionId: "12345678901234567",
    roots,
  });
  assert.equal(discovery.session.directory_id, "12345678901234567");
  assert.equal(discovery.session.trajectories.length, 1);
  assert.equal(discovery.session.trajectories[0].agent_id, "agent_fixture");
  assert.equal(discovery.session.native_cwd, null);
  assert.equal(discovery.logs.length, 1);
  assert.equal(discovery.logs[0].task_binding, "unbound");
});

