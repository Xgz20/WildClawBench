import assert from "node:assert/strict";
import test from "node:test";

import {
  trustDialogMatchesProject,
} from "../../tools/report/skills/general-e2e/orchestrate-general-e2e/drivers/codex-desktop/register-projects.mjs";

test("General E2E folder trust requires the exact requested absolute path", () => {
  const project = "/tmp/general-score/tasks/task-one";
  const dialog = `Trust this folder?\n${project}\n\nTrust folder\nCancel`;
  assert.equal(trustDialogMatchesProject(dialog, project), true);
  assert.equal(trustDialogMatchesProject(dialog, "/tmp/general-score/tasks/task"), false);
});
