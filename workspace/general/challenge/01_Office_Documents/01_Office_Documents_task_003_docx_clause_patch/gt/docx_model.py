"""Read-only H003 OOXML projection; native REF/bookmark/link identity matters.

Accepts simple and complex Word fields, different run boundaries, bookmark names
and relationship IDs. Never opens Office or follows hyperlink targets.
"""
import hashlib
import io
import json
from pathlib import Path
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
NS = {'w': W[1:-1]}
PUNCT = str.maketrans({'，': ',', '。': '.', '；': ';', '：': ':', '（': '(', '）': ')', '“': '"', '”': '"', '‘': "'", '’': "'"})
TABLE_KEYS = {'费用与付款': 'milestones', '服务支持': 'services'}


class DocxModelError(ValueError):
    pass


def norm(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(text)).translate(PUNCT))


def authored(text):
    return norm(re.sub(r'\[\[MAIL:(.*?)\]\]', lambda m: '[[LINK:mailto:' + m[1] + '|' + m[1] + ']]', text))


def text_only(node):
    if node.tag in {W+'del', W+'moveFrom', W+'drawing', W+'pict', W+'object'}:
        return ''
    if node.tag == W+'r' and hidden(node):
        return ''
    if node.tag == W+'t':
        return node.text or ''
    return ''.join(text_only(child) for child in node)


def hidden(node):
    setting = node.find('./w:rPr/w:vanish', NS)
    return setting is not None and setting.attrib.get(W+'val', 'true').lower() not in {'0', 'false', 'off'}


def _events(node):
    if node.tag in {W+'del', W+'moveFrom', W+'drawing', W+'pict', W+'object'}:
        return
    if node.tag == W+'r' and hidden(node):
        return
    if node.tag == W+'fldSimple':
        yield ('field', {'instruction': node.attrib.get(W+'instr', ''), 'cache': text_only(node)})
    elif node.tag == W+'hyperlink' and node.attrib.get(R+'id'):
        yield ('link', {'rid': node.attrib[R+'id'], 'display': text_only(node)})
    elif node.tag == W+'fldChar':
        yield ('control', node.attrib.get(W+'fldCharType', ''))
    elif node.tag == W+'instrText':
        yield ('instruction', node.text or '')
    elif node.tag == W+'t':
        yield ('text', node.text or '')
    elif node.tag in {W+'tab', W+'br'}:
        yield ('text', ' ')
    else:
        for child in node:
            yield from _events(child)


