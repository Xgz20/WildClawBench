/** Match machine.py's OS-account paths; HOME/CODEX_HOME cannot redirect targets. */
import {userInfo,hostname,arch} from 'node:os';
import {join,resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {realpathSync} from 'node:fs';

export function pathsForHome(home) {
  const acode=join(home,'.acode'),debug=join(home,'debug-workspace/e2e-evaluate/memory-e2e');
  return {home,debug,ui_lock:join(debug,'.memory-native-ui.lock'),acode,
    overlay:join(acode,'acode/acode-home-overlay'),astudio_db:join(acode,'acode/userdata/state.sqlite'),
    qwen_db:join(home,'Library/Application Support/QwenWorkCN/data/agents.db'),
    qwen_trace:join(home,'.qwenworkcn'),workbuddy:join(home,'.workbuddy')};
}
const user=userInfo();
if(resolve(user.homedir)!==user.homedir||realpathSync(user.homedir)!==user.homedir)throw Error('MACHINE_HOME');
export const MACHINE_PATHS=Object.freeze(pathsForHome(user.homedir));
export function verifyMachine(profile) {
  if(!profile)return; // Legacy profiles retain their original frozen policy.
  const architecture=arch()==='x64'?'x86_64':arch();
  if(profile.contract!=='wildclawbench.memory-machine/v1'||profile.host!==hostname()
    ||profile.uid!==user.uid||profile.architecture!==architecture
    ||Object.keys(MACHINE_PATHS).some(k=>profile.paths?.[k]!==MACHINE_PATHS[k]))throw Error('NATIVE_MACHINE_DRIFT');
}
export function verifyNodeRuntime(profile) {
  if(profile&&(profile.version!==process.version||profile.architecture!==arch()
    ||profile.executable!==process.execPath))throw Error('NATIVE_NODE_DRIFT');
}
let python;
export function memoryPython() {
  if(python)return python;
  const selected=process.env.MEMORY_E2E_PYTHON||'python3';
  const result=JSON.parse(execFileSync(selected,['-c','import sys,json; print(json.dumps({"version":list(sys.version_info[:2]),"path":sys.executable}))'],{encoding:'utf8',timeout:5000}));
  if(result.version[0]!==3||result.version[1]<11)throw Error('MEMORY_PYTHON_311_REQUIRED');
  python=realpathSync(result.path);return python;
}
