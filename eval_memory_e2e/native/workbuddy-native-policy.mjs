/* Append mandatory denies without replacing WorkBuddy's native SBPL or grants.
 * Every profile cache is bound to one socket, OS peer, native session and revision.
 */
import path from 'node:path';
import crypto from 'node:crypto';
import {StringDecoder} from 'node:string_decoder';
import net from 'node:net';
import fs from 'node:fs';

const hash=text=>crypto.createHash('sha256').update(text).digest('hex');
const record=value=>value&&typeof value==='object'&&!Array.isArray(value);
const check=(ok,reason)=>{if(!ok)throw Error(reason)};
const FETCH='sandbox.rules.fetch_profile';

function userPath(value) {
  check(typeof value==='string'&&value.startsWith('/Users/')&&path.posix.normalize(value)===value
    &&!value.endsWith('/')&&!/[\x00-\x1f\x7f"\\]/.test(value),'WB_POLICY_DENY_PATH');
  return value;
}

export function centerCoordinationPaths(appHome,socketPath) {
  userPath(appHome);check(/^\/tmp\/wcbm-wb-[a-f0-9]+\.sock$/.test(socketPath),'WB_POLICY_CENTER_SOCKET');
  const fnv=value=>{let state=0xcbf29ce484222325n;for(const byte of Buffer.from(value))state=BigInt.asUintN(64,(state^BigInt(byte))*0x100000001b3n);
    return state.toString(16).padStart(16,'0')};
  return [socketPath,'/tmp/workbuddy-sandbox-center-epoch-'+fnv(socketPath)+'.lock',
    '/tmp/workbuddy-sandbox-center-'+fnv(appHome)+'.lock'];
}

export function buildUnitMemoryRules({debugRoot,allowedPaths,readLiterals=[],writeLiterals=[]}) {
  userPath(debugRoot);
  check(Array.isArray(allowedPaths)&&allowedPaths.length>0&&allowedPaths.length<=8
    &&Array.isArray(readLiterals)&&readLiterals.length<=16&&Array.isArray(writeLiterals)&&writeLiterals.length<=4,'WB_POLICY_UNIT_PATHS');
  // A trusted Center may create its one owned IPC socket. Data-worker policy
  // rejects this option below and never receives a writable control endpoint.
  for(const value of writeLiterals)check(/^\/tmp\/(?:wcbm-wb-[a-z-]*[a-f0-9]+\.sock|workbuddy-sandbox-center-(?:epoch-)?[a-f0-9]{16}\.lock)$/.test(value),'WB_POLICY_UNIT_IPC_LITERAL');
  for(const value of [...allowedPaths,...readLiterals])
    check(userPath(value).startsWith(debugRoot+'/'),'WB_POLICY_UNIT_ROOT');
  const aliases=values=>values.flatMap(p=>[p,'/System/Volumes/Data'+p]);
  const predicate=(kind,value)=>'('+kind+' '+JSON.stringify(value)+')';
  const pathExclusions=aliases(allowedPaths).map(p=>'(require-not '+predicate('subpath',p)+')');
  const ancestors=new Set();
  for(const value of [...allowedPaths,...readLiterals]){
    let parent=path.posix.dirname(value);
    while(parent===debugRoot||parent.startsWith(debugRoot+'/')){ancestors.add(parent);if(parent===debugRoot)break;parent=path.posix.dirname(parent)}
  }
  const metadata=aliases([...ancestors]);
  const readExclusions=[...pathExclusions,...aliases(readLiterals).map(p=>'(require-not '+predicate('literal',p)+')'),
    ...metadata.map(p=>'(require-not '+predicate('literal',p)+')')].join('\n');
  const read=aliases([debugRoot]).map(p=>'(require-all '+predicate('subpath',p)+'\n'+readExclusions+')').join('\n');
  const writes=[...pathExclusions,...writeLiterals.flatMap(p=>[p,'/private'+p]).map(p=>'(require-not '+predicate('literal',p)+')'),
    '(require-not (literal "/dev/null"))','(require-not (literal "/dev/tty"))'].join('\n');
  return ['(deny file-read*\n'+read+')','(deny file-read-data\n'+metadata.map(p=>predicate('literal',p)).join('\n')+')',
    '(deny file-write* (require-all\n'+writes+'))'];
}

export class NativeProfileBinding {
  constructor({uid,peerPid,deniedRoots,memoryUnit=null,audit=()=>{}}) {
    check(typeof uid==='string'&&uid.length>0&&Number.isSafeInteger(peerPid)&&peerPid>0,'WB_POLICY_IDENTITY');
    check(Array.isArray(deniedRoots)&&deniedRoots.length>0&&deniedRoots.length<=256,'WB_POLICY_DENIES');
    for(const root of deniedRoots)userPath(root);
    this.uid=uid;this.peerPid=peerPid;this.deniedRoots=Object.freeze([...new Set(deniedRoots)]);
    check(!memoryUnit?.writeLiterals?.length,'WB_POLICY_DATA_WORKER_CONTROL_SOCKET');
    this.unitRules=memoryUnit?buildUnitMemoryRules(memoryUnit):[];
    this.pending=new Map();this.profiles=new Map();this.audit=audit;this.highestRevision=-1;
  }
  request(message) {
    check(record(message)&&message.uid===this.uid,'WB_POLICY_UID');
    check(typeof message.messageId==='string'&&message.messageId.length>0&&message.messageId.length<=256
      &&!this.pending.has(message.messageId)&&this.pending.size<256,'WB_POLICY_REQUEST_ID');
    check(typeof message.command==='string'&&message.command.startsWith('sandbox.')&&record(message.data),'WB_POLICY_REQUEST');
    if(message.data._client?.pid!==undefined)
      check(message.data._client.pid===this.peerPid,'WB_POLICY_CLAIMED_PID');
    let key=null;
    if(message.command===FETCH) {
      const session=message.data.sessionId;
      check(typeof session==='string'&&session.length>0&&session.length<=512
        &&(message.sessionId===undefined||message.sessionId===session),'WB_POLICY_SESSION');
      check(message.data.platform==='macos','WB_POLICY_PLATFORM');
      key=JSON.stringify([session,message.data.platform]);
    }
    this.pending.set(message.messageId,{command:message.command,key});
    this.audit({event:'request',command:message.command,peer_pid:this.peerPid,
      session_id:message.sessionId??null,profile_key:key});
  }
  response(message) {
    check(record(message)&&this.pending.has(message.messageId),'WB_POLICY_UNBOUND_RESPONSE');
    const request=this.pending.get(message.messageId);this.pending.delete(message.messageId);
    if(request.command!==FETCH||message.success!==true)return {message,changed:false};
    const data=message.data;
    check(record(data)&&Number.isSafeInteger(data.serverRevision)&&data.serverRevision>=this.highestRevision,'WB_POLICY_REVISION');
    this.highestRevision=data.serverRevision;
    if(data.upToDate===true&&!data.profile) {
      const binding=this.profiles.get(request.key);
      check(binding?.revision===data.serverRevision,'WB_POLICY_UNBOUND_CACHE');
      this.audit({event:'cached_profile_verified',peer_pid:this.peerPid,key:request.key,revision:binding.revision,
        composed_sha256:binding.sha256});
      return {message,changed:false};
    }
    check(typeof data.profile==='string'&&data.profile.length>0&&record(data.execParams),'WB_POLICY_PROFILE');
    const original=data.profile,rules=JSON.parse(original);
    check(Array.isArray(rules)&&rules.length>0&&rules.every(x=>typeof x==='string'),'WB_POLICY_NATIVE_FRAGMENTS');
    const escaped=rules.some(x=>x.includes('\\"'));
    const added=[...this.deniedRoots.map(root=>'(deny file-read* file-write* (subpath '+JSON.stringify(root)+'))'),...this.unitRules]
      .map(rule=>escaped?rule.replaceAll('"','\\"'):rule);
    const end=original.lastIndexOf(']');
    check(end>=0,'WB_POLICY_PROFILE_END');
    const combined=original.slice(0,end)+','+added.map(x=>JSON.stringify(x)).join(',')+original.slice(end);
    check(JSON.stringify(JSON.parse(combined).slice(0,rules.length))===JSON.stringify(rules),'WB_POLICY_FRAGMENT_MUTATION');
    const oldDenies=data.execParams.deniedReadPaths??[];
    check(Array.isArray(oldDenies)&&oldDenies.every(x=>typeof x==='string'),'WB_POLICY_EXEC_DENIES');
    const output={...message,data:{...data,profile:combined,execParams:{...data.execParams,
      deniedReadPaths:[...new Set([...oldDenies,...this.deniedRoots.map(x=>x+'/**')])]}}};
    const fingerprint=hash(combined);
    this.profiles.set(request.key,{revision:data.serverRevision,sha256:fingerprint});
    this.audit({event:'profile_composed',peer_pid:this.peerPid,key:request.key,revision:data.serverRevision,
      original_sha256:hash(original),composed_sha256:fingerprint,original_native_fragments_preserved:true,
      controller_grants_appended:false,mandatory_denies:this.deniedRoots,memory_unit_rules:this.unitRules.length});
    return {message:output,changed:true};
  }
}

export async function startNativeProfileProxy({socketPath,upstreamPath,authorize,assertFrozen,uid,deniedRoots,memoryUnit=null,audit}) {
  for(const value of [socketPath,upstreamPath])check(/^\/tmp\/wcbm-wb-[a-z-]*[a-f0-9]+\.sock$/.test(value),'WB_POLICY_SOCKET');
  check(socketPath!==upstreamPath&&!fs.existsSync(socketPath),'WB_POLICY_FRESH_SOCKET');
  const sockets=new Set();
  const server=net.createServer(front=>{
    let upstream,binding;
    const reject=error=>{audit({event:'connection_rejected',reason:String(error.message)});front.destroy();upstream?.destroy()};
    try {
      assertFrozen();const peer=authorize(front);
      check(record(peer)&&Number.isSafeInteger(peer.pid)&&peer.pid>0,'WB_POLICY_PEER');
      binding=new NativeProfileBinding({uid,peerPid:peer.pid,deniedRoots,memoryUnit,audit});
      upstream=net.createConnection(upstreamPath);sockets.add(front);sockets.add(upstream);
      audit({event:'connection_authorized',peer});
    }catch(error){reject(error);return}
    function lines(socket,consume) {
      const decoder=new StringDecoder('utf8');let pending='';
      socket.on('data',bytes=>{
        try{
          pending+=decoder.write(bytes);check(Buffer.byteLength(pending)<=16*1024*1024,'WB_POLICY_FRAME_SIZE');
          let at;
          while((at=pending.indexOf('\n'))>=0){const line=pending.slice(0,at);pending=pending.slice(at+1);
            check(line.trim().length>0,'WB_POLICY_EMPTY_FRAME');assertFrozen();consume(line,JSON.parse(line));}
        }catch(error){reject(error)}
      });
      socket.on('end',()=>{if(pending.length||decoder.end().length)reject(Error('WB_POLICY_TRUNCATED_FRAME'));else socket===front?upstream.end():front.end()});
    }
    lines(front,(raw,message)=>{binding.request(message);upstream.write(raw+'\n')});
    lines(upstream,(raw,message)=>{const output=binding.response(message);front.write((output.changed?JSON.stringify(output.message):raw)+'\n')});
    for(const socket of [front,upstream]){
      socket.on('error',reject);
      socket.on('close',()=>{sockets.delete(socket);front.destroy();upstream.destroy()});
    }
  });
  await new Promise((ok,no)=>{server.once('error',no);server.listen(socketPath,ok)});
  fs.chmodSync(socketPath,0o600);
  return {async close(){for(const socket of sockets)socket.destroy();await new Promise(ok=>server.close(ok))}};
}
