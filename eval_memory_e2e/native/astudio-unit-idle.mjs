/** A scope's own native sessions and job status only. Never submits or edits. */
import {readFile,readdir,realpath,mkdir} from 'node:fs/promises';
import {dirname} from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
import {staleRunningProjectionHasTerminalWitness} from './astudio-bound-continuation.mjs';
import {queryNativeSessions} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';
import {isBlockingActiveSession} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';
let spec=JSON.parse(await readFile(process.argv[2],'utf8'));
const continuation=spec.contract==='astudio-memory-unit-continuation/v1';
if(spec.contract==='astudio-memory-unit-continuation/v1'){
  const bytes=await readFile(spec.origin_scope),base=JSON.parse(bytes);
  if(spec.diagnostic_only!==true||createHash('sha256').update(bytes).digest('hex')!==spec.origin_scope_sha256
    ||base.unit_id!==spec.unit_id||JSON.stringify(base.paths)!==JSON.stringify(spec.paths))throw Error('UNIT_IDLE_CONTINUATION_DRIFT');
  spec=base;
}
if(spec.contract!=='astudio-case-memory-unit/v1')throw Error('UNIT_IDLE_SCOPE');
const privateTmp=dirname(process.argv[2])+'/control/idle-tmp';
await mkdir(privateTmp,{recursive:true,mode:0o700});
process.env.TMPDIR=privateTmp;
const sessions=await queryNativeSessions(spec.paths.astudio_db);
const jobs=[];
for(const root of [spec.paths.acode,spec.paths.overlay]){
  for(const name of await readdir(root)){
    if(!/^(state|memories)_\d+\.sqlite$/.test(name))continue;
    const file=await realpath(root+'/'+name);
    if(!file.startsWith(spec.paths.runtime+'/'))throw Error('UNIT_SQLITE_OUTSIDE_SCOPE');
    if(jobs.some(x=>x.path===file))continue;
    const db=new DatabaseSync(file,{readOnly:true});
    try{
      const tables=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'").all();
      if(tables.length){
        const columns=db.prepare('PRAGMA table_info(jobs)').all().map(x=>x.name);
        if(!columns.includes('status')||!columns.includes('lease_until'))throw Error('UNIT_JOBS_SCHEMA_UNVERIFIED');
        const rows=db.prepare('SELECT status,COUNT(*) AS count FROM jobs GROUP BY status').all();
        if(rows.some(x=>!['pending','running','done','error'].includes(x.status)))throw Error('UNIT_JOB_STATUS_UNVERIFIED');
        const active=db.prepare("SELECT COUNT(*) AS count FROM jobs WHERE status='running' OR lease_until>?").get(Math.floor(Date.now()/1000));
        jobs.push({path:file,statuses:rows,running:Number(active.count),lease_checked:true});
      }
    }finally{db.close()}
  }
}
const terminalWitnesses=[];
if(continuation){
  for(const row of sessions.filter(isBlockingActiveSession)){
    const matches=[];
    for(const home of [spec.paths.acode,spec.paths.overlay])for(const name of await readdir(home)){
      if(!/^state_\d+\.sqlite$/.test(name))continue;
      const db=new DatabaseSync(home+'/'+name,{readOnly:true});
      try{matches.push(...db.prepare('SELECT rollout_path FROM threads WHERE id=?').all(row.session_id))}finally{db.close()}
    }
    if(matches.length!==1)continue;
    const file=await realpath(matches[0].rollout_path);
    if(![spec.paths.acode,spec.paths.overlay].some(home=>file.startsWith(home+'/sessions/')))throw Error('UNIT_IDLE_ROLLOUT_OUTSIDE_SCOPE');
    const bytes=await readFile(file),events=bytes.toString('utf8').trim().split(/\r?\n/).map(s=>JSON.parse(s));
    if(staleRunningProjectionHasTerminalWitness(row,events))terminalWitnesses.push({thread_id:row.thread_id,turn_id:row.turn_id,
      source_path:file,sha256:createHash('sha256').update(bytes).digest('hex'),basis:'native task_complete plus completed latest turn, ready session and no active turn'});
  }
}
const blocking=sessions.filter(row=>isBlockingActiveSession(row)&&!terminalWitnesses.some(t=>t.thread_id===row.thread_id)).length;
console.log(JSON.stringify({unit_id:spec.unit_id,at:new Date().toISOString(),native_session_count:sessions.length,
  blocking_session_count:blocking,terminal_witnesses:terminalWitnesses,jobs,running_jobs:jobs.reduce((n,x)=>n+x.running,0),source_database_write:false,
  idle:blocking===0&&jobs.every(x=>x.running===0)}));
