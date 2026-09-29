#!/usr/bin/env node
// Model tool identities come from rollout response items, not desktop item types.
import { createHash, randomUUID } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { readFile, lstat, mkdir, writeFile, rename, rm, readdir } from 'node:fs/promises';
import { dirname, resolve, join, sep, isAbsolute } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

export const ROLLOUT_PATH = 'raw/astronstudio-rollout.jsonl';
export const SUPPLEMENT_SCHEMA = 'wildclawbench.astronstudio-rollout-supplement/v1';
export const ROLLOUT_METRICS_PROFILE = 2;
const ensure = (ok, code) => { if (!ok) throw Error(code); };
const hash = b => createHash('sha256').update(b).digest('hex');
const json = v => Buffer.from(JSON.stringify(v, null, 2) + '\n');
const stable = v => Array.isArray(v) ? v.map(stable) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, stable(v[k])])) : v;
const same = (a,b) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));
const inside = (root,p) => resolve(p).startsWith(resolve(root)+sep);
const FIELDS = ['input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens','total_tokens'];
const zero = () => Object.fromEntries(FIELDS.map(k => [k,0]));
const validUsage = v => v && FIELDS.every(k => Number.isSafeInteger(v[k]) && v[k]>=0)
  && v.total_tokens===v.input_tokens+v.output_tokens && v.cached_input_tokens<=v.input_tokens
  && v.reasoning_output_tokens<=v.output_tokens;
export async function readRolloutFile(path, expected) {
  const a=await lstat(path);
  ensure(a.isFile()&&!a.isSymbolicLink()&&a.size<=64*1024*1024,'ROLLOUT_FILE_UNSAFE');
  const bytes=await readFile(path),b=await lstat(path);
  ensure(a.size===bytes.length&&a.size===b.size&&a.ino===b.ino&&a.mtimeMs===b.mtimeMs,'ROLLOUT_FILE_CHANGED');
  const proof={sha256:hash(bytes),size:bytes.length};
  if(expected)ensure(same(proof,{sha256:expected.sha256,size:expected.size}),'ROLLOUT_SHA_MISMATCH');
  return {bytes,...proof};
}

