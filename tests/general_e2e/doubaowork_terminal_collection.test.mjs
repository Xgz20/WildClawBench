import assert from "node:assert/strict";
import { test } from "node:test";
import { verifyTrajectoryPrompt } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/doubaowork/collector.mjs";
import { summarizePromptReadback } from "../../tools/report/e2e-shared/doubaowork/lib.mjs";

test("Only independently verified non-success may retain an empty native trajectory", () => {
  const hash = summarizePromptReadback("original prompt").sha256;
  for (const sourceBytes of [null, Buffer.alloc(0), Buffer.from(" \n")]) {
    assert.equal(verifyTrajectoryPrompt([], hash, { sourceBytes, nonSuccessVerified: true }).status, "unavailable");
    assert.throws(() => verifyTrajectoryPrompt([], hash, { sourceBytes }), /TRAJECTORY_PROMPT_MISMATCH/);
  }
  assert.throws(() => verifyTrajectoryPrompt([], hash, { sourceBytes: Buffer.from("unparsed nonempty content"), nonSuccessVerified: true }), /TRAJECTORY_PROMPT_MISMATCH/);
  assert.throws(() => verifyTrajectoryPrompt([{ kind: "tool_result" }], hash, { sourceBytes: Buffer.alloc(0), nonSuccessVerified: true }), /TRAJECTORY_PROMPT_MISMATCH/);
  assert.throws(() => verifyTrajectoryPrompt([{ kind: "user_message", content: "foreign prompt" }], hash,
    { sourceBytes: Buffer.from("foreign prompt"), nonSuccessVerified: true }), /TRAJECTORY_PROMPT_MISMATCH/);
  assert.equal(verifyTrajectoryPrompt([{ kind: "user_message", content: "original prompt\n" }], hash,
    { sourceBytes: Buffer.from("original prompt") }).status, "verified");
});
