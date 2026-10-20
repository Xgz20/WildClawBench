/* Zero-model admission of one live unit. Reuse only frozen public SDK code. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {WorkBuddyCdpClient} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';

const [scopeArg, sdkArg, oldFactArg] = process.argv.slice(2);
const check = (ok, reason) => { if (!ok) throw Error(reason); };
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
const read = file => JSON.parse(fs.readFileSync(file));
const publish = (file, value) => fs.writeFileSync(file, JSON.stringify(value, null, 2)+'\n', {flag:'wx', mode:0o600});
const scopePath = path.resolve(scopeArg), scope = read(scopePath), root = path.dirname(scopePath);
check(scope.contract === 'workbuddy-case-memory-unit/v1' && scope.root === root
  && fs.realpathSync(root) === root && !fs.existsSync(root+'/manifest.json')
  && !fs.existsSync(root+'/desktop-main-exited.json'), 'WB_ADMISSION_FRESH_LIVE_UNIT');
const original = read(path.resolve(sdkArg)), originalScope = read(original.scope);
check(original.contract === 'workbuddy-live-synthetic-os-probe/v1'
  && originalScope.installation.cli.sha256 === scope.installation.cli.sha256
  && hash(fs.readFileSync(scope.installation.cli.path)) === scope.installation.cli.sha256,
  'WB_ADMISSION_PUBLIC_SDK_IDENTITY');
const oldFact = path.resolve(oldFactArg);
check(oldFact.startsWith(scope.debug_root+'/') && !oldFact.startsWith(root+'/')
  && fs.realpathSync(oldFact) === oldFact && fs.statSync(oldFact).isFile(), 'WB_ADMISSION_SYNTHETIC_OLD_FILE');
const dir = scope.app_home+'/admission-probe';
fs.mkdirSync(dir, {mode:0o700});
const modules = {};
for (const id of ['68331','84283']) {
  const item = original.modules[id], bytes = fs.readFileSync(item.path);
  check(hash(bytes) === item.sha256, 'WB_ADMISSION_PUBLIC_SDK_DRIFT');
  const file = dir+'/module-'+id+'.js';
  fs.writeFileSync(file, bytes, {flag:'wx', mode:0o600});
  modules[id] = {path:file, sha256:item.sha256};
}
const helper = path.join(path.dirname(fileURLToPath(import.meta.url)), 'workbuddy-live-probe.cjs');
check(hash(fs.readFileSync(helper)) === original.source_sha256, 'WB_ADMISSION_PROBE_DRIFT');
const specPath = dir+'/spec.json';
publish(specPath, {contract:original.contract, scope:scopePath, modules, source_sha256:original.source_sha256,
  old_synthetic_fact:oldFact, outside_synthetic_write:path.dirname(root)+'/SYNTHETIC-DENIED-WRITE-'+scope.unit_id});
const gateway = read(root+'/gateway.json');
const port = scope.ports.backend_inspector;
const owner = Number(execFileSync('/usr/sbin/lsof', ['-nP','-iTCP:'+port,'-sTCP:LISTEN','-t'], {encoding:'utf8'}).trim());
const command = execFileSync('/bin/ps', ['-p',String(owner),'-o','command='], {encoding:'utf8'}).trim();
const ppid = Number(execFileSync('/bin/ps', ['-p',String(owner),'-o','ppid='], {encoding:'utf8'}).trim());
check(command === gateway.backend_command && ppid === gateway.main.pid, 'WB_ADMISSION_BACKEND_OWNER');
const targets = await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
check(targets.length === 1 && targets[0].type === 'node', 'WB_ADMISSION_BACKEND_TARGET');
const client = await WorkBuddyCdpClient.connect(targets[0].webSocketDebuggerUrl, 30000);
try {
  const observed = await client.evaluate(`(() => {
    const fs = process.getBuiltinModule('node:fs');
    const home = process.env.CODEBUDDY_CONFIG_DIR;
    const p = home+'/settings.json';
    const settings = fs.existsSync(p) ? JSON.parse(fs.readFileSync(p,'utf8')) : {};
    return {backend_pid:process.pid,config_dir:process.env.WORKBUDDY_CONFIG_DIR,cli_home:home,
      temp_dir:process.env.TMPDIR,os_temp_dir:process.getBuiltinModule('node:os').tmpdir(),
      memory_enabled:process.env.CODEBUDDY_DISABLE_AUTO_MEMORY !== '1'
        && process.env.CODEBUDDY_DISABLE_AUTO_MEMORY !== 'true'
        && !['1','true','yes','on'].includes((process.env.CODEBUDDY_CODE_DISABLE_AUTO_MEMORY??'').toLowerCase())
        && settings.memory?.autoMemoryEnabled !== false,
      basis:'actual scoped settings/environment and audited default'};
  })()`);
  check(observed.backend_pid === owner && observed.config_dir === scope.app_home
    && observed.cli_home === scope.app_home && observed.memory_enabled === true, 'WB_ADMISSION_RUNTIME_HOME');
  publish(root+'/runtime-observation.json', observed);
  const value = await client.evaluate(`process.getBuiltinModule('node:module').createRequire(${JSON.stringify(helper)})(${JSON.stringify(helper)}).run(${JSON.stringify(specPath)})`);
  publish(root+'/live-os-probe-control-receipt.json', {at:new Date().toISOString(), result:value});
  check(value.pass === true && value.model_prompts_sent === 0, 'WB_ADMISSION_OS_PROBE_FAILED');
  console.log(JSON.stringify({status:'PASS', root, backend_pid:owner, native_pid:value.native_pid, model_prompts:0}));
} finally { client.close(); }
