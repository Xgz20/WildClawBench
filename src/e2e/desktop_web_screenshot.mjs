import { createHash } from "node:crypto";
import { lstat, readFile, realpath, writeFile } from "node:fs/promises";
import path from "node:path";
import { receiverStatus, startReceiver } from "./score-web-e2e/scripts/screenshot_receiver.mjs";

const [filename, expectedSha256] = process.argv.slice(2);
if (!/^native-[a-z0-9]+(?:-[a-z0-9]+)*\.png$/.test(filename ?? "") || filename.length > 104 ||
    (expectedSha256 !== undefined && !/^[a-f0-9]{64}$/.test(expectedSha256))) {
  throw new Error("需要原生截图文件名，若工具提供 sha256 请一并传入");
}
const work = await realpath(process.cwd());
const privateDir = path.join(work, "private-scoring");
const capture = path.join(privateDir, "browser-captures", filename);
const evidence = path.join(privateDir, "evidence", filename);
const receipt = evidence + ".receipt.json";
const info = await lstat(capture);
const maxBytes = 8 * 1024 * 1024;
if (!info.isFile() || info.size > maxBytes || await realpath(capture) !== capture) {
  throw new Error("原生截图文件位置或大小无效");
}
const sha256 = (data) => createHash("sha256").update(data).digest("hex");
const bytes = await readFile(capture);
const captureSha256 = sha256(bytes);
if (expectedSha256 && captureSha256 !== expectedSha256) throw new Error("原生截图摘要不匹配");

let output;
try {
  const previous = JSON.parse(await readFile(receipt, "utf8"));
  if (previous.sha256 !== captureSha256 || sha256(await readFile(evidence)) !== captureSha256) {
    throw new Error("已回传截图发生漂移");
  }
  output = previous;
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
if (!output) {
  // 接收完成后进程中断时，复用接收器已落盘的同一份回执。
  const previous = receiverStatus(work).state;
  if (previous.status === "COMPLETED" && previous.output?.path === `private-scoring/evidence/${filename}`) {
    output = previous.output;
    if (sha256(await readFile(evidence)) !== captureSha256) throw new Error("已回传截图发生漂移");
  } else {
    const { state } = await startReceiver(work, { filename, maxBytes: String(maxBytes) });
    const url = new URL(state.upload_url);
    if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" ||
        url.port !== String(state.port) || !/^\/screenshot\/[a-f0-9]{48}$/.test(url.pathname)) {
      throw new Error("截图接收器地址无效");
    }
    const response = await fetch(url, {
      method: "POST", headers: { "Content-Type": "image/png" }, body: bytes,
      redirect: "error", signal: AbortSignal.timeout(30_000),
    });
    if (response.status !== 201) throw new Error(`截图接收失败 (HTTP ${response.status})`);
    output = await response.json();
  }
  if (output.sha256 !== captureSha256 || output.bytes !== bytes.length) {
    throw new Error("截图接收摘要不匹配");
  }
  await writeFile(receipt, JSON.stringify(output) + "\n", { flag: "wx", mode: 0o600 });
}
console.log(JSON.stringify({ path: evidence, evidence: `evidence/${filename}`, sha256: captureSha256,
  viewport: { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) } }));
