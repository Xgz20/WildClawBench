from copy import deepcopy
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import openpyxl

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source

LAYOUT=RUNTIME.news_workbook_layout
WORKSPACE=REPO_ROOT/'workspace/general_e2e/02_Office/task_003_news_event_multifile_extract'


class CompleteNewsWorkbookTests(unittest.TestCase):
    def inputs(self,enabled):
        task=next((REPO_ROOT/'tasks/general_e2e').rglob(LAYOUT.TASK+'.md'));_,sections,_=_parse_task_source(task)
        contract={'task_id':LAYOUT.TASK,'automated_checks':_strip_codeblock(sections['Automated Checks'])}
        row=next(r for r in RUNTIME.private_reference_guard.registry() if r['task_id']==LAYOUT.TASK)
        entries=[{'path':r['path'],'type':'file','sha256':r['canonical_sha256'],'size':r['size']} for r in row['references']]
        dataset={'id':row['dataset_id'],'digest':row['dataset_digest']}
        manifest={'identity':{'task_id':LAYOUT.TASK},'dataset':dataset,'digests':{'contract_sha256':LAYOUT.CONTRACT_SHA},
            'private_scoring':{'workspace_entries':entries},'runtime':{'private_reference_guard_profile':
                RUNTIME.private_reference_guard.marker(contract,LAYOUT.CONTRACT_SHA,dataset,entries)}}
        if enabled:manifest['runtime']['news_workbook_layout_profile']=LAYOUT.marker(contract,LAYOUT.CONTRACT_SHA)
        return contract,manifest

    def run_fixture(self,label,*,enabled,aliases=False,oversized=False):
        root=self.root/label;root.mkdir();workspace=root/'workspace';workspace.mkdir()
        shutil.copytree(WORKSPACE/'gt',workspace/'gt');shutil.copytree(WORKSPACE/'gt',workspace/'results')
        if aliases or oversized:
            path=workspace/'results/events.xlsx';wb=openpyxl.load_workbook(path)
            cached=openpyxl.load_workbook(path,data_only=True)
            for ws in wb:
                for row in ws:
                    for cell in row:
                        if cell.data_type=='f':cell.value=cached[ws.title][cell.coordinate].value
            cached.close()
            mapping={'canonical_entity_or_topic':'规范主体/主题','citation_anchors':'片段锚点（≤80字）',
                'alias_seen':'实际出现名称/别名','source_section':'来源章节/位置','first_mention_order':'首次提及顺序',
                'event_count':'合计','merged_source_count':'报道片段合计','evidence_snippet':'排除内容（短片段）','notes':'说明'}
            if aliases:
                for ws in wb:
                    for cell in ws[1]:
                        if cell.value in mapping:cell.value=mapping[cell.value]
                    sources=[c.column for c in ws[1] if c.value=='source_file']
                    for column in sources:
                        for row in range(2,ws.max_row+1):
                            cell=ws.cell(row,column)
                            if isinstance(cell.value,str):cell.value=Path(cell.value).name
                ws=wb['category_summary'];start=ws.max_column+1
                ws.cell(1,start,'2026-04-10 事件数');ws.cell(1,start+1,'2026-04-11 事件数')
                total=next(c.column for c in ws[1] if c.value=='合计')
                for r in range(2,ws.max_row+1):ws.cell(r,start,ws.cell(r,total).value);ws.cell(r,start+1,0)
                ws=wb['events'];column=ws.max_column+1;ws.cell(1,column,'未映射附加原列');ws.cell(2,column,'只保全，不虚构字段')
                ws=wb.create_sheet('公式附注');ws.cell(1,1,'=1+1')
            if oversized:
                ws=wb.create_sheet('完整证据资源上限测试')
                for col in range(1,101):ws.cell(1,col,'文'*20000)
            wb.save(path);wb.close()
        files,_=RUNTIME._inventory_tree(workspace/'gt')
        RUNTIME._guard_candidate_office_copies(workspace/'gt',files,role='test-header-canonical-reference')
        before=RUNTIME._inventory_tree(workspace/'results')[1]
        contract,manifest=self.inputs(enabled);source,_=RUNTIME._effective_rule_source(manifest,contract['automated_checks'])
        request={'schema_version':RUNTIME.WORKER_REQUEST_SCHEMA,'workspace_path':str(workspace),'transcript':[],
            'automated_checks':source}
        path=root/'request.json';path.write_text(json.dumps(request),encoding='utf-8');result=root/'result.json'
        process=subprocess.run([sys.executable,'-I',str(Path(RUNTIME.__file__).with_name('rule_worker.py')),
            '--request',str(path),'--result',str(result)],capture_output=True,timeout=60)
        document=json.loads(result.read_text())
        self.assertEqual(before,RUNTIME._inventory_tree(workspace/'results')[1])
        return process.returncode,document,workspace

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)

    def tearDown(self):
        RUNTIME._remove_tree(self.root);self.temp.cleanup()

    def test_canonical_and_allowed_equivalent_layout_keep_original_numeric_results(self):
        old_code,old,_=self.run_fixture('original',enabled=False)
        new_code,new,workspace=self.run_fixture('canonical',enabled=True)
        alias_code,alias,other=self.run_fixture('aliases',enabled=True,aliases=True)
        for code,result in [(old_code,old),(new_code,new),(alias_code,alias)]:self.assertEqual(code,0,result.get('error'))
        numeric=lambda data:{k:v for k,v in data['result'].items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
        self.assertEqual(numeric(old),numeric(new));self.assertEqual(numeric(new),numeric(alias))
        payload=json.loads((other/'evaluator_evidence/03_other_tables.json').read_text())
        raw=payload['tables']['_complete_workbook_cells']
        self.assertIn('只保全，不虚构字段',json.dumps(raw,ensure_ascii=False))
        formula=next(s for s in raw if s['sheet']=='公式附注')['rows'][0]['cells'][0]
        self.assertEqual(formula['formula'],'=1+1');self.assertIsNone(formula['value'])
        self.assertEqual({p.name for p in (workspace/'evaluator_evidence').iterdir()},
            {'01_frozen_input.json','02_events.json','03_other_tables.json','04_reference.json','05_summary.json','06_status.json'})

    def test_exact_profile_only_and_original_numeric_functions_stay_present(self):
        contract,manifest=self.inputs(True);original=contract['automated_checks']
        effective,receipt=RUNTIME._effective_rule_source(manifest,original)
        self.assertEqual(receipt['correction_id'],LAYOUT.PROFILE)
        self.assertFalse(receipt['business_values_invented']);self.assertFalse(receipt['original_workbook_rewritten'])
        for name in ['def event_identity(', 'def set_f1(', 'def rollup_score(', 'def grade(']:
            self.assertEqual(original.count(name),effective.count(name))
        bad=deepcopy(manifest);bad['digests']['contract_sha256']='0'*64
        with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(bad,original)
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),LAYOUT.SOURCE_SHA)

    def test_oversized_complete_evidence_fails_without_silent_truncation(self):
        code,result,workspace=self.run_fixture('oversized',enabled=True,oversized=True)
        self.assertNotEqual(code,0);self.assertEqual(result['error']['type'],'EvidenceError')
        self.assertIn('Required evidence exceeds collector budget',result['error']['message'])
        self.assertFalse((workspace/'evaluator_evidence').exists())


if __name__=='__main__':unittest.main()
