/* Main-process bootstrap. Preserve the signed app and all five native RPC FDs. */
exports.install=function(spec){
  const fs=require('node:fs'),cp=require('node:child_process'),crypto=require('node:crypto'),mod=require('node:module');
  const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
  const app='/Applications/WorkBuddy.app/Contents/MacOS/Electron';
  const entry='/Applications/WorkBuddy.app/Contents/Resources/app.asar/main/daemon-app-server-entry.js';
  if(spec.contract!=='workbuddy-main-os-boundary/v1'||process.execPath!==app||process.pid!==spec.main_pid)
    throw Error('WB_MAIN_GUARD_IDENTITY');
  const spawn=cp.spawn;
  function frozen(){
    for(const item of [spec.backend_profile,spec.center_profile,spec.gateway_spec,spec.backend_guard,spec.center_binary,spec.native_cli])
      if(fs.realpathSync(item.path)!==item.path||sha(fs.readFileSync(item.path))!==item.sha256)throw Error('WB_MAIN_GUARD_DRIFT');
  }
  function home(env){
    if(env?.WORKBUDDY_CONFIG_DIR!==spec.app_home||env.CODEBUDDY_CONFIG_DIR!==spec.app_home)
      throw Error('WB_MAIN_GUARD_DATA_HOME');
  }
  frozen();
  cp.spawn=function(command,args,options){
    if(command===spec.native_cli.path)throw Error('WB_MAIN_UNBROKERED_NATIVE_EXECUTOR');
    if(command===app&&Array.isArray(args)&&args.includes(entry)){
      frozen();home(options?.env);
      if(options.env.ELECTRON_RUN_AS_NODE!=='1'||JSON.stringify(options.stdio)!=='["pipe","pipe","pipe","pipe","pipe"]')
        throw Error('WB_MAIN_BACKEND_RPC_SHAPE');
      const env={...options.env,WCB_MEMORY_WB_GATEWAY:spec.gateway_spec.path,TMPDIR:(spec.temp_alias??spec.temp)+'/'};
      const selected={...options,env};
      const debug=spec.backend_inspector_port?['--inspect=127.0.0.1:'+spec.backend_inspector_port]:[];
      const child=spawn.call(this,'/usr/bin/sandbox-exec',['-f',spec.backend_profile.path,command,...debug,'--require',spec.backend_guard.path,...args],selected);
      process.stderr.write('[memory-e2e-workbuddy-backend] '+JSON.stringify({pid:child.pid,profile_sha256:spec.backend_profile.sha256})+'\n');
      return child;
    }
    if(command===spec.center_binary.path){
      frozen();home(options?.env);
      if(!Array.isArray(args)||args.length!==4||args[0]!=='--config'||args[2]!=='--app_home'||args[3]!==spec.app_home)
        throw Error('WB_MAIN_CENTER_ARGS');
      const config=JSON.parse(args[1]);
      if(config.appHome!==spec.app_home||config.ipcAddress!==spec.center_socket)throw Error('WB_MAIN_CENTER_EPOCH');
      const child=spawn.call(this,'/usr/bin/sandbox-exec',['-f',spec.center_profile.path,command,...args],options);
      process.stderr.write('[memory-e2e-workbuddy-center] '+JSON.stringify({pid:child.pid,profile_sha256:spec.center_profile.sha256})+'\n');
      return child;
    }
    return spawn.apply(this,arguments);
  };
  mod.syncBuiltinESMExports();
  return {installed:true,contract:spec.contract,main_pid:process.pid,backend_rpc_fds:5,
    native_sandbox_disabled:false,application_admitted:false};
};