def load_docx(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 10_000_000:
        raise DocxModelError('missing, linked or oversized DOCX')
    raw = path.read_bytes()
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        with archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) > 3000 or len(set(names)) != len(names) or sum(item.file_size for item in infos) > 60_000_000:
                raise DocxModelError('package extraction bounds')
            if any(name.startswith('/') or '\\' in name or '..' in name.split('/') for name in names):
                raise DocxModelError('unsafe package member')
            def xml(name):
                value = archive.read(name)
                if b'<!DOCTYPE' in value.upper() or b'<!ENTITY' in value.upper():
                    raise DocxModelError('XML declarations unsupported')
                return ET.fromstring(value)
            if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
                raise DocxModelError('missing DOCX parts')
            document = xml('word/document.xml')
            body = document.find(W+'body')
            if body is None:
                raise DocxModelError('document body absent')
            missing_relationships = 'word/_rels/document.xml.rels' not in names
            rel_root = ET.Element('Relationships') if missing_relationships else xml('word/_rels/document.xml.rels')
            rels = {item.attrib['Id']: dict(item.attrib) for item in rel_root}
            bookmarks, active_ids, bookmark_counts = {}, {}, {}
            for paragraph in body.iter(W+'p'):
                visible = text_only(paragraph)
                match = re.fullmatch(r'\s*第\s*([1-9][0-9]*)\s*条\s*(\S.*?)\s*', visible)
                heading = {'number': int(match[1]), 'title': norm(match[2])} if match else None
                for node in paragraph.iter():
                    if node.tag == W+'bookmarkStart':
                        identity, name = node.attrib.get(W+'id'), node.attrib.get(W+'name')
                        bookmark_counts[name] = bookmark_counts.get(name, 0) + 1
                        active_ids[identity] = {'name': name, 'text': '', 'heading': heading}
                    elif node.tag == W+'t':
                        for opened in active_ids.values():
                            opened['text'] += node.text or ''
                    elif node.tag == W+'bookmarkEnd':
                        opened = active_ids.pop(node.attrib.get(W+'id'), None)
                        if opened:
                            bookmarks[opened['name']] = opened
            issues = ['unclosed bookmark'] if active_ids else []
            if missing_relationships: issues.append('missing document relationships')
            fields, links = [], []

            def link_token(target, display, location, valid=True):
                links.append({'target': target, 'display': display, 'location': location, 'valid_relationship': valid})
                return '[[LINK:' + target + '|' + display + ']]'

            def field_token(field, location):
                code, cache = field['instruction'], field['cache']
                ref = re.match(r'^\s*REF\s+(?:"([^"]+)"|(\S+))', code, re.I)
                if ref:
                    target = ref[1] or ref[2]
                    bookmark = bookmarks.get(target)
                    heading = bookmark.get('heading') if bookmark else None
                    title = heading['title'] if heading else '?' + target
                    valid = bool(heading and bookmark_counts.get(target) == 1
                                 and norm(bookmark['text']) == str(heading['number']) and norm(cache) == str(heading['number']))
                    fields.append({'kind': 'REF', 'target_name': target, 'target_title': title, 'cache': cache,
                                   'bookmark_text': bookmark['text'] if bookmark else None, 'valid': valid, 'location': location})
                    return '[[REF:' + title + ']]'
                href = re.match(r'^\s*HYPERLINK\s+(?:"([^"]+)"|(\S+))', code, re.I)
                if href:
                    return link_token(href[1] or href[2], cache, location)
                fields.append({'kind': 'other', 'instruction': code, 'cache': cache, 'location': location})
                return cache

            def paragraph_value(paragraph, location):
                output, stack = [], []
                def add(value):
                    if stack:
                        if stack[-1]['phase'] == 'cache': stack[-1]['cache'] += value
                    else:
                        output.append(value)
                for kind, value in _events(paragraph):
                    if kind == 'control':
                        if value == 'begin':
                            if len(stack) > 8: raise DocxModelError('field nesting bound')
                            stack.append({'phase': 'code', 'instruction': '', 'cache': ''})
                        elif value == 'separate' and stack:
                            stack[-1]['phase'] = 'cache'
                        elif value == 'end' and stack:
                            add(field_token(stack.pop(), location))
                        else:
                            issues.append('unbalanced field control')
                    elif kind == 'instruction':
                        if stack: stack[-1]['instruction'] += value
                        else: issues.append('orphan field instruction')
                    elif kind == 'text':
                        add(value)
                    elif kind == 'field':
                        add(field_token(value, location))
                    elif kind == 'link':
                        relation = rels.get(value['rid'], {})
                        valid = relation.get('Type', '').endswith('/hyperlink') and relation.get('TargetMode') == 'External'
                        add(link_token(relation.get('Target', 'BROKEN'), value['display'], location, valid))
                if stack: issues.append('unclosed field')
                return norm(''.join(output))

            front, clauses, tables = [], [], []
            current = None
            for node in body:
                if node.tag == W+'p':
                    visible = text_only(node)
                    match = re.fullmatch(r'\s*第\s*([1-9][0-9]*)\s*条\s*(\S.*?)\s*', visible)
                    if match:
                        current = {'title': norm(match[2]), 'number': int(match[1]), 'paragraphs': [], 'stream': []}
                        clauses.append(current)
                    else:
                        value = paragraph_value(node, 'clause:' + current['title'] if current else 'front')
                        if value:
                            if current:
                                current['paragraphs'].append(value); current['stream'].append(value)
                            else: front.append(value)
                elif node.tag == W+'tbl':
                    owner = current['title'] if current else ''
                    key = TABLE_KEYS.get(owner, 'unknown')
                    rows = []
                    for row_number, row in enumerate(node.findall(W+'tr')):
                        rows.append([''.join(paragraph_value(para, 'table:' + key + '/row:' + str(row_number) + '/col:' + str(column))
                                             for para in cell.findall(W+'p')) for column, cell in enumerate(row.findall(W+'tc'))])
                    item = {'key': key, 'owner': owner, 'rows': rows,
                            'grid_columns': len(node.findall('./w:tblGrid/w:gridCol', NS)),
                            'merged_cells': sum(int(span.attrib.get(W+'val', '1')) > 1 for span in node.findall('.//w:gridSpan', NS)) + len(node.findall('.//w:vMerge', NS))}
                    tables.append(item)
                    if current: current['stream'].append('[[TABLE:' + key + ']]')
            headers = []
            settings = xml('word/settings.xml') if 'word/settings.xml' in names else ET.Element('settings')
            def enabled(node):
                return node is not None and node.attrib.get(W+'val', 'true').lower() not in {'0', 'false', 'off'}
            even_headers = enabled(settings.find(W+'evenAndOddHeaders'))
            inherited_headers = {}
            for section in document.findall('.//w:sectPr', NS):
                for reference in section.findall(W+'headerReference'):
                    inherited_headers[reference.attrib.get(W+'type', 'default')] = reference.attrib.get(R+'id')
                active_types = ['default'] + (['even'] if even_headers else []) + (['first'] if enabled(section.find(W+'titlePg')) else [])
                for kind in active_types:
                    identity = inherited_headers.get(kind)
                    if not identity:
                        headers.append('')
                        continue
                    relation = rels.get(identity, {})
                    target = relation.get('Target', '')
                    part = posixpath.normpath(posixpath.join('word', target)) if not target.startswith('/') else target.lstrip('/')
                    if part not in names:
                        issues.append('missing header relationship')
                    else:
                        headers.append(norm(text_only(xml(part))))
            return {'schema_version': 'h003-docx-projection/v1', 'source_sha256': hashlib.sha256(raw).hexdigest(),
                    'front': front, 'clauses': clauses, 'tables': tables, 'bookmarks': bookmarks,
                    'fields': fields, 'links': links, 'headers': headers, 'issues': issues,
                    'tracked_changes': len(document.findall('.//w:ins', NS)) + len(document.findall('.//w:del', NS)),
                    'drawings': len(document.findall('.//w:drawing', NS)) + len(document.findall('.//w:pict', NS))}
    except DocxModelError:
        raise
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, RuntimeError) as exc:
        raise DocxModelError('invalid DOCX package/XML') from exc


def unique_clause(model, title):
    matches = [clause for clause in model['clauses'] if clause['title'] == norm(title)]
    return matches[0] if len(matches) == 1 else None


def unique_table(model, key):
    matches = [table for table in model['tables'] if table['key'] == key]
    return matches[0] if len(matches) == 1 else None


def cell_value(model, key, row_label, header):
    table = unique_table(model, key)
    if not table or not table['rows']: return None
    columns = [i for i, value in enumerate(table['rows'][0]) if value == norm(header)]
    rows = [row for row in table['rows'][1:] if row and row[0] == norm(row_label)]
    if len(columns) != 1 or len(rows) != 1 or columns[0] >= len(rows[0]): return None
    return rows[0][columns[0]]
