import assert from "node:assert/strict";
import test from "node:test";

import {
  trustDialogMatchesProject,
  clickNewProjectControl,
} from "../../tools/report/skills/general-e2e/orchestrate-general-e2e/drivers/codex-desktop/register-projects.mjs";
import { clickNewProjectControl as clickWebNewProjectControl } from "../../tools/report/skills/web-e2e/orchestrate-web-e2e/drivers/codex-desktop/register-projects.mjs";

test("General E2E folder trust requires the exact requested absolute path", () => {
  const project = "/tmp/general-score/tasks/task-one";
  const dialog = `Trust this folder?\n${project}\n\nTrust folder\nCancel`;
  assert.equal(trustDialogMatchesProject(dialog, project), true);
  assert.equal(trustDialogMatchesProject(dialog, "/tmp/general-score/tasks/task"), false);
});

for (const [scene, click] of [['General', clickNewProjectControl], ['Web', clickWebNewProjectControl]]) {
  test(`${scene} reveals the uniquely bound hover-only project control and refuses ambiguous headers`, async () => {
    const calls = [];
    const button = { click: async options => { assert.equal(options.force, undefined); calls.push('click'); } };
    const page = count => ({ locator: selector => {
      assert.equal(selector, '[class~="group/nav-section-title"]');
      return { filter: options => { assert.equal(options.has, button); return { count: async () => count, hover: async () => calls.push('hover') }; } };
    } });
    await click(page(1), button, 1000);
    assert.deepEqual(calls, ['hover', 'click']);
    calls.length = 0;
    await assert.rejects(click(page(2), button, 1000), /不唯一/);
    assert.deepEqual(calls, []);
    await click(page(0), button, 1000);
    assert.deepEqual(calls, ['click']);
  });
}
