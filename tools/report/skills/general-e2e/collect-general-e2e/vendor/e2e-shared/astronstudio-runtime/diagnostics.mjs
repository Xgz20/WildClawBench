import {createHash,randomUUID} from "node:crypto";
import {open,readFile,writeFile,mkdir,rename,stat,lstat,mkdtemp,rm} from "node:fs/promises";
import {dirname,join,resolve,relative} from "node:path";
import {tmpdir,freemem,loadavg} from "node:os";
import {copySnapshotFile,configureSnapshotReader} from "../sqlite-snapshot/index.mjs";
import {snapshotDarwinTaskProcesses} from "../task-process-cleanup/macos-task-processes.mjs";
import {readRuntimeConfig} from "./guard.mjs";

export const DIAGNOSTIC_SCHEMA="wildclawbench.astudio-runtime-diagnostics/v1";
const actorId=randomUUID();
let sequence=0;
const hash=b=>createHash("sha256").update(b).digest("hex");
const json=d=>JSON.stringify(d,null,2)+"\n";
function diagnosticAttempt(state) {
  const id=state.identity?.attempt_id;
  if(typeof id!=="string"||!id||id.length>256||[".",".."].includes(id)||/[\/\\]/u.test(id))
    throw Error("DIAGNOSTIC_ATTEMPT_ID_INVALID");
  return id;
}
function safeEvent(value) {
  if(Array.isArray(value))return value.map(safeEvent);
  if(value&&typeof value==="object")return Object.fromEntries(Object.entries(value).map(([key,item])=>{
    const secret=/^(?:prompt|argv|arguments|command|commandline|accesstoken|refreshtoken|apikey|authorization|password|secret)$/iu
      .test(key.replace(/[_-]/gu,""));
    return [key,secret?"[OMITTED]":safeEvent(item)];
  }));
  return typeof value==="string"?redactDiagnosticText(value):value;
}
const signalMarkers=/backend exited|APP SESSION (?:START|END)|abandoning stalled Acode turn|turn\/interrupt|invalidated by credential|catalog invalidated|server\.shutdown|account change reconciliation failed|recycling Acode app-server|shared.*(?:transport|exited)|failed to (?:stop|retire)|backend[- ]watchdog|shutdown watchdog|stdin reader finished|stdout writer exited|transport connection (?:closed|opened)|interrupt received|aborting running task|Shutting down Codex instance|processor task exited/iu;
export function redactDiagnosticText(value) {
  return String(value)
    .replace(/\bBearer\s+[A-Za-z0-9._~+\/-]+/giu,"Bearer [REDACTED]")
    .replace(/((?:access[_-]?token|refresh[_-]?token|api[_-]?key|authorization|password|secret)\s*(?:\\?["'])?\s*[:=]\s*(?:\\?["'])?)[^\s"'\\,}]+/giu,"$1[REDACTED]")
    .replace(/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/gu,"[REDACTED_JWT]");
}
export async function appendFrameworkEvent(path,event,{durable=false,maxBytes=32*1024*1024}={}) {
  await mkdir(dirname(path),{recursive:true});
  const row={...safeEvent(event),at:new Date().toISOString(),monotonic_ns:process.hrtime.bigint().toString(),
    actor_pid:process.pid,actor_instance_id:actorId,actor_sequence:++sequence,origin:"evaluation-framework"};
  // Do not pass Prompt, full argv, model outputs or credentials into the journal.
  const bytes=Buffer.from(JSON.stringify(row)+"\n");
  if(bytes.length>64*1024)throw Error("ASTUDIO_DIAGNOSTIC_EVENT_TOO_LARGE");
  const handle=await open(path,"a",0o600);
  try {
    if((await handle.stat()).size+bytes.length>maxBytes)throw Error("ASTUDIO_FRAMEWORK_AUDIT_BUDGET");
    const result=await handle.write(bytes);
    if(result.bytesWritten!==bytes.length)throw Error("ASTUDIO_DIAGNOSTIC_EVENT_SHORT_WRITE");
    if(durable)await handle.sync();
  } finally {await handle.close();}
  return row;
}
async function atomicJson(path,value) {
  const temporary=path+"."+randomUUID()+".tmp";
  await writeFile(temporary,json(value),{mode:0o600,flag:"wx"});
  await rename(temporary,path);
}
export function projectKernelDiagnostic(row) {
  const body=String(row.feedback_log_body||"");
  const base={id:row.id,ts:row.ts,ts_nanos:row.ts_nanos,level:row.level,target:row.target,
    thread_id:row.thread_id,process_uuid:row.process_uuid,file:row.file,line:row.line,body_sha256:hash(body)};
  if(body.includes("raw_frame=")) {
    let frame;try{frame=JSON.parse(body.split("raw_frame=")[1]);}catch{return null;}
    if(!["turn/interrupt","thread/unsubscribe","thread/read"].includes(frame.method))return null;
    return {...base,frame:{id:frame.id,method:frame.method,
      threadId:frame.params?.threadId,turnId:frame.params?.turnId},body_omitted:true};
  }
  if(!signalMarkers.test(body)&&!["ERROR","WARN"].includes(row.level))return null;
  if(/reasoning.*delta|SSE event|content\.delta/iu.test(body))return null;
  if(!/(?:app_server|core::(?:session|tasks)|state|rollout::recorder)/u.test(String(row.target))
      ||!signalMarkers.test(body))return {...base,body_omitted:true,omission_reason:"non-lifecycle-body"};
  return {...base,body_excerpt:redactDiagnosticText(body).slice(0,2048),excerpt_truncated:body.length>2048};
}
async function sqliteSnapshot(path,operation) {
  const info=await stat(path);
  if(info.size>2*1024**3)throw Error("DIAGNOSTIC_SQLITE_SIZE_BUDGET");
  const root=await mkdtemp(join(tmpdir(),"astudio-diagnostic-"));
  try {
    const dest=join(root,"source.sqlite");
    await copySnapshotFile(path,dest);
    for(const suffix of ["-wal","-shm"]) {
      try{await copySnapshotFile(path+suffix,dest+suffix);}
      catch(error){if(error.code!=="ENOENT")throw error;}
    }
    const {DatabaseSync}=await import("node:sqlite");
    const db=new DatabaseSync(dest,{readOnly:true});
    try{configureSnapshotReader(db);return await operation(db);}
    finally{db.close();}
  } finally {await rm(root,{recursive:true,force:true});}
}
async function captureDatabases(config,state,center) {
  const result={captured_at:new Date().toISOString(),auxiliary_only:true,unavailable:[]};
  const dbPath=config.state_database.path;
  try {
    if(!state.session.thread_id||!state.session.turn_id)throw Error("DIAGNOSTIC_NATIVE_IDENTITY_UNBOUND");
    result.native_context=await sqliteSnapshot(dbPath,db=>{
      const thread=state.session.thread_id,turn=state.session.turn_id;
      const row=db.prepare("SELECT status,last_seen_at,runtime_payload_json FROM provider_session_runtime WHERE thread_id=?").get(thread);
      const payload=row?JSON.parse(row.runtime_payload_json||"{}"):{};
      const turns=db.prepare("SELECT turn_id,state,requested_at,started_at,completed_at,termination_origin FROM projection_turns WHERE thread_id=? AND turn_id=?").all(thread,turn);
      const events=[];
      for(const e of db.prepare("SELECT sequence,event_type,occurred_at,actor_kind,command_id,payload_json FROM orchestration_events WHERE aggregate_kind='thread' AND stream_id=? ORDER BY sequence DESC LIMIT 150").iterate(thread)) {
        const p=JSON.parse(e.payload_json),kind=p.activity?.kind;
        if(!e.event_type.includes("interrupt")&&!["runtime.error","turn.completed","turn.aborted"].includes(kind))continue;
        events.push({sequence:e.sequence,event_type:e.event_type,occurred_at:e.occurred_at,
          actor_kind:e.actor_kind,command_id:e.command_id,activity_kind:kind,
          error:redactDiagnosticText(p.activity?.payload?.message||"").slice(0,1000)});
      }
      return {thread_id:thread,turn_id:turn,turns,runtime:row?{status:row.status,last_seen_at:row.last_seen_at,
        lastRuntimeEvent:payload.lastRuntimeEvent,lastRuntimeEventAt:payload.lastRuntimeEventAt}:null,events};
    });
  } catch(error){result.unavailable.push({source:"native-state",reason:redactDiagnosticText(error.message).slice(0,300)});}
  const kernel=join(dirname(dbPath),"..","acode-home-overlay","logs_2.sqlite");
  try {
    const epoch=Math.floor(Date.parse(center)/1000);
    result.kernel=await sqliteSnapshot(kernel,db=>{
      const rows=[];let bytes=0,read=0;
      const columns="id,ts,ts_nanos,level,target,thread_id,process_uuid,file,line,feedback_log_body";
      const seen=new Set();
      const queries=state.session.session_id?[
        [`SELECT ${columns} FROM logs WHERE thread_id=? ORDER BY ts DESC,ts_nanos DESC,id DESC LIMIT 500`,[state.session.session_id],500],
      ]:[];
      queries.push([`SELECT ${columns} FROM logs WHERE ts BETWEEN ? AND ? ORDER BY ts,ts_nanos,id LIMIT 5000`,[epoch-120,epoch+120],5000]);
      let truncated=false;
      for(const [sql,args,limit] of queries) {
       let count=0;
       for(const row of db.prepare(sql).iterate(...args)) {
        if(++count>=limit)truncated=true;
        read++;bytes+=Buffer.byteLength(row.feedback_log_body||"");
        if(bytes>16*1024*1024){truncated=true;break;}
        if(seen.has(row.id))continue;seen.add(row.id);
        const projected=projectKernelDiagnostic(row);
        if(projected&&rows.length<300)rows.push(projected);
        else if(projected)truncated=true;
       }
      }
      return {source:kernel,center,rows_examined:read,raw_byte_budget:16*1024*1024,truncated,rows,
        limitation:"Retained kernel logs are capped by the client; missing rows do not prove missing actions."};
    });
  } catch(error){result.unavailable.push({source:"kernel-logs",reason:redactDiagnosticText(error.message).slice(0,300)});}
  return result;
}

export async function captureRuntimeDiagnostics(config,state,{reason="observation",force=false,nativeSession=null,
  intervalMs=30_000,maxBytes=16*1024*1024,processSnapshot=snapshotDarwinTaskProcesses,readConfig=readRuntimeConfig,
  databases=captureDatabases}={}) {
  const started=process.hrtime.bigint();
  const attempt=diagnosticAttempt(state),relativeIndex=`diagnostics/${attempt}/index.json`;
  const base=join(dirname(config.stateFile),"diagnostics");
  await mkdir(base,{recursive:true});
  if((await lstat(base)).isSymbolicLink())throw Error("DIAGNOSTIC_DIRECTORY_SYMLINK");
  const root=join(base,attempt);
  await mkdir(root,{recursive:true});
  if((await lstat(root)).isSymbolicLink())throw Error("DIAGNOSTIC_DIRECTORY_SYMLINK");
  const indexPath=join(root,"index.json");
  let index;
  try{index=JSON.parse(await readFile(indexPath,"utf8"));}catch(error){if(error.code!=="ENOENT")throw error;}
  index ||= {schema_version:DIAGNOSTIC_SCHEMA,identity:state.identity,files:[],captures:[],cursors:{},max_bytes:maxBytes,
    auxiliary_only:true,redacted:true,native_cause_inferred:false};
  if(JSON.stringify(index.identity)!==JSON.stringify(state.identity))throw Error("DIAGNOSTIC_IDENTITY_DRIFT");
  const now=new Date().toISOString();
  if(!force&&Date.parse(now)-Date.parse(index.last_capture_at||0)<intervalMs)return {index_path:relativeIndex,index_sha256:hash(await readFile(indexPath))};
  if(force&&index.last_forced_reason===reason&&Date.parse(now)-Date.parse(index.last_forced_at||0)<60_000)
    return {index_path:relativeIndex,index_sha256:hash(await readFile(indexPath))};
  const total=index.files.reduce((n,f)=>n+f.size,0);
  if(total>=maxBytes&&!force)index.skipped_budget=(index.skipped_budget||0)+1;
  let emergency=force;
  const capture={id:randomUUID(),at:now,reason,framework_pid:process.pid,unavailable:[],native_session:nativeSession?{
    thread_id:nativeSession.thread_id,turn_id:nativeSession.turn_id,status:nativeSession.status,
    completed_at:nativeSession.completed_at}:null};
  capture.framework_resources={rss_bytes:process.memoryUsage().rss,cpu_usage_us:process.cpuUsage(),
    system_free_memory_bytes:freemem(),system_load_average:loadavg()};
  let runtime;
  try{runtime=await readConfig(state);}
  catch(error){capture.unavailable.push({source:"run-config",reason:redactDiagnosticText(error.message).slice(0,300)});}
  async function store(name,value) {
    const bytes=Buffer.from(json(value));
    // A terminal capture has a separate small reserve after periodic budget is reached.
    if(total+bytes.length>maxBytes+(emergency?2*1024*1024:0)){capture.unavailable.push({source:name,reason:"diagnostic-output-budget"});return;}
    await writeFile(join(root,name),bytes,{mode:0o600});
    index.files=index.files.filter(x=>x.path!==name);index.files.push({path:name,size:bytes.length,sha256:hash(bytes)});
  }
  try{capture.processes=await processSnapshot(config.candidateWorkspace);}
  catch(error){capture.unavailable.push({source:"process-snapshot",reason:redactDiagnosticText(error.message).slice(0,300)});}
  if(runtime) {
    const logs=join(dirname(runtime.state_database.path),"logs");
    const files=["desktop-main.log","server-child.log","server.log","provider/events.log"].flatMap(x=>[x+".2",x+".1",x]);
    const markers=[];
    for(const name of files) {
      const path=join(logs,name);
      let handle;
      try {
        if((await lstat(path)).isSymbolicLink())throw Error("DIAGNOSTIC_LOG_SYMLINK");
        handle=await open(path,"r");const info=await handle.stat();
        const cursor=Object.values(index.cursors).find(c=>c.inode===info.ino&&c.device===info.dev
          &&c.birthtime_ms===info.birthtimeMs&&info.size>=c.offset);
        const same=Boolean(cursor);
        const from=same?cursor.offset:index.last_capture_at?0:Math.max(0,info.size-256*1024);
        const start=Math.max(from,info.size-4*1024*1024),buffer=Buffer.alloc(info.size-start);
        const read=await handle.read(buffer,0,buffer.length,start);
        let chunk=buffer.subarray(0,read.bytesRead),offset=start;
        // A tail window can start in the middle of a secret or UTF-8 sequence.
        // Never publish that unlabelled fragment. Resume only after full LF.
        let skipPartial=false;
        if(start>0&&(!same||start>from||cursor?.skip_partial)) {
          const first=chunk.indexOf(10);
          if(first<0){capture.unavailable.push({source:path,reason:"oversized-partial-log-line"});chunk=Buffer.alloc(0);offset=info.size;skipPartial=true;}
          else{chunk=chunk.subarray(first+1);offset+=first+1;}
        }
        const last=chunk.lastIndexOf(10);
        if(last<0)chunk=Buffer.alloc(0);
        else chunk=chunk.subarray(0,last+1);
        for(const line of chunk.length?chunk.subarray(0,chunk.length-1).toString("utf8").split("\n"):[]) {
          if(signalMarkers.test(line))markers.push({source:path,inode:info.ino,source_byte_offset:offset,
            source_line:null,excerpt:redactDiagnosticText(line).slice(0,2048),original_line_sha256:hash(line)});
          offset+=Buffer.byteLength(line)+1;
        }
        if(start>from)capture.unavailable.push({source:path,reason:"log-delta-budget",omitted_bytes:start-from});
        index.cursors[name]={inode:info.ino,device:info.dev,birthtime_ms:info.birthtimeMs,
          offset:offset>info.size?info.size:offset,skip_partial:skipPartial,at:now};
      } catch(error){if(error.code!=="ENOENT"||!/[.]\d$/u.test(name))
        capture.unavailable.push({source:path,reason:error.code==="ENOENT"?"log-source-not-found":redactDiagnosticText(error.message).slice(0,300)});}
      finally{await handle?.close();}
    }
    capture.log_markers=markers.slice(-100);
    if(markers.length>100)capture.unavailable.push({source:"log-markers",reason:"marker-count-budget",omitted:markers.length-100});
    const processKey=JSON.stringify(capture.processes?.infrastructure_roots?.map(x=>[x.pid,x.started_at,x.command_sha256]).sort()||[]);
    const processChanged=index.native_process_key!==undefined&&index.native_process_key!==processKey;
    const alarms=markers.filter(x=>/backend exited|APP SESSION END|abandoning stalled|turn\/interrupt|invalidated|server\.shutdown|transport.*(?:failed|closed)/iu.test(x.excerpt));
    const unseen=alarms.filter(x=>!(index.alarm_hashes||[]).includes(x.original_line_sha256));
    index.alarm_hashes=[...(index.alarm_hashes||[]),...unseen.map(x=>x.original_line_sha256)].slice(-200);
    index.native_process_key=processKey;
    if(force||processChanged||unseen.length) {
      emergency=true;
      capture.escalation={forced:force,process_identity_changed:processChanged,new_alarm_count:unseen.length};
      capture.databases=await databases(runtime,state,nativeSession?.completed_at||state.execution.finished_at||now);
    }
  } else capture.unavailable.push({source:"run-config",reason:"frozen-runtime-config-unavailable"});
  capture.finished_at=new Date().toISOString();
  capture.duration_ms=Number(process.hrtime.bigint()-started)/1e6;
  await store(capture.id+".json",capture);
  index.captures.push({id:capture.id,at:now,reason,unavailable:capture.unavailable});
  if(index.captures.length>500)index.captures=index.captures.slice(-500);
  index.last_capture_at=now;
  if(force){index.last_forced_at=now;index.last_forced_reason=reason;}
  await atomicJson(indexPath,index);
  return {index_path:relativeIndex,index_sha256:hash(await readFile(indexPath))};
}

export async function loadDiagnosticArtifacts(state,stateFile) {
  const ref=state.evidence?.runtime_diagnostics;
  if(!ref)return [];
  const attempt=diagnosticAttempt(state),base=resolve(dirname(stateFile),"diagnostics",attempt),path=resolve(dirname(stateFile),ref.index_path);
  if(path!==join(base,"index.json"))throw Error("DIAGNOSTIC_INDEX_OUTSIDE_ATTEMPT");
  if((await lstat(base)).isSymbolicLink()||(await lstat(path)).isSymbolicLink())throw Error("DIAGNOSTIC_SYMLINK");
  if((await lstat(path)).size>4*1024*1024)throw Error("DIAGNOSTIC_INDEX_SIZE_BUDGET");
  const bytes=await readFile(path);
  if(hash(bytes)!==ref.index_sha256)throw Error("DIAGNOSTIC_INDEX_HASH_MISMATCH");
  const index=JSON.parse(bytes);
  if(index.schema_version!==DIAGNOSTIC_SCHEMA||JSON.stringify(index.identity)!==JSON.stringify(state.identity))throw Error("DIAGNOSTIC_INDEX_BINDING_INVALID");
  const result=[{path,relative:attempt+"/index.json",bytes}];
  for(const item of index.files) {
    const name=String(item.path);
    if(relative(base,resolve(base,name))!==name||name.includes("/")||name.includes("\\"))throw Error("DIAGNOSTIC_FILE_OUTSIDE_ATTEMPT");
    const file=join(base,name),info=await lstat(file);
    if(!info.isFile()||info.isSymbolicLink()||info.size>18*1024*1024)throw Error("DIAGNOSTIC_SYMLINK_OR_SIZE");
    const data=await readFile(file);
    if(data.length!==item.size||hash(data)!==item.sha256)throw Error("DIAGNOSTIC_FILE_HASH_MISMATCH");
    result.push({path:file,relative:attempt+"/"+name,bytes:data});
  }
  return result;
}

export async function loadFrameworkAuditArtifacts(unitRoot) {
  const path=join(resolve(unitRoot),".general-e2e","diagnostics","framework-events.jsonl");
  let handle;
  try {
    const info=await lstat(path);
    if(!info.isFile()||info.isSymbolicLink()||info.size>33*1024*1024)throw Error("DIAGNOSTIC_FRAMEWORK_JOURNAL_UNSAFE");
    handle=await open(path,"r");
    // Freeze a bounded prefix. Concurrent later appends remain in the original
    // journal; drop any unfinished last line and disclose the exact boundary.
    const buffer=Buffer.alloc(info.size);let count=0;
    while(count<buffer.length) {
      const read=await handle.read(buffer,count,buffer.length-count,count);
      if(!read.bytesRead)break;count+=read.bytesRead;
    }
    const observed=buffer.subarray(0,count),end=observed.lastIndexOf(10)+1,bytes=observed.subarray(0,end);
    const provenance=Buffer.from(json({schema_version:"wildclawbench.astudio-framework-audit-snapshot/v1",
      source:path,captured_at:new Date().toISOString(),source_inode:info.ino,source_device:info.dev,
      source_observed_size:info.size,captured_read_bytes:count,retained_bytes:bytes.length,
      retained_sha256:hash(bytes),source_start_line:1,retained_lines:bytes.reduce((n,b)=>n+(b===10),0),
      trailing_incomplete_bytes:observed.length-end,later_appends_included:false,auxiliary_only:true}));
    return [{path,relative:"framework-events.jsonl",bytes},
      {path,relative:"framework-events-source.json",bytes:provenance}];
  } catch(error){if(error.code==="ENOENT")return [];throw error;}
  finally{await handle?.close();}
}

export async function captureStandaloneDiagnostics({unitRoot,stateFile,outputDir,reason="manual-read-only"}) {
  const root=resolve(unitRoot),source=resolve(stateFile),target=resolve(outputDir);
  const rel=relative(root,source);
  if(!rel||rel.startsWith("..")||rel.startsWith("/"))throw Error("DIAGNOSTIC_STATE_OUTSIDE_UNIT");
  if(!(await lstat(source)).isFile())throw Error("DIAGNOSTIC_STATE_NOT_REGULAR_FILE");
  const bytes=await readFile(source),state=JSON.parse(bytes);
  const manifest=JSON.parse(await readFile(join(root,"manifest.json"),"utf8"));
  if(state.identity?.batch_id!==manifest.batch_id||state.identity?.unit_id!==manifest.unit_id
      ||!manifest.task_ids.includes(state.identity.task_id))throw Error("DIAGNOSTIC_UNIT_BINDING_INVALID");
  const candidate=resolve(state.candidate_workspace);
  if(target===candidate||!relative(candidate,target).startsWith(".."))throw Error("DIAGNOSTIC_OUTPUT_IN_CANDIDATE");
  await mkdir(target,{recursive:false,mode:0o700});
  await writeFile(join(target,"source-state.json"),bytes,{flag:"wx",mode:0o600});
  const ref=await captureRuntimeDiagnostics({unitRoot:root,stateFile:join(target,"source-state.json"),
    candidateWorkspace:candidate},state,{reason,force:true});
  const receipt={schema_version:"wildclawbench.astudio-diagnostic-capture/v1",identity:state.identity,
    source_state:source,source_state_sha256:hash(bytes),output_root:target,diagnostics:ref,
    read_only:true,harness_started:false,prompt_sent:false,score_changed:false};
  await writeFile(join(target,"receipt.json"),json(receipt),{flag:"wx",mode:0o600});
  return receipt;
}
