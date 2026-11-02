from pathlib import Path
import importlib.util
import tempfile
import unittest
import zipfile

from tools.report.lib.eval_dataset.task_files import TaskDocument

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('static_dataset_paths',ROOT/'tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py')
STATIC=importlib.util.module_from_spec(spec);spec.loader.exec_module(STATIC)


class StaticResourcePathsTests(unittest.TestCase):
    def refs(self,root,text):
        return STATIC._workspace_refs(TaskDocument(root/'task.md',raw=text),root)

    def test_execution_overlay_unicode_and_space_paths_are_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'exec/input').mkdir(parents=True)
            text='`input/07_董事会问题与呈现口径.md` 和 `exec/input/Floor Layout for Interviews.png`'
            refs=self.refs(root,text)
            self.assertEqual(refs,sorted([(root/'exec/input/07_董事会问题与呈现口径.md').resolve(),(root/'exec/input/Floor Layout for Interviews.png').resolve()]))

    def test_python_division_and_diagnostics_are_not_literal_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            refs=self.refs(root,'无 `gt/score.py` 或外部评分脚本依赖\n```python\np=gt/name\nraise RuntimeError("frozen input/GT missing or changed: "+name)\n```')
            self.assertEqual(refs,[])

    def test_nested_attachment_suffix_uses_full_declared_input_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'exec/input/mail/thread/attachments').mkdir(parents=True)
            refs=self.refs(root,"```python\na={'input/mail/thread/attachments/a.pdf':{'attachment_ref':'attachments/a.pdf'}}\n```")
            self.assertEqual(refs,[(root/'exec/input/mail/thread/attachments/a.pdf').resolve()])

    def test_real_missing_reference_is_still_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'exec/input').mkdir(parents=True)
            refs=self.refs(root,'必需输入 `input/真实缺失.xlsx`')
            self.assertEqual(len(refs),1);self.assertFalse(refs[0].exists())

    def test_private_reference_does_not_map_to_execution_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'exec/gt').mkdir(parents=True)
            refs=self.refs(root,'`gt/reference_answer.md`')
            self.assertEqual(refs,[(root/'gt/reference_answer.md').resolve()])

    def test_xmind_internal_attachments_are_verified_inside_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'exec/input').mkdir(parents=True)
            with zipfile.ZipFile(root/'exec/input/source.xmind','w') as archive:
                archive.writestr('attachments/卡片/问题.txt','frozen input')
            refs=self.refs(root,'`input/source.xmind`\n```python\nexpected="attachments/卡片/问题.txt"\n```')
            self.assertEqual(refs,[(root/'exec/input/source.xmind').resolve()])
            missing=self.refs(root,'`input/source.xmind`\n```python\nexpected="attachments/卡片/真实缺失.txt"\n```')
            self.assertIn((root/'exec/attachments/卡片/真实缺失.txt').resolve(),missing)
