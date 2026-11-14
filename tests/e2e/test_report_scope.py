import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from src.e2e.common import digest, file_sha256
from src.e2e.general_reports import build_report, report_module, _unavailable_row


class ReportScopeTests(unittest.TestCase):
    def test_partial_scoring_does_not_shrink_frozen_execution_scope(self):
        core,_=report_module()
        tasks=[{'task_id':'case'+str(i),'name':'case'+str(i),'scene':'general','category':'office','difficulty':'easy','modality':'pure-text','dataset':{'id':'d','digest':'same'}} for i in range(3)]
        unit={'unit_id':'u','scene':'general','harness':'astronstudio','model':'sut','reasoning_effort':'high','task_ids':[t['task_id'] for t in tasks]}
        manifest={'units':[unit],'tasks':tasks}
        items=[{'key':t['task_id'],'task_id':t['task_id'],'unit_id':'u','run_index':1,'attempt_id':'exec-'+t['task_id'],'phase':'COMPLETED'} for t in tasks]
        class Store:
            def __init__(self,root):pass
            def rows(self):return items
        def source_row(reader,source,item,task,original,result,target):
            row=_unavailable_row(reader,item,task,original,None)
            if item['task_id']=='case0':row.update(score_status='valid',total_score=0.0)
            return row
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);result=root/'result.json'
            result.write_text(json.dumps({'schema':'wildclawbench.headless-score-set/v1','source_batch_root':str(root/'batch'),'batch_id':'original',
                'batch_manifest_sha256':digest(manifest),'summary':{'containers_held':0},'config':{'harness':'codex','model':'judge','reasoning_effort':'high','concurrency':2},
                'executions':[{'execution_key':'case0','unit_id':'u','run_index':1,'agent_used':True}]}))
            definition={'id':'r','sources':[{'id':'1','result_file':str(result),'result_sha256':file_sha256(result),'unit_id':'u','run_index':1}]}
            with patch('src.e2e.general_reports.load_batch',return_value=manifest),patch('src.e2e.general_reports.BatchStore',Store),patch('src.e2e.general_reports.verify_ready'),patch('src.e2e.general_reports._source_row',side_effect=source_row):
                data=build_report(definition,root/'report')
            self.assertEqual(data['scope']['task_run_count'],3)
            score=data['units'][0]['score']
            self.assertEqual(score['valid_zero_score_count'],1)
            self.assertEqual(score['mean_score'],0.0)
            self.assertEqual(score['unscored_count'],2)
            self.assertEqual(score['score_denominator'],1)
