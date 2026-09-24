import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdir, readFile, realpath, rename, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { defaultNativeRoots, discoverNativeSources } from "./platform.mjs";

const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function save(path, value) {
  const temp = `${path}.tmp-${randomUUID()}`;
  await writeFile(temp, JSON.stringify(value, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  await rename(temp, path);
}

// Snapshot only a journal-bound session. Each observation records when these
// exact bytes were already present; it does not invent an event timestamp.
export async function captureTrajectoryVersion({ outputRoot, journal, discovery, sourceRoot = defaultNativeRoots().sessions_root }) {
  if (!journal.session?.conversation_id || journal.send?.dispatch_attempt_count !== 1) return null;
  const sessionId = journal.session.conversation_id;
  discovery ??= await discoverNativeSources({ sessionId });
  const sources = discovery.session?.trajectories;
  if (!Array.isArray(sources)) throw new Error("DOUBAOWORK_TRAJECTORY_DISCOVERY_INVALID");
  if (!sources.length) return null;
  if (sources.length !== 1) throw new Error("DOUBAOWORK_ARCHIVE_AGENT_AMBIGUOUS");
  const source = sources[0].path;
  if (!source || !resolve(source).startsWith(`${resolve(sourceRoot)}/${sessionId}/`) || await realpath(source) !== resolve(source)) throw new Error("DOUBAOWORK_ARCHIVE_SOURCE_UNSAFE");
  const before = await lstat(source, { bigint: true });
  if (!before.isFile() || before.isSymbolicLink() || before.size > 16n * 1024n * 1024n) throw new Error("DOUBAOWORK_ARCHIVE_SOURCE_INVALID");
  const bytes = await readFile(source), after = await lstat(source, { bigint: true });
  if (before.ino !== after.ino || before.size !== after.size || before.mtimeNs !== after.mtimeNs) return null;
  const text = bytes.toString("utf8");
  if (!text.endsWith("\n")) return null;
  try { for (const line of text.trimEnd().split(/\r?\n/u)) if (line.trim()) JSON.parse(line); } catch { return null; }
  const capturedAt = new Date().toISOString(), digest = sha(bytes);
  const identity = { attempt_id: journal.attempt_id, conversation_id: sessionId, workspace: journal.workspace };
  await mkdir(outputRoot, { recursive: true });
  if (await realpath(outputRoot) !== resolve(outputRoot)) throw new Error("DOUBAOWORK_ARCHIVE_OUTPUT_UNSAFE");
  const indexPath = join(outputRoot, "index.json");
  let index;
  try {
    const st = await lstat(indexPath); if (!st.isFile() || st.isSymbolicLink()) throw new Error("DOUBAOWORK_ARCHIVE_INDEX_UNSAFE");
    index = JSON.parse(await readFile(indexPath, "utf8"));
    if (JSON.stringify(index.identity) !== JSON.stringify(identity)) throw new Error("DOUBAOWORK_ARCHIVE_IDENTITY_DRIFT");
  } catch (e) {
    if (e.code !== "ENOENT") throw e;
    index = { schema: "wildclawbench.doubaowork-trajectory-observations/v1", identity, clock: "same-host-wall-clock-observation-upper-bound", snapshots: [] };
  }
  if (index.snapshots.some(s => s.sha256 === digest)) return index;
  if (index.snapshots.length >= 256 || index.snapshots.reduce((sum, s) => sum + s.size, bytes.length) > 128 * 1024 * 1024) throw new Error("DOUBAOWORK_ARCHIVE_CAPACITY_EXCEEDED");
  const name = `${String(index.snapshots.length).padStart(4, "0")}-${digest}.jsonl`;
  await writeFile(join(outputRoot, name), bytes, { flag: "wx", mode: 0o600 });
  index.snapshots.push({ file: name, sha256: digest, size: bytes.length, captured_at: capturedAt,
    native_source: source, agent_id: sources[0].agent_id, device: String(after.dev), inode: String(after.ino), mtime_ns: String(after.mtimeNs) });
  await save(indexPath, index);
  return index;
}

export function startTrajectoryArchivePump({ journals, intervalMs = 200, onError }) {
  let stopped = false;
  const work = (async () => {
    while (!stopped) {
      let inputs;
      try { inputs = await journals(); }
      catch (error) { await onError({ message: error.message, at: new Date().toISOString() }); break; }
      for (const { outputRoot, journal } of inputs) {
        try { await captureTrajectoryVersion({ outputRoot, journal }); }
        catch (error) { if (error.code !== "ENOENT") await onError({ outputRoot, attempt_id: journal.attempt_id, message: error.message, at: new Date().toISOString() }); }
      }
      if (!stopped) await sleep(intervalMs);
    }
  })();
  return async () => { stopped = true; await work; };
}
