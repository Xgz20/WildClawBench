/* Control-only bootstrap: wrap exactly the installed backend spawn, without
 * changing RPCs, models, UI handlers, credentials or Chromium sandbox flags. */
exports.install=function(spec) {
  if(spec.contract!=='macos-seatbelt-astudio-backend/v1'
    ||Object.hasOwn(spec,'compiled_kernel')||Object.hasOwn(spec,'native_executor'))throw Error('ASTUDIO_PRODUCTION_PACKAGE_REQUIRED');
  const fs=require('node:fs'),crypto=require('node:crypto'),cp=require('node:child_process'),module=require('node:module');
  const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
  const app='/Applications/AStudio.app/Contents/MacOS/AStudio';
  const entry='/Applications/AStudio.app/Contents/Resources/app.asar/apps/server/dist/index.mjs';
  if(process.execPath!==app
    ||fs.realpathSync(spec.profile)!==spec.profile||hash(fs.readFileSync(spec.profile))!==spec.profile_sha256)
    throw Error('SEATBELT_SPAWN_SPEC_UNVERIFIED');
  const original=cp.spawn,profile=spec.profile,checksum=spec.profile_sha256;
  const scope=spec.astudio_scope;
  function installedKernel(env={}) {
    const kernel=spec.kernel,file=kernel?.path;
    if(!/^\/Applications\/AStudio\.app\/Contents\/Resources\/bin\/acode-darwin-(arm64|x64|universal)$/.test(file??'')
      ||fs.realpathSync(file)!==file||hash(fs.readFileSync(file))!==kernel.sha256
      ||(env.ASTUDIO_ACODE_BIN&&env.ASTUDIO_ACODE_BIN!==file)||env.ACODE_EXEC_SERVER_URL)
      throw Error('ASTUDIO_PRODUCTION_PACKAGE_REQUIRED');
  }
  installedKernel(process.env);
  function scopedEnvironment(env) {
    if(!scope)return env;
    if(scope.contract!=='astudio-case-memory-unit/v1'||fs.realpathSync(scope.scope)!==scope.scope
      ||hash(fs.readFileSync(scope.scope))!==scope.scope_sha256)throw Error('SEATBELT_UNIT_SPEC_DRIFT');
    const saved=JSON.parse(fs.readFileSync(scope.scope,'utf8'));
    if(saved.unit_id!==scope.unit_id||Object.keys(saved.paths).length!==Object.keys(scope.paths).length
      ||Object.keys(saved.paths).some(key=>saved.paths[key]!==scope.paths[key])
      ||env.ASTUDIO_HOME!==scope.paths.desktop)throw Error('SEATBELT_UNIT_ENVIRONMENT_REJECTED');
    return {...env,ASTUDIO_HOME:scope.paths.desktop,ASTUDIO_ACODE_HOME:scope.paths.acode,
      ACODE_HOME:scope.paths.acode,TMPDIR:scope.paths.temp+'/'};
  }
  cp.spawn=function(command,args,options) {
    if(command!==app||!Array.isArray(args)||!args.includes(entry))return original.apply(this,arguments);
    if(options?.env?.ELECTRON_RUN_AS_NODE!=='1'||fs.realpathSync(profile)!==profile||hash(fs.readFileSync(profile))!==checksum)
      throw Error('SEATBELT_BACKEND_SPAWN_REJECTED');
    installedKernel(options.env);
    const selected=scope?{...options,env:scopedEnvironment(options.env)}:options;
    const child=original.call(this,'/usr/bin/sandbox-exec',['-f',profile,command,...args],selected);
    // Existing desktop identity/watchdog code must see the final exec identity,
    // rather than the brief sandbox-exec image of this same PID.
    const started=Date.now();let bound=false;
    while(Date.now()-started<5000) {
      let value='';try{value=cp.execFileSync('/bin/ps',['-p',String(child.pid),'-o','command='],{encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim()}catch{}
      if(value.startsWith(app+' ')&&value.includes(entry)){bound=true;break}
    }
    if(!bound)throw Error('SEATBELT_BACKEND_EXEC_UNVERIFIED');
    process.stderr.write('[memory-e2e-seatbelt-spawn] '+JSON.stringify({backend_pid:child.pid,profile_sha256:checksum})+'\n');
    return child;
  };
  module.syncBuiltinESMExports();
  return {installed:true,contract:spec.contract,profile_sha256:checksum,scope:'exact installed backend spawn only'};
};
