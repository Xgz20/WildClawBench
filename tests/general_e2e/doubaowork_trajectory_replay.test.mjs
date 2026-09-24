import assert from "node:assert/strict";
import { test } from "node:test";
import { deduplicateTrajectoryEvents } from "../../tools/report/e2e-shared/doubaowork/native-evidence.mjs";

test("Identical remote calculator replays are deduplicated with both raw locations retained", () => {
  const call = { kind: "assistant_tool_call", role: "assistant", agent_id: "main", call_id: "calc", tool_name: "calculator", arguments: { inputs: ["10+20"] }, source: { line: 2 } };
  const result = { kind: "tool_result", role: "tool", agent_id: "main", call_id: "calc", content: "30", outcome: "unknown", source: { line: 3 } };
  const r = deduplicateTrajectoryEvents([call, result, { ...call, source: { line: 4 } }, { ...result, source: { line: 5 } }]);
  assert.equal(r.events.length, 2); assert.equal(r.raw_event_count, 4); assert.equal(r.duplicates.length, 2);
  assert.deepEqual(r.duplicates[0].kept, { line: 2 }); assert.deepEqual(r.duplicates[0].duplicate, { line: 4 });
  assert.throws(() => deduplicateTrajectoryEvents([call, { ...call, arguments: { inputs: ["20+20"] } }]), /REPLAY_CONFLICT/);
  assert.throws(() => deduplicateTrajectoryEvents([result, { ...result, content: "40" }]), /REPLAY_CONFLICT/);
});
