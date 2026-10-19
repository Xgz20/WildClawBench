/** Read-only admission for changing AStudio configuration; no Codex operations. */
import {execFileSync} from 'node:child_process';
import {queryNativeSessions} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';
import {isBlockingActiveSession} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';
import {requireGui} from './common.mjs';
import {MACHINE_PATHS} from './machine.mjs';
await requireGui();
const pids=[...new Set(execFileSync('/usr/sbin/lsof',['-nP','-iTCP:9240','-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim().split(/\s+/))];
if(pids.length!==1)throw Error('ASTUDIO_LISTENER_AMBIGUOUS');
const command=execFileSync('/bin/ps',['-p',pids[0],'-o','command='],{encoding:'utf8'}).trim();
if(!command.startsWith('/Applications/AStudio.app/Contents/MacOS/AStudio '))throw Error('ASTUDIO_LISTENER_OWNER');
const sessions=await queryNativeSessions(MACHINE_PATHS.astudio_db);
const blocking=sessions.filter(isBlockingActiveSession);
if(blocking.length)throw Error('ASTUDIO_ACTIVE_SESSION');
console.log(JSON.stringify({harness:'AstronStudio',pid:Number(pids[0]),native_session_count:sessions.length,
  blocking_session_count:0,source_database_write:false,verified_at:new Date().toISOString()}));
