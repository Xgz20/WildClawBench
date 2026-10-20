/* Route only the frozen WorkBuddy native execution service to its owned broker.
 * Native args/env and actual PID/exit remain observable. No local fallback.
 */
const fs=require('node:fs'),crypto=require('node:crypto'),cp=require('node:child_process');
const {EventEmitter}=require('node:events'),mod=require('node:module');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function install(specPath){
  const bytes=fs.readFileSync(specPath),spec=JSON.parse(bytes);
  if(spec.contract!=='workbuddy-owned-executor-gateway/v1'||process.env.WCB_MEMORY_WB_GATEWAY!==specPath)
    throw Error('WB_EXEC_GUARD_SPEC');
  const originalSpawn=cp.spawn,originalSync=cp.execFileSync;
  const helper=spec.sources.client;
  function frozen(){
    if(sha(fs.readFileSync(specPath))!==sha(bytes)||sha(fs.readFileSync(helper.path))!==helper.sha256)
      throw Error('WB_EXEC_GUARD_DRIFT');
  }
  function environment(){
    return {PATH:'/usr/bin:/bin:/usr/sbin:/sbin',HOME:spec.os_home,USER:process.env.USER,LOGNAME:process.env.LOGNAME,
      ELECTRON_RUN_AS_NODE:'1',LANG:'en_US.UTF-8',TMPDIR:spec.temp+'/'};
  }
  function helperArgs(action){return [helper.path,action,specPath]}
  function control(action,input){
    frozen();const output=originalSync(spec.node,helperArgs(action),{env:environment(),input:JSON.stringify(input),encoding:'utf8',timeout:20000});
    const response=JSON.parse(output);
    if(response.ok!==true)throw Error('WB_EXEC_GATEWAY_REJECTED:'+response.error);
    return response;
  }
  cp.spawn=function(command,args,options){
    if(command!==spec.native_cli.path)return originalSpawn.apply(this,arguments);
    frozen();
    if(!Array.isArray(args)||!options||JSON.stringify(options.stdio)!=='["ignore","ignore","ignore"]'
      ||options.detached===true||options.shell)throw Error('WB_EXEC_NATIVE_SPAWN_SHAPE');
    const launched=control('spawn',{command,args,env:options.env,cwd:options.cwd??null});
    const child=new EventEmitter();
    Object.assign(child,{pid:launched.pid,spawnfile:command,spawnargs:[command,...args],killed:false,
      exitCode:null,signalCode:null,connected:false,stdin:null,stdout:null,stderr:null,stdio:[null,null,null]});
    child.kill=function(signal='SIGTERM'){
      const response=control('kill',{job:launched.job,signal});this.killed=response.sent===true;return this.killed;
    };
    const watcher=originalSpawn(spec.node,helperArgs('watch'),{env:environment(),stdio:['pipe','pipe','pipe']});
    let output='',errors='';watcher.stdin.end(JSON.stringify({job:launched.job}));
    watcher.stdout.on('data',b=>{output+=b});watcher.stderr.on('data',b=>{errors+=b});
    watcher.on('error',error=>child.emit('error',error));
    watcher.on('close',code=>{
      try{
        if(code!==0)throw Error('WB_EXEC_WATCH_TRANSPORT:'+errors.slice(-300));
        const response=JSON.parse(output);if(!response.ok||response.pid!==child.pid)throw Error('WB_EXEC_WATCH_IDENTITY');
        child.exitCode=response.exit.code;child.signalCode=response.exit.signal;
        child.emit('exit',child.exitCode,child.signalCode);child.emit('close',child.exitCode,child.signalCode);
      }catch(error){child.emit('error',error)}
    });
    process.nextTick(()=>child.emit('spawn'));
    return child;
  };
  mod.syncBuiltinESMExports();
  return {installed:true,native_cli:spec.native_cli.sha256,no_local_fallback:true};
}
exports.install=install;
if(process.env.WCB_MEMORY_WB_GATEWAY)install(process.env.WCB_MEMORY_WB_GATEWAY);
