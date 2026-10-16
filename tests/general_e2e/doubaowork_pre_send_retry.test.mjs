import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import vm from "node:vm";
import { assertPreSendRetryEligible } from "../../tools/report/e2e-shared/doubaowork/controller.mjs";
import { createAttemptState, transitionAttempt } from "../../tools/report/e2e-shared/doubaowork/state.mjs";

test("a failed pre-send reconnect preserves the active journal and idempotent archive", async t => {
  const root = await mkdtemp(join(tmpdir(), "doubao-zero-send-retry-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = await readFile(new URL("../../tools/report/e2e-shared/doubaowork/controller.mjs", import.meta.url), "utf8");
  const STATE_FILE = /const STATE_FILE = "([^"]+)"/.exec(source)[1];
  const previous = createAttemptState({ attemptId: "fixture", batchId: "batch", taskId: "task", workspace: join(root, "workspace"),
    promptFile: join(root, "prompt.md"), prompt: "fixture" });
  previous.scene = "general"; previous.client.project_name = "fixture"; previous.client.manifest_sha256 = "a".repeat(64);
  transitionAttempt(previous, "CLIENT_READY"); transitionAttempt(previous, "INFRA_FAILED");
  previous.error = { code: "DEVELOPMENT_PRE_SEND_FAILED" };
  assertPreSendRetryEligible(previous);
  const stateFile = join(root, STATE_FILE), bytes = Buffer.from(JSON.stringify(previous));
  await writeFile(stateFile, bytes);
  // Execute the production function bodies; only connection and lock adapters
  // are replaced. This fixture never connects to a client or dispatches a task.
  const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end));
  const release = async () => {}; release.owner = {};
  const context = vm.createContext({ isAbsolute, resolve, dirname, join, STATE_FILE, readFile, writeFile, mkdir, rm,
    acquireExclusiveWorkerLock: async () => release,
    readAttemptState: async path => JSON.parse(await readFile(path)), assertPreSendRetryEligible,
    preflightDoubaoPaths: async () => ({}), releaseUnsentObserver: async () => {},
    connectClient: async () => { throw new Error("fixture connection failed"); },
  });
  vm.runInContext(section("async function archiveAttemptState(", "async function dispatchFromSelectedProject(")
    + section("async function markFailure(", "export function assertPreSendRetryEligible(")
    + section("async function retryPreSendDevelopmentRunUnlocked(", "async function navigateToConversation("), context);
  const options = { outputDir: root, scene: "general", validateTask: async () => ({ batchId: "batch", taskId: "task",
    workspace: previous.workspace, promptFile: previous.prompt.file, promptSha256: previous.prompt.sha256, manifestSha256: previous.client.manifest_sha256 }) };
  for (let attempt = 0; attempt < 2; attempt++) {
    await assert.rejects(context.retryPreSendDevelopmentRunUnlocked(options), /fixture connection failed/);
    assert.deepEqual(await readFile(stateFile), bytes);
    await access(join(root, ".attempts", previous.attempt_id, STATE_FILE));
  }
});

for(const confirmed of [false,true])for(const prepareOnly of [true,false])test(`zero-send recovery preserves prepare-only=${prepareOnly}, existing-project=${confirmed}`,async t=>{
  const root=await mkdtemp(join(tmpdir(),'doubao-prepare-retry-'));t.after(()=>rm(root,{recursive:true,force:true}));
  const source=await readFile(new URL('../../tools/report/e2e-shared/doubaowork/controller.mjs',import.meta.url),'utf8');
  const previous=createAttemptState({attemptId:'before',batchId:'batch',taskId:'task',workspace:join(root,'workspace'),promptFile:join(root,'prompt.md'),prompt:'placeholder never sent during preparation'});
  previous.scene='general';previous.client.project_name='owned-project';previous.client.manifest_sha256='a'.repeat(64);
  transitionAttempt(previous,'CLIENT_READY');transitionAttempt(previous,'INFRA_FAILED');previous.error={code:'DEVELOPMENT_PRE_SEND_FAILED'};
  const projectHash='b'.repeat(64);
  if(confirmed){previous.workspace_selection.confirmed=true;previous.workspace_selection.actual_path=previous.workspace;previous.workspace_selection.display_value=previous.workspace;previous.client.project_id_sha256=projectHash;}
  let dispatches=0,archived=0,last;
  const release=async()=>{};release.owner={};
  const client={app:{version:'fixture',app_path:'/Applications/DoubaoWork.app'},endpoint:'http://127.0.0.1:9260',listener:{listeners:[{pid:1}]},page:{},browser:{close:async()=>{}}};
  const context=vm.createContext({isAbsolute,resolve,dirname,join,STATE_FILE:'automation_state.json',Date,randomUUID:()=> 'new-attempt',
    acquireExclusiveWorkerLock:async()=>release,readAttemptState:async()=>JSON.parse(JSON.stringify(previous)),assertPreSendRetryEligible,
    preflightDoubaoPaths:async()=>({}),archiveAttemptState:async()=>{archived++},connectClient:async()=>client,
    assertExecutionActivityAllowed:async()=>{},inspectPage:async()=>({snapshot:{visible_conversation_count:0},visibleConversationIds:[]}),
    assertNoConflictingActivity:()=>{},defaultNativeRoots:()=>({}),homedir:()=>root,listSessionDirectoryIds:async()=>[],
    createAttemptState,transitionAttempt,atomicWriteAttemptState:async(path,state)=>{last=JSON.parse(JSON.stringify(state))},verifyExecutionEnvironment:async()=>{},
    createProject:async(page,state)=>{state.phase='WORKSPACE_CONFIRMED';state.workspace_selection.confirmed=true;},
    openProjectConversation:async()=>({projectIdSha256:projectHash}),verifyPreparedProjectWorkspace:async()=>{},
    confirmWorkspaceReadback:(state)=>{state.phase='WORKSPACE_CONFIRMED';state.workspace_selection.confirmed=true;},
    sha256Text:()=>projectHash,sanitizedStateSummary:state=>({phase:state.phase,send:state.send}),
    dispatchFromSelectedProject:async()=>{dispatches++;return {dispatched:true}},releaseUnsentObserver:async()=>{},markFailure:async()=>{},
  });
  const start=source.indexOf('async function retryPreSendDevelopmentRunUnlocked('),end=source.indexOf('async function navigateToConversation(');
  vm.runInContext(source.slice(start,end),context);
  const config={batchId:'batch',taskId:'task',workspace:previous.workspace,promptFile:previous.prompt.file,promptSha256:previous.prompt.sha256,
    manifestSha256:previous.client.manifest_sha256,prompt:'placeholder never sent during preparation'};
  const result=await context.retryPreSendDevelopmentRunUnlocked({outputDir:root,scene:'general',prepareOnly,validateTask:async()=>({...config})});
  assert.equal(archived,1);assert.equal(dispatches,prepareOnly?0:1);
  if(prepareOnly){assert.equal(result.prepared_only,true);assert.equal(last.prepared_project,true);assert.equal(last.send.dispatch_attempt_count,0);}
});
