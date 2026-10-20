/* Run only fixed synthetic FS programs through a scoped, signed desktop backend. */
exports.run=async function(specPath){
  const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
  const cp=require('node:child_process'),net=require('node:net'),asyncHooks=require('node:async_hooks');
  const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
  const spec=JSON.parse(fs.readFileSync(specPath,'utf8')),scope=JSON.parse(fs.readFileSync(spec.scope,'utf8'));
  const root=scope.root,gw=JSON.parse(fs.readFileSync(root+'/gateway.json','utf8'));
  if(spec.contract!=='workbuddy-live-synthetic-os-probe/v1'||scope.zero_model_bootstrap_only!==true
    ||process.env.WCB_MEMORY_WB_GATEWAY!==root+'/gateway.json'||scope.app_home!==process.env.CODEBUDDY_CONFIG_DIR
    ||specPath!==scope.app_home+'/admission-probe/spec.json')throw Error('WB_LIVE_PROBE_SCOPE');
  if(hash(fs.readFileSync(__filename))!==spec.source_sha256)throw Error('WB_LIVE_PROBE_SOURCE');
  for(const item of Object.values(spec.modules))
    if(!item.path.startsWith(scope.app_home+'/admission-probe/')||fs.realpathSync(item.path)!==item.path
      ||hash(fs.readFileSync(item.path))!==item.sha256)throw Error('WB_LIVE_PROBE_SDK');
  const builtins=new Map([[16698,asyncHooks],[77030,net]]),cache=new Map();
  function load(id){
    if(builtins.has(id))return builtins.get(id);if(cache.has(id))return cache.get(id);
    const item=spec.modules[id];if(!item)throw Error('WB_LIVE_PROBE_IMPORT');
    const exports={};cache.set(id,exports);
    vm.runInNewContext(fs.readFileSync(item.path,'utf8'),{process,Buffer,console,setTimeout,clearTimeout,setInterval,clearInterval,setImmediate,clearImmediate},
      {filename:item.path,timeout:1000})(null,exports,load);return exports;
  }
  const address='SYNTHETIC_'+crypto.randomBytes(8).toString('hex'),commands=load(68331).SANDBOX_COMMANDS;
  const result={at:new Date().toISOString(),backend_pid:process.pid,source_sha256:spec.source_sha256,
    account_fingerprint:scope.account_fingerprint,model_prompts_sent:0,tests:[],application_admitted:false};
  let service,client,serviceExit=null,serviceError=null;
  const wait=async predicate=>{for(let i=0;i<150;i++){if(predicate())return;await new Promise(ok=>setTimeout(ok,50))}throw Error('WB_LIVE_PROBE_TIMEOUT')};
  try{
    service=cp.spawn(gw.native_cli.path,['--config',JSON.stringify({extraPath:[],enableGlobalProjection:false,ipcAddress:address}),
      '--rule_decision','center','--uid',gw.account_uid,'--app_home',scope.app_home],
      {cwd:path.dirname(gw.native_cli.path),stdio:['ignore','ignore','pipe'],env:{PATH:'/usr/bin:/bin',HOME:scope.os_home,
        USER:process.env.USER,LOGNAME:process.env.LOGNAME,LANG:'en_US.UTF-8',TMPDIR:scope.temp+'/',
        SANDBOX_CENTER_UID:gw.account_uid,SANDBOX_CENTER_IPC_ADDRESS:gw.center_socket}});
    result.native_pid=service.pid;service.stderr.on('data',()=>{});
    service.on('error',e=>{serviceError=e.message});service.on('close',(code,signal)=>{serviceExit={code,signal}});
    client=load(84283).createSandboxCliClient();const events=[];
    client.addReverseListener({commands:[commands.PROCESS_OUTPUT,commands.PROCESS_EXIT,commands.REPORT_EVENT]},message=>events.push(message));
    await client.connect({address,connectTimeoutMs:5000,requestTimeoutMs:5000});
    const session='SYNTHETIC-owned-desktop-os-admission';await client.sendRequest(session,commands.OPEN_SESSION,{workingDir:scope.app_home});
    for(const name of ['control','write-control','protected','alias','old-unit','outside-write']){
      const target=name==='control'?scope.app_home+'/synthetic-control.txt':name==='write-control'?scope.app_home+'/admission-probe/allowed-write':
        name==='protected'?root+'/synthetic-non-target/fact.txt':name==='alias'?scope.app_home+'/protected-alias/fact.txt':
        name==='old-unit'?spec.old_synthetic_fact:spec.outside_synthetic_write;
      if(!target.startsWith(scope.debug_root+'/'))throw Error('WB_LIVE_PROBE_SYNTHETIC_ONLY');
      const started=await client.sendRequest(session,commands.RUN_EXECUTABLE,{executable:name.includes('write')?'/usr/bin/touch':'/bin/cat',
        args:[target],cwdDir:scope.app_home,timeoutMs:3000,executionMode:'sandbox',stdoutMode:'pipe',stdinMode:'pipe',killProcessTree:true,
        env:{PATH:'/usr/bin:/bin',LANG:'en_US.UTF-8',TMPDIR:scope.temp+'/'}});
      await wait(()=>events.some(e=>e.command===commands.PROCESS_EXIT&&e.data?.processId===started.processId));
      const observed=events.filter(e=>e.data?.processId===started.processId);
      result.tests.push({name,started,exit:observed.find(e=>e.command===commands.PROCESS_EXIT)?.data.exitCode,
        output:observed.filter(e=>e.command===commands.PROCESS_OUTPUT).map(e=>Buffer.from(e.data.data,'base64').toString('utf8')).join(''),events:observed});
    }
    await client.sendRequest(session,commands.CLOSE_SESSION,{});await client.disconnect();client=null;
    service.kill('SIGTERM');await wait(()=>!!serviceExit||!!serviceError);
    result.service_exit=serviceExit;result.service_error=serviceError;
    result.pass=result.tests.length===6&&result.tests.every(t=>t.name==='control'?t.exit===0&&t.output.includes('SYNTHETIC-ALLOW'):
      t.name==='write-control'?t.exit===0&&fs.existsSync(scope.app_home+'/admission-probe/allowed-write'):
        t.exit!==0&&t.output.includes('Operation not permitted'))&&serviceExit?.code===0&&!serviceError;
  }catch(error){result.error=String(error.stack||error)}
  finally{
    if(client)await client.disconnect();
    // No model turn exists in this scope. This service owns only the bounded
    // synthetic commands above; application-owned native services are untouched.
    if(service&&!service.killed){try{service.kill('SIGTERM')}catch(error){result.cleanup_error=error.message}}
    result.at_end=new Date().toISOString();
    fs.writeFileSync(scope.app_home+'/admission-probe/result.json',JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
  }
  return {pass:result.pass,native_pid:result.native_pid,error:result.error,result:scope.app_home+'/admission-probe/result.json',model_prompts_sent:0};
};
