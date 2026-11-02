from copy import deepcopy
from io import BytesIO
from pathlib import Path
import ast
import hashlib
import tempfile
import unittest
import zipfile
from lxml import etree

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source

NAMC = RUNTIME.namc_inline_distances
NS = {'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}


class NamcInlineDistanceTests(unittest.TestCase):
    def source(self):
        path = next((REPO_ROOT / 'tasks/general_e2e').rglob(NAMC.TASK + '.md'))
        _, sections, _ = _parse_task_source(path)
        return _strip_codeblock(sections['Automated Checks'])

    def helper(self):
        namespace = {'CandidateRenderError': ValueError, '_general_e2e_namc_inline_audit': []}
        node = next(n for n in ast.parse(NAMC.HELPERS).body if isinstance(n, ast.FunctionDef) and n.name == '_general_e2e_namc_inline_defaults')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<renderer-transport-helper>', 'exec'), namespace)
        return namespace

    def package(self, body):
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:wp="' + NS['wp'] + '" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14"><w:body>' + body + '</w:body></w:document>')
            z.writestr('word/media/unchanged.bin', b'actual image bytes remain unchanged')
        return stream.getvalue()

    def test_exact_frozen_profile_and_legacy_source_remain_separate(self):
        original = self.source()
        contract = {'task_id': NAMC.TASK, 'automated_checks': original}
        marker = NAMC.marker(contract, NAMC.CONTRACT_SHA, NAMC.DATASET)
        self.assertIsNotNone(marker)
        manifest = {'identity': {'task_id': NAMC.TASK}, 'digests': {'contract_sha256': NAMC.CONTRACT_SHA},
                    'dataset': dict(NAMC.DATASET), 'runtime': {'namc_inline_distance_profile': marker}}
        fixed, receipt = RUNTIME._effective_rule_source(manifest, original)
        self.assertEqual(fixed.count('_general_e2e_namc_inline_defaults(local, source)'), 2)  # definition and guarded call
        old = "    if lo:\n        profile=work/'profile'"
        expected = original.replace(old, "    if lo:\n        _general_e2e_namc_inline_defaults(local, source)\n        profile=work/'profile'")
        expected = expected.replace('def grade(transcript, workspace_path):', 'def grade(transcript, workspace_path):\n    _general_e2e_namc_inline_audit.clear()')
        expected = expected.replace('    export_evidence(root,infos,diag)', "    export_evidence(root,infos,diag)\n    diag['inline_distance_compatibility'] = list(_general_e2e_namc_inline_audit)")
        self.assertEqual(fixed, expected + NAMC.HELPERS)
        self.assertEqual(len([n for n in ast.parse(fixed).body if isinstance(n, ast.FunctionDef) and n.name == 'grade']), 1)
        self.assertFalse(receipt['candidate_rewritten'])
        self.assertFalse(receipt['reference_rewritten'])
        self.assertFalse(receipt['numeric_decisions_assigned'])
        self.assertEqual(RUNTIME._effective_rule_source({}, original), (original, None))
        bad = deepcopy(manifest)
        bad['dataset']['digest'] = '0' * 64
        with self.assertRaises(RUNTIME.ScoringRuntimeError):
            RUNTIME._effective_rule_source(bad, original)

    def test_missing_distances_only_and_idempotence_preserve_original_and_other_members(self):
        namespace = self.helper()
        blob = self.package('<w:p><w:r><w:t>原文内容</w:t><w:drawing><wp:inline><wp:extent cx="1234440" cy="694372"/></wp:inline></w:drawing></w:r></w:p>')
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'original.docx'; source.write_bytes(blob)
            local = Path(folder) / 'render-copy.docx'; local.write_bytes(blob)
            namespace['_general_e2e_namc_inline_defaults'](local, source)
            after = local.read_bytes()
            self.assertEqual(source.read_bytes(), blob)
            with zipfile.ZipFile(BytesIO(after)) as z:
                self.assertEqual(z.read('word/media/unchanged.bin'), b'actual image bytes remain unchanged')
                tree = etree.fromstring(z.read('word/document.xml'))
                inline = tree.find('.//wp:inline', NS)
                self.assertEqual(inline.attrib, {'distL': '0', 'distR': '0'})
                self.assertEqual(inline[0].attrib, {'cx': '1234440', 'cy': '694372'})
                del inline.attrib['distL']; del inline.attrib['distR']
                with zipfile.ZipFile(BytesIO(blob)) as before:
                    self.assertEqual(etree.tostring(tree), etree.tostring(etree.fromstring(before.read('word/document.xml'))))
            namespace['_general_e2e_namc_inline_defaults'](local, source)
            self.assertEqual(local.read_bytes(), after)
            audit = namespace['_general_e2e_namc_inline_audit']
            self.assertEqual(len(audit[0]['changes']), 2)
            self.assertEqual(audit[1]['changes'], [])
            self.assertTrue(all(row['source_modified'] is False for row in audit))

    def test_explicit_values_and_floating_objects_are_not_reinterpreted(self):
        namespace = self.helper()
        blob = self.package('<wp:inline distL="44" distR="55"/><wp:anchor distL="666" distR="777"/>')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'explicit.docx'; path.write_bytes(blob)
            namespace['_general_e2e_namc_inline_defaults'](path, path)
            self.assertEqual(path.read_bytes(), blob)
            self.assertEqual(namespace['_general_e2e_namc_inline_audit'][0]['changes'], [])

    def test_duplicate_zip_members_and_dtd_fail_without_changing_the_render_copy(self):
        namespace = self.helper()
        for kind in ['duplicate', 'dtd']:
            stream = BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                xml = '<!DOCTYPE document [<!ENTITY x "external">]><document>&x;</document>' if kind == 'dtd' else '<document/>'
                z.writestr('word/document.xml', xml)
                if kind == 'duplicate':
                    z.writestr('word/document.xml', '<another/>')
            blob = stream.getvalue()
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'bad.docx'; path.write_bytes(blob)
                with self.assertRaisesRegex(ValueError, 'DUPLICATE_MEMBER|DTD_UNSUPPORTED'):
                    namespace['_general_e2e_namc_inline_defaults'](path, path)
                self.assertEqual(path.read_bytes(), blob)


if __name__ == '__main__':
    unittest.main()
