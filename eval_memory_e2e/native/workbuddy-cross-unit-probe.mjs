/* Control side for bounded synthetic old-unit probes; never sends prompts. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {WorkBuddyCdpClient} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
const check = (ok, reason) => {if (!ok) throw Error(reason);};
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
const [scopeArg,...files] = process.argv.slice(2), scope = JSON.parse(fs.readFileSync(path.resolve(scopeArg)));
check(scope.contract === 'workbuddy-case-memory-unit/v1' && files.length > 0 && files.length <= 2
  && !fs.existsSync(scope.root+'/manifest.json'), 'WB_CROSS_UNIT_UNUSED_UNIT');
const gateway = JSON.parse(fs.readFileSync(scope.root+'/gateway.json'));
const port = scope.ports.backend_inspector;
const owner = Number(execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+port,'-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim());
check(execFileSync('/bin/ps',['-p',String(owner),'-o','command='],{encoding:'utf8'}).trim() === gateway.backend_command
  && Number(execFileSync('/bin/ps',['-p',String(owner),'-o','ppid='],{encoding:'utf8'}).trim()) === gateway.main.pid,
  'WB_CROSS_UNIT_BACKEND_IDENTITY');
const old = files.map((arg,index) => {
  const file = path.resolve(arg);
  check(file.startsWith(scope.debug_root+'/') && !file.startsWith(scope.root+'/')
    && fs.realpathSync(file) === file && fs.statSync(file).isFile(), 'WB_CROSS_UNIT_SYNTHETIC_FILE');
  const label = String(index+1), alias = scope.app_home+'/admission-probe/old-unit-'+label;
  fs.symlinkSync(file,alias);
  return {file,label,alias,sha256:hash(fs.readFileSync(file))};
});
const specPath = scope.app_home+'/admission-probe/cross-unit-spec.json';
fs.writeFileSync(specPath,JSON.stringify({contract:'workbuddy-cross-unit-synthetic-probe/v1',unit_id:scope.unit_id,
  app_home:scope.app_home,debug_root:scope.debug_root,backend_pid:owner,old_files:old},null,2)+'\n',{flag:'wx',mode:0o600});
const helper = fileURLToPath(new URL('./workbuddy-cross-unit-probe.cjs',import.meta.url));
const sourceSha = hash(fs.readFileSync(helper));
const targets = await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
check(targets.length === 1 && targets[0].type === 'node', 'WB_CROSS_UNIT_BACKEND_TARGET');
const client = await WorkBuddyCdpClient.connect(targets[0].webSocketDebuggerUrl,30000);
try {
  const result = await client.evaluate(`process.getBuiltinModule('node:module').createRequire(${JSON.stringify(helper)})(${JSON.stringify(helper)}).run(${JSON.stringify(specPath)})`);
  check(hash(fs.readFileSync(helper)) === sourceSha && result.backend_pid === owner, 'WB_CROSS_UNIT_PROBE_IDENTITY');
  const unchanged = old.every(item => hash(fs.readFileSync(item.file)) === item.sha256);
  fs.writeFileSync(scope.root+'/cross-unit-control-receipt.json',JSON.stringify({source_sha256:sourceSha,
    old_files:old,old_files_unchanged:unchanged,result},null,2)+'\n',{flag:'wx',mode:0o600});
  check(result.pass && unchanged, 'WB_CROSS_UNIT_DENIAL_FAILED');
  console.log(JSON.stringify({status:'PASS',backend_pid:owner,denials:result.tests.length,old_files_unchanged:unchanged}));
} finally {client.close();}
