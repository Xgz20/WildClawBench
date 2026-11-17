import {createHash} from 'node:crypto';
import {open} from 'node:fs/promises';
import {join} from 'node:path';

export const PRETRANSPORT_ABORT_SOURCE = 'a4d6617fed907d07ca23ffc65b0052a938be0e08d6580476ea58027d38aa0413';
export const ADAPTER_ATTESTATION = 'astudio-fenced-pretransport-source/v1';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

// Read only. The allowlisted module has a timeout guarded by !submitted and
// an abort check after onSubmit, before empty-prewarm clearing / RPC writing.
// No unknown source or generic possibly-submitted record is accepted.
export async function readAdapterAttestation(appPath,processIdentity=null) {
  if(typeof appPath!=='string'||!appPath)return null;
  const path=join(appPath,'Contents/Resources/app.asar');
  let handle;
  try {
    handle=await open(path,'r');
    const before=await handle.stat(),prefix=Buffer.alloc(16);
    if ((await handle.read(prefix,0,16,0)).bytesRead!==16 || prefix.readUInt32LE(0)!==4) return null;
    const pickle=prefix.readUInt32LE(4),length=prefix.readUInt32LE(12);
    if(length<=0||length>16*1024*1024||pickle<length+8||8+pickle>=before.size)return null;
    const header=Buffer.alloc(length);
    if((await handle.read(header,0,length,16)).bytesRead!==length)return null;
    let entry=JSON.parse(header.toString('utf8'));
    for(const part of ['apps','server','dist','index.mjs'])entry=entry.files?.[part];
    if(!entry||entry.unpacked||entry.link||!/^[0-9]+$/u.test(entry.offset)
        ||!Number.isSafeInteger(entry.size)||entry.size<=0||entry.size>32*1024*1024
        ||entry.integrity?.algorithm!=='SHA256'||entry.integrity.hash!==PRETRANSPORT_ABORT_SOURCE)return null;
    const offset=8+pickle+Number(entry.offset);
    if(!Number.isSafeInteger(offset)||offset<8+pickle||offset+entry.size>before.size)return null;
    const source=Buffer.alloc(entry.size);
    if((await handle.read(source,0,source.length,offset)).bytesRead!==source.length
        ||sha(source)!==PRETRANSPORT_ABORT_SOURCE)return null;
    const after=await handle.stat();
    if(before.ino!==after.ino||before.size!==after.size||before.mtimeMs!==after.mtimeMs)return null;
    return {schema_version:ADAPTER_ATTESTATION,app_path:appPath,asar_size:before.size,
      asar_inode:String(before.ino),asar_modified_at:before.mtime.toISOString(),
      observed_at:new Date().toISOString(),server_entry:'apps/server/dist/index.mjs',
      server_entry_sha256:PRETRANSPORT_ABORT_SOURCE,asar_header_sha256:sha(header),
      ...(processIdentity?.identity_verified&&processIdentity.running?{main_process:{
        pid:processIdentity.pid,started_at:processIdentity.started_at,
        executable_path:processIdentity.executable_path,command_sha256:processIdentity.command_sha256}}:{}),
      source_executed:false,native_files_modified:false};
  } catch {return null;} finally {await handle?.close();}
}

export function attestedPretransportAbort(source,state) {
  const process=source?.main_process;
  return source?.schema_version===ADAPTER_ATTESTATION&&source.app_path==='/Applications/AStudio.app'
    &&source.server_entry==='apps/server/dist/index.mjs'&&source.server_entry_sha256===PRETRANSPORT_ABORT_SOURCE
    &&/^[0-9a-f]{64}$/u.test(source.asar_header_sha256)&&source.source_executed===false
    &&Number.isSafeInteger(source.asar_size)&&source.asar_size>0&&/^[0-9]+$/u.test(source.asar_inode)
    &&source.native_files_modified===false&&state.client?.version==='3.6.4'
    &&Number.isSafeInteger(process?.pid)&&process.pid>0
    &&process.executable_path==='/Applications/AStudio.app/Contents/MacOS/AStudio'
    &&/^[0-9a-f]{64}$/u.test(process.command_sha256)&&Number.isFinite(Date.parse(process.started_at))
    &&Number.isFinite(Date.parse(source.observed_at))&&Number.isFinite(Date.parse(source.asar_modified_at))
    &&Date.parse(source.asar_modified_at)<Date.parse(process.started_at)
    &&Date.parse(process.started_at)<Date.parse(state.send.dispatch_armed_at)
    &&Date.parse(source.observed_at)>=Date.parse(state.send.dispatch_completed_at);
}
