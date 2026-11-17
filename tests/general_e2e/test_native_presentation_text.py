"""PPTX reader contracts; these small packages are structural test fixtures only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from src.wildclawbench_grading_core.native_text import NativeTextError, extract_native_text
from tests.general_e2e.test_native_artifact_text import write_xlsx


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def rels(*rows):
    return '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(
        f'<Relationship Id="{identity}" Type="{R}/{kind}" Target="{target}"{mode}/>'
        for identity, kind, target, mode in rows) + '</Relationships>'


def write_pptx(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        book = write_xlsx(Path(temporary) / 'data.xlsx').read_bytes()
    parts = {
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="258" r:id="r2"/><p:sldId id="256" r:id="r1"/></p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/></p:presentation>',
        'ppt/_rels/presentation.xml.rels': rels(('r1', 'slide', 'slides/slide1.xml', ''), ('r2', 'slide', 'slides/slide9.xml', '')),
        'ppt/slides/slide9.xml': f'''<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:c="{C}" xmlns:r="{R}"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/></p:nvSpPr><p:txBody><a:p><a:r><a:rPr sz="2400"/><a:t>年度</a:t></a:r><a:fld><a:t>报告</a:t></a:fld><a:br/><a:r><a:t>2026</a:t></a:r></a:p></p:txBody></p:sp>
<p:grpSp><p:nvGrpSpPr><p:cNvPr id="3" name="Group" hidden="1"/></p:nvGrpSpPr><p:sp><p:nvSpPr><p:cNvPr id="4" name="Grouped note"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>明确分组文本</a:t></a:r></a:p></p:txBody></p:sp></p:grpSp>
<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="5" name="Table"/></p:nvGraphicFramePr><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>收入</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>1200</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>
<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="6" name="Chart"/></p:nvGraphicFramePr><a:graphic><a:graphicData><c:chart r:id="chart1"/></a:graphicData></a:graphic></p:graphicFrame>
</p:spTree></p:cSld></p:sld>''',
        'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{P}" xmlns:a="{A}" show="0"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="Hidden slide title"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>第二页隐藏文本</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
        'ppt/slides/_rels/slide9.xml.rels': rels(('chart1', 'chart', '../charts/chart4.xml', ''), ('notes1', 'notesSlide', '../notesSlides/notesSlide2.xml', ''), ('url1', 'hyperlink', 'https://example.invalid/never-fetch', ' TargetMode="External"')),
        'ppt/notesSlides/notesSlide2.xml': f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>仅备注：未经核实不能宣称完成</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:notes>',
        'ppt/charts/chart4.xml': f'''<c:chartSpace xmlns:c="{C}" xmlns:a="{A}" xmlns:r="{R}"><c:chart><c:title><c:tx><c:rich><a:p><a:r><a:t>年度收入</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea><c:barChart><c:ser><c:idx val="0"/><c:order val="0"/><c:tx><c:v>收入系列</c:v></c:tx><c:cat><c:strRef><c:f>判定!$A$1</c:f><c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>第一期</c:v></c:pt></c:strCache></c:strRef></c:cat><c:val><c:numRef><c:f>判定!$A$2</c:f><c:numCache><c:ptCount val="4"/><c:pt idx="0"><c:v>0</c:v></c:pt><c:pt idx="1"><c:v>1199</c:v></c:pt><c:pt idx="3"/></c:numCache></c:numRef></c:val></c:ser></c:barChart></c:plotArea></c:chart><c:externalData r:id="book1"/></c:chartSpace>''',
        'ppt/charts/_rels/chart4.xml.rels': rels(('book1', 'package', '../embeddings/book1.xlsx', '')),
        'ppt/embeddings/book1.xlsx': book,
        'ppt/slides/orphan.xml': '<unreferenced>不能把孤立的答案部件当作幻灯片</unreferenced>',
    }
    with zipfile.ZipFile(path, 'w') as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return path


def mutate(path, part, before, after):
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts[part] = parts[part].replace(before.encode(), after.encode())
    with zipfile.ZipFile(path, 'w') as archive:
        for name, blob in parts.items():
            archive.writestr(name, blob)


class NativePresentationTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = write_pptx(self.root / 'annual.pptx')

    def rows(self):
        return [json.loads(line) for line in extract_native_text(self.path)['text'].splitlines()]

    def test_slide_order_groups_tables_notes_and_hidden_content_stay_distinct(self):
        rows = {row['locator']: row for row in self.rows()}
        self.assertEqual(rows['slide:1']['part'], 'ppt/slides/slide9.xml')
        self.assertFalse(rows['slide:2']['show'])
        self.assertEqual(rows['slide:1/shape:2/paragraph:1']['text'], '年度报告\n2026')
        self.assertEqual(rows['slide:1/shape:2/paragraph:1']['explicit_font_sizes_hundredth_pt'], ['2400'])
        self.assertTrue(rows['slide:1/shape:3']['hidden'])
        self.assertEqual(rows['slide:1/shape:3/shape:4/paragraph:1']['text'], '明确分组文本')
        self.assertEqual(rows['slide:1/shape:5/table:1/row:1/cell:2/paragraph:1']['text'], '1200')
        self.assertEqual(rows['slide:1/notes/shape:2/paragraph:1']['context'], 'speaker_notes')
        self.assertNotIn('孤立的答案', extract_native_text(self.path)['text'])

    def test_chart_cache_missing_points_and_embedded_cells_never_override_each_other(self):
        rows = self.rows()
        points = [row for row in rows if row.get('context') == 'chart_stored_point' and '/val/' in row['locator']]
        self.assertEqual([(row['index'], row['value']) for row in points], [(0, '0'), (1, '1199'), (3, None)])
        cells = [row for row in rows if row.get('context') == 'embedded_workbook_cell']
        cell = next(row for row in cells if row['locator'].endswith('/判定!A2'))
        self.assertEqual(cell['value'], '1200')
        self.assertTrue(cell['cached_value_available'])
        with zipfile.ZipFile(self.path) as archive:
            digest = hashlib.sha256(archive.read('ppt/embeddings/book1.xlsx')).hexdigest()
        self.assertEqual(cell['workbook_sha256'], digest)
        self.assertIn('not interpreted', ' '.join(extract_native_text(self.path)['limitations']))

    def test_paging_source_binding_and_extractor_version(self):
        whole = extract_native_text(self.path)
        page = extract_native_text(self.path, record_offset=8, record_limit=4)
        self.assertEqual(page['text'].splitlines(), whole['text'].splitlines()[8:12])
        self.assertEqual(whole['source_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(whole['engine']['version'], 'wildclawbench.pptx-text/v1')
        self.assertTrue(extract_native_text(self.path, max_chars=15)['truncated'])

    def test_relationship_escape_wrong_type_and_duplicate_id_are_rejected(self):
        part = 'ppt/_rels/presentation.xml.rels'
        original = self.path.read_bytes()
        for before, after in [('slides/slide9.xml', '../../outside.xml'),
                              ('slides/slide9.xml', 'slides/%2e%2e/slide9.xml'),
                              (R + '/slide', R + '/image'), ('Id="r1"', 'Id="r2"')]:
            with self.subTest(after=after):
                self.path.write_bytes(original)
                mutate(self.path, part, before, after)
                with self.assertRaises(NativeTextError):
                    self.rows()

    def test_external_ole_workbook_is_identified_without_reading_network(self):
        mutate(self.path, 'ppt/charts/_rels/chart4.xml.rels', R + '/package', R + '/oleObject')
        mutate(self.path, 'ppt/charts/_rels/chart4.xml.rels', 'Target="../embeddings/book1.xlsx"',
               'Target="https://example.invalid/book.xlsx" TargetMode="External"')
        with patch('urllib.request.urlopen', side_effect=AssertionError('must stay offline')):
            rows = self.rows()
        self.assertTrue(any(row.get('content_status') == 'external_not_followed' for row in rows))
        self.assertFalse(any(row.get('context') == 'embedded_workbook_cell' for row in rows))

    def test_duplicate_shape_ids_cannot_produce_ambiguous_locators(self):
        mutate(self.path, 'ppt/slides/slide9.xml', 'id="4" name="Grouped note"', 'id="2" name="Grouped note"')
        with self.assertRaisesRegex(NativeTextError, 'ambiguous presentation shape ID'):
            self.rows()

    def test_duplicate_chart_point_and_nested_zip_budget_are_explicit_errors(self):
        original = self.path.read_bytes()
        mutate(self.path, 'ppt/charts/chart4.xml', '<c:pt idx="3"/>', '<c:pt idx="1"/>')
        with self.assertRaisesRegex(NativeTextError, 'duplicate chart cache'):
            self.rows()
        self.path.write_bytes(original)
        with zipfile.ZipFile(self.path) as archive:
            expanded = sum(row.file_size for row in archive.infolist())
        with patch('src.wildclawbench_grading_core.native_text.MAX_ZIP_BYTES', expanded + 1):
            with self.assertRaisesRegex(NativeTextError, 'combined extraction limit'):
                self.rows()

    def test_image_only_slides_do_not_invent_text(self):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('ppt/presentation.xml', f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="1" r:id="r1"/></p:sldIdLst></p:presentation>')
            archive.writestr('ppt/_rels/presentation.xml.rels', rels(('r1', 'slide', 'slides/slide1.xml', '')))
            archive.writestr('ppt/slides/slide1.xml', f'<p:sld xmlns:p="{P}"><p:cSld><p:spTree><p:pic><p:nvPicPr><p:cNvPr id="2" name="Not real OCR"/></p:nvPicPr></p:pic></p:spTree></p:cSld></p:sld>')
        with self.assertRaises(NativeTextError) as caught:
            self.rows()
        self.assertEqual(caught.exception.code, 'NATIVE_TEXT_UNAVAILABLE')

    def test_legacy_declared_presentation_works_outside_checkout_and_gt_stays_private(self):
        repo = Path(__file__).resolve().parents[2]
        modules = self.root / 'modules'
        modules.mkdir()
        shutil.copy2(repo / 'src/utils/workspace_evidence.py', modules / '_workspace_evidence.py')
        shutil.copy2(repo / 'src/wildclawbench_grading_core/native_text.py', modules / '_native_artifact_text.py')
        workspace = self.root / 'workspace'
        write_pptx(workspace / 'results/annual.pptx')
        write_pptx(workspace / 'gt/private.pptx')
        code = ('import sys,json;sys.path.insert(0,' + repr(str(modules)) + ');'
                'from _workspace_evidence import collect_workspace_evidence;'
                'v=collect_workspace_evidence(' + repr(str(workspace)) + ',{"required":["results/annual.pptx"]});'
                'print(json.dumps({"selected":v["metadata"]["selected"],"text":v["text"]}))')
        run = subprocess.run([sys.executable, '-I', '-c', code], cwd=modules, check=True, capture_output=True, text=True)
        value = json.loads(run.stdout)
        self.assertEqual([row['path'] for row in value['selected']], ['results/annual.pptx'])
        self.assertIn('年度报告', value['text'])
        self.assertNotIn('gt/private', value['text'])


if __name__ == '__main__':
    unittest.main()
