/* Control-only bootstrap: wrap exactly the installed backend spawn, without
 * changing RPCs, models, UI handlers, credentials or Chromium sandbox flags. */
exports.install=function(spec) {
  const fs=require('node:fs'),crypto=require('node:crypto'),cp=require('node:child_process'),module=require('node:module');
  const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
  const app='/Applications/AStudio.app/Contents/MacOS/AStudio';
  const entry='/Applications/AStudio.app/Contents/Resources/app.asar/apps/server/dist/index.mjs';
  if(!['macos-seatbelt-astudio-backend/v1','macos-seatbelt-astudio-native-executor/v2','macos-seatbelt-astudio-compiled-kernel/v3'].includes(spec.contract)||process.execPath!==app
    ||fs.realpathSync(spec.profile)!==spec.profile||hash(fs.readFileSync(spec.profile))!==spec.profile_sha256)
    throw Error('SEATBELT_SPAWN_SPEC_UNVERIFIED');
  const original=cp.spawn,profile=spec.profile,checksum=spec.profile_sha256;
  const scope=spec.astudio_scope;
  const native=spec.native_executor;
  const kernel=spec.compiled_kernel;
  if(spec.contract==='macos-seatbelt-astudio-backend/v1'&&native)throw Error('SEATBELT_NATIVE_CONTRACT');
  if((spec.contract==='macos-seatbelt-astudio-compiled-kernel/v3')!==!!kernel)throw Error('SEATBELT_COMPILED_KERNEL_CONTRACT');
  if(spec.contract!=='macos-seatbelt-astudio-backend/v1'
    &&(!scope||!/^ws:\/\/127\.0\.0\.1:\d+\/[a-f0-9]{64}$/.test(native?.launch?.url??'')))
    throw Error('SEATBELT_NATIVE_EXECUTOR_REQUIRED');
  function kernelPath() {
    if(!kernel)return null;
    if(fs.realpathSync(kernel.manifest)!==kernel.manifest||hash(fs.readFileSync(kernel.manifest))!==kernel.manifest_sha256)
      throw Error('SEATBELT_COMPILED_KERNEL_MANIFEST_DRIFT');
    const saved=JSON.parse(fs.readFileSync(kernel.manifest,'utf8')),file=kernel.identity.path;
    if(saved.contract!=='astudio-compiled-app-kernel/v1'||saved.diagnostic_only!==true||saved.installed_astudio_modified!==false
      ||Object.keys(kernel.identity).some(key=>saved[key]!==kernel.identity[key])
      ||fs.realpathSync(file)!==file||hash(fs.readFileSync(file))!==kernel.identity.sha256)
      throw Error('SEATBELT_COMPILED_KERNEL_BINARY_DRIFT');
    return file;
  }
  kernelPath();
  function scopedEnvironment(env) {
    if(!scope)return env;
    if(scope.contract!=='astudio-case-memory-unit/v1'||fs.realpathSync(scope.scope)!==scope.scope
      ||hash(fs.readFileSync(scope.scope))!==scope.scope_sha256)throw Error('SEATBELT_UNIT_SPEC_DRIFT');
    const saved=JSON.parse(fs.readFileSync(scope.scope,'utf8'));
    if(saved.unit_id!==scope.unit_id||Object.keys(saved.paths).length!==Object.keys(scope.paths).length
      ||Object.keys(saved.paths).some(key=>saved.paths[key]!==scope.paths[key])
      ||env.ASTUDIO_HOME!==scope.paths.desktop)throw Error('SEATBELT_UNIT_ENVIRONMENT_REJECTED');
    return {...env,ASTUDIO_HOME:scope.paths.desktop,ASTUDIO_ACODE_HOME:scope.paths.acode,
      ACODE_HOME:scope.paths.acode,TMPDIR:scope.paths.temp+'/',
      ...(native?{ACODE_EXEC_SERVER_URL:native.launch.url}:{}),
      ...(kernel?{ASTUDIO_ACODE_BIN:kernelPath()}:{} )};
  }
  cp.spawn=function(command,args,options) {
    if(command!==app||!Array.isArray(args)||!args.includes(entry))return original.apply(this,arguments);
    if(options?.env?.ELECTRON_RUN_AS_NODE!=='1'||fs.realpathSync(profile)!==profile||hash(fs.readFileSync(profile))!==checksum)
      throw Error('SEATBELT_BACKEND_SPAWN_REJECTED');
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
