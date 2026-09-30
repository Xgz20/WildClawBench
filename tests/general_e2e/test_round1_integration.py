"""Synthetic regression evidence for repairs discovered during four-client E2E."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SKILLS=ROOT/'tools/report/skills/general-e2e'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
LEADER=module('leader_round1',SKILLS/'report-general-e2e/scripts/leader_report.py')
FAILURE=module('failure_round1',SKILLS/'score-general-e2e/scripts/failure_evidence.py')
BUNDLE=module('bundle_round1',SKILLS/'run-general-e2e/scripts/build_developer_bundle.py')
sha=lambda b:hashlib.sha256(b).hexdigest()
encoded=lambda d:(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(encoded(d))


class Round1IntegrationTests(unittest.TestCase):
    def test_new_prompt_root_mapping_does_not_excuse_a_candidate_that_nests_outputs(self):
        from tests.general_e2e.test_local_scoring_runtime import RUNTIME
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);prompt=b"Write ./results/answer.json";p=root/'PROMPT.md';p.write_bytes(prompt)
            manifest={'tasks':[{'task_id':'t','prompt':{'mapping':[{'from':'/tmp_workspace','to':'.'}],
                'path':'PROMPT.md','sent_sha256':sha(prompt)}}]}
            execution={'prompt':{'sha256':sha(prompt)}}
            result=RUNTIME._workspace_path_resolution(unit_root=root,unit_manifest=manifest,execution=execution,task_id='t',
                candidate_entries=[{'type':'file','path':'workspace/results/answer.json'}])
            self.assertEqual(result['mode'],'direct');self.assertEqual(result['workspace_argument'],'runtime/workspace')
            p.write_text('changed')
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'MAPPED_PROMPT_DRIFT'):
                RUNTIME._workspace_path_resolution(unit_root=root,unit_manifest=manifest,execution=execution,task_id='t',candidate_entries=[])

    def test_direct_prompt_mapping_records_existing_root_results(self):
        from tests.general_e2e.test_local_scoring_runtime import RUNTIME
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);prompt=b"Write ./results/answer.json";p=root/'PROMPT.md';p.write_bytes(prompt)
            manifest={'tasks':[{'task_id':'t','prompt':{'mapping':[{'from':'/tmp_workspace','to':'./workspace'}],
                'path':'PROMPT.md','sent_sha256':sha(prompt)}}]}
            execution={'prompt':{'sha256':sha(prompt)}}
            result=RUNTIME._workspace_path_resolution(unit_root=root,unit_manifest=manifest,execution=execution,task_id='t',
                candidate_entries=[{'type':'file','path':'results/answer.json'}])
            self.assertEqual(result['mode'],'direct')
            self.assertEqual(result['root_result_count'],1)
            self.assertEqual(result['mapped_result_count'],0)
    def test_leadership_supports_one_or_multiple_units_missing_metrics_and_no_fixed_task_count(self):
        def data(peers):
            labels=['Target@Harness',*peers]
            tables={'总览':{'headers':['unit','score','count'],'rows':[[label,0 if i==0 else 80,3] for i,label in enumerate(labels)]}}
            for name in LEADER.DIMENSIONS:
                tables[name]={'headers':['unit','score','维度平均分(3例)'],'rows':[[label,0 if i==0 else 80,None if name=='Agent能力对比' else i*80] for i,label in enumerate(labels)]}
            tables['效率对比']={'rows':[[label,None,None] for label in labels],'cell_annotations':{}}
            tables['工具调用对比']={'groups':[{'title':label,'rows':[[label,'全部工具',None]],'cell_annotations':{}} for label in labels]}
            return {'target':{'label':labels[0]},'tables':tables}
        for peers in [[],['Other@Harness'],['Other@Harness','Third@Harness']]:
            summaries=LEADER.summaries(data(peers));self.assertEqual(len(summaries),7)
            self.assertTrue(all(x.startswith('Target@Harness') for x in summaries.values()))
            self.assertNotIn('60题',''.join(summaries.values()))
            self.assertIn('不可用',summaries['效率对比'])
            self.assertIn('0.00',summaries['总览'])

    def test_failed_output_admission_binds_actual_source_hashes_without_a_run_id_allowlist(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);contract={'task_id':'synthetic-task','grading_type':'hybrid'}
            digest=sha(json.dumps(contract,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
            policy=root/'policy.json';write(policy,{'schema_version':'wildclawbench.failed-output-evidence-policy/v1','profiles':{digest:{**contract,'candidate_required':True,'final_response_required':False,'tool_history_required':False}}})
            identity={'batch_id':'synthetic-batch','unit_id':'synthetic-unit','task_id':'synthetic-task','attempt_id':'arbitrary-attempt'}
            prompt=b'fixture prompt'
            execution={'identity':identity,'harness':{'id':'astronstudio'},'phase':'FAILED',
                'execution':{'business_status':'candidate_error'},'prompt':{'send_status':'sent','sha256':sha(prompt)},
                'session':{'session_id':'session','cwd':'/synthetic/workspace','verified':True},
                'candidate':{'drift_status':'stable','frozen_sha256':'a'*64},'failure_evidence':{'schema':FAILURE.ADMISSION}}
            state={**copy.deepcopy(execution),'send':{'dispatch_attempt_count':1}}
            state['session']['native_status']='error';state['execution']['error']={'code':'ASTRONSTUDIO_TURN_ERROR','message':'native max_output_tokens'}
            original=copy.deepcopy(execution);original.pop('failure_evidence')
            files={'original-execution-record.json':encoded(original),'original-state.json':encoded(state),'PROMPT.md':prompt}
            files['original-evidence-manifest.json']=encoded({'artifacts':[{'path':'evidence/task/attempt/execution/automation-state.json','sha256':sha(files['original-state.json'])}]})
            proof={'identity':identity,'source_record_sha256':sha(files['original-execution-record.json']),
                'files':[{'path':k,'sha256':sha(v),'size':len(v)} for k,v in files.items()]}
            files['proof.json']=encoded(proof);execution['failure_evidence']['sha256']=sha(files['proof.json'])
            with patch.object(FAILURE,'POLICY_PATH',policy):
                self.assertTrue(FAILURE.validate(execution,contract,files)['original_failure_preserved'])
                changed=dict(files);changed['original-state.json']+=b' '
                with self.assertRaisesRegex(ValueError,'ARTIFACT_SHA'):FAILURE.validate(execution,contract,changed)
                foreign=copy.deepcopy(execution);foreign['harness']['id']='qwenwork'
                with self.assertRaisesRegex(ValueError,'NATIVE_FAILURE_PROFILE_UNSUPPORTED'):FAILURE.profile(foreign,contract)
                with self.assertRaisesRegex(ValueError,'CONTRACT_NOT_REVIEWED'):FAILURE.profile(execution,{**contract,'grading_type':'llm_judge'})
                unknown=copy.deepcopy(execution);unknown['execution']['business_status']='infrastructure_error'
                with self.assertRaisesRegex(ValueError,'EXECUTION_INVALID'):FAILURE.profile(unknown,contract)

    def test_developer_zip_root_matches_filename_and_preserves_zero_score_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();package=root/'package';report=root/'report';output=root/'out'
            tid='fixture-task';uid='fixture-unit';attempt='attempt';score_attempt='judge'
            base=package/'unit/evidence/tasks'/tid/attempt
            identity={'batch_id':'b','unit_id':uid,'task_id':tid,'attempt_id':attempt}
            execution={'identity':identity,'execution':{'business_status':'candidate_error'},
                'candidate':{'path':f'evidence/tasks/{tid}/{attempt}/candidate/workspace'},
                'evidence':{'completeness':'partial','trace_index_path':None,'transcript_path':None},'resource_metrics_path':None}
            record=base/'execution-record.json';write(record,execution)
            candidate=base/'candidate/workspace';candidate.mkdir(parents=True);(candidate/'data.txt').write_text('fixture')
            (candidate/'alias.txt').symlink_to('data.txt')
            score_path=package/'scoring/attempts'/tid/score_attempt/'score.json'
            score={'identity':{**identity,'attempt_id':score_attempt},'execution':{'attempt_id':attempt,'business_status':'candidate_error','record_sha256':sha(record.read_bytes())},'result':{'valid':True,'total_score':0}}
            write(score_path,score)
            entries=[]
            for p in sorted(package.rglob('*')):
                kind='symlink' if p.is_symlink() else 'directory' if p.is_dir() else 'file'
                b=os.readlink(p).encode() if kind=='symlink' else b'' if kind=='directory' else p.read_bytes()
                entry={'path':p.relative_to(package).as_posix(),'kind':kind,'mode':format(stat.S_IMODE(p.lstat().st_mode),'04o'),'size':len(b),'sha256':sha(b)}
                if kind=='symlink':entry['link_target']=os.readlink(p)
                entries.append(entry)
            write(package/'package-manifest.json',{'identity':{'unit_id':uid,'task_ids':[tid]},'entries':entries})
            source_index=report/'developer-source-index.json'
            write(source_index,{'imports':{uid:{'target':str(package),'package_id':'p','package_manifest_sha256':sha((package/'package-manifest.json').read_bytes())}}})
            task_index=report/'developer-task-index.json'
            write(task_index,{'source_index_sha256':sha(source_index.read_bytes()),'selected_tasks':[{'unit_id':uid,'task_id':tid,'execution_record':str(record),'score_file':str(score_path)}]})
            fields=['total_tokens','request_count','call_count','agent_duration_seconds','duration_seconds']
            data={'scope':{'task_ids':[tid],'task_run_count':1},'units':[{'unit_id':uid,'harness':{'id':'astronstudio'}}],
                'artifact_filenames':{'excel':'fixture.xlsx'},'tasks':[{'run_id':uid+'::'+tid,'unit_id':uid,'task_id':tid,'task_name':'Synthetic case',
                    'score_status':'valid','total_score':0,'execution_status':'candidate_error','execution_attempt_id':attempt,'scoring_attempt_id':score_attempt,
                    'resource':{k:{'value':None} for k in fields},'lineage':{'execution_record_sha256':sha(record.read_bytes()),'score_sha256':sha(score_path.read_bytes())}}]}
            write(report/'general_e2e_report_data.json',data);(report/'fixture.xlsx').write_bytes(b'fixture-only')
            (report/'通用场景端到端自动化评测报告.md').write_text('fixture')
            write(report/'receipts/report-receipt.json',{'artifacts':[{'path':'reports/r/'+p.name,'sha256':sha(p.read_bytes())}
                for p in [report/'general_e2e_report_data.json',report/'fixture.xlsx',source_index,task_index]]})
            with redirect_stdout(io.StringIO()):
                BUNDLE.main(['--workspace-root',str(root),'--report-dir',str(report),'--output-root',str(output)])
            receipt=json.loads((output/'bundle-receipts/latest-bundle-receipt.json').read_text())
            import zipfile
            archive=Path(receipt['archive'])
            with zipfile.ZipFile(archive) as z:
                self.assertEqual({n.split('/')[0] for n in z.namelist()},{archive.stem})
                tasks=json.loads(z.read(archive.stem+'/TASK_INDEX.json'))['tasks']
                self.assertEqual(tasks[0]['score_0_1'],0)
            checked=subprocess.run([sys.executable,str(Path(receipt['bundle_directory'])/'VERIFY.py'),str(archive)],capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stderr)
            self.assertEqual(json.loads(checked.stdout)['verified_symlinks'],1)


if __name__=='__main__':unittest.main()
