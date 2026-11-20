// Trusted actual synchronous module replay. VM is an execution boundary, not an OS sandbox.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {stripTypeScriptTypes} from 'node:module';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const [root,requestPath,responsePath,python]=process.argv.slice(2);
const req=JSON.parse(fs.readFileSync(requestPath,'utf8'));
const hash=b=>createHash('sha256').update(b).digest('hex');
const source=Object.fromEntries(['api.py','store.ts','view.ts'].map(n=>[n,fs.readFileSync(path.join(root,'project',n))]));
const hashes=Object.fromEntries(Object.entries(source).map(([n,b])=>['project/'+n,hash(b)]));
const clone=x=>JSON.parse(JSON.stringify(x));
class Unsupported extends Error {}
function typed(e){return e instanceof Unsupported||e.code==='ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX'||e.code==='ERR_SCRIPT_EXECUTION_TIMEOUT';}
function serializeError(e){return {status:typed(e)?'unassessed':'candidate_error',error:String(e.code||e.name)+': '+String(e.message)};}
async function load(){
 const context=vm.createContext(undefined,{name:'h050-JSON-function-realm',codeGeneration:{strings:false,wasm:false}});
 const modules=new Map();
 for(const name of ['store.ts','view.ts']){
  const code=stripTypeScriptTypes(source[name].toString('utf8'),{mode:'strip'});
  const mod=new vm.SourceTextModule(code,{context,identifier:name,importModuleDynamically(){throw new Unsupported('dynamic import outside synchronous profile');}});
  modules.set(name,mod);
 }
 const link=async(specifier)=>{
  if(!['./store.ts','./view.ts','./store','./view'].includes(specifier))throw new Unsupported('external module outside profile: '+specifier);
  return modules.get(specifier.slice(2).replace(/^(store|view)$/, '$1.ts'));
 };
 for(const mod of modules.values())if(mod.status==='unlinked')await mod.link(link);
 for(const mod of modules.values())if(mod.status==='linked')await mod.evaluate({timeout:700});
 context.__store=modules.get('store.ts').namespace;context.__view=modules.get('view.ts').namespace;
 const run=code=>new vm.Script(code).runInContext(context,{timeout:700});
 if(run('[__store.createState,__store.reduce,__store.getSnapshot,__view.present].some(f=>typeof f==="function"&&["AsyncFunction","AsyncGeneratorFunction"].includes(f.constructor.name))'))throw new Unsupported('async export outside synchronous profile');
 const input=x=>{context.__inputJSON=JSON.stringify(x);run('globalThis.__input=JSON.parse(__inputJSON)');};
 return {context,run,input,read:code=>JSON.parse(run('JSON.stringify('+code+')'))};
}
const responseKeys=['query','items','total','counts','page','pageSize','lastPage','version'];
function visible(s){
 const d=s.data,q=s.query;
 return !!(d&&s.pending===null&&!s.needsRefresh&&s.error===null&&d.version>=s.minVersion&&['status','term','pageSize'].every(k=>d.query?.[k]===q[k])&&d.page===q.page);
}
function projection(s){
 const selected={};for(const k of ['query','pending','minVersion','needsRefresh','error'])selected[k]=s[k];
 selected.eligible_data=visible(s)?Object.fromEntries(responseKeys.map(k=>[k,s.data[k]])):null;
 return clone(selected);
}
function api(requests){
 const result=spawnSync(python,['-I','-B','-X','utf8',path.join(path.dirname(new URL(import.meta.url).pathname),'api_probe.py'),path.join(root,'project/api.py')],{input:JSON.stringify(requests),encoding:'utf8',timeout:12000,maxBuffer:8*1024*1024,env:{PATH:process.env.PATH||'',PYTHONUTF8:'1'}});
 if(result.error)throw new Unsupported('Python child infrastructure: '+result.error.message);
 if(result.status!==0)throw new Unsupported('Python probe infrastructure exit '+result.status+': '+result.stderr);
 let data;try{data=JSON.parse(result.stdout);}catch(e){throw new Unsupported('Python probe did not return protocol JSON');}
 if(data.status==='profile_unsupported')throw new Unsupported('Python source profile: '+data.error);
 return data;
}
async function unit(c){
 if(c.kind==='api')return null;
 let realm;
 try{
  realm=await load();
  if(c.kind==='view'){
   realm.input(c.snapshot);const original=realm.read('__input');
   realm.run('globalThis.__output=__view.present(__input)');
   if(realm.run('__output&&typeof __output.then==="function"'))throw new Unsupported('thenable view outside synchronous profile');
   const output=realm.read('__output');
   return {case_id:c.case_id,status:'completed',output,inputs_unchanged:JSON.stringify(original)===JSON.stringify(realm.read('__input'))};
  }
  realm.run('globalThis.__states=Object.create(null)');const out=[];let unchanged=true;
  for(const action of c.actions){
   const id=action.instance||'main';realm.input({id,action,initial:c.initial||{}});
   realm.run('if(!Object.hasOwn(__states,__input.id))__states[__input.id]=__store.createState(__input.initial);globalThis.__actionBefore=JSON.stringify(__input.action);__states[__input.id]=__store.reduce(__states[__input.id],__input.action);globalThis.__snapshot=__store.getSnapshot(__states[__input.id]);');
   if(realm.run('__states[__input.id]&&typeof __states[__input.id].then==="function"'))throw new Unsupported('thenable state outside synchronous profile');
   unchanged=unchanged&&realm.run('__actionBefore===JSON.stringify(__input.action)');
   const snap=realm.read('__snapshot');
   // JSON copy protocol: mutating the snapshot must not alter the stored state.
   realm.run('if(__snapshot&&__snapshot.query)__snapshot.query.page=987654');
   const again=realm.read('__store.getSnapshot(__states[__input.id])');
   unchanged=unchanged&&JSON.stringify(snap)===JSON.stringify(again);
   out.push({instance:id,snapshot:projection(snap)});
  }
  return {case_id:c.case_id,status:'completed',output:out,inputs_unchanged:unchanged};
 }catch(e){return {case_id:c.case_id,...serializeError(e)};}
}
async function scenario(c,fixture){
 try{
  const r=await load();r.run('globalThis.__state=__store.createState()');
  let rows=clone(fixture.records),version=fixture.version;const issued=new Map(),captures=new Map(),steps=[];
  for(let index=0;index<c.steps.length;index++){
   const s=c.steps[index];let action=null,request=null,response=null;
   if(s.op==='request')action={type:'request',token:s.token,patch:s.patch};
   else if(s.op==='capture'){
    request=issued.get(s.token);if(!request)throw new Unsupported('capture unknown issued token');
    const got=api([{case_id:c.case_id+':'+index,records:rows,query:request,version}]);
    response=got.cases?.[0]||got;captures.set(s.token,response);
   }else if(s.op==='deliver'){
    response=captures.get(s.token);if(!response)throw new Unsupported('deliver uncaptured token');
    if(response.status==='completed')action={type:'resolve',token:s.token,result:response.output};
   }else if(s.op==='commit'){
    const commit=fixture.commits.find(x=>x.revision===s.revision);if(!commit||commit.revision!==version+1)throw new Unsupported('non-sequential trusted commit');
    for(const change of commit.changes){const row=rows.find(x=>x.id===change.id);Object.assign(row,change,{revision:commit.revision});}version=commit.revision;
   }else if(s.op==='notify')action={type:'invalidate',event_id:s.event_id,revision:s.revision};
   else if(s.op==='reject')action={type:'reject',token:s.token};
   if(action){r.input(action);r.run('__state=__store.reduce(__state,__input)');}
   r.run('globalThis.__snapshot=__store.getSnapshot(__state);globalThis.__shown=__view.present(__snapshot)');
   const snap=r.read('__snapshot'),shown=r.read('__shown');
   if(s.op==='request'){issued.set(s.token,clone(snap.query));request=snap.query;}
   steps.push({index,operation:s,server_version:version,request,response,view:shown});
  }
  return {case_id:c.case_id,status:'completed',steps};
 }catch(e){return {case_id:c.case_id,...serializeError(e)};}
}
const out={schema_version:'h050-actual-replay/v1',profile:'h050-synchronous-json-functions/v1',sources_sha256:hashes,node:{version:process.version,sha256:hash(fs.readFileSync(process.execPath))},engine_sha256:hash(fs.readFileSync(new URL(import.meta.url))),api_probe_sha256:hash(fs.readFileSync(new URL('./api_probe.py',import.meta.url))),profile_sha256:hash(fs.readFileSync(new URL('./profile.py',import.meta.url))),fixture_sha256:req.fixture_sha256,scenarios_sha256:req.scenarios_sha256,scope:'actual synchronous Python/TypeScript function replay; no browser/DOM/Harness/OS-sandbox claim',units:[],scenarios:[]};
try{
 const apis=(req.units||[]).filter(c=>c.kind==='api');
 if(apis.length){const data=api(apis);out.units.push(...(data.cases||apis.map(c=>({case_id:c.case_id,...data}))));}
 for(const c of req.units||[])if(c.kind!=='api')out.units.push(await unit(c));
 for(const c of req.scenarios||[])out.scenarios.push(await scenario(c,req.fixture));
 if([...out.units,...out.scenarios].some(x=>x.status==='unassessed'||x.status==='profile_unsupported'))out.unassessed=true;
}catch(e){out.unassessed=true;out.infrastructure=serializeError(e);}
fs.writeFileSync(responsePath,JSON.stringify(out,null,2)+'\n');
