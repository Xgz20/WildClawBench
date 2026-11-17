// Offline provenance replay only. No native app, provider or scoring call.
import {readFile} from 'node:fs/promises';
import {readFrozenStartRejection} from '../vendor/e2e-shared/astronstudio-start-rejection/index.mjs';

const [root,stateFile,recordFile]=process.argv.slice(2);
if(!root||!stateFile||!recordFile)throw Error('START_REJECTION_INPUT_REQUIRED');
const state=JSON.parse(await readFile(stateFile,'utf8'));
const record=JSON.parse(await readFile(recordFile,'utf8'));
const result=await readFrozenStartRejection(root,state,record);
if(!result)throw Error('START_REJECTION_PROOF_REQUIRED');
console.log(JSON.stringify({status:'PASS',profile:result.proof.profile,
  identity:result.proof.identity,prompt_sha256:result.proof.prompt_sha256,
  native_message_accepted:result.proof.framework_prompt_delivery_verified,
  native_turn_id:result.proof.native_turn_id,native_sdk_session_id:result.proof.native_sdk_session_id,
  error:result.proof.error,failed_at:result.proof.failed_at,score_assigned:false}));