export function analyzeRollout(bytes, state, {profileVersion=ROLLOUT_METRICS_PROFILE}={}) {
  ensure([1,2].includes(profileVersion),'ROLLOUT_PROFILE_UNSUPPORTED');
  ensure(state.session?.verified!==false&&state.prompt?.send_status==='sent'
    && ['COMPLETED','FAILED'].includes(state.phase),'ROLLOUT_EXECUTION_UNBOUND');
  const session=state.session, target=session.turn_id;
  ensure(target&&session.session_id&&session.cwd&&state.prompt.sha256,'ROLLOUT_BINDING_MISSING');
  let metaCount=0,current=null,starts=0,ended=false,promptMatches=0,usageEvents=0,repeated=0,requests=0;
  let previous=zero(),usageComplete=true;
  const calls=new Map(),sums=zero(),usageLines=[],warnings=[],terminals=[];
  const lines=bytes.toString('utf8').split('\n');
  for(let i=0;i<lines.length;i++) {
    if(!lines[i].trim())continue;
    const e=JSON.parse(lines[i]),p=e.payload||{},line=i+1;
    if(e.type==='session_meta'){
      metaCount++;
      ensure(p.id===session.session_id&&resolve(p.cwd)===resolve(session.cwd),'ROLLOUT_SESSION_MISMATCH');
    }
    if(e.type==='event_msg'&&p.type==='task_started'){
      current=p.turn_id;
      if(current===target){starts++;ended=false;}
    }
    if(e.type==='turn_context'){
      ensure(p.turn_id,'ROLLOUT_TURN_CONTEXT_MISSING_ID');
      current=p.turn_id;
      if(current===target)ensure(resolve(p.cwd)===resolve(session.cwd),'ROLLOUT_CWD_MISMATCH');
    }
    const explicit=p.internal_chat_message_metadata_passthrough?.turn_id;
    if(explicit&&current)ensure(explicit===current,'ROLLOUT_ITEM_TURN_MISMATCH');
    const bound=(explicit||current)===target;
    if(e.type==='event_msg'&&p.type==='token_count'){
      const total=p.info?.total_token_usage,last=p.info?.last_token_usage;
      if(!validUsage(total)||!validUsage(last)){
        if(bound)usageComplete=false;
        continue;
      }
      if(bound){
        usageEvents++;
        if(same(total,previous)){repeated++;continue;}
        ensure(FIELDS.every(k=>total[k]>=previous[k]),'ROLLOUT_USAGE_RESET');
        if(!FIELDS.every(k=>total[k]===previous[k]+last[k]))usageComplete=false;
        requests++;usageLines.push(line);
        for(const k of FIELDS)sums[k]+=last[k];
      }
      previous={...total};
    }
    if(!bound)continue;
    if(e.type==='event_msg'&&p.type==='user_message'){
      ensure(typeof p.message==='string','ROLLOUT_PROMPT_MISSING');
      ensure(hash(Buffer.from(p.message))===state.prompt.sha256,'ROLLOUT_PROMPT_MISMATCH');
      promptMatches++;
    }
    if(e.type==='event_msg'&&['task_complete','turn_aborted'].includes(p.type)){
      ensure(p.turn_id===target,'ROLLOUT_TERMINAL_MISMATCH');ended=true;
      if(profileVersion===2){
        ensure(state.phase!=='COMPLETED'||p.type==='task_complete','ROLLOUT_TERMINAL_STATUS_MISMATCH');
        if(p.duration_ms!==undefined&&p.duration_ms!==null)ensure(Number.isSafeInteger(p.duration_ms)&&p.duration_ms>=0,'ROLLOUT_DURATION_INVALID');
        terminals.push({line,type:p.type,duration_ms:p.duration_ms??null});
      }
    }
    if(e.type==='event_msg'&&p.type==='error'&&state.phase==='FAILED')ended=true;
    if(e.type!=='response_item')continue;
    if(!['function_call','custom_tool_call','tool_search_call'].includes(p.type)) {
      // New provider builtins must get an explicit counting profile.
      ensure(!p.type?.endsWith('_call'),'ROLLOUT_TOOL_TYPE_UNSUPPORTED');
      continue;
    }
    const name=p.type==='tool_search_call'?'tool_search':p.name;
    const id=p.call_id||(p.type==='tool_search_call'?p.id:null);
    ensure(typeof id==='string'&&id&&typeof name==='string'&&name,'ROLLOUT_TOOL_IDENTITY_MISSING');
    const signature=hash(json(stable({type:p.type,name,arguments:p.arguments??p.input??null})));
    if(calls.has(id)){ensure(calls.get(id).signature===signature,'ROLLOUT_CALL_ID_CONFLICT');continue;}
    calls.set(id,{call_id:id,tool_name:name,source_type:p.type,raw_line:line,signature});
  }
  ensure(metaCount===1&&starts===1&&promptMatches===1,'ROLLOUT_SCOPE_AMBIGUOUS');
  ensure(ended,'ROLLOUT_TURN_NOT_TERMINAL');
  const catalog=[...calls.values()],byTool={};
  for(const c of catalog)byTool[c.tool_name]=(byTool[c.tool_name]||0)+1;
  const toolCounts={status:'complete',total:catalog.length,by_tool:byTool,catalog,
    basis:'Bound rollout response_item tool calls, unique call_id; exact function/custom name; native tool_search_call = tool_search; outputs excluded; not tool success count'};
  const requestKnown=usageComplete&&requests>0;
  if(!requestKnown)warnings.push('ROLLOUT_USAGE_UNRECONCILED_OR_ABSENT');
  const requestMetric={value:requestKnown?requests:null,status:requestKnown?'inferred':requests?'partial':'unavailable',
    basis:'Bound rollout advancing token_count total_token_usage reconciled with last_token_usage; repeated cumulative snapshots excluded; observed model responses, not HTTP attempts'};
  const result={tool_counts:toolCounts,
    metrics:{tools:{call_count:{value:catalog.length,status:'observed',basis:toolCounts.basis}},
      requests:{request_count:requestMetric,request_attempt_count:{value:null,status:'unavailable',basis:'Rollout does not expose all HTTP requests or retries'}}},
    collection:{status:'partial',coverage:{call_count:{known:catalog.length,total:catalog.length,unit:'rollout-tool-call'},
      request_count:{known:requestKnown?requests:0,total:requests||null,unit:'model-usage-advance'},
      request_attempt_count:{known:0,total:null,unit:'http_attempt'}},
      known_subtotals:!requestKnown&&requests?{request_count:requests}:{},warnings},
    usage_reconciliation:{usage_events:usageEvents,advancing_updates:requests,repeated_snapshots:repeated,
      reconciled:requestKnown,summed_usage:sums,source_lines:usageLines}};
  if(profileVersion===1)return result; // Frozen v9 receipts retain their exact projection.
  const coverage=result.collection.coverage,subtotals=result.collection.known_subtotals;
  const sources=result.collection.metric_sources={};
  const usage={};
  for(const [raw,field] of Object.entries({input_tokens:'input_tokens',cached_input_tokens:'cache_read_input_tokens',
    output_tokens:'output_tokens',reasoning_output_tokens:'reasoning_output_tokens',total_tokens:'total_tokens'})){
    usage[field]={value:requestKnown?sums[raw]:null,status:requestKnown?'observed':requests?'partial':'unavailable',
      basis:`Bound rollout last_token_usage.${raw} summed after cumulative reconciliation and deduplication; cache is within input and reasoning is within output`};
    coverage[field]={known:requestKnown?requests:0,total:requests||null,unit:'model-usage-advance'};
    if(!requestKnown&&requests)subtotals[field]=sums[raw];
    sources[field]=usageLines.map(n=>`trace/${ROLLOUT_PATH}#L${n}`);
  }
  usage.cache_creation_input_tokens={value:null,status:'unavailable',basis:'Rollout token_count does not expose cache creation input tokens'};
  coverage.cache_creation_input_tokens={known:0,total:null,unit:'model-usage-advance'};
  const durations=new Set(terminals.map(t=>JSON.stringify([t.type,t.duration_ms])));
  ensure(durations.size<=1,'ROLLOUT_DURATION_AMBIGUOUS');
  const duration=terminals[0]?.duration_ms??null;
  result.metrics.usage=usage;
  result.metrics.timing={agent_duration_seconds:{value:duration===null?null:duration/1000,status:duration===null?'unavailable':'observed',
    basis:'Bound rollout terminal payload.duration_ms / 1000; native task duration, excluding evaluator preparation and terminal observation delay'}};
  coverage.agent_duration_seconds={known:duration===null?0:1,total:1,unit:'turn'};
  sources.agent_duration_seconds=terminals.map(t=>`trace/${ROLLOUT_PATH}#L${t.line}`);
  for(const f of ['call_count','request_count','request_attempt_count','cache_creation_input_tokens'])sources[f]=[`trace/${ROLLOUT_PATH}`];
  if(duration===null)warnings.push('ROLLOUT_NATIVE_DURATION_UNAVAILABLE');
  result.timing_reconciliation={duration_ms:duration,terminal_rows:terminals};
  result.profile_version=profileVersion;
  return result;
}

