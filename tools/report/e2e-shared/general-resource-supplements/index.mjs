#!/usr/bin/env node
// Immutable, offline resource repair. Never changes a scored execution record.
import { constants, createReadStream } from "node:fs";
import { copyFile, lstat, mkdir, mkdtemp, readFile, readdir, realpath, rename, rm, writeFile } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import { createInterface } from "node:readline";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { normalizeTraceRows } from "./archive_astronstudio_trace.mjs";
import { collectAstronStudioResourceMetrics } from "./collect_astronstudio_resource_metrics.mjs";
import { recountArchivedTools } from "../doubaowork/tool-counts.mjs";

export const SCHEMA = "wildclawbench.general-e2e-resource-supplement/v1";
const ensure = (ok, code) => { if (!ok) throw Error(code); };
const load = async p => JSON.parse(await readFile(p, "utf8"));
const bytes = v => Buffer.from(JSON.stringify(v, null, 2) + "\n");
const digest = b => createHash("sha256").update(b).digest("hex");
const stable = v => Array.isArray(v) ? v.map(stable) : v && typeof v === "object"
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, stable(v[k])])) : v;
const same = (a,b) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));
const inside = (root,p) => resolve(p).startsWith(resolve(root)+sep);
function child(root, rel) {
  ensure(typeof rel === "string" && !isAbsolute(rel) && !rel.split(/[\\/]/).some(x => !x || x === ".." || x === "."), "SUPPLEMENT_PATH_INVALID");
  const p=resolve(root,rel);ensure(inside(root,p),"SUPPLEMENT_PATH_ESCAPE");return p;
}
export async function hashFile(p) {
  const a=await lstat(p);ensure(a.isFile()&&!a.isSymbolicLink(),"SUPPLEMENT_SOURCE_NOT_REGULAR");
  const h=createHash("sha256");let size=0;
  for await(const b of createReadStream(p)){h.update(b);size+=b.length;}
  const z=await lstat(p);ensure(size===a.size&&z.size===a.size&&z.ino===a.ino&&z.mtimeMs===a.mtimeMs,"SUPPLEMENT_SOURCE_CHANGED");
  return {sha256:h.digest("hex"),size};
}
async function copyBound(src,dst,expected=null) {
  const proof=await hashFile(src);
  if(expected)ensure(proof.sha256===expected.sha256&&proof.size===expected.size,"SUPPLEMENT_SOURCE_DRIFT");
  await mkdir(dirname(dst),{recursive:true});await copyFile(src,dst,constants.COPYFILE_EXCL|constants.COPYFILE_FICLONE);
  ensure(same(await hashFile(dst),proof),"SUPPLEMENT_COPY_DRIFT");return proof;
}
async function inventory(root) {
  const out=[];
  async function walk(dir){for(const e of await readdir(dir,{withFileTypes:true})){
    const p=join(dir,e.name);ensure(!e.isSymbolicLink(),"SUPPLEMENT_SYMLINK");
    if(e.isDirectory())await walk(p);else if(p!==join(root,"supplement.json"))out.push({path:relative(root,p).split(sep).join("/"),...await hashFile(p)});
  }}
  await walk(root);return out.sort((a,b)=>a.path.localeCompare(b.path));
}
async function normalizeAstron(root,state,originalIndex) {
  ensure(originalIndex.raw_trace?.length===1,"SUPPLEMENT_ASTRON_RAW_AMBIGUOUS");
  const raw=child(join(root,"trace"),originalIndex.raw_trace[0].path), rows=[];
  let lineNo=0,last=-1,first=null;
  for await(const line of createInterface({input:createReadStream(raw),crlfDelay:Infinity})){
    lineNo++;ensure(Buffer.byteLength(line)<2*1024*1024,"SUPPLEMENT_EVENT_OVERSIZED");
    const row=JSON.parse(line);
    ensure(row.thread_id===state.session.thread_id&&row.turn_id===state.session.turn_id&&row.sequence>last,"SUPPLEMENT_NATIVE_IDENTITY_OR_SEQUENCE");
    first??=row.sequence;last=row.sequence;
    if(row.event_type!=="content.delta")rows.push({...row,raw_line:lineNo});
  }
  ensure(originalIndex.raw_event_range.event_count===lineNo&&originalIndex.raw_event_range.first_sequence===first&&originalIndex.raw_event_range.last_sequence===last,"SUPPLEMENT_NATIVE_RANGE");
  const normalized=normalizeTraceRows(rows,state),tr=Buffer.from(normalized.events.map(e=>JSON.stringify(e)).join("\n")+"\n");
  const users=normalized.events.filter(e=>e.type==="user_message");
  ensure(users.length===1&&digest(Buffer.from(users[0].content))===state.prompt.sha256,"SUPPLEMENT_PROMPT_BINDING");
  const index={...originalIndex,adapter:{...originalIndex.adapter,version:"0.1.1"},
    transcript:{path:"transcript.jsonl",sha256:digest(tr),size:tr.length,event_count:normalized.events.length},
    calls:normalized.calls,completeness:normalized.completeness,
    normalization:{...normalized.normalization,native_event_count:lineNo,filtered_native_event_count:lineNo-normalized.events.length}};
  await writeFile(join(root,"trace/transcript.jsonl"),tr);
  await writeFile(join(root,"trace/trace-index.json"),bytes(index));
}
async function compute(root,execution,{output}={}) {
  const stateFile=join(root,"execution/automation-state.json"),traceIndex=join(root,"trace/trace-index.json");
  if(execution.harness.id==="astronstudio"){
    const temporary=await mkdtemp(join(tmpdir(),"general-resource-verify-"));
    try{
      await collectAstronStudioResourceMetrics({stateFile,traceIndex,output:join(temporary,"resource.json"),replace:false});
      return await load(join(temporary,"resource.json"));
    }finally{await rm(temporary,{recursive:true,force:true});}
  }
  ensure(execution.harness.id==="doubaowork","SUPPLEMENT_HARNESS_UNSUPPORTED");
  const counted=await recountArchivedTools({stateFile,traceIndex});
  if(output)await writeFile(join(root,"tool-count-summary.json"),bytes(counted),{flag:"wx"});
  return {identity:execution.identity,metrics:{tools:{call_count:{value:counted.total,status:"observed",basis:counted.basis}}},
    collection:{status:"partial",coverage:{call_count:{known:counted.total,total:counted.total,unit:"native-call-or-invocation-block"}},known_subtotals:{}},tool_counts:counted};
}
export async function createResourceSupplement({unitRoot,executionRecord,stateFile,traceIndex}) {
  unitRoot=resolve(unitRoot);executionRecord=resolve(executionRecord);
  ensure(await realpath(unitRoot)===unitRoot,"SUPPLEMENT_UNIT_SYMLINK");
  ensure(inside(unitRoot,executionRecord),"SUPPLEMENT_EXECUTION_OUTSIDE_UNIT");
  const execution=await load(executionRecord),original=await hashFile(executionRecord);
  const task=execution.identity.task_id;ensure(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(task),"SUPPLEMENT_TASK_ID");
  stateFile=resolve(stateFile||join(dirname(executionRecord),"execution/automation-state.json"));
  traceIndex=resolve(traceIndex||child(unitRoot,execution.evidence.trace_index_path));
  const state=await load(stateFile),index=await load(traceIndex);
  ensure(same(state.identity,execution.identity)&&same(index.identity,execution.identity),"SUPPLEMENT_IDENTITY");
  ensure(state.session.verified===true&&state.session.session_id===execution.session.session_id&&state.session.cwd===execution.session.cwd
    &&state.prompt.sha256===execution.prompt.sha256&&execution.prompt.send_status==="sent"&&state.send.dispatch_attempt_count===1,"SUPPLEMENT_EXECUTION_BINDING");
  const out=join(unitRoot,"evidence/resource-supplements",task),stage=out+".staging-"+randomUUID();
  try{await lstat(out);throw Error("SUPPLEMENT_ALREADY_EXISTS");}catch(e){if(e.code!=="ENOENT")throw e;}
  await mkdir(stage,{recursive:true});
  ensure(await realpath(stage)===stage,"SUPPLEMENT_OUTPUT_SYMLINK");
  try{
    await copyBound(executionRecord,join(stage,"original-execution-record.json"));
    await copyBound(stateFile,join(stage,"execution/automation-state.json"));
    await copyBound(traceIndex,join(stage,"original-trace-index.json"));
    await copyBound(traceIndex,join(stage,"trace/trace-index.json"));
    const seen=new Set();
    for(const entry of [index.transcript,...index.raw_trace,...(index.binding_evidence||[])]){
      ensure(!seen.has(entry.path),"SUPPLEMENT_DUPLICATE_ARTIFACT");seen.add(entry.path);
      await copyBound(child(dirname(traceIndex),entry.path),child(join(stage,"trace"),entry.path),entry);
    }
    if(execution.harness.id==="astronstudio")await normalizeAstron(stage,state,index);
    const metrics=await compute(stage,execution,{output:true});await writeFile(join(stage,"resource-metrics.json"),bytes(metrics),{flag:"wx"});
    const manifest={schema_version:SCHEMA,identity:execution.identity,harness:execution.harness.id,
      execution_record_sha256:original.sha256,original_resource_sha256:execution.resource_metrics_path?(await hashFile(child(unitRoot,execution.resource_metrics_path))).sha256:null,
      metrics_path:"resource-metrics.json",trace_index_path:"trace/trace-index.json",score_changed:false,
      artifacts:await inventory(stage)};
    await writeFile(join(stage,"supplement.json"),bytes(manifest),{flag:"wx"});
    ensure(same(await hashFile(executionRecord),original),"SUPPLEMENT_EXECUTION_CHANGED");
    await rename(stage,out);return await verifyResourceSupplement({unitRoot,taskId:task,executionRecord});
  }catch(e){await rm(stage,{recursive:true,force:true});throw e;}
}
export async function verifyResourceSupplement({unitRoot,taskId,executionRecord}) {
  ensure(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(taskId),"SUPPLEMENT_TASK_ID");
  const root=join(resolve(unitRoot),"evidence/resource-supplements",taskId),manifest=await load(join(root,"supplement.json")),ex=await load(executionRecord);
  ensure(await realpath(root)===root&&manifest.metrics_path==="resource-metrics.json"&&manifest.trace_index_path==="trace/trace-index.json","SUPPLEMENT_LAYOUT_INVALID");
  ensure(manifest.schema_version===SCHEMA&&same(manifest.identity,ex.identity)&&manifest.harness===ex.harness.id&&manifest.score_changed===false,"SUPPLEMENT_MANIFEST_IDENTITY");
  ensure((await hashFile(executionRecord)).sha256===manifest.execution_record_sha256,"SUPPLEMENT_ORIGINAL_EXECUTION_DRIFT");
  ensure(same(await inventory(root),manifest.artifacts),"SUPPLEMENT_ARTIFACT_DRIFT");
  ensure((await hashFile(join(root,"original-execution-record.json"))).sha256===manifest.execution_record_sha256,"SUPPLEMENT_EXECUTION_COPY_DRIFT");
  if(manifest.original_resource_sha256)ensure((await hashFile(child(unitRoot,ex.resource_metrics_path))).sha256===manifest.original_resource_sha256,"SUPPLEMENT_ORIGINAL_RESOURCE_DRIFT");
  const recorded=await load(join(root,manifest.metrics_path)),computed=await compute(root,ex);
  ensure(same(recorded,computed),"SUPPLEMENT_RECOMPUTATION_MISMATCH");
  return {status:"PASS",identity:ex.identity,metrics:computed,manifest_sha256:(await hashFile(join(root,"supplement.json"))).sha256,
    trace_index_path:relative(unitRoot,join(root,manifest.trace_index_path)).split(sep).join("/"),
    transcript_path:relative(unitRoot,join(root,"trace/transcript.jsonl")).split(sep).join("/")};
}

