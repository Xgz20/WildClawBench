import fs from 'node:fs';
import vm from 'node:vm';
const [sourcePath,requestPath,responsePath]=process.argv.slice(2),req=JSON.parse(fs.readFileSync(requestPath,'utf8'));
const context=vm.createContext(undefined,{codeGeneration:{strings:false,wasm:false}});
const run=code=>new vm.Script(code).runInContext(context,{timeout:700});
const read=code=>JSON.parse(run('JSON.stringify('+code+')'));
const input=x=>{context.__json=JSON.stringify(x);run('globalThis.__input=JSON.parse(__json)');};
const out={status:'completed',observations:[],requests:[],all_inflight_loading:true};
try{
 const mod=new vm.SourceTextModule(fs.readFileSync(sourcePath,'utf8'),{context,importModuleDynamically(){throw new Error('H052_PROFILE_UNSUPPORTED: dynamic import');}});
 await mod.link(spec=>{throw new Error('H052_PROFILE_UNSUPPORTED: external client import '+spec);});await mod.evaluate({timeout:700});context.__client=mod.namespace;
 run('globalThis.__queue=[];globalThis.__resolvers=Object.create(null);globalThis.__sequence=0;globalThis.__transport=(method,path,body)=>new Promise(resolve=>{const id=++__sequence;__queue.push({id,method,path,body:body??{}});__resolvers[id]=resolve;});globalThis.__controller=__client.createController(__transport);');
 for(const step of req.steps){
  input(step);run('globalThis.__done=false;globalThis.__error=null;Promise.resolve(__input.op==="load"?__controller.load():__controller.submit(__input.operation,__input.payload,__input.key)).then(()=>__done=true,e=>{__error=String(e);__done=true;});');
  const deadline=Date.now()+6000;
  while(!run('__done')){
   if(Date.now()>deadline)throw new Error('H052_UNASSESSED: controller promise deadline');
   await new Promise(resolve=>setImmediate(resolve));
   const pending=read('__queue.splice(0)');
   for(const call of pending){
    out.all_inflight_loading=out.all_inflight_loading&&run('__controller.snapshot().loading===true');
    if(typeof call.path!=='string'||!call.path.startsWith('/')||call.path.startsWith('//'))throw new Error('H052_PROFILE_UNSUPPORTED: transport path must be relative local endpoint');
    const response=await fetch(req.base_url+call.path,{method:call.method,headers:{'Content-Type':'application/json','X-Actor':req.actor},...(call.method==='GET'?{}:{body:JSON.stringify(call.body)}),signal:AbortSignal.timeout(5000)});
    const value={status:response.status,body:await response.json()};out.requests.push({request:{method:call.method,path:call.path,actor:req.actor,body:call.body},response:value});
    input({id:call.id,response:value});run('__resolvers[__input.id](__input.response);delete __resolvers[__input.id];');
   }
  }
  if(run('__error!==null'))throw new Error(run('__error'));
  run('globalThis.__snapshot=__controller.snapshot();globalThis.__html=__client.render(__snapshot)');
  const snapshot=read('__snapshot'),html=read('__html');
  run('try{if(__snapshot.rows?.length)__snapshot.rows[0].name="H052-copy-probe";}catch(e){}');
  const again=read('__controller.snapshot()');
  if(JSON.stringify(snapshot)!==JSON.stringify(again))out.snapshot_alias=true;
  out.observations.push({snapshot,html});
 }
}catch(e){out.status=String(e.message).includes('H052_PROFILE_UNSUPPORTED')||String(e.message).includes('H052_UNASSESSED')||e.code==='ERR_SCRIPT_EXECUTION_TIMEOUT'||e.name==='TimeoutError'?'unassessed':'candidate_error';out.error=String(e);}
fs.writeFileSync(responsePath,JSON.stringify(out,null,2)+'\n');
