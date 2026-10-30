import assert from "node:assert/strict";
import test from "node:test";
import {mkdtemp, mkdir, writeFile, rm, realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

import {
  trustDialogMatchesProject,
  clickNewProjectControl,
  openProjectWithOfficialCli,
  confirmProjectTrust,
  waitForExactProjectTrust,
} from "../../tools/report/skills/general-e2e/orchestrate-general-e2e/drivers/codex-desktop/register-projects.mjs";
import { clickNewProjectControl as clickWebNewProjectControl } from "../../tools/report/skills/web-e2e/orchestrate-web-e2e/drivers/codex-desktop/register-projects.mjs";

test("General E2E folder trust requires the exact requested absolute path", () => {
  const project = "/tmp/general-score/tasks/task-one";
  const dialog = `Trust this folder?\n${project}\n\nTrust folder\nCancel`;
  assert.equal(trustDialogMatchesProject(dialog, project), true);
  assert.equal(trustDialogMatchesProject(dialog, "/tmp/general-score/tasks/task"), false);
});

test('官方CLI只按argv打开已绑定目录并记录可复核摘要', async () => {
  const root = await mkdtemp(join(tmpdir(),'general-native-cli-'));
  try {
    const app=join(root,'Codex App.app'),project=join(root,'score $literal (case)');
    const bin=join(app,'Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex');
    await mkdir(join(bin,'..'),{recursive:true}); await writeFile(bin,'fixture cli',{mode:0o700});await mkdir(project);
    const calls=[];
    const run=async (file,args,opts)=>{ calls.push({file,args});assert.ok(opts.timeout>0);
      return {stdout:args[1]==='--help'?'Usage: codex app [OPTIONS] [PATH]':'Opening workspace',stderr:''};};
    const proof=await openProjectWithOfficialCli({appPath:app,project,timeout:1000,platform:'darwin',run});
    assert.deepEqual(calls.map(c=>c.args),[['app','--help'],['app',await realpath(project)]]);
    assert.equal(proof.executable,await realpath(bin));assert.match(proof.executable_sha256,/^[a-f0-9]{64}$/u);
    assert.deepEqual(proof.argv,['app',await realpath(project)]);
    await assert.rejects(openProjectWithOfficialCli({appPath:app,project,timeout:1000,platform:'darwin',run:async()=>({stdout:'unsupported',stderr:''})}),/未证明支持/);
    assert.equal(await openProjectWithOfficialCli({appPath:app,project,timeout:1000,platform:'linux',run}),null);
  } finally {await rm(root,{recursive:true,force:true});}
});

test('自动信任只点击唯一完整匹配的目录弹窗，迟到弹窗可等待', async () => {
  const folder='/private/general/score-one';let clicks=0,round=0;
  const dialog=text=>({isVisible:async()=>true,innerText:async()=>text,
    getByRole:(_role,opts)=>{assert.ok(opts.name.test('Trust folder'));return {count:async()=>1,click:async()=>{clicks++;}};},
    waitFor:async opts=>assert.equal(opts.state,'hidden')});
  const page=rows=>({getByRole:role=>{assert.equal(role,'dialog');return {count:async()=>rows().length,nth:i=>rows()[i]};},waitForTimeout:async()=>{round++;}});
  await assert.rejects(confirmProjectTrust(page(()=>[dialog('Trust folder?\n/private/general/score-two')]),folder,1000),/未完整回显/);
  assert.equal(clicks,0);
  await assert.rejects(confirmProjectTrust(page(()=>[dialog(folder),dialog(folder)]),folder,1000),/唯一/);
  assert.equal(clicks,0);
  await waitForExactProjectTrust(page(()=>round<2?[]:[dialog('Trust folder?\n'+folder)]),folder,1000);
  assert.equal(clicks,1);assert.equal(round,2);
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
