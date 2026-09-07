import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:net";
import test from "node:test";

import {
  SCREENSHOT_RECEIVER_SCHEMA,
  receiverStatus,
  startReceiver,
  stopReceiver,
} from "../tools/report/skills/score-web-e2e/scripts/screenshot_receiver.mjs";
import {
  CANDIDATE_ARTIFACT_SCHEMA,
  TREE_HASH_ALGORITHM,
  snapshotWorkspace,
} from "../tools/report/skills/score-web-e2e/scripts/workspace-integrity.mjs";

const PNG_1X1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);
const JPEG_SIGNATURE_SAMPLE = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0xff, 0xd9]);

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

async function writeJson(filename, value) {
  await writeFile(filename, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
}

async function fixture() {
  const packageRoot = await mkdtemp(join(tmpdir(), "score-web-e2e-screenshot-"));
  const taskRoot = join(packageRoot, "score", "tasks", "task-1");
  const workspace = join(taskRoot, "workspace");
  const privateRoot = join(taskRoot, "private-scoring");
  await mkdir(workspace, { recursive: true });
  await mkdir(privateRoot, { recursive: true });
  await writeFile(join(workspace, "index.html"), "<main>frozen</main>\n", "utf8");
  const frozen = snapshotWorkspace(workspace).sha256;
  await writeJson(join(privateRoot, "candidate_artifact.json"), {
    schema_version: CANDIDATE_ARTIFACT_SCHEMA,
    hash_algorithm: TREE_HASH_ALGORITHM,
    batch_id: "batch-1",
    task_id: "task-1",
    harness_id: "workbuddy",
    model: { id: "xopglm52", display_name: "xopglm52" },
    expected_sha256: frozen,
  });
  await writeFile(join(taskRoot, ".web-e2e-scoring-ready"), "batch-1\ntask-1\n", "utf8");
  return { packageRoot, taskRoot, workspace };
}

async function waitForTerminal(taskRoot, expectedStatus, timeoutMs = 3_000) {
  const deadline = Date.now() + timeoutMs;
  let result;
  do {
    result = receiverStatus(taskRoot);
    if (result.state.status === expectedStatus && !result.process) return result;
    await sleep(25);
  } while (Date.now() < deadline);
  assert.fail(`receiver did not reach ${expectedStatus}: ${JSON.stringify(result?.state)}`);
}

test("receiver saves one PNG under private-scoring/evidence and exits", async () => {
  const { packageRoot, taskRoot, workspace } = await fixture();
  const candidateBefore = await readFile(join(workspace, "index.html"));
  try {
    const started = await startReceiver(taskRoot, {
      filename: "desktop-main.png",
      port: "0",
      timeoutMs: "3000",
      maxBytes: "1024",
    });
    assert.equal(started.state.schema_version, SCREENSHOT_RECEIVER_SCHEMA);
    assert.equal(started.state.status, "RUNNING");
    const upload = new URL(started.state.upload_url);
    assert.equal(upload.hostname, "127.0.0.1");

    const response = await fetch(upload, {
      method: "POST",
      headers: { "content-type": "image/png" },
      body: PNG_1X1,
    });
    assert.equal(response.status, 201, await response.text());
    const terminal = await waitForTerminal(taskRoot, "COMPLETED");
    assert.equal(terminal.state.output.path, "private-scoring/evidence/desktop-main.png");
    assert.equal(terminal.state.output.bytes, PNG_1X1.length);
    assert.deepEqual(await readFile(join(taskRoot, terminal.state.output.path)), PNG_1X1);
    assert.deepEqual(await readFile(join(workspace, "index.html")), candidateBefore);
  } finally {
    await stopReceiver(taskRoot).catch(() => {});
    await rm(packageRoot, { recursive: true, force: true });
  }
});

test("receiver enforces MIME, extension, signature and byte limit before accepting JPEG", async () => {
  const { packageRoot, taskRoot } = await fixture();
  try {
    const started = await startReceiver(taskRoot, {
      filename: "interaction.jpg",
      port: "0",
      timeoutMs: "3000",
      maxBytes: "100",
    });
    const wrongMime = await fetch(started.state.upload_url, {
      method: "POST",
      headers: { "content-type": "image/png" },
      body: JPEG_SIGNATURE_SAMPLE,
    });
    assert.equal(wrongMime.status, 415);
    const wrongSignature = await fetch(started.state.upload_url, {
      method: "POST",
      headers: { "content-type": "image/jpeg" },
      body: PNG_1X1,
    });
    assert.equal(wrongSignature.status, 415);
    const tooLarge = await fetch(started.state.upload_url, {
      method: "POST",
      headers: { "content-type": "image/jpeg" },
      body: Buffer.alloc(101, 0xff),
    });
    assert.equal(tooLarge.status, 413);

    const accepted = await fetch(started.state.upload_url, {
      method: "POST",
      headers: { "content-type": "image/jpeg" },
      body: JPEG_SIGNATURE_SAMPLE,
    });
    assert.equal(accepted.status, 201, await accepted.text());
    await waitForTerminal(taskRoot, "COMPLETED");
    await assert.rejects(
      () => startReceiver(taskRoot, { filename: "interaction.jpg" }),
      /拒绝覆盖/,
    );
  } finally {
    await stopReceiver(taskRoot).catch(() => {});
    await rm(packageRoot, { recursive: true, force: true });
  }
});

test("receiver rejects output path escape before creating a process", async () => {
  const { packageRoot, taskRoot } = await fixture();
  try {
    await assert.rejects(
      () => startReceiver(taskRoot, { filename: "../outside.png" }),
      /不能包含目录/,
    );
    await assert.rejects(
      () => startReceiver(taskRoot, { filename: "/tmp/outside.jpg" }),
      /不能包含目录/,
    );
    assert.equal(receiverStatus(taskRoot).state.status, "NOT_STARTED");
  } finally {
    await rm(packageRoot, { recursive: true, force: true });
  }
});

test("receiver has a bounded timeout and stop uses the recorded process identity", async () => {
  const { packageRoot, taskRoot } = await fixture();
  try {
    await startReceiver(taskRoot, {
      filename: "timeout.png",
      port: "0",
      timeoutMs: "800",
      maxBytes: "1024",
    });
    await waitForTerminal(taskRoot, "TIMED_OUT");

    const started = await startReceiver(taskRoot, {
      filename: "stopped.png",
      port: "0",
      timeoutMs: "3000",
      maxBytes: "1024",
    });
    const stopped = await stopReceiver(taskRoot);
    assert.equal(stopped.state.status, "STOPPED");
    assert.equal(stopped.state.cleanup.pid, started.state.pid);
    assert.equal(stopped.state.cleanup.exact_identity_verified, true);
    assert.equal(receiverStatus(taskRoot).process, null);
  } finally {
    await stopReceiver(taskRoot).catch(() => {});
    await rm(packageRoot, { recursive: true, force: true });
  }
});

test("receiver port conflict fails without leaving a managed process", async () => {
  const { packageRoot, taskRoot } = await fixture();
  const blocker = createServer();
  await new Promise((resolvePromise, rejectPromise) => {
    blocker.once("listening", resolvePromise);
    blocker.once("error", rejectPromise);
    blocker.listen(0, "127.0.0.1");
  });
  const address = blocker.address();
  assert.ok(address && typeof address !== "string");
  try {
    await assert.rejects(
      () => startReceiver(taskRoot, {
        filename: "blocked.png",
        port: String(address.port),
        timeoutMs: "3000",
        maxBytes: "1024",
      }),
      /启动失败|EADDRINUSE/,
    );
    const status = receiverStatus(taskRoot);
    assert.equal(status.state.status, "FAILED");
    assert.equal(status.process, null);
    assert.equal(status.state.upload_url, null);
  } finally {
    await stopReceiver(taskRoot).catch(() => {});
    await new Promise((resolvePromise) => blocker.close(resolvePromise));
    await rm(packageRoot, { recursive: true, force: true });
  }
});
