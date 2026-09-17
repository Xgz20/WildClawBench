import { lstat } from "node:fs/promises";
import { homedir } from "node:os";
import { join, relative } from "node:path";
import { empty, parseAstron, parseWorkBuddy, parseQwen } from "./parsers.mjs";
import { inspectQwenRuntime } from "./qwen-profile.mjs";
import {
  DEFAULT_MAX_TRACE_BYTES,
  assertTraceWorkspace,
  astronSessionRoots,
  findAstronTrace,
  findTraceFiles,
  isSafeNativeId,
  readTrace,
  sameNativePath,
} from "../../vendor/e2e-shared/resource-metrics/trace-io.mjs";

export { astronSessionRoots, findAstronTrace, readTrace };

export async function collectLocalMetrics(input) {
  const { harness, state, workspace, sessionDb, home = homedir() } = input;
  const session = state.session || {};
  let result, sources = [], sessionId;
  if (harness === "astronstudio") {
    const thread = session.conversation_id, turn = session.turn_id;
    if (!isSafeNativeId(thread) || !isSafeNativeId(turn)) throw new Error("MISSING_STABLE_SESSION");
    const { queryResourceIdentity } = await import("../astronstudio/lib.mjs");
    const identity = await queryResourceIdentity(sessionDb, thread, turn);
    sessionId = identity.nativeId;
    if (!isSafeNativeId(sessionId) || !sameNativePath(identity.cwd, workspace)) throw new Error("SESSION_IDENTITY_MISMATCH");
    const { file, root } = await findAstronTrace(home, sessionDb, sessionId);
    const trace = await readTrace(file, root);
    assertTraceWorkspace(trace.rows.filter(r => r.type === "session_meta"), workspace, r => r.payload?.cwd);
    result = parseAstron(trace.rows, turn);
    sources = [trace.source];
  } else if (harness === "workbuddy") {
    sessionId = session.conversation_id || session.dom_conversation_id;
    if (!isSafeNativeId(sessionId)) throw new Error("MISSING_STABLE_SESSION");
    const root = join(home, ".workbuddy", "projects");
    const files = await findTraceFiles(root, 1, name => name === `${sessionId}.jsonl`);
    if (files.length !== 1) throw new Error("AMBIGUOUS_TRACE");
    const trace = await readTrace(files[0], root);
    assertTraceWorkspace(trace.rows, workspace, r => r.cwd);
    if (trace.rows.some(r => r.sessionId && r.sessionId !== sessionId)) throw new Error("SESSION_IDENTITY_MISMATCH");
    result = parseWorkBuddy(trace.rows); sources = [trace.source];
  } else if (harness === "qwenwork") {
    sessionId = session.session_id;
    if (!isSafeNativeId(sessionId)) throw new Error("MISSING_STABLE_SESSION");
    const root = join(home, ".qwenworkcn");
    const transcripts = await findTraceFiles(join(root, "projects"), 1, name => name === `${sessionId}.jsonl`);
    if (transcripts.length !== 1) throw new Error("AMBIGUOUS_TRACE");
    const transcript = await readTrace(transcripts[0], root);
    assertTraceWorkspace(transcript.rows, workspace, r => r.cwd);
    if (transcript.rows.some(r => r.sessionId && r.sessionId !== sessionId)) throw new Error("SESSION_IDENTITY_MISMATCH");
    // 项目目录由已校验的原生会话反查，不遍历其他题目的日志内容。
    const project = relative(join(root, "projects"), transcripts[0]).split(/[\\/]/u)[0];
    const segments = await findTraceFiles(join(root, "logs", "sessions", project, sessionId, "segments"), 0, n => n.endsWith(".jsonl"));
    if (!segments.length || segments.length > 100) throw new Error("INVALID_SEGMENT_COUNT");
    const traces = []; let totalBytes = 0;
    for (const file of segments.sort()) {
      totalBytes += (await lstat(file)).size;
      if (totalBytes > 2 * DEFAULT_MAX_TRACE_BYTES) throw new Error("TOTAL_TRACE_SIZE_LIMIT");
      traces.push(await readTrace(file, root));
    }
    const runtimeIdentity = await inspectQwenRuntime(input.appPath || state.client?.app_path, state.client?.version, transcript.rows);
    result = parseQwen(traces.flatMap(t => t.rows), { runtimeIdentity });
    sources = [transcript.source, ...traces.map(t => t.source)];
  } else return empty("UNSUPPORTED_HARNESS");
  result.collection.sources = sources;
  result.collection.collected_at = new Date().toISOString();
  result.collection.session_id = sessionId;
  result.collection.attempt_id = state.attempt_id;
  return result;
}
