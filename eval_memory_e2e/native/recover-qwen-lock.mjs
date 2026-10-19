import {MACHINE_PATHS} from './machine.mjs';
/** Archive one dead Qwen General-step lock bound to a frozen Memory intent. */
import {readFile,open,link,unlink,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {loadQwenCanaryConfig,assertQwenCanaryProbe,inspectLockOwner} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs';
import {assertQwenJournalMatches} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/journal.mjs';
import {assertNoLinks,readJson,sha,requestHash} from './common.mjs';

export function assertMemoryQwenRecoveryOwner(owner,input,cfg,status) {
  if(owner.schema_version!=='wildclawbench.general-e2e-qwenwork-attempt-lock/v1'||owner.owner_id!==input.expected_owner_id
    ||owner.attempt_id!==cfg.identity.attempt_id||owner.state_file!==cfg.state_file||!owner.process_start_identity)throw Error('MEMORY_QWEN_RECOVERY_OWNER');
  if(!status.verifiable||!status.stale||status.active)throw Error('MEMORY_QWEN_RECOVERY_OWNER_ACTIVE_OR_UNKNOWN');
}

export async function recoverMemoryQwenLock(input,{inspect=inspectLockOwner}={}) {
  const root=resolve(input.root);
  if(!root.startsWith(MACHINE_PATHS.debug+'/')
    ||!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(input.expected_owner_id||''))throw Error('MEMORY_QWEN_RECOVERY_SCOPE');
  if(input.output!==join(root,'runtime-recovery','qwen-step-'+input.expected_owner_id+'.json'))throw Error('MEMORY_QWEN_RECOVERY_OUTPUT');
  const manifest=await readJson(join(root,'manifest.json'));
  if(manifest.mode!=='native'||manifest.contract!=='wildclawbench.memory-e2e/v1')throw Error('MEMORY_QWEN_RECOVERY_SCOPE');
  const item=manifest.episodes.find(e=>e.id===input.episode_id&&e.harness==='QwenWork');
  if(!item||!/^op-[a-f0-9]{64}$/.test(input.operation_id))throw Error('MEMORY_QWEN_RECOVERY_SCOPE');
  const history=(await readFile(join(root,'events.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
  const intents=history.filter(e=>e.kind==='INTENT'&&e.episode_id===item.id&&e.payload.operation_id===input.operation_id);
  if(intents.length!==1)throw Error('MEMORY_QWEN_RECOVERY_INTENT');
  const request=intents[0].payload.request,control=join(root,'.native/QwenWork',input.operation_id);
  const state=await readJson(join(control,'state.json')),configPath=join(control,'general-step-config.json');
  if(request.harness!=='QwenWork'||state.requestHash!==requestHash(request)||state.configPath!==configPath)throw Error('MEMORY_QWEN_RECOVERY_BINDING');
  const probe=await readJson(input.probe),probeBytes=await readFile(input.probe);
  const cfg=await loadQwenCanaryConfig(configPath,{requireLiveAuthorization:true,resume:true,
    resumeProbePath:input.probe,resumeProbeSha256:sha(probeBytes)});
  if(cfg.managed_queue_id)throw Error('MEMORY_QWEN_RECOVERY_MANAGED_QUEUE_NOT_ADMITTED');
  assertQwenCanaryProbe(probe,cfg,Date.now(),{requireFresh:true,requireIdle:true});
  if(cfg.candidate_workspace!==request.workspace||cfg.prompt.sha256!==request.prompt_sha256
    ||cfg.state_file!==join(control,'general-journal.json'))throw Error('MEMORY_QWEN_RECOVERY_BINDING');
  const lock=cfg.state_file+'.lock',guardPath=lock+'.memory-recovery';
  for(const path of [root,configPath,cfg.state_file,lock,input.probe])await assertNoLinks(path);
  const guard=await open(guardPath,'wx',0o600);
  try {
    const bytes=await readFile(lock),journalBytes=await readFile(cfg.state_file),owner=JSON.parse(bytes);
    const status=await inspect(owner);
    assertMemoryQwenRecoveryOwner(owner,input,cfg,status);
    assertQwenJournalMatches(JSON.parse(journalBytes),{identity:cfg.identity,dataset:cfg.dataset,configDigest:cfg.config_digest,
      candidateWorkspace:cfg.candidate_workspace,prompt:cfg.prompt});
    const archive=lock+'.stale-'+owner.owner_id+'.json';
    if(sha(await readFile(lock))!==sha(bytes)||sha(await readFile(cfg.state_file))!==sha(journalBytes))throw Error('MEMORY_QWEN_RECOVERY_DRIFT');
    await link(lock,archive);
    if(sha(await readFile(lock))!==sha(bytes)||sha(await readFile(cfg.state_file))!==sha(journalBytes))throw Error('MEMORY_QWEN_RECOVERY_DRIFT');
    await unlink(lock);
    const receipt={status:'RECOVERED',at:new Date().toISOString(),operation_id:input.operation_id,episode_id:item.id,
      owner,archive,lock_sha256:sha(bytes),journal_sha256:sha(journalBytes),probe_sha256:sha(probeBytes),
      prompt_sent:false,prompt_resent:false,native_task_cancelled:false,journal_rewritten:false};
    await writeFile(input.output,JSON.stringify(receipt,null,2)+'\n',{flag:'wx',mode:0o600});return receipt;
  }finally{await guard.close();await unlink(guardPath);}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{let text='';for await(const part of process.stdin)text+=part;console.log(JSON.stringify(await recoverMemoryQwenLock(JSON.parse(text))));}
  catch(error){console.error(error.stack||error);process.exitCode=2;}
}
