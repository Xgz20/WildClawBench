import assert from "node:assert/strict";
import test from "node:test";
import {ensureProjectVisible} from "../../tools/report/e2e-shared/doubaowork/controller.mjs";

test("prepared projects can be found across sidebar pages without dispatching a prompt",async()=>{
  let clicks=0;
  const title={count:async()=>clicks>=2?1:0};
  const grouped={count:async()=>1,getByTitle:()=>title,locator:()=>({count:async()=>clicks+1}),
    getByRole:()=>({count:async()=>1,isVisible:async()=>true,click:async()=>{clicks++;}})};
  const page={getByTestId:()=>grouped,waitForTimeout:async()=>{}};
  assert.equal(await ensureProjectVisible(page,"exact-project"),title);assert.equal(clicks,2);
  title.count=async()=>2;
  await assert.rejects(()=>ensureProjectVisible(page,"exact-project"),/PROJECT_NOT_UNIQUE/);
  assert.equal(clicks,2);
});