export async function discoverRollout(sessionId, root=join(homedir(),'.acode/acode/acode-home-overlay/sessions')) {
  ensure(/^[A-Za-z0-9-]+$/.test(sessionId),'ROLLOUT_SESSION_ID_UNSAFE');
  const found=[];
  async function walk(p){for(const e of await readdir(p,{withFileTypes:true})){
    if(e.isSymbolicLink())continue;
    if(e.isDirectory())await walk(join(p,e.name));
    else if(e.isFile()&&e.name.startsWith('rollout-')&&e.name.endsWith(`-${sessionId}.jsonl`))found.push(join(p,e.name));
  }}
  await walk(root);ensure(found.length===1,'ROLLOUT_FILE_NOT_UNIQUE');return found[0];
}
export async function analyzeIndexedRollout(indexPath, state, options={}) {
  const index=JSON.parse(await readFile(indexPath,'utf8'));
  ensure(same(index.identity,state.identity)&&['session_id','turn_id','cwd'].every(k=>index.session[k]===state.session[k]),'ROLLOUT_INDEX_BINDING');
  const refs=index.raw_trace.filter(r=>r.path===ROLLOUT_PATH);
  ensure(refs.length===1,'ROLLOUT_INDEX_MISSING_OR_AMBIGUOUS');
  const file=await readRolloutFile(join(dirname(indexPath),ROLLOUT_PATH),refs[0]);
  const result=analyzeRollout(file.bytes,state,options),ids=new Set(result.tool_counts.catalog.map(c=>c.call_id));
  ensure((index.calls||[]).every(c=>ids.has(c.call_id)),'ROLLOUT_PROVIDER_CALL_MISSING');
  return {...result,source:{path:ROLLOUT_PATH,sha256:file.sha256,size:file.size}};
}

