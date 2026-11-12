import ast,copy,json,re,unicodedata,unittest
from tests.general_e2e.test_source_repairs_round7 import sources
from tests.general_e2e.test_local_scoring_runtime import RUNTIME

HEADERS=RUNTIME.acl_index_headers


def header_reader(source):
    grade=ast.parse(source).body[0]
    nodes=[n for n in grade.body if isinstance(n,ast.FunctionDef) and n.name in {'normalized_text','header_keys'}
           or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='aliases' for t in n.targets)]
    scope={'re':re,'unicodedata':unicodedata}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<index-header-reader>','exec'),scope)
    return scope['header_keys']


class ACLIndexHeaderTests(unittest.TestCase):
    def fixture(self):
        _,_,original,_=sources(HEADERS.TASK)
        manifest={'identity':{'task_id':HEADERS.TASK},'runtime':{}}
        return original,manifest

    def test_alias_is_exact_and_historical_attempts_keep_original_parser(self):
        source,manifest=self.fixture();self.assertEqual(HEADERS.effective_source(manifest,source,source,None),(source,None))
        manifest['runtime']['acl_index_header_profile']=HEADERS.marker({'task_id':HEADERS.TASK,'automated_checks':source})
        fixed,receipt=HEADERS.effective_source(manifest,source,source,None)
        before,after=header_reader(source),header_reader(fixed)
        self.assertEqual(before('正式标题'),[]);self.assertEqual(after('正式标题'),['title'])
        for label in ['论文标识','论文标题','正式题名','标题','问答分类','旧论文标题','论文标题说明','正式标题说明','正式标题/问答分类']:
            if label=='正式标题/问答分类':self.assertEqual(after(label),['title','qa_classification'])
            else:self.assertEqual(before(label),after(label),label)
        self.assertFalse(receipt['rubric_and_weights_changed']);self.assertFalse(receipt['candidate_rewritten'])
        manifest['runtime']['acl_index_header_profile']['source_sha256']='0'*64
        with self.assertRaises(ValueError):HEADERS.effective_source(manifest,source,source,None)

    def test_new_rule_profile_composes_with_existing_pdf_repair(self):
        source,manifest=self.fixture()
        manifest['runtime']['shared_rule_source_repair']=RUNTIME.shared_source_repairs.marker({'task_id':HEADERS.TASK,'automated_checks':source})
        manifest['runtime']['acl_index_header_profile']=HEADERS.marker({'task_id':HEADERS.TASK,'automated_checks':source})
        corrected,receipt=RUNTIME._effective_rule_source(manifest,source)
        self.assertEqual(receipt['correction_id'],HEADERS.PROFILE)
        self.assertEqual(receipt['prior_correction']['correction_id'],'invalid-candidate-pdf-structure/v1')
        self.assertEqual(header_reader(corrected)('正式标题'),['title'])
        _,_,_,current=sources(HEADERS.TASK)
        self.assertIsNotNone(HEADERS.marker({'task_id':HEADERS.TASK,'automated_checks':current}))


if __name__=='__main__':unittest.main()
