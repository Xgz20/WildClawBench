import base64
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from tests.general_e2e.test_local_scoring_runtime import RUNTIME

MODULE = (Path(__file__).resolve().parents[2] / 'tools/report/e2e-shared/general-resource-supplements/astronstudio-final-prefix-divergence.mjs').as_uri()
SCRIPT = r'''
import {createHash} from 'node:crypto';
const m=await import(process.argv[1]),suffix=process.argv[2]==='suffix';
const sha=b=>createHash('sha256').update(b).digest('hex');
const bytes=v=>Buffer.from(JSON.stringify(v));
const full='First content and final content',text=suffix?'final content':'First content';
const identity={batch_id:'batch',unit_id:'unit',task_id:'task',attempt_id:'attempt'};
const session={thread_id:'thread',turn_id:'turn',session_id:'sdk',cwd:'/workspace',verified:true,native_status:'completed'};
const final=Buffer.from(text+'\n'),prompt={send_status:'sent',sha256:sha('prompt')};
const state={identity,session,phase:'COMPLETED',execution:{business_status:'completed'},prompt,
 send:{dispatch_attempt_count:1},evidence:{final_response_sha256:sha(final)}};
const sdk=Buffer.from([{type:'session_meta',payload:{id:'sdk',cwd:'/workspace'}},
 {type:'event_msg',payload:{type:'task_started',turn_id:'turn'}},
 {type:'event_msg',payload:{type:'user_message',message:'prompt'}},
 {type:'response_item',payload:{type:'message',id:'final',role:'assistant',content:[{type:'output_text',text:full}],internal_chat_message_metadata_passthrough:{turn_id:'turn'}}},
 {type:'event_msg',payload:{type:'task_complete',turn_id:'turn',last_agent_message:full}}].map(JSON.stringify).join('\n')+'\n');
const native={thread_id:'thread',turn_id:'turn',latest_turn_id:'turn',turn_state:'completed',role:'assistant',is_streaming:0,
 message_id:'assistant:final',assistant_message_id:'assistant:final',text,cwd:'/workspace'};
const names=suffix?[m.FINAL_SUFFIX_STATE,m.FINAL_SUFFIX_NATIVE,m.FINAL_SUFFIX_TEXT,m.FINAL_SUFFIX_PROOF]
 :[m.FINAL_PREFIX_STATE,m.FINAL_PREFIX_NATIVE,m.FINAL_PREFIX_TEXT,m.FINAL_PREFIX_PROOF];
const missing=suffix?'native-final-suffix-divergence':'native-final-prefix-divergence';
const index={schema_id:'urn:wildclawbench:schema:general-e2e:trace-index:v1',identity,session,
 adapter:{id:'astronstudio-provider-runtime-events'},canonical_source_policy:{id:'bound-native-sdk-canonical/v1'},
 completeness:{status:'partial',missing:[missing],omitted_event_count:0}};
const stateBytes=bytes(state),proof=(suffix?m.deriveFinalSuffix:m.deriveFinalPrefix)(stateBytes,index,sdk,native,final);
const transcript=Buffer.from(JSON.stringify({type:'assistant_message',identity,event_id:'final',content:full})+'\n');
const files={'raw/astronstudio-rollout.jsonl':sdk,'transcript.jsonl':transcript,'final-response-bound.txt':final,
 [names[0]]:stateBytes,[names[1]]:bytes(native),[names[2]]:final,[names[3]]:bytes(proof)};
const ref=path=>({path,sha256:sha(files[path]),size:files[path].length});
index.transcript=ref('transcript.jsonl');index.raw_trace=[ref('raw/astronstudio-rollout.jsonl')];
index.binding_evidence=names.map(ref);
index[suffix?'native_final_suffix_divergence_profile':'native_final_prefix_divergence_profile']={id:proof.profile};
files['trace-index.json']=bytes(index);
const execution={identity,harness:{id:'astronstudio'},phase:'COMPLETED',session,prompt,
 execution:{business_status:'completed'},evidence:{completeness:'partial',missing:[missing],
 trace_index_path:'index',transcript_path:'transcript',final_response_path:'native'}};
const record=bytes(execution),contract=bytes({task_id:'task',grading_type:'llm_judge'});
files['sdk-final-authorization.json']=bytes({schema_version:'authorized-astronstudio-sdk-final/v1',
 authorization_reference:'synthetic explicit content-only authority',tasks:[{identity,
 execution_record_sha256:sha(record),contract_sha256:sha(contract),trace_index_sha256:sha(files['trace-index.json']),
 divergence_proof_sha256:sha(files[names[3]]),sdk_final_sha256:sha(full)}]});
console.log(JSON.stringify({record:record.toString('base64'),contract:contract.toString('base64'),
 files:Object.fromEntries(Object.entries(files).map(([key,value])=>[key,value.toString('base64')]))}));
'''


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class SDKFinalFragmentAdmissionTests(unittest.TestCase):
    def fixture(self, kind):
        result = subprocess.run([shutil.which('node'),'--input-type=module','-e',SCRIPT,MODULE,kind],
            check=True,capture_output=True,timeout=30)
        data=json.loads(result.stdout)
        record=base64.b64decode(data['record'])
        return json.loads(record),record,base64.b64decode(data['contract']),{k:base64.b64decode(v) for k,v in data['files'].items()}

    def test_authorized_prefix_and_suffix_preserve_native_bytes_and_display_uncertainty(self):
        for kind in ['prefix','suffix']:
            execution,record,contract,files=self.fixture(kind)
            original=dict(files)
            admission=RUNTIME.sdk_final.validate(execution,record,contract,files)
            self.assertFalse(admission['client_display_of_sdk_final_verified'])
            self.assertNotEqual(admission['scoring_reply_sha256'],admission['native_reply_document_sha256'])
            self.assertEqual(files,original)
            self.assertIn(kind,admission['proof']['profile'])

    def test_suffix_requires_exact_authority_and_unchanged_originals(self):
        execution,record,contract,files=self.fixture('suffix')
        authority=json.loads(files[RUNTIME.sdk_final.AUTHORIZATION])
        authority['tasks'][0]['sdk_final_sha256']='0'*64
        altered={**files,RUNTIME.sdk_final.AUTHORIZATION:json.dumps(authority).encode()}
        with self.assertRaisesRegex(ValueError,'binding drift'):
            RUNTIME.sdk_final.validate(execution,record,contract,altered)
        altered={**files,'bindings/final-suffix-original-response.txt':b'changed'}
        with self.assertRaisesRegex(ValueError,'proof rejected'):
            RUNTIME.sdk_final.validate(execution,record,contract,altered)