export async function createRolloutSupplement({executionRecord,stateFile,rolloutFile,outputDir,baseDirectory}) {
  const execution=await readRolloutFile(executionRecord),stateSource=await readRolloutFile(stateFile),ex=JSON.parse(execution.bytes),state=JSON.parse(stateSource.bytes);
  ensure(ex.harness.id==='astronstudio'&&same(state.identity,ex.identity)&&same(state.session.session_id,ex.session.session_id)
    &&state.session.turn_id===ex.session.turn_id&&state.session.cwd===ex.session.cwd&&state.prompt.sha256===ex.prompt.sha256,'ROLLOUT_SUPPLEMENT_BINDING');
  const native=await readRolloutFile(rolloutFile),result=analyzeRollout(native.bytes,state);
  try{await lstat(outputDir);throw Error('ROLLOUT_SUPPLEMENT_EXISTS');}catch(e){if(e.code!=='ENOENT')throw e;}
  const stage=outputDir+'.staging-'+randomUUID();await mkdir(join(stage,'raw'),{recursive:true});
  try{
    const artifacts=[];
    for(const [path,bytes] of [['original-execution-record.json',execution.bytes],['automation-state.json',stateSource.bytes],[ROLLOUT_PATH,native.bytes],['rollout-metrics.json',json(result)]]){
      await writeFile(join(stage,path),bytes,{flag:'wx'});artifacts.push({path,sha256:hash(bytes),size:bytes.length});
    }
    const metrics={};for(const group of Object.values(result.metrics))for(const [k,v] of Object.entries(group))metrics[k]={...v,coverage:result.collection.coverage[k]};
    let base=null,baseSources=[];
    if(baseDirectory){
      async function copyBase(dir,rel='base'){
        await mkdir(join(stage,rel),{recursive:true});
        for(const entry of await readdir(dir,{withFileTypes:true})){
          ensure(!entry.isSymbolicLink(),'ROLLOUT_BASE_SYMLINK');
          const src=join(dir,entry.name),dst=join(rel,entry.name);
          if(entry.isDirectory())await copyBase(src,dst);
          else {
            // Large provider archives are copied separately with streaming hashes.
            const {createReadStream,constants}=await import('node:fs');
            const {copyFile}=await import('node:fs/promises');
            const before=await lstat(src),h=createHash('sha256');let size=0;
            for await(const chunk of createReadStream(src)){h.update(chunk);size+=chunk.length;}
            const after=await lstat(src);ensure(before.size===size&&after.mtimeMs===before.mtimeMs,'ROLLOUT_BASE_CHANGED');
            await copyFile(src,join(stage,dst),constants.COPYFILE_EXCL|constants.COPYFILE_FICLONE);
            artifacts.push({path:dst.split(sep).join('/'),sha256:h.digest('hex'),size});
          }
        }
      }
      await copyBase(baseDirectory);
      const baseBytes=await readFile(join(stage,'base/resource-supplement.json'));
      const baseDoc=JSON.parse(baseBytes);
      ensure(same(baseDoc.identity,ex.identity)&&baseDoc.execution_record_sha256===execution.sha256,'ROLLOUT_BASE_IDENTITY');
      base={path:'base/resource-supplement.json',sha256:hash(baseBytes)};baseSources=baseDoc.sources;
    }
    const doc={schema_version:SUPPLEMENT_SCHEMA,profile_version:ROLLOUT_METRICS_PROFILE,identity:ex.identity,execution_record_sha256:execution.sha256,
      score_changed:false,zero_imputation_used:false,rollout_path:ROLLOUT_PATH,metrics,tool_calls:result.tool_counts,base_supplement:base,
      artifacts,sources:[{path:resolve(executionRecord),sha256:execution.sha256,size:execution.size},
        {path:resolve(stateFile),sha256:stateSource.sha256,size:stateSource.size},
        {path:resolve(rolloutFile),sha256:native.sha256,size:native.size},...baseSources]};
    await writeFile(join(stage,'resource-supplement.json'),json(doc),{flag:'wx'});
    await rename(stage,outputDir);return await verifyRolloutSupplement({directory:outputDir,executionRecord});
  }catch(e){await rm(stage,{recursive:true,force:true});throw e;}
}
export async function verifyRolloutSupplement({directory,executionRecord}) {
  const doc=JSON.parse((await readRolloutFile(join(directory,'resource-supplement.json'))).bytes);
  const execution=await readRolloutFile(executionRecord),ex=JSON.parse(execution.bytes);
  ensure(doc.schema_version===SUPPLEMENT_SCHEMA&&doc.execution_record_sha256===execution.sha256&&same(doc.identity,ex.identity)
    &&ex.harness.id==='astronstudio'&&doc.score_changed===false,'ROLLOUT_SUPPLEMENT_IDENTITY');
  const expected=['original-execution-record.json','automation-state.json',ROLLOUT_PATH,'rollout-metrics.json'];
  ensure(new Set(doc.artifacts.map(a=>a.path)).size===doc.artifacts.length&&expected.every(p=>doc.artifacts.some(a=>a.path===p))
    &&doc.artifacts.every(a=>expected.includes(a.path)||(doc.base_supplement&&a.path.startsWith('base/')&&!a.path.split('/').includes('..'))),'ROLLOUT_SUPPLEMENT_ARTIFACT_SCOPE');
  const files={};for(const a of doc.artifacts.filter(a=>expected.includes(a.path)))files[a.path]=(await readRolloutFile(join(directory,a.path),a)).bytes;
  if(doc.base_supplement)ensure(doc.base_supplement.path==='base/resource-supplement.json'
    &&hash(await readFile(join(directory,doc.base_supplement.path)))===doc.base_supplement.sha256,'ROLLOUT_BASE_MANIFEST_DRIFT');
  ensure(hash(files['original-execution-record.json'])===execution.sha256,'ROLLOUT_EXECUTION_COPY_DRIFT');
  const state=JSON.parse(files['automation-state.json']);
  ensure(same(state.identity,ex.identity)&&state.session.session_id===ex.session.session_id
    &&state.session.turn_id===ex.session.turn_id&&state.session.cwd===ex.session.cwd&&state.prompt.sha256===ex.prompt.sha256,'ROLLOUT_SUPPLEMENT_STATE_BINDING');
  const result=analyzeRollout(files[ROLLOUT_PATH],state,{profileVersion:doc.profile_version??1});
  ensure(same(result,JSON.parse(files['rollout-metrics.json']))&&same(result.tool_counts,doc.tool_calls),'ROLLOUT_RECOMPUTATION_MISMATCH');
  const flat={};for(const group of Object.values(result.metrics))for(const [k,v] of Object.entries(group))flat[k]={...v,coverage:result.collection.coverage[k]};
  ensure(same(doc.metrics,flat),'ROLLOUT_SUPPLEMENT_METRIC_DRIFT');
  return {status:'PASS',identity:ex.identity,metrics:result,tool_counts:result.tool_counts,usage_reconciliation:result.usage_reconciliation};
}
export async function main(argv=process.argv.slice(2)) {
  const [cmd,...args]=argv;const {values:v}=parseArgs({args,options:Object.fromEntries(['execution-record','state-file','rollout-file','output-dir','directory','trace-index','binding','base-directory'].map(k=>[k,{type:'string'}]))});
  const opts={executionRecord:v['execution-record'],stateFile:v['state-file'],rolloutFile:v['rollout-file'],outputDir:v['output-dir'],directory:v.directory,baseDirectory:v['base-directory']};
  ensure(['create','verify','verify-index'].includes(cmd),'ROLLOUT_COMMAND_INVALID');
  let result;
  if(cmd==='verify-index'){
    const ex=v.binding?JSON.parse(v.binding):JSON.parse((await readRolloutFile(opts.executionRecord)).bytes);result=await analyzeIndexedRollout(v['trace-index'],ex);
  }else result=await(cmd==='create'?createRolloutSupplement(opts):verifyRolloutSupplement(opts));
  console.log(JSON.stringify(result));
}
if(process.argv[1]&&realpathSync(resolve(process.argv[1]))===realpathSync(fileURLToPath(import.meta.url)))main().catch(e=>{console.error(e.message);process.exitCode=1});
