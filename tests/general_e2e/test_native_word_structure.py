"""Declared OOXML structure fixtures; minimal ZIPs are not dataset documents."""
from __future__ import annotations

import hashlib,json
from pathlib import Path
import tempfile,unittest,zipfile
from unittest.mock import patch

from src.wildclawbench_grading_core.native_text import extract_native_text,NativeTextError,W,R

NS=W[1:-1];REL=R[1:-1]
def word_bytes(*,parts=None,document=None,relationships=None):
    document=document or f'''<w:document xmlns:w="{NS}"><w:body>
<w:p><w:r><w:t>转换说明</w:t></w:r></w:p>
<w:tbl><w:tblGrid><w:gridCol w:w="1800"/><w:gridCol w:w="1800"/><w:gridCol w:w="1800"/><w:gridCol w:w="1800"/></w:tblGrid>
<w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>双列标题</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>金额</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>附注</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>甲组</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>甲行A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1200</w:t></w:r><w:r><w:footnoteReference w:id="1"/></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>说明一</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc><w:tc><w:p><w:r><w:t>甲行B</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>800</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>说明二</w:t></w:r><w:r><w:footnoteReference w:id="2"/></w:r></w:p></w:tc></w:tr>
<w:tr><w:trPr><w:gridBefore w:val="1"/><w:gridAfter w:val="1"/><w:tblHeader w:val="0"/></w:trPr><w:tc><w:p><w:r><w:t>偏移行</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>900</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl><w:p><w:r><w:t>结尾条款</w:t></w:r><w:r><w:endnoteReference w:id="3"/></w:r></w:p></w:body></w:document>'''
    relationships=relationships if relationships is not None else f'<Relationships><Relationship Id="fn" Type="{REL}/footnotes" Target="footnotes.xml"/><Relationship Id="en" Type="{REL}/endnotes" Target="endnotes.xml"/></Relationships>'
    defaults={'word/document.xml':document,'word/_rels/document.xml.rels':relationships,
      'word/footnotes.xml':f'<w:footnotes xmlns:w="{NS}"><w:footnote w:id="-1" w:type="separator"><w:p><w:r><w:separator/></w:r></w:p></w:footnote><w:footnote w:id="1"><w:p><w:r><w:t>仅适用甲行A</w:t></w:r></w:p></w:footnote><w:footnote w:id="2"><w:p><w:r><w:t>仅适用说明二</w:t></w:r></w:p><w:p><w:r><w:t>补充第二段</w:t></w:r></w:p></w:footnote></w:footnotes>',
      'word/endnotes.xml':f'<w:endnotes xmlns:w="{NS}"><w:endnote w:id="3"><w:p><w:r><w:t>结尾条款尾注</w:t></w:r></w:p></w:endnote></w:endnotes>'}
    defaults.update(parts or {})
    return {k:v for k,v in defaults.items() if v is not None}
def write_word(path,**kwargs):
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w') as archive:
        for name,value in word_bytes(**kwargs).items():archive.writestr(name,value)
    return path

class NativeWordStructureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def rows(self,**kwargs):
        self.path=write_word(self.root/'converted.docx',**kwargs);self.projection=extract_native_text(self.path,max_chars=1_000_000)
        return {r['locator']:r for r in map(json.loads,self.projection['text'].splitlines())}

    def test_merged_grid_preserves_xml_cells_and_actual_logical_intervals(self):
        rows=self.rows();self.assertEqual(rows['table:1/grid']['declared_column_count'],4)
        self.assertEqual(rows['table:1/grid']['repeated_header_rows'],[1])
        first=rows['table:1/row:1/cell:1']['table_structure'];self.assertEqual((first['grid_column_start'],first['grid_span']),(1,2))
        self.assertEqual(rows['table:1/row:1/cell:2']['text'],'金额')
        self.assertEqual(rows['table:1/row:1/cell:2']['table_structure']['grid_column_start'],3)
        continued=rows['table:1/row:3/cell:1']['table_structure']
        self.assertEqual(continued['vertical_anchor'],'table:1/row:2/cell:1');self.assertEqual(continued['vertical_merge_status'],'matched')
        self.assertEqual(rows['table:1/row:4/cell:1']['table_structure']['grid_column_start'],2)
        self.assertEqual(rows['table:1/row:4/cell:2']['table_structure']['row_grid_after'],1)
        self.assertFalse(rows['table:1/row:4/cell:1']['table_structure']['repeated_header'])

    def test_notes_bind_body_cell_to_note_id_part_and_actual_text_records(self):
        rows=self.rows();reference=rows['table:1/row:2/cell:3']['note_references'][0]
        self.assertEqual(reference,{'kind':'footnote','id':'1','part':'word/footnotes.xml','content_status':'available','target_locator':'word/footnotes.xml/footnote:1'})
        note=rows[reference['target_locator']];self.assertTrue(note['part_linked_from_document'])
        self.assertEqual(rows[note['paragraph_locators'][0]]['text'],'仅适用甲行A')
        self.assertEqual(rows['word/footnotes.xml/footnote:2']['paragraph_locators'],['word/footnotes.xml/paragraph:3','word/footnotes.xml/paragraph:4'])
        self.assertEqual(rows['paragraph:2']['note_references'][0]['target_locator'],'word/endnotes.xml/endnote:3')
        with zipfile.ZipFile(self.path) as archive:self.assertEqual(note['part_sha256'],hashlib.sha256(archive.read(note['part'])).hexdigest())

    def test_same_text_wrong_note_attachment_changes_structural_evidence(self):
        correct=self.rows();doc=word_bytes()['word/document.xml'];doc=doc.replace('w:id="1"','w:id="999"').replace('w:id="2"','w:id="1"').replace('w:id="999"','w:id="2"')
        wrong=self.rows(document=doc)
        cell='table:1/row:2/cell:3';self.assertEqual(correct[cell]['text'],wrong[cell]['text'])
        self.assertNotEqual(correct[cell]['note_references'],wrong[cell]['note_references'])

    def test_orphan_and_span_mismatches_remain_explicit_without_guessing(self):
        doc=word_bytes()['word/document.xml'].replace('<w:vMerge w:val="restart"/>','')
        rows=self.rows(document=doc);value=rows['table:1/row:3/cell:1']['table_structure']
        self.assertIsNone(value['vertical_anchor']);self.assertEqual(value['vertical_merge_status'],'orphan_or_span_mismatch')
        doc=word_bytes()['word/document.xml'].replace('<w:vMerge/>','<w:gridSpan w:val="2"/><w:vMerge/>')
        value=self.rows(document=doc)['table:1/row:3/cell:1']['table_structure']
        self.assertIsNone(value['vertical_anchor']);self.assertEqual(value['grid_span'],2)

    def test_invalid_span_does_not_become_a_one_column_cell(self):
        doc=word_bytes()['word/document.xml'].replace('<w:gridSpan w:val="2"/>','<w:gridSpan w:val="wrong"/>')
        rows=self.rows(document=doc);first=rows['table:1/row:1/cell:1']['table_structure']
        self.assertIsNone(first['grid_span']);self.assertEqual(first['grid_span_raw'],'wrong')
        self.assertIsNone(rows['table:1/row:1/cell:2']['table_structure']['grid_column_start'])

    def test_legacy_horizontal_declarations_and_parent_nested_text_are_not_fabricated_geometry(self):
        doc=f'<w:document xmlns:w="{NS}"><w:body><w:tbl><w:tr><w:tc><w:tcPr><w:hMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>合并</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:hMerge/></w:tcPr><w:p/></w:tc></w:tr></w:tbl></w:body></w:document>'
        rows=self.rows(document=doc);self.assertEqual(rows['table:1/row:1/cell:2']['table_structure']['horizontal_anchor'],'table:1/row:1/cell:1')
        doc=f'<w:document xmlns:w="{NS}"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>父格</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>子格</w:t></w:r><w:r><w:footnoteReference w:id="1"/></w:r></w:p></w:tc></w:tr></w:tbl></w:tc></w:tr></w:tbl></w:body></w:document>'
        rows=self.rows(document=doc);self.assertTrue(rows['table:1/row:1/cell:1']['table_structure']['contains_nested_table'])
        self.assertNotIn('note_references',rows['table:1/row:1/cell:1'])

    def test_missing_relationship_part_and_note_are_distinct(self):
        rows=self.rows(relationships='<Relationships/>');self.assertEqual(rows['table:1/row:2/cell:3']['note_references'][0]['content_status'],'relationship_missing')
        self.assertFalse(rows['word/footnotes.xml/footnote:1']['part_linked_from_document'])
        rows=self.rows(parts={'word/footnotes.xml':None});self.assertEqual(rows['table:1/row:2/cell:3']['note_references'][0]['content_status'],'missing_part')
        notes=word_bytes()['word/footnotes.xml'].replace('w:id="1"','w:id="11"')
        rows=self.rows(parts={'word/footnotes.xml':notes});self.assertEqual(rows['table:1/row:2/cell:3']['note_references'][0]['content_status'],'note_missing')

    def test_external_notes_are_not_fetched_or_assumed_to_be_local(self):
        relationships=f'<Relationships><Relationship Id="x" Type="{REL}/footnotes" Target="https://example.invalid/notes.xml" TargetMode="External"/></Relationships>'
        with patch('urllib.request.urlopen',side_effect=AssertionError('no network')):rows=self.rows(relationships=relationships)
        ref=rows['table:1/row:2/cell:3']['note_references'][0];self.assertEqual(ref['content_status'],'external_not_followed');self.assertIsNone(ref['target_locator'])

    def test_encoded_internal_target_is_bound_but_traversal_and_schemes_rejected(self):
        parts=word_bytes();notes=parts['word/footnotes.xml']
        relationships=f'<Relationships><Relationship Id="x" Type="{REL}/footnotes" Target="notes/my%20notes.xml"/></Relationships>'
        rows=self.rows(parts={'word/footnotes.xml':None,'word/notes/my notes.xml':notes},relationships=relationships)
        self.assertEqual(rows['table:1/row:2/cell:3']['note_references'][0]['part'],'word/notes/my notes.xml')
        for target in ['../../outside.xml','%2e%2e/%2e%2e/outside.xml','file:///tmp/notes.xml']:
            with self.subTest(target=target),self.assertRaises(NativeTextError):self.rows(relationships=relationships.replace('notes/my%20notes.xml',target))

    def test_duplicate_ids_ambiguous_relationships_and_wrong_roots_are_errors(self):
        original=word_bytes();notes=original['word/footnotes.xml'].replace('w:id="2"','w:id="+01"')
        with self.assertRaisesRegex(NativeTextError,'duplicate Word note ID'):self.rows(parts={'word/footnotes.xml':notes})
        rel=original['word/_rels/document.xml.rels'].replace('Id="en"','Id="fn"')
        with self.assertRaisesRegex(NativeTextError,'ambiguous Word relationship ID'):self.rows(relationships=rel)
        rel=original['word/_rels/document.xml.rels'].replace('</Relationships>',f'<Relationship Id="extra" Type="{REL}/footnotes" Target="other.xml"/></Relationships>')
        with self.assertRaisesRegex(NativeTextError,'ambiguous Word note relationship type'):self.rows(relationships=rel)
        with self.assertRaisesRegex(NativeTextError,'wrong Word note part root'):self.rows(parts={'word/footnotes.xml':f'<w:document xmlns:w="{NS}"/>'})

    def test_deleted_references_are_excluded_and_inserted_references_retained(self):
        doc=word_bytes()['word/document.xml'].replace('<w:r><w:footnoteReference w:id="1"/></w:r>','<w:del><w:r><w:footnoteReference w:id="1"/></w:r></w:del>')
        rows=self.rows(document=doc);self.assertNotIn('note_references',rows['table:1/row:2/cell:3'])
        doc=word_bytes()['word/document.xml'].replace('<w:r><w:footnoteReference w:id="1"/></w:r>','<w:ins><w:r><w:footnoteReference w:id="1"/></w:r></w:ins>')
        self.assertEqual(self.rows(document=doc)['table:1/row:2/cell:3']['note_references'][0]['id'],'1')

    def test_paging_hashes_version_and_truncation_remain_auditable(self):
        rows=self.rows();whole=self.projection;page=extract_native_text(self.path,record_offset=5,record_limit=3,max_chars=100_000)
        self.assertEqual(page['text'].splitlines(),whole['text'].splitlines()[5:8])
        self.assertEqual(whole['engine']['version'],'wildclawbench.docx-text/v1')
        self.assertEqual(whole['source_sha256'],hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertTrue(extract_native_text(self.path,max_chars=15)['truncated'])

if __name__=='__main__':unittest.main()
