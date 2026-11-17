// Synthetic frozen rejection transport for Python scoring admission tests.
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {rejectionFixture,fencedRejectionFixture} from './native-start-rejection.mjs';
import {verifyNativeStartRejection} from '../../../tools/report/e2e-shared/astronstudio-start-rejection/index.mjs';
const sha=v=>createHash('sha256').update(v).digest('hex');
const [recordFile,workspace,fenced,tamper]=process.argv.slice(2);
const execution=JSON.parse(await readFile(recordFile,'utf8'));
const f=(fenced==='true'?fencedRejectionFixture:rejectionFixture)(workspace);
f.state.identity=execution.identity;f.state.dataset=execution.dataset;
const old=structuredClone(f.state),oldRecord={identity:old.identity,prompt:old.prompt};
const proof={...verifyNativeStartRejection(f.data,old,f.config),identity:old.identity};
if(tamper==='late-turn')f.data.projection_turns.push({turn_id:'late-model-turn'});
if(tamper==='unknown-source')f.data.native_adapter_source.server_entry_sha256='0'.repeat(64);
const files={'original-state.json':JSON.stringify(old)+'\n',
 'original-execution-record.json':JSON.stringify(oldRecord)+'\n',
 'native-snapshot.json':JSON.stringify(f.data)+'\n'};
proof.files=Object.entries(files).map(([path,value])=>({path,sha256:sha(value),size:Buffer.byteLength(value)}));
const proofBytes=JSON.stringify(proof)+'\n';
const binding={path:'evidence/start-rejection/proof.json',sha256:sha(proofBytes)};
const state=structuredClone(old);state.phase='FAILED';state.prompt.send_status='sent';
state.session={verified:false,thread_id:proof.thread_id,turn_id:null,session_id:null,cwd:workspace};
state.evidence.native_start_rejection=binding;
state.execution={business_status:'candidate_error',error:{code:'ASTRONSTUDIO_NATIVE_START_REJECTED',message:proof.error},native_rejected_at:proof.failed_at};
execution.phase=state.phase;execution.harness={id:'astronstudio',version:state.client.version};
execution.prompt=structuredClone(state.prompt);execution.session=structuredClone(state.session);
execution.execution=structuredClone(state.execution);
execution.evidence={completeness:'partial',missing:['native-start-rejection','native-model-turn-not-started'],
 transcript_path:null,trace_index_path:null,final_response_path:null,native_start_rejection:binding};
console.log(JSON.stringify({execution,state,proof:proofBytes,files,prompt:'Create the requested deliverables.'}));