export async function verifyExternalResourceSupplement({unitRoot, executionRecord, directory, workspaceRoot, sourceMap}) {
  // Compatibility with independently frozen pre-protocol supplements. Validate
  // their original source hashes and recompute; never trust supplied totals.
  workspaceRoot=resolve(workspaceRoot);directory=resolve(directory);
  ensure(inside(workspaceRoot,directory),"EXTERNAL_SUPPLEMENT_SCOPE");
  const doc=await load(join(directory,"resource-supplement.json")),ex=await load(executionRecord);
  ensure(doc.schema_version==="general-e2e-resource-supplement/v1"&&same(doc.identity,ex.identity)
    &&doc.execution_record_sha256===(await hashFile(executionRecord)).sha256&&doc.score_changed===false
    &&doc.zero_imputation_used!==true,"EXTERNAL_SUPPLEMENT_IDENTITY");
  const mapping=sourceMap?(await load(sourceMap)).sources:{};
  for(const source of doc.sources){
    const mapped=mapping[source.path];
    const p=mapped?child(workspaceRoot,mapped.archive_path):resolve(source.path);
    ensure(inside(workspaceRoot,p),"EXTERNAL_SUPPLEMENT_SOURCE_SCOPE");
    const actual=await hashFile(p);ensure(actual.sha256===source.sha256&&actual.size===source.size,"EXTERNAL_SUPPLEMENT_SOURCE_DRIFT");
  }
  let metrics,toolCounts;
  if(ex.harness.id==="astronstudio"){
    const state=await load(join(directory,"execution/automation-state.json"));
    ensure(same(state.identity,ex.identity)&&state.session.session_id===ex.session.session_id&&state.session.cwd===ex.session.cwd
      &&state.prompt.sha256===ex.prompt.sha256,"EXTERNAL_SUPPLEMENT_STATE_BINDING");
    metrics=await compute(directory,ex);
    const index=await load(join(directory,"trace/trace-index.json"));
    const tr=await readFile(child(join(directory,"trace"),index.transcript.path));
    ensure(digest(tr)===index.transcript.sha256&&tr.length===index.transcript.size,"EXTERNAL_SUPPLEMENT_TRANSCRIPT_DRIFT");
    const events=tr.toString().split("\n").filter(Boolean).map(JSON.parse);
    ensure(events.every(row=>same(row.identity,ex.identity)),"EXTERNAL_SUPPLEMENT_EVENT_IDENTITY");
    const calls=events.filter(row=>row.type==="tool_call"),ids=new Set(calls.map(row=>row.tool.call_id)),byTool={};
    ensure(ids.size===calls.length&&calls.length===metrics.metrics.tools.call_count.value,"EXTERNAL_SUPPLEMENT_TOOL_RECONCILIATION");
    for(const row of calls)byTool[row.tool.name]=(byTool[row.tool.name]||0)+1;
    toolCounts={status:"complete",total:calls.length,by_tool:byTool,basis:"replayed native trace with unique call IDs"};
  }else{
    ensure(ex.harness.id==="doubaowork","EXTERNAL_SUPPLEMENT_HARNESS");
    toolCounts=await recountArchivedTools({stateFile:join(dirname(executionRecord),"execution/automation-state.json"),traceIndex:child(unitRoot,ex.evidence.trace_index_path)});
    metrics={metrics:{tools:{call_count:{value:toolCounts.total,status:"observed",basis:toolCounts.basis}}},
      collection:{status:"partial",coverage:{call_count:{known:toolCounts.total,total:toolCounts.total,unit:"native-call-or-invocation-block"}},known_subtotals:{}}};
  }
  const flat=Object.assign({},...Object.values(metrics.metrics));
  for(const [field,expected] of Object.entries(doc.metrics)){
    ensure(flat[field]&&flat[field].value===expected.value&&flat[field].status===expected.status
      &&same(metrics.collection.coverage[field],expected.coverage),"EXTERNAL_SUPPLEMENT_RECOMPUTATION_MISMATCH");
  }
  ensure(toolCounts.total===doc.tool_calls.total&&same(toolCounts.by_tool,doc.tool_calls.by_tool),"EXTERNAL_SUPPLEMENT_COUNTS_MISMATCH");
  return {status:"PASS",identity:ex.identity,metrics,tool_counts:toolCounts,score_changed:false};
}
export async function main(argv=process.argv.slice(2)) {
  const [command,...args]=argv;
  const {values:v}=parseArgs({args,options:{"unit-root":{type:"string"},"execution-record":{type:"string"},"state-file":{type:"string"},"trace-index":{type:"string"},"task-id":{type:"string"},"directory":{type:"string"},"workspace-root":{type:"string"},"source-map":{type:"string"},help:{type:"boolean"}}});
  if(v.help||command==="--help"){console.log("Offline immutable resource supplement: create|verify --unit-root ABS --execution-record ABS [--state-file ABS --trace-index ABS] [--task-id ID]");return;}
  ensure(isAbsolute(v["unit-root"]||"")&&isAbsolute(v["execution-record"]||""),"SUPPLEMENT_ABSOLUTE_PATH_REQUIRED");
  const options={unitRoot:v["unit-root"],executionRecord:v["execution-record"],stateFile:v["state-file"],traceIndex:v["trace-index"],taskId:v["task-id"]};
  if(command==="verify-external"){
    ensure(isAbsolute(v.directory||"")&&isAbsolute(v["workspace-root"]||""),"EXTERNAL_SUPPLEMENT_ABSOLUTE_PATH");
    console.log(JSON.stringify(await verifyExternalResourceSupplement({...options,directory:v.directory,workspaceRoot:v["workspace-root"],sourceMap:v["source-map"]})));return;
  }
  ensure(["create","verify"].includes(command),"SUPPLEMENT_COMMAND");
  console.log(JSON.stringify(await(command==="create"?createResourceSupplement(options):verifyResourceSupplement(options))));
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error(e.message);process.exitCode=1});
