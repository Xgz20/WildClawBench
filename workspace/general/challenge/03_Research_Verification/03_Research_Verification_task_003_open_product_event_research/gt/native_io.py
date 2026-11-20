"""H029 offline native readers and mechanical evidence checks.

No network, model, candidate writes, reference-answer reads, or event oracle.
Only the independently acquired production bundle may provide source bodies.
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import struct
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import zlib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MISSING = object()
EVENT_FIELDS = ('event_id', 'change_group_id', 'product_id', 'product_name',
                'provider_name', 'provider_region', 'change_summary', 'stage',
                'event_date_ids', 'planned_date_ids', 'publication_date_ids',
                'availability', 'user_impact', 'claim_ids', 'citation_ids',
                'uncertainties')
SLOT_FIELDS = ('change_summary', 'stage', 'event_time', 'availability', 'provider_region')
COMMON_COLUMNS = {
    'event_id': ['事件编号', '事件标识', '事件标识ID'],
    'change_group_id': ['变更组ID', '变更组编号', '实质变化组ID', '实质变更组', '变更去重键'],
    'product_id': ['产品编号', '产品标识', '产品标识ID'],
    'product_name': ['产品', '产品名', '产品或模块', '产品/模块'],
    'provider_name': ['提供方名称', '运营主体', '运营主体名称', '产品提供方'],
    'provider_region': ['运营归属', '提供方地区归属', '运营主体归属', '国内/海外归属', '提供方国内海外归属'],
    'change_summary': ['变更摘要', '事件内容', '本次变化', '变更内容', '产品变更', '变化摘要'],
    'stage': ['阶段', '发布状态', '可用阶段', '事件阶段', '生命周期状态'],
    'event_date_ids': ['事件时间引用', '事件日期引用', '发生时间证据ID', '发生日期观察ID', '事件日期证据ID', 'event_time_refs'],
    'planned_date_ids': ['计划日期引用', '计划时间引用', '后续可用时间引用', '计划时间证据ID', 'planned_time_refs'],
    'publication_date_ids': ['发布时间引用', '发表时间引用', '来源发布日期ID', '来源发表日期ID', '来源发表时间引用', 'publication_time_refs'],
    'availability': ['可用性', '可用范围/条件', '发布可用范围', '覆盖范围', 'release_availability'],
    'user_impact': ['用户工作流影响', '直接用户影响', '工作流影响', 'user_workflow_impact'],
    'claim_ids': ['关联主张', '关联主张ID', '主张编号集合', '主张引用'],
    'citation_ids': ['关联引用', '关联引用ID', '引用编号集合', '证据引用', '来源引用ID'],
    'uncertainties': ['不确定性', '未知/限制', '限制和未知', '未知和限制', '限制与不确定性'],
}
DATE_ROLES = {'publication', 'modified', 'event', 'planned'}
PRECISIONS = {'timestamp', 'date', 'month', 'interval', 'unknown'}
UNKNOWN = {'', 'null', 'unknown', 'notdocumented', 'notstated', 'notreported',
           'n/a', 'na', '未知', '未注明', '未说明', '未披露', '不详', '—', '–'}


class CandidateError(ValueError):
    pass


class TrustedEvidenceError(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def textnorm(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value))).strip()


def heading_key(value):
    value = textnorm(value).strip('# *_`')
    value = re.sub(r'^[^\w\u3400-\u9fff]+', '', value)
    return value.rstrip(' .:：。!?！？').strip()


def locator_aliases(locator):
    if not isinstance(locator, dict):
        return locator
    result = dict(locator)
    for alias in ('physical_page_1based', 'physical_page', 'page_1based'):
        if alias in result and 'page' not in result:
            result['page'] = result[alias]
    return result


def markdown_literal_text(text):
    # CommonMark backslash-escaped ASCII punctuation is visible literally.
    # This is used only for verified curDoc.MDContent, never arbitrary sources.
    return re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\\\]^_`{|}~])', r'\1', text)


def norm(value):
    return re.sub(r'\s+', '', textnorm('' if value is None else value)).casefold()


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def unknown(value):
    return value is None or isinstance(value, str) and norm(value) in UNKNOWN


def string(value):
    return isinstance(value, str) and bool(value.strip())


def integer(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def parse_value(value):
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(('[', '{')) or text in {'null', 'true', 'false'}:
            try:
                return json.loads(text)
            except ValueError:
                pass
    return value


def refs(value):
    value = parse_value(value)
    if isinstance(value, list):
        return [x.strip() for x in value if string(x)]
    if not isinstance(value, str) or unknown(value):
        return []
    return [x for x in re.split(r'[,;，；|\s]+', value.strip()) if x]


def candidate_path(root, relative, limit=5 * 1024 * 1024):
    root = Path(root).resolve()
    path = root / relative
    if not path.is_file() or path.is_symlink() or root not in path.resolve().parents:
        raise CandidateError('missing/unsafe candidate file: ' + relative)
    if path.stat().st_size > limit:
        raise CandidateError('candidate delivery exceeds 5MiB: ' + relative)
    return path


def read_ledger(path):
    try:
        result = json.loads(Path(path).read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise CandidateError('source_ledger.json must be UTF-8 JSON') from exc
    if not isinstance(result, dict):
        raise CandidateError('source_ledger.json must be an object')
    return result


def _column(address):
    match = re.fullmatch(r'([A-Z]+)([1-9]\d*)', str(address))
    if not match:
        raise CandidateError('invalid XLSX cell address')
    column = 0
    for char in match[1]:
        column = column * 26 + ord(char) - 64
    return int(match[2]), column


def _package(path):
    """Bound decompression and reject executable/externally fetched data."""
    try:
        archive = zipfile.ZipFile(path)
        infos = archive.infolist()
        if len(infos) > 10000 or sum(x.file_size for x in infos) > 100 * 1024 * 1024:
            archive.close()
            raise CandidateError('native package exceeds deterministic parsing limit')
        if any(x.flag_bits & 1 for x in infos):
            archive.close()
            raise CandidateError('encrypted native package')
        for info in infos:
            name = info.filename
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                archive.close()
                raise CandidateError('unsafe native package path')
            lower = name.lower()
            if any(x in lower for x in ('vbaproject', '/activex/', '/externallinks/', '/connections.xml', '/querytables/')):
                archive.close()
                raise CandidateError('active content/external data connection in native package')
            if lower.endswith('.rels'):
                tree = ET.fromstring(archive.read(name))
                for item in tree:
                    reltype = item.get('Type', '').rsplit('/', 1)[-1]
                    # Ordinary document hyperlinks are evidence links. Linked
                    # OLE objects, templates and package parts are not needed.
                    if item.get('TargetMode') == 'External' and reltype != 'hyperlink':
                        archive.close()
                        raise CandidateError('external native data/template relationship')
        return archive
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, OSError, EOFError, zlib.error, struct.error, NotImplementedError) as exc:
        if isinstance(exc, CandidateError):
            raise
        raise CandidateError('invalid native OOXML package: ' + str(exc)) from exc


def read_book(path):
    """Read editable native values; a caller must recalculate formulas first."""
    try:
        with _package(path) as archive:
            def xml(name):
                return ET.fromstring(archive.read(name))
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(n.itertext()) for n in xml('xl/sharedStrings.xml').findall(S + 'si')]
            styles = []
            if 'xl/styles.xml' in archive.namelist():
                tree = xml('xl/styles.xml')
                formats = {int(n.get('numFmtId')): n.get('formatCode', '') for n in tree.findall(S + 'numFmts/' + S + 'numFmt')}
                fonts = list(tree.find(S + 'fonts') or [])
                fills = list(tree.find(S + 'fills') or [])
                for node in tree.findall(S + 'cellXfs/' + S + 'xf'):
                    font = fonts[int(node.get('fontId', '0'))] if fonts else None
                    fill = fills[int(node.get('fillId', '0'))] if fills else None
                    size = font.find(S + 'sz') if font is not None else None
                    color = font.find(S + 'color') if font is not None else None
                    fg = fill.find(S + 'patternFill/' + S + 'fgColor') if fill is not None else None
                    hidden = formats.get(int(node.get('numFmtId', '0')), '').replace(' ', '') == ';;;'
                    hidden = hidden or size is not None and float(size.get('val', '11')) <= 0
                    if color is not None and color.get('rgb'):
                        rgb = color.get('rgb')[-6:].upper()
                        background = fg.get('rgb', '')[-6:].upper() if fg is not None else ''
                        hidden = hidden or rgb == background or rgb == 'FFFFFF' and background in {'', 'FFFFFF'}
                    protection = node.find(S + 'protection')
                    styles.append({'visible': not hidden, 'locked': protection is None or protection.get('locked', '1') not in {'0', 'false'}})
            relationships = {n.get('Id'): posixpath.normpath(posixpath.join('xl', n.get('Target', ''))) if not n.get('Target', '').startswith('/') else n.get('Target').lstrip('/') for n in xml('xl/_rels/workbook.xml.rels')}
            result = []
            for sheet in xml('xl/workbook.xml').findall(S + 'sheets/' + S + 'sheet'):
                tree = xml(relationships[sheet.get(R + 'id')])
                cells = {}
                hidden_columns = set()
                protection = tree.find(S + 'sheetProtection')
                sheet_protected = protection is not None and protection.get('sheet', '1') not in {'0', 'false'}
                for column in tree.findall(S + 'cols/' + S + 'col'):
                    if column.get('hidden') in {'1', 'true'} or column.get('width') == '0':
                        lo, hi = int(column.get('min')), int(column.get('max'))
                        if hi - lo > 16384:
                            raise CandidateError('invalid native column range')
                        hidden_columns.update(range(lo, hi + 1))
                for row in tree.findall(S + 'sheetData/' + S + 'row'):
                    row_visible = row.get('hidden') not in {'1', 'true'} and row.get('ht') != '0'
                    for cell in row.findall(S + 'c'):
                        address = cell.get('r')
                        rownum, column = _column(address)
                        node = cell.find(S + 'v')
                        value = node.text if node is not None else None
                        kind = cell.get('t')
                        style = styles[int(cell.get('s', '0'))] if styles else {'visible': True, 'locked': True}
                        if kind == 'inlineStr':
                            inline = cell.find(S + 'is')
                            value = ''.join(inline.itertext()) if inline is not None else ''
                        elif kind == 's':
                            value = strings[int(value)]
                        elif kind == 'b':
                            value = value == '1'
                        elif kind not in {'str', 'e', 'd'} and value is not None:
                            value = float(value)
                            value = int(value) if math.isfinite(value) and value.is_integer() else value
                        cells[(rownum, column)] = {'value': value, 'visible': sheet.get('state', 'visible') == 'visible' and row_visible and column not in hidden_columns and style['visible'], 'editable': not sheet_protected or not style['locked'], 'formula': cell.find(S + 'f') is not None, 'address': address}
                result.append({'name': sheet.get('name'), 'state': sheet.get('state', 'visible'), 'cells': cells})
            return result
    except (KeyError, ET.ParseError, ValueError, TypeError, IndexError, AttributeError, OverflowError, EOFError, zlib.error, struct.error, NotImplementedError) as exc:
        if isinstance(exc, CandidateError):
            raise
        raise CandidateError('invalid native XLSX package: ' + str(exc)) from exc


def extract_events(book, public):
    """Discover logical row tables and transposed tables; merge by explicit ID."""
    spec = public.get('results', {}).get('event_matrix.xlsx', {})
    aliases = {norm(a): key for key in EVENT_FIELDS for a in [key, key.replace('_', ' ')] + spec.get('column_aliases', {}).get(key, []) + COMMON_COLUMNS.get(key, [])}
    aliases.update({norm(x): 'selected' for x in ('selected', 'final_selected', '最终计数', '最终入选')})
    explicit_mappings, alias_conflicts = [], set()
    # Optional visible two-column declaration: canonical field + actual label.
    # This is a deterministic explicit mapping, not prose/answer inference.
    field_headers = {norm(x) for x in ('field_id', 'logical_field', 'canonical_field', '逻辑字段', '标准字段', '字段标识')}
    label_headers = {norm(x) for x in ('column_label', 'actual_header', 'header_label', '实际列名', '表头名称', '实际字段名')}
    for sheet in book:
        cells = sheet['cells']
        rows = sorted({r for r, c in cells})
        for row in rows:
            values = {c: cell for (r, c), cell in cells.items() if r == row}
            field_cols = [c for c, cell in values.items() if norm(cell['value']) in field_headers and cell['visible'] and cell['editable']]
            label_cols = [c for c, cell in values.items() if norm(cell['value']) in label_headers and cell['visible'] and cell['editable']]
            if len(field_cols) != 1 or len(label_cols) != 1:
                continue
            for rr in [r for r in rows if r > row]:
                field_cell = cells.get((rr, field_cols[0]), {})
                label_cell = cells.get((rr, label_cols[0]), {})
                field = field_cell.get('value')
                label = label_cell.get('value')
                if not isinstance(field, str) or field not in EVENT_FIELDS or not string(label) or not all(cell.get('visible') and cell.get('editable') for cell in (field_cell, label_cell)):
                    continue
                key = norm(label)
                if key in aliases and aliases[key] != field:
                    alias_conflicts.add(key)
                else:
                    aliases[key] = field
                explicit_mappings.append({'sheet': sheet['name'], 'row': rr, 'field': field, 'column_label': label})
    for key in alias_conflicts:
        aliases.pop(key, None)
    fragments = []
    headers = []
    for sheet in book:
        cells = sheet['cells']
        rownums = sorted({r for r, c in cells})
        found = []
        for rr in rownums:
            raw = {c: v for (r, c), v in cells.items() if r == rr}
            mapping = {c: aliases.get(norm(v['value'])) for c, v in raw.items()}
            known = {k for k in mapping.values() if k}
            if 'event_id' in known and len(known) >= 2:
                columns = {}
                for col, key in mapping.items():
                    if key and key not in columns:
                        columns[key] = col
                found.append((rr, columns))
                headers.append({'sheet': sheet['name'], 'row': rr, 'orientation': 'rows', 'fields': list(columns), 'mapping': columns, 'observed_labels': {key: raw[col]['value'] for key, col in columns.items()}})
        for rr, columns in found:
            end = min([r for r, m in found if r > rr] + [max(rownums, default=rr) + 1])
            for rownum in range(rr + 1, end):
                values = {k: parse_value(cells.get((rownum, col), {}).get('value')) for k, col in columns.items()}
                if not string(values.get('event_id')):
                    continue
                members = [cells[(rownum, col)] for col in columns.values() if (rownum, col) in cells]
                head = [cells[(rr, col)] for col in columns.values()]
                fragments.append(dict(values, _visible=all(x['visible'] for x in members + head), _editable=all(x['editable'] for x in members + head), _locations=[{'sheet': sheet['name'], 'row': rownum}], _conflicts=[]))
        # Equivalent transposed native tables have field labels down one column,
        # with event_id and at least two other logical fields.
        colnums = sorted({c for r, c in cells})
        for col in colnums:
            mapping = {r: aliases.get(norm(x['value'])) for (r, c), x in cells.items() if c == col}
            known = {k for k in mapping.values() if k}
            if 'event_id' not in known or len(known) < 3:
                continue
            keyrows = {}
            for row, key in mapping.items():
                if key and key not in keyrows:
                    keyrows[key] = row
            for valuecol in [c for c in colnums if c > col]:
                values = {k: parse_value(cells.get((row, valuecol), {}).get('value')) for k, row in keyrows.items()}
                if not string(values.get('event_id')):
                    continue
                members = [cells[(row, valuecol)] for row in keyrows.values() if (row, valuecol) in cells]
                labels = [cells[(row, col)] for row in keyrows.values()]
                fragments.append(dict(values, _visible=all(x['visible'] for x in members + labels), _editable=all(x['editable'] for x in members + labels), _locations=[{'sheet': sheet['name'], 'column': valuecol}], _conflicts=[]))
            headers.append({'sheet': sheet['name'], 'column': col, 'orientation': 'columns', 'fields': list(keyrows), 'mapping': keyrows, 'observed_labels': {key: cells[(row, col)]['value'] for key, row in keyrows.items()}})
    merged = {}
    for fragment in fragments:
        eid = fragment['event_id']
        if eid not in merged:
            merged[eid] = fragment
            continue
        target = merged[eid]
        for key, value in fragment.items():
            if key.startswith('_'):
                continue
            if key not in target or target[key] is None:
                target[key] = value
            elif value is not None and (type(target[key]) is not type(value) or target[key] != value):
                target['_conflicts'].append(key)
        target['_visible'] &= fragment['_visible']
        target['_editable'] &= fragment['_editable']
        target['_locations'].extend(fragment['_locations'])
    records = list(merged.values())
    selected = [r for r in records if r.get('selected') is True or isinstance(r.get('selected'), str) and norm(r['selected']) in {'yes', 'true', 'selected', '是', '入选'}]
    final = selected if selected else records
    return {'events': final, 'all_events': records, 'headers': headers, 'explicit_header_mappings': explicit_mappings, 'header_alias_conflicts': sorted(alias_conflicts), 'selection_unambiguous': len(final) == 4 and not alias_conflicts, 'slots': final[:4] + [None] * max(0, 4 - len(final))}


def read_docx(path):
    """Extract visible editable main-document paragraphs in document order."""
    try:
        with _package(path) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
            settings = ET.fromstring(archive.read('word/settings.xml')) if 'word/settings.xml' in archive.namelist() else None
            protected = settings.find(W + 'documentProtection') if settings is not None else None
            editable = protected is None or protected.get(W + 'enforcement', '0') in {'0', 'false', 'off'}
            body = root.find(W + 'body')
            if body is None:
                raise CandidateError('DOCX lacks native main body')
            instructions = [node.text or '' for node in root.iter(W + 'instrText')]
            instructions.extend(node.get(W + 'instr', '') for node in root.iter(W + 'fldSimple'))
            if any(re.search(r'\b(?:DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|DATABASE|MACROBUTTON|AUTOTEXTLIST)\b', instruction, re.I) for instruction in instructions):
                raise CandidateError('DOCX automatic/external field content unsupported')
            parents = {child: parent for parent in body.iter() for child in parent}
            paragraphs = []
            for p in body.iter(W + 'p'):
                pieces = []
                for run in p.iter(W + 'r'):
                    ancestor = parents.get(run)
                    deleted = False
                    while ancestor is not None and ancestor is not p:
                        deleted |= ancestor.tag in {W + 'del', W + 'moveFrom'}
                        ancestor = parents.get(ancestor)
                    if deleted:
                        continue
                    prop = run.find(W + 'rPr')
                    hidden = False
                    if prop is not None:
                        for key in ('vanish', 'webHidden'):
                            flag = prop.find(W + key)
                            hidden |= flag is not None and flag.get(W + 'val', '1') not in {'0', 'false', 'off'}
                        color = prop.find(W + 'color')
                        if color is not None and color.get(W + 'val', '').upper() == 'FFFFFF':
                            hidden = True
                    if hidden:
                        continue
                    for node in run.iter():
                        if node.tag == W + 't':
                            pieces.append(node.text or '')
                        elif node.tag in {W + 'br', W + 'tab'}:
                            pieces.append('\n' if node.tag == W + 'br' else '\t')
                text = ''.join(pieces).strip()
                if text:
                    paragraphs.append(text)
            return {'paragraphs': paragraphs, 'text': '\n'.join(paragraphs), 'editable': editable, 'visible_native': bool(paragraphs)}
    except (KeyError, ET.ParseError, ValueError, TypeError, AttributeError, EOFError, zlib.error, struct.error, NotImplementedError) as exc:
        if isinstance(exc, CandidateError):
            raise
        raise CandidateError('invalid native DOCX package: ' + str(exc)) from exc


def ledger_records(ledger):
    """Canonical views without requiring extra top-level JSON collections."""
    ledger = ledger if isinstance(ledger, dict) else {}
    sources = ledger.get('sources', [])
    sources = sources if isinstance(sources, list) else []
    collections = {key: list(ledger.get(key, [])) if isinstance(ledger.get(key), list) else [] for key in ('date_evidence', 'claims', 'brief_sections', 'lineage_edges', 'discovery_candidates')}
    if isinstance(ledger.get('lineage'), list):
        collections['lineage_edges'].extend(ledger['lineage'])
    if isinstance(ledger.get('discovery'), dict) and isinstance(ledger['discovery'].get('candidates'), list):
        collections['discovery_candidates'].extend(ledger['discovery']['candidates'])
    for source in sources:
        if not isinstance(source, dict):
            continue
        sid = source.get('source_id')
        for key in collections:
            items = source.get(key, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    item = dict(item)
                    if key == 'date_evidence':
                        item.setdefault('source_id', sid)
                collections[key].append(item)
    def index(items, key):
        result, duplicates = {}, set()
        for item in items:
            if not isinstance(item, dict) or not string(item.get(key)):
                continue
            ident = item[key]
            if ident in result:
                duplicates.add(ident)
            result[ident] = item
        return result, sorted(duplicates)
    maps, duplicates = {}, {}
    maps['sources'], duplicates['sources'] = index(sources, 'source_id')
    for key, ident in (('date_evidence', 'date_id'), ('claims', 'claim_id'), ('brief_sections', 'section_id')):
        maps[key], duplicates[key] = index(collections[key], ident)
    citation_map, citation_duplicates = {}, set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        for citation in source.get('citations', []) if isinstance(source.get('citations'), list) else []:
            if not isinstance(citation, dict) or not string(citation.get('citation_id')):
                continue
            cid = citation['citation_id']
            if cid in citation_map:
                citation_duplicates.add(cid)
            citation_map[cid] = (source.get('source_id') if isinstance(source.get('source_id'), str) else None, citation)
    maps['citations'] = citation_map
    duplicates['citations'] = sorted(citation_duplicates)
    return dict(collections, sources=sources, maps=maps, duplicates=duplicates)


def claim_slot_graph(owner, field, claim_ids, direct_citations, maps, duplicates):
    """Resolve transitive event/section -> multi-target claim -> citation IDs.

    Direct matrix references remain valid references, but do not have to repeat
    the entire citation closure of a claim shared across multiple objects.
    """
    claims = [maps['claims'][cid] for cid in claim_ids if cid in maps['claims'] and cid not in duplicates.get('claims', []) and owner in refs(maps['claims'][cid].get('event_id_or_section_id')) and field in refs(maps['claims'][cid].get('supports_fields'))]
    citations = sorted({cid for claim in claims for cid in refs(claim.get('citation_ids'))})
    def known(items):
        return bool(items) and all(cid in maps['citations'] and cid not in duplicates.get('citations', []) for cid in items)
    return {'claims': claims, 'citation_ids': citations, 'id_graph': bool(claims and known(citations) and known(direct_citations))}


def trusted_path(root, relative):
    if not isinstance(relative, str) or '\\' in relative or PurePosixPath(relative).is_absolute() or any(p in {'', '..', '.'} for p in relative.split('/')):
        raise TrustedEvidenceError('unsafe research bundle path')
    path = root / relative
    if not path.is_file() or path.is_symlink() or root not in path.resolve().parents:
        raise TrustedEvidenceError('research bundle file missing/unsafe: ' + relative)
    return path


def _get_time(value, label):
    if not isinstance(value, str):
        raise TrustedEvidenceError('trusted source ' + label + ' must be an aware timestamp')
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise TrustedEvidenceError('trusted source ' + label + ' timestamp invalid') from exc
    if parsed.tzinfo is None:
        raise TrustedEvidenceError('trusted source ' + label + ' timezone missing')
    return parsed


def source_acquisition(root, manifest, source, receipt):
    """Keep the current binding distinct from the original network GET.

    The managed 0.25 outer verifier authenticates the complete origin capsule.
    This offline rule additionally checks its row/wrapper/original-GET pointers
    and hashes, without loading old candidate/GT content into rule/Judge text.
    """
    provenance = source.get('provenance')
    if provenance is None:
        if receipt.get('schema_version') == 'wildclawbench.research-source-reuse-receipt/v1':
            raise TrustedEvidenceError('reuse receipt missing row provenance')
        original = receipt
        origin_sha = source['receipt_sha256']
        mode = 'fresh_network_get'
        original_path = source['receipt_path']
    else:
        if not isinstance(provenance, dict) or provenance.get('kind') != 'verified_snapshot_reuse' or provenance.get('projection_kind') != 'verified_frozen_origin_bytes':
            raise TrustedEvidenceError('trusted reuse provenance invalid')
        if receipt.get('schema_version') != 'wildclawbench.research-source-reuse-receipt/v1' or receipt.get('provenance') != provenance or receipt.get('collector_sha256') != manifest.get('collector_sha256') or any(key in receipt for key in ('started_at', 'finished_at')):
            raise TrustedEvidenceError('trusted reuse wrapper/provenance drift')
        origins = manifest.get('reuse_origins')
        if not isinstance(origins, list):
            raise TrustedEvidenceError('trusted reuse origin proofs missing')
        proofs = [proof for proof in origins if isinstance(proof, dict) and proof.get('path') == provenance.get('origin_path')]
        if len(proofs) != 1:
            raise TrustedEvidenceError('trusted reuse origin proof ambiguous/missing')
        proof = proofs[0]
        for pkey, okey in (('prior_identity', 'identity'), ('prior_attempt_manifest_sha256', 'attempt_manifest_sha256'), ('prior_lock_sha256', 'lock_sha256'), ('prior_bundle_manifest_sha256', 'bundle_manifest_sha256')):
            if provenance.get(pkey) != proof.get(okey):
                raise TrustedEvidenceError('trusted reuse origin identity/hash drift')
        if not isinstance(provenance.get('prior_identity'), dict) or not string(provenance.get('prior_source_id')) or not all(isinstance(provenance.get(key), str) and re.fullmatch(r'[a-f0-9]{64}', provenance[key]) for key in ('prior_attempt_manifest_sha256', 'prior_lock_sha256', 'prior_bundle_manifest_sha256', 'prior_source_sha256', 'prior_receipt_sha256', 'original_receipt_sha256')):
            raise TrustedEvidenceError('trusted reuse origin field types invalid')
        origin_relative = provenance.get('origin_path')
        if not string(origin_relative):
            raise TrustedEvidenceError('trusted reuse origin path invalid')
        origin_paths = {}
        for name, digest_key in (('attempt-manifest.json', 'prior_attempt_manifest_sha256'), ('research-sources.lock.json', 'prior_lock_sha256'), ('private/research-sources/manifest.json', 'prior_bundle_manifest_sha256')):
            origin_file = trusted_path(root, origin_relative + '/' + name)
            if sha(origin_file) != provenance[digest_key]:
                raise TrustedEvidenceError('trusted reuse origin manifest/lock SHA drift')
            origin_paths[name] = origin_file
        try:
            old_manifest = json.loads(origin_paths['private/research-sources/manifest.json'].read_text(encoding='utf-8'))
        except (ValueError, UnicodeError) as exc:
            raise TrustedEvidenceError('trusted reuse origin source manifest invalid') from exc
        old_rows = old_manifest.get('sources') if isinstance(old_manifest, dict) else None
        if not isinstance(old_rows, list):
            raise TrustedEvidenceError('trusted reuse origin source records invalid')
        old_rows = [row for row in old_rows if isinstance(row, dict) and row.get('source_id') == provenance['prior_source_id']]
        if len(old_rows) != 1:
            raise TrustedEvidenceError('trusted reuse prior source identity missing/ambiguous')
        old = old_rows[0]
        old_encoded = (json.dumps(old, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
        if hashlib.sha256(old_encoded).hexdigest() != provenance['prior_source_sha256'] or old.get('receipt_sha256') != provenance['prior_receipt_sha256'] or old.get('url') != source.get('url') or any(old.get(key) != source.get(key) for key in ('body_sha256', 'projection_sha256', 'text_sha256', 'media_type', 'final_url')):
            raise TrustedEvidenceError('trusted reuse prior source row/hash drift')
        original_path = source.get('original_receipt_path')
        path = trusted_path(root, original_path)
        origin_sha = sha(path)
        if origin_sha != provenance['original_receipt_sha256'] or receipt.get('original_receipt_sha256') != origin_sha or receipt.get('original_receipt_path') != original_path:
            raise TrustedEvidenceError('trusted original GET receipt SHA/path drift')
        try:
            original = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError) as exc:
            raise TrustedEvidenceError('trusted original GET receipt invalid JSON') from exc
        if not isinstance(original, dict) or original.get('schema_version') == 'wildclawbench.research-source-reuse-receipt/v1':
            raise TrustedEvidenceError('original-response must preserve a network GET receipt')
        reused = _get_time(provenance.get('reused_at'), 'reused_at')
        if reused.utcoffset() != dt.timedelta(0) or reused < _get_time(original.get('finished_at'), 'original GET finished_at'):
            raise TrustedEvidenceError('trusted reuse time precedes original GET')
        mode = 'verified_snapshot_reuse'
    if original.get('requested_url') != source.get('url') or original.get('final_url') != source.get('final_url') or original.get('body_sha256') != source.get('body_sha256') or original.get('media_type') != source.get('media_type'):
        raise TrustedEvidenceError('trusted original GET receipt source identity drift')
    if _get_time(original.get('started_at'), 'original GET started_at') > _get_time(original.get('finished_at'), 'original GET finished_at'):
        raise TrustedEvidenceError('trusted original GET time order invalid')
    return {'mode': mode, 'network_get_performed_this_collection': mode == 'fresh_network_get', 'current_receipt_path': source['receipt_path'], 'current_receipt_sha256': source['receipt_sha256'], 'original_get_receipt_path': original_path, 'original_get_receipt_sha256': origin_sha, 'original_get_started_at': original['started_at'], 'original_get_finished_at': original['finished_at'], 'original_get_collector_sha256': original.get('collector_sha256'), 'current_collector_sha256': manifest.get('collector_sha256'), 'origin_provenance': provenance}


def load_bundle(ledger, *, ledger_path=None):
    root_env = os.environ.get('GENERAL_E2E_RESEARCH_SOURCE_BUNDLE')
    digest = os.environ.get('GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256')
    if not root_env or not digest:
        raise TrustedEvidenceError('managed independent research bundle context missing')
    root = Path(root_env).resolve()
    path = trusted_path(root, 'manifest.json')
    if sha(path) != digest:
        raise TrustedEvidenceError('research manifest SHA drift')
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise TrustedEvidenceError('invalid trusted research manifest') from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get('sources'), list) or not isinstance(manifest.get('candidate_input_status'), str) or manifest.get('candidate_input_status') not in {'valid', 'missing_ledger', 'invalid_ledger'}:
        raise TrustedEvidenceError('research manifest contract invalid')
    if manifest.get('schema_version') != 'wildclawbench.research-source-bundle/v1' or not isinstance(manifest.get('bindings'), dict) or not isinstance(manifest.get('acquisition_identity'), dict):
        raise TrustedEvidenceError('production research bundle identity/bindings missing')
    if ledger_path is not None:
        entries = manifest['bindings'].get('deliverables')
        if not isinstance(entries, list):
            raise TrustedEvidenceError('research bundle deliverable bindings missing')
        selected_entry = [row for row in entries if isinstance(row, dict) and row.get('path') == 'results/source_ledger.json']
        path = Path(ledger_path)
        actual = sha(path) if path.is_file() else None
        if len(selected_entry) != 1 or selected_entry[0].get('exists') is not path.is_file() or selected_entry[0].get('sha256') != actual:
            raise TrustedEvidenceError('research bundle candidate ledger SHA binding drift')
    if manifest.get('errors') and (manifest['candidate_input_status'] == 'valid' or manifest['sources']):
        raise TrustedEvidenceError('research collector reported unresolved acquisition errors')
    rows = ledger.get('sources', []) if isinstance(ledger, dict) else []
    rows = rows if isinstance(rows, list) else []
    ledgermap = {s['source_id']: s for s in rows if isinstance(s, dict) and isinstance(s.get('source_id'), str)}
    byid = {}
    for source in manifest['sources']:
        if not isinstance(source, dict) or not isinstance(source.get('status'), str) or source.get('status') not in {'acquired', 'not_requested', 'candidate_invalid'}:
            raise TrustedEvidenceError('research source acquisition status invalid')
        sid = source.get('source_id')
        if not isinstance(sid, str) or sid in byid:
            raise TrustedEvidenceError('duplicate/missing trusted source ID')
        if ledger is not None and manifest['candidate_input_status'] == 'valid':
            row = ledgermap.get(sid)
            if row is None or source.get('url') != row.get('url') or source.get('citations') != row.get('citations'):
                raise TrustedEvidenceError('research bundle/candidate ledger binding drift: ' + sid)
        if source['status'] == 'acquired':
            paths = {}
            for part in ('body', 'text', 'projection', 'receipt'):
                p = trusted_path(root, source.get(part + '_path'))
                if not isinstance(source.get(part + '_sha256'), str) or sha(p) != source[part + '_sha256']:
                    raise TrustedEvidenceError('research ' + part + ' SHA drift: ' + sid)
                paths[part] = p
            try:
                projection = json.loads(paths['projection'].read_text(encoding='utf-8'))
                receipt = json.loads(paths['receipt'].read_text(encoding='utf-8'))
            except (ValueError, UnicodeError) as exc:
                raise TrustedEvidenceError('invalid trusted source projection/receipt') from exc
            if not isinstance(projection, dict) or projection.get('schema_version') != 'wildclawbench.research-source-text/v1' or projection.get('source_sha256') != source['body_sha256'] or projection.get('complete') is not True or not isinstance(projection.get('records'), list) or not projection.get('engine'):
                raise TrustedEvidenceError('source extraction incomplete/unbound: ' + sid)
            if not isinstance(receipt, dict) or receipt.get('requested_url') != source['url'] or receipt.get('final_url') != source.get('final_url') or receipt.get('body_sha256') != source['body_sha256']:
                raise TrustedEvidenceError('source receipt identity drift: ' + sid)
            acquisition = source_acquisition(root, manifest, source, receipt)
            source = dict(source, _text=projection, _body=paths['body'].read_bytes(), _receipt=receipt, _acquisition=acquisition)
        byid[sid] = source
    if ledger is not None and manifest['candidate_input_status'] == 'valid':
        selected = {sid for sid, source in ledgermap.items() if isinstance(source.get('access_status'), str) and source['access_status'] in {'read_full', 'read_excerpt'} or bool(source.get('citations'))}
        if set(byid) != selected:
            raise TrustedEvidenceError('research selected source set binding drift')
    summary = manifest.get('acquisition_summary')
    if summary is not None:
        actual = {'fresh_get_count': sum(source.get('_acquisition', {}).get('mode') == 'fresh_network_get' for source in byid.values()), 'reused_snapshot_count': sum(source.get('_acquisition', {}).get('mode') == 'verified_snapshot_reuse' for source in byid.values())}
        if summary != actual:
            raise TrustedEvidenceError('research fresh/reuse acquisition counts drift')
    return manifest, byid


def quote_match(quote, text, table=False):
    def clean(value):
        value = textnorm(value)
        # Native PDF line/cell layout may insert spaces next to Han text.
        # Preserve spacing between Latin words, punctuation, case and digits.
        value = re.sub(r'(?<=[\u3400-\u9fff])\s+|\s+(?=[\u3400-\u9fff])', '', value)
        return re.sub(r'\s+', '', value.replace('|', ' ')) if table else value
    quote, text = clean(quote), clean(text)
    if quote and quote in text:
        return True
    parts = [p.strip() for p in re.split(r'(?:\.{3}|…+|\[\.\.\.\])', quote) if p.strip()]
    if len(parts) < 2:
        return False
    cursor = 0
    for part in parts:
        position = text.find(part, cursor)
        if position < 0:
            return False
        cursor = position + len(part)
    return True


class _HtmlLocator(HTMLParser):
    """Ephemeral native HTML index, always backed by trusted body SHA.

    This indexes visible locations in the actual acquired body; it is not an
    alternative source fetch/cache or an independently authored text oracle.
    Only selected locations are emitted into managed rule observations.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.headings, self.anchors, self.tables = [], [], {}, []
        self.frames = []
        self.heading = self.table = self.row = self.cell = None
        self.links, self.current_link = [], None
        self.spans, self.pending_spans = [], []

    def text_offset(self):
        return sum(len(x) for x in self.parts)

    def handle_starttag(self, tag, attrs):
        attrs = {key: value or '' for key, value in attrs}
        inherited = self.frames[-1][1] if self.frames else False
        hidden = inherited or tag in {'script', 'style', 'noscript', 'template'} or 'hidden' in attrs or attrs.get('aria-hidden', '').lower() == 'true'
        if tag not in {'meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'area', 'base', 'embed', 'param', 'track', 'wbr'}:
            self.frames.append((tag, hidden))
        if hidden:
            return
        if tag in {'p', 'div', 'li', 'br', 'article', 'main', 'section', 'header', 'footer', 'table', 'tr', 'td', 'th', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            self.parts.append('\n' if tag not in {'td', 'th'} else ' ')
        if attrs.get('id'):
            self.anchors[attrs['id']] = self.text_offset()
        if tag == 'a' and attrs.get('href'):
            self.current_link = {'href': attrs['href'], 'start': self.text_offset()}
        classes = (attrs.get('class', '') + ' ' + attrs.get('id', '')).lower()
        if tag in {'article', 'main'} or tag == 'time' or re.search(r'date|publish|timestamp|updated', classes):
            kind = 'body' if tag in {'article', 'main'} else 'update' if 'updat' in classes else 'date'
            self.pending_spans.append({'depth': len(self.frames) - 1, 'kind': kind, 'start': self.text_offset()})
        if re.fullmatch(r'h[1-6]', tag):
            self.heading = {'level': int(tag[1]), 'start': self.text_offset(), 'parts': [], 'id': attrs.get('id')}
        if tag == 'table':
            self.table = {'start': self.text_offset(), 'rows': [], 'heading': self.headings[-1]['text'] if self.headings else ''}
        if tag == 'tr' and self.table is not None:
            self.row = []
        if tag in {'td', 'th'} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.frames and self.frames[-1][1]:
            return
        self.parts.append(data)
        if self.heading is not None:
            self.heading['parts'].append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        hidden = self.frames[-1][1] if self.frames else False
        removed_index = len(self.frames)
        for index in range(len(self.frames) - 1, -1, -1):
            if self.frames[index][0] == tag:
                removed_index = index
                del self.frames[index:]
                break
        if hidden:
            return
        for span in self.pending_spans[:]:
            if span['depth'] >= removed_index:
                self.spans.append(dict(span, end=self.text_offset()))
                self.pending_spans.remove(span)
        if tag == 'a' and self.current_link is not None:
            self.links.append(dict(self.current_link, end=self.text_offset()))
            self.current_link = None
        if re.fullmatch(r'h[1-6]', tag) and self.heading is not None:
            self.heading['text'] = textnorm(''.join(self.heading.pop('parts'))).lstrip('# ').strip()
            self.headings.append(self.heading)
            self.heading = None
        if tag in {'td', 'th'} and self.cell is not None:
            self.row.append(textnorm(''.join(self.cell)))
            self.cell = None
        if tag == 'tr' and self.table is not None and self.row is not None:
            self.table['rows'].append(self.row)
            self.row = None
        if tag == 'table' and self.table is not None:
            self.table['end'] = self.text_offset()
            self.tables.append(self.table)
            self.table = None
        if tag in {'p', 'div', 'li', 'article', 'main', 'section', 'header', 'footer', 'tr', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            self.parts.append('\n')


def _html_location(body, media_type, locator, base_url=''):
    charset = re.search(r'charset\s*=\s*[\"\']?([^;\s\"\']+)', media_type, re.I)
    parser = _HtmlLocator()
    try:
        parser.feed(body.decode(charset[1] if charset else 'utf-8-sig', errors='strict'))
        parser.close()
    except (ValueError, UnicodeError, LookupError, RecursionError) as exc:
        raise TrustedEvidenceError('trusted HTML locator indexing failed: ' + str(exc)) from exc
    full = ''.join(parser.parts)
    start, end = 0, len(full)
    if 'href' in locator:
        requested = locator['href']
        if not isinstance(requested, str):
            return '', False, 'invalid native link target'
        links = [link for link in parser.links if urllib.parse.urljoin(base_url, link['href']) == urllib.parse.urljoin(base_url, requested)]
        if 'heading' in locator:
            title = heading_key(locator['heading']) if isinstance(locator['heading'], str) else ''
            matches = [h for h in parser.headings if heading_key(h['text']) == title]
            if len(matches) != 1:
                return '', False, 'declared link heading absent or ambiguous'
            heading = matches[0]
            heading_end = min([h['start'] for h in parser.headings if h['start'] > heading['start'] and h['level'] <= heading['level']] + [len(full)])
            links = [link for link in links if heading['start'] <= link['start'] < heading_end]
        values = [full[link['start']:link['end']] for link in links]
        if isinstance(locator.get('anchor_text'), str):
            values = [value for value in values if textnorm(value) == textnorm(locator['anchor_text'])]
        return '\n'.join(values), False, 'actual HTML link target/anchor within any declared heading'
    if 'heading' in locator:
        title = heading_key(locator['heading']) if isinstance(locator['heading'], str) else ''
        generic = {'article body': 'body', 'article date': 'date', 'article update note': 'update'}
        if title.casefold() in generic:
            kind = generic[title.casefold()]
            parts = [full[span['start']:span['end']] for span in parser.spans if span['kind'] == kind]
            if kind == 'body' and not parts:
                parts = [full]
            if kind in {'date', 'update'}:
                parts.extend(line for line in full.splitlines() if DATE_TOKEN.search(line) and (kind == 'date' or re.match(r'\s*(?:Updated|Last updated|更新)', line, re.I)))
            return '\n'.join(parts), False, 'actual visible HTML ' + kind + ' region'
        matches = [h for h in parser.headings if heading_key(h['text']) == title]
        if not matches or len(matches) > 1 and not locator.get('anchor'):
            return '', False, 'actual HTML heading absent or ambiguous'
        heading = matches[0]
        start = heading['start']
        end = min([h['start'] for h in parser.headings if h['start'] > start and h['level'] <= heading['level']] + [len(full)])
    if 'anchor' in locator:
        anchor = urllib.parse.unquote(str(locator['anchor']).lstrip('#'))
        if anchor not in parser.anchors:
            return '', False, 'actual HTML anchor absent'
        start = parser.anchors[anchor]
        end = min([h['start'] for h in parser.headings if h['start'] > start] + [len(full)])
    requested_row = locator.get('table_row', locator.get('row'))
    if any(k in locator for k in ('table', 'table_row', 'cell')):
        tables = [t for t in parser.tables if start <= t['start'] < end]
        requested = locator.get('table')
        if isinstance(requested, dict):
            requested_row = requested.get('row', requested.get('table_row', requested_row))
            requested = requested.get('index', requested.get('heading'))
        if requested is not None and not isinstance(requested, (str, int, float)):
            return '', True, 'invalid actual HTML table locator'
        if integer(requested) is not None:
            index = integer(requested)
            tables = tables[index - 1:index] if index and index > 0 else []
        elif string(requested):
            tables = [t for t in tables if textnorm(requested) in {textnorm(t['heading']), textnorm(' '.join(t['rows'][0])) if t['rows'] else ''}]
        rows = [row for table in tables for row in table['rows']]
        if requested_row is not None:
            if isinstance(requested_row, (int, float)) and not isinstance(requested_row, bool):
                index = integer(requested_row)
                rows = rows[index - 1:index] if index and index > 0 else []
            else:
                rows = [row for row in rows if any(textnorm(requested_row) == textnorm(cell) for cell in row)]
        if 'cell' in locator:
            cell = locator['cell']
            column = integer(cell)
            if column is not None and column > 0:
                rows = [[row[column - 1]] for row in rows if len(row) >= column]
            elif isinstance(cell, str):
                columns = {i for table in tables if table['rows'] for i, value in enumerate(table['rows'][0]) if textnorm(value) == textnorm(cell)}
                rows = [[row[c]] for row in rows for c in sorted(columns) if len(row) > c]
            else:
                rows = []
        return '\n'.join(' | '.join(row) for row in rows), True, 'actual HTML logical table/row'
    segment = full[start:end]
    # Route normal HTML paragraph/line locators through the same deterministic
    # text locator, with no semantic inference or arbitrary fuzzy matching.
    if 'paragraph' in locator or 'lines' in locator:
        return locate({'complete': True, 'records': [{'locator': {}, 'text': segment}]}, {k: v for k, v in locator.items() if k in {'paragraph', 'lines'}})
    if 'heading' in locator or 'anchor' in locator:
        return segment, False, 'actual HTML heading/anchor section'
    return '', False, 'no native HTML location requested'


def _metadata_selected(projection, locator):
    key = locator.get('metadata_key', locator.get('property'))
    path = locator.get('json_path', locator.get('json_pointer'))
    rows = projection.get('metadata', {}).get('observations', [])
    selected = []
    keys = {key} if isinstance(key, str) else set()
    if isinstance(key, str):
        keys.update(re.findall(r'meta\s*\[\s*(?:name|property)\s*=\s*[\"\']?([^\]\"\'\s]+)', key, re.I))
        keys.update(re.findall(r'\b(datePublished|dateModified|article:published_time|article:modified_time|published_time)\b', key))
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        if key is not None and row.get('property') not in keys:
            continue
        if path is not None and path not in (row.get('json_path'), row.get('json_pointer')):
            continue
        if 'script_index' in locator and row.get('script_index') != locator['script_index']:
            continue
        value = row.get('value')
        selected.append(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True))
    return '\n'.join(selected)


def locate(projection, locator):
    """Resolve only within the managed helper projection, without fuzzy text."""
    if not isinstance(projection, dict) or projection.get('complete') is not True:
        raise TrustedEvidenceError('managed source projection incomplete')
    if not isinstance(locator, dict) or not locator:
        return '', False, 'missing structured locator'
    locator = locator_aliases(locator)
    if 'metadata_key' in locator or isinstance(locator.get('kind'), str) and locator['kind'] in {'metadata', 'jsonld', 'html_meta'}:
        text = _metadata_selected(projection, locator)
        return text, False, 'metadata field' if text else 'metadata field not observed'
    if 'json_path' in locator or 'json_pointer' in locator:
        metadata = _metadata_selected(projection, locator)
        if metadata:
            return metadata, False, 'exact observed metadata JSON path'
    records = projection.get('records', [])
    if not isinstance(records, list):
        raise TrustedEvidenceError('managed source projection records invalid')
    records = [r for r in records if isinstance(r, dict) and isinstance(r.get('text'), str) and isinstance(r.get('locator'), dict)]
    records = [dict(record, text=markdown_literal_text(record['text'])) if record['locator'].get('kind') == 'router_json' else record for record in records]
    if 'page' in locator:
        page = integer(locator['page'])
        records = [r for r in records if page is not None and page > 0 and r['locator'].get('page') == page]
    if 'record' in locator:
        index = integer(locator['record'])
        records = records[index - 1:index] if index is not None and index > 0 else []
    if 'json_path' in locator or 'json_pointer' in locator:
        target = locator.get('json_path', locator.get('json_pointer'))
        records = [r for r in records if target in (r['locator'].get('json_path'), r['locator'].get('json_pointer'))]
    full = '\n\n'.join(r['text'] for r in records)
    if not full:
        return '', False, 'source record/page/path not present'
    lines = full.splitlines()
    if 'heading' in locator:
        heading = heading_key(locator['heading']) if isinstance(locator['heading'], str) else ''
        matches = [i for i, line in enumerate(lines) if heading_key(line) == heading]
        document_titles = [row.get('value') for row in projection.get('metadata', {}).get('observations', []) if isinstance(row, dict) and row.get('property') in {'Title', 'title'}]
        if not matches and any(isinstance(title, str) and heading_key(title) == heading for title in document_titles):
            return full, False, 'document title observed in independent structured source'
        if len(matches) != 1:
            return '', False, 'source heading absent or ambiguous'
        start = matches[0]
        marks = re.match(r'^\s*(#{1,6})\s+', lines[start])
        end = len(lines)
        if marks:
            level = len(marks[1])
            end = next((i for i in range(start + 1, len(lines)) if re.match(r'^\s*#{1,' + str(level) + r'}\s+', lines[i])), len(lines))
        lines = lines[start:end]
        full = '\n'.join(lines)
    table = any(k in locator for k in ('table', 'table_row', 'cell'))
    if table:
        # Literal Markdown logical rows exist in native MDContent projections.
        # Static HTML tables may be cited by paragraph/heading + original quote.
        rows = [line for line in lines if '|' in line]
        requested = locator.get('table_row', locator.get('row'))
        table_spec = locator.get('table')
        if isinstance(table_spec, dict):
            requested = table_spec.get('row', table_spec.get('table_row', requested))
        if requested is not None:
            if integer(requested) is not None and not isinstance(requested, str):
                index = integer(requested)
                rows = rows[index - 1:index] if index and index > 0 else []
            else:
                rows = [r for r in rows if any(textnorm(c) == textnorm(requested) for c in r.strip('|').split('|'))]
        if not rows:
            return '', True, 'logical table row not present'
        if 'cell' in locator:
            column = integer(locator['cell'])
            if column is not None and column > 0:
                rows = [r.strip('|').split('|')[column - 1] for r in rows if len(r.strip('|').split('|')) >= column]
            else:
                return '', True, 'logical table cell requires positive column'
        return '\n'.join(rows), True, 'logical table row'
    if 'lines' in locator:
        limits = locator['lines']
        if not isinstance(limits, list) or len(limits) != 2 or any(integer(x) is None for x in limits):
            return '', False, 'invalid line locator'
        first, last = map(integer, limits)
        if first < 1 or last < first or last > len(lines):
            return '', False, 'line locator outside source'
        return '\n'.join(lines[first - 1:last]), False, 'source line range'
    if 'paragraph' in locator:
        paragraph = locator['paragraph']
        if integer(paragraph) is not None and not isinstance(paragraph, str):
            index = integer(paragraph)
            values = [line for line in lines if line.strip()]
            return (values[index - 1] if index and 0 < index <= len(values) else ''), False, 'source paragraph'
        if isinstance(paragraph, str) and paragraph.strip():
            matches = [line for line in lines if textnorm(paragraph) in textnorm(line)]
            return '\n'.join(matches), False, 'source paragraph text'
        return '', False, 'invalid paragraph locator'
    if 'anchor' in locator and 'heading' not in locator:
        return '', False, 'anchor needs explicit projected heading or paragraph'
    if any(k in locator for k in ('page', 'record', 'heading', 'json_path', 'json_pointer')):
        return full, False, 'source record/section'
    return '', False, 'locator has no supported source location'


def resolve_citation(source, citation):
    if not isinstance(source, dict) or source.get('status') != 'acquired':
        return {'resolved': False, 'reason': 'source not independently acquired'}
    if not isinstance(citation, dict) or not string(citation.get('quote')) or not isinstance(citation.get('locator'), dict):
        return {'resolved': False, 'reason': 'missing quote/structured locator'}
    candidates = []
    for name, projection in (('managed_supplement', source.get('_derived')), ('production_projection', source.get('_text'))):
        if isinstance(projection, dict) and projection.get('complete') is True:
            selected, table, reason = locate(projection, citation['locator'])
            candidates.append((selected, table, reason, name))
    media = source.get('media_type', '')
    body = source.get('_body', b'')
    if isinstance(media, str) and isinstance(body, bytes) and ('html' in media.lower() or body.lstrip().lower().startswith((b'<!doctype html', b'<html'))):
        candidates.append((*_html_location(body, media, locator_aliases(citation['locator']), source.get('final_url', source.get('url', ''))), 'trusted_original_HTML_structure'))
    for selected, table, reason, origin in candidates:
        if selected and quote_match(citation['quote'], selected, table):
            return {'resolved': True, 'reason': 'verbatim original quote at independent location', 'selected_text': selected, 'selected_text_sha256': hashlib.sha256(selected.encode('utf-8')).hexdigest(), 'locator': citation['locator'], 'evidence_origin': origin, 'normalization': 'NFKC/whitespace; verified router MDContent also decodes only CommonMark literal punctuation escapes', 'source_body_sha256': source.get('body_sha256'), 'source_projection_sha256': source.get('projection_sha256')}
    selected, table, reason, origin = candidates[0] if candidates else ('', False, 'independent source has no usable projection', None)
    return {'resolved': False, 'reason': reason if not selected else 'quote not at independent location', 'selected_text': selected, 'locator': citation['locator'], 'evidence_origin': origin}


MONTHS = {name.casefold(): index for index in range(1, 13) for name in (calendar.month_name[index], calendar.month_abbr[index])}
DATE_TOKEN = re.compile(r'(?<![\w-])\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?(?![\w-])|(?<![\w-])\d{4}-\d{2}(?![\w-])|\d{4}年\d{1,2}月(?:\d{1,2}日)?|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})|\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b', re.I)
_MONTH_WORD = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
DATE_TOKEN = re.compile(DATE_TOKEN.pattern + r'|(?<![\w-])\d{4}-\d{1,2}-\d{1,2}(?![\w-])|(?<![\w-])\d{4}-\d{1,2}(?![\w-])|\b' + _MONTH_WORD + r'\.?\s+\d{4}\b|\b\d{1,2}\s+' + _MONTH_WORD + r'\.?\s+\d{4}\b', re.I)


def date_token(value):
    if not isinstance(value, str):
        return None
    value = textnorm(value)
    try:
        if re.fullmatch(r'\d{4}-\d{1,2}', value):
            year, month = map(int, value.split('-'))
            return ('month', dt.date(year, month, 1).strftime('%Y-%m'))
        if re.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}', value):
            return ('date', dt.date(*map(int, value.split('-'))).isoformat())
        if re.match(r'^\d{4}-\d\d-\d\d[T ]\d\d:', value):
            parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            return ('timestamp', parsed)
        match = re.fullmatch(r'(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?', value)
        if match:
            parsed = dt.date(int(match[1]), int(match[2]), int(match[3] or 1))
            return ('date', parsed.isoformat()) if match[3] else ('month', parsed.strftime('%Y-%m'))
        clean = re.sub(r'(\d)(?:st|nd|rd|th)\b', r'\1', value, flags=re.I).replace(',', '').replace('.', '')
        match = re.fullmatch(r'([A-Za-z]+)\s+(\d{4})', clean)
        if match and match[1].casefold() in MONTHS:
            return ('month', dt.date(int(match[2]), MONTHS[match[1].casefold()], 1).strftime('%Y-%m'))
        match = re.fullmatch(r'([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})', clean)
        if match and match[1].casefold() in MONTHS:
            return ('date', dt.date(int(match[3]), MONTHS[match[1].casefold()], int(match[2])).isoformat())
        match = re.fullmatch(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', clean)
        if match and match[2].casefold() in MONTHS:
            return ('date', dt.date(int(match[3]), MONTHS[match[2].casefold()], int(match[1])).isoformat())
    except (ValueError, OverflowError):
        return None
    return None


def _same_token(a, b):
    if not a or not b or a[0] != b[0]:
        return False
    if a[0] == 'timestamp':
        left, right = a[1], b[1]
        return left.replace(tzinfo=None) == right.replace(tzinfo=None) and left.utcoffset() == right.utcoffset()
    return a[1] == b[1]


def raw_bound(raw, selected):
    if isinstance(raw, dict):
        return all(key in raw and raw_bound(raw[key], selected) for key in ('start', 'end'))
    token = date_token(raw)
    if not token:
        return False
    observed = [date_token(match.group()) for match in DATE_TOKEN.finditer(selected)]
    return any(_same_token(token, candidate) for candidate in observed)


def interval_parts(value):
    """Explicit object or unambiguous two-token interval string equivalence."""
    if isinstance(value, dict) and 'start' in value and 'end' in value:
        return dict(value)
    if not isinstance(value, str):
        return None
    tokens = [match.group() for match in DATE_TOKEN.finditer(value)]
    if len(tokens) != 2:
        return None
    between = DATE_TOKEN.sub('', value).strip()
    if not re.fullmatch(r'[\s\[\](){};,/至到–—-]*', between):
        return None
    result = {'start': tokens[0], 'end': tokens[1]}
    if value.lstrip().startswith(('[', '(')) and value.rstrip().endswith((']', ')')):
        result['start_inclusive'] = value.lstrip().startswith('[')
        result['end_inclusive'] = value.rstrip().endswith(']')
    return result


def normalized_label(value):
    if isinstance(value, dict):
        for key in ('value', 'label', 'source_calendar_label', 'date', 'month'):
            if key in value:
                return value[key]
        return None
    return value


def _timestamp(raw, timezone):
    token = date_token(raw)
    if not token or token[0] != 'timestamp':
        return None
    value = token[1]
    if value.tzinfo is None:
        if not string(timezone) or unknown(timezone):
            return None
        zone = timezone_label(timezone)
        if zone is None:
            return None
        value = value.replace(tzinfo=zone)
    return value


def timezone_label(label):
    if not isinstance(label, str):
        return None
    if label in {'UTC', 'GMT', 'Z', 'Etc/UTC'}:
        return dt.timezone.utc
    match = re.fullmatch(r'(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?', label)
    if match:
        hour, minute = int(match[2]), int(match[3] or 0)
        if hour > 23 or minute > 59:
            return None
        return dt.timezone((1 if match[1] == '+' else -1) * dt.timedelta(hours=hour, minutes=minute))
    try:
        return ZoneInfo(label)
    except (ValueError, ZoneInfoNotFoundError):
        return None


def source_timezone_bound(raw, timezone, selected):
    """A candidate timezone is insufficient when the actual token is naive."""
    token = date_token(raw)
    if not token or token[0] != 'timestamp':
        return False
    if token[1].tzinfo is not None:
        return True
    target = _timestamp(raw, timezone)
    if target is None:
        return False
    labels = re.findall(r'(?<![\w/])(?:UTC|GMT)(?:[+-]\d{1,2}(?::?\d{2})?)?(?![\w+-])|(?<![\w/])[A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)*(?![\w/])|(?<![\w:])[+-]\d{2}:?\d{2}(?![\w:])', selected)
    for label in labels:
        zone = timezone_label(label)
        if zone is not None and token[1].replace(tzinfo=zone).utcoffset() == target.utcoffset():
            return True
    return False


def _timezone_matches(value, timezone):
    if not isinstance(timezone, str) or unknown(timezone):
        return False
    zone = timezone_label(timezone)
    if zone is None:
        return False
    offset = value.astimezone(zone).utcoffset()
    return value.utcoffset() == offset


def precision_check(observation):
    precision = observation.get('precision')
    raw = observation.get('raw_value')
    normalized = observation.get('normalized_value')
    timezone = observation.get('timezone')
    reason = observation.get('unknown_reason')
    if not isinstance(precision, str):
        return False
    if precision == 'unknown':
        return raw is None and unknown(normalized) and unknown(timezone) and string(reason)
    if precision == 'interval':
        raw, normalized = interval_parts(raw), interval_parts(normalized)
        if raw is None or normalized is None:
            return False
        if not all(key in raw and key in normalized for key in ('start', 'end')):
            return False
        endpoints = []
        for key in ('start', 'end'):
            token = date_token(raw[key])
            if not token:
                return False
            child = dict(observation, raw_value=raw[key], normalized_value=normalized[key], precision=token[0])
            if not precision_check(child):
                return False
            endpoints.append(token)
        if endpoints[0][0] != endpoints[1][0]:
            return False
        if endpoints[0][0] == 'timestamp':
            return _timestamp(raw['start'], timezone) <= _timestamp(raw['end'], timezone)
        return endpoints[0][1] <= endpoints[1][1]
    token = date_token(raw)
    if not token or token[0] != precision:
        return False
    if precision == 'timestamp':
        value = _timestamp(raw, timezone)
        parsed = _timestamp(normalized_label(normalized), 'unknown')
        return value is not None and _timezone_matches(value, timezone) and parsed is not None and parsed.utcoffset() == dt.timedelta(hours=8) and value.astimezone(ZoneInfo('Asia/Shanghai')) == parsed
    if precision not in {'date', 'month'} or not unknown(timezone) or normalized_label(normalized) != token[1]:
        return False
    reporting = observation.get('reporting_range', observation.get('normalized_reporting_range'))
    if isinstance(normalized, dict) and 'start' in normalized:
        reporting = normalized
    if reporting is not None:
        mode = reporting.get('mode', observation.get('reporting_mode')) if isinstance(reporting, dict) else None
        if not isinstance(reporting, dict) or mode != 'calendar_reporting_only':
            return False
        if 'start' not in reporting and 'end' not in reporting:
            return reporting.get('source_calendar_label', token[1]) == token[1]
        first = dt.date.fromisoformat(token[1] + '-01') if precision == 'month' else dt.date.fromisoformat(token[1])
        following = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) if precision == 'month' else first + dt.timedelta(days=1)
        if reporting.get('start') not in (first.isoformat(), first.isoformat() + 'T00:00:00+08:00') or reporting.get('end') not in (following.isoformat(), following.isoformat() + 'T00:00:00+08:00'):
            return False
    return True


def window_relation(observation, window):
    precision, raw = observation.get('precision'), observation.get('raw_value')
    start = dt.datetime.fromisoformat(window['start_inclusive'])
    end = dt.datetime.fromisoformat(window['end_exclusive'])
    if precision == 'interval':
        raw = interval_parts(raw)
        normalized = interval_parts(observation.get('normalized_value'))
        if raw is None or normalized is None:
            return 'invalid'
        observation = dict(observation, raw_value=raw, normalized_value=normalized)
    if precision == 'unknown':
        return 'indeterminate'
    if precision == 'timestamp':
        value = _timestamp(raw, observation.get('timezone'))
        return 'invalid' if value is None else 'in_window' if start <= value < end else 'outside'
    token = date_token(raw)
    if precision == 'month' and token and token[0] == 'month':
        return 'in_window' if token[1] == start.strftime('%Y-%m') and end.day == 1 and (end.year * 12 + end.month) - (start.year * 12 + start.month) == 1 else 'outside'
    if precision == 'date' and token and token[0] == 'date':
        day = dt.date.fromisoformat(token[1])
        # A natural day without a source timezone can cross either task edge.
        if day in {start.date() - dt.timedelta(days=1), start.date(), end.date() - dt.timedelta(days=1), end.date()}:
            return 'indeterminate'
        return 'in_window' if start.date() < day < end.date() - dt.timedelta(days=1) else 'outside'
    if precision == 'interval' and isinstance(raw, dict):
        normalized = observation.get('normalized_value', {})
        if not isinstance(normalized, dict):
            return 'invalid'
        first, last = date_token(raw.get('start')), date_token(raw.get('end'))
        if first and last and first[0] == last[0] == 'timestamp':
            left, right = _timestamp(raw['start'], observation.get('timezone')), _timestamp(raw['end'], observation.get('timezone'))
            if left is None or right is None or right < left:
                return 'invalid'
            end_exclusive = normalized.get('end_exclusive') is True or normalized.get('end_inclusive') is False or raw.get('end_exclusive') is True or raw.get('end_inclusive') is False
            if start <= left and (right < end or right == end and end_exclusive):
                return 'in_window'
            return 'outside'
        relations = []
        for key in ('start', 'end'):
            token = date_token(raw.get(key))
            if not token:
                return 'invalid'
            child = dict(observation, raw_value=raw[key], normalized_value=normalized.get(key), precision=token[0])
            relations.append(window_relation(child, window))
        if relations == ['in_window', 'in_window']:
            return 'in_window'
        return 'outside' if 'outside' in relations else 'indeterminate'
    return 'invalid'


def date_check(observation, maps, bundle, citation_checks, window):
    if not isinstance(observation, dict):
        return {'bound': False, 'precision': False, 'arithmetic': False, 'reason': 'date observation missing'}
    sid = observation.get('source_id')
    sid = sid if isinstance(sid, str) else None
    source = bundle.get(sid)
    citations = refs(observation.get('citation_ids'))
    valid_refs = bool(citations) and all(cid in citation_checks and citation_checks[cid]['resolved'] and maps['citations'].get(cid, (None,))[0] == sid for cid in citations)
    selected = '\n'.join(citation_checks[cid].get('selected_text', '') for cid in citations if cid in citation_checks)
    is_unknown = observation.get('precision') == 'unknown'
    if is_unknown:
        derived = source.get('_derived', {}) if source else {}
        metadata = derived.get('metadata', {})
        observed = metadata.get('observations', []) if isinstance(metadata, dict) else []
        observed = observed if isinstance(observed, list) else []
        known_publication = any(isinstance(row, dict) and isinstance(row.get('property'), str) and row['property'] in {'datePublished', 'article:published_time', 'published_time'} and date_token(row.get('value')) for row in observed)
        absence = observation.get('absence_check')
        explicit_absence = isinstance(absence, dict) and string(absence.get('checked')) and source and source.get('status') == 'acquired'
        inspected = valid_refs or explicit_absence
        if inspected and source and source.get('status') == 'acquired' and (not isinstance(metadata, dict) or metadata.get('complete') is not True):
            raise TrustedEvidenceError('independent unknown-date metadata inspection unresolved: ' + str(sid))
        bound = inspected and derived.get('complete') is True and isinstance(metadata, dict) and metadata.get('complete') is True and string(observation.get('unknown_reason')) and not ('publication' in refs(observation.get('role')) and known_publication)
    else:
        raw = interval_parts(observation.get('raw_value')) if observation.get('precision') == 'interval' else observation.get('raw_value')
        bound = valid_refs and raw_bound(raw, selected)
        if observation.get('precision') == 'timestamp':
            bound = bound and source_timezone_bound(raw, observation.get('timezone'), selected)
        elif observation.get('precision') == 'interval' and isinstance(raw, dict):
            bound = bound and all(not date_token(raw[key]) or date_token(raw[key])[0] != 'timestamp' or source_timezone_bound(raw[key], observation.get('timezone'), selected) for key in ('start', 'end'))
    precision = precision_check(observation)
    relation = window_relation(observation, window) if precision else 'invalid'
    stated = observation.get('window_relation')
    arithmetic = precision and relation != 'invalid' and (stated is None or stated == relation)
    return {'bound': bool(bound), 'precision': bool(precision), 'arithmetic': bool(arithmetic), 'computed_window_relation': relation, 'candidate_window_relation': stated, 'citation_ids': citations, 'role': observation.get('role'), 'raw_value': observation.get('raw_value'), 'reason': 'Mechanical token/precision/arithmetic only; date-to-event meaning requires Judge'}


def contains_id(text, ident):
    return string(ident) and bool(re.search(r'(?<![\w.-])' + re.escape(ident) + r'(?![\w.-])', text))


def brief_blocks(docx, sections):
    text = docx.get('text', '') if isinstance(docx, dict) else ''
    occurrences = [(m.start(), sid) for sid in sections for m in re.finditer(r'(?<![\w.-])' + re.escape(sid) + r'(?![\w.-])', text)]
    occurrences.sort()
    blocks = {sid: [] for sid in sections}
    for index, (start, sid) in enumerate(occurrences):
        end = occurrences[index + 1][0] if index + 1 < len(occurrences) else len(text)
        blocks[sid].append(text[start:end])
    return blocks
