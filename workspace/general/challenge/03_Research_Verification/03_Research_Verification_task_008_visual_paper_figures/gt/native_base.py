"""H034 facts-free OOXML readers, retained from the H032 native mechanism."""
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
        raise TrustedEvidenceError('candidate file exceeds evaluator parsing capacity (not a public candidate limit): ' + relative)
    return path


def read_ledger(path):
    try:
        result = json.loads(Path(path).read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise CandidateError('evidence_matrix.json must be UTF-8 JSON') from exc
    if not isinstance(result, dict):
        raise CandidateError('evidence_matrix.json must be an object')
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
            raise TrustedEvidenceError('normal native package exceeds evaluator parsing capacity')
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
        if isinstance(exc, (CandidateError, TrustedEvidenceError)):
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
                formats = {0:'General',9:'0%',10:'0.00%'}
                formats.update({int(n.get('numFmtId')): n.get('formatCode', '') for n in tree.findall(S + 'numFmts/' + S + 'numFmt')})
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
                    styles.append({'visible': not hidden, 'locked': protection is None or protection.get('locked', '1') not in {'0', 'false'},'number_format':formats.get(int(node.get('numFmtId','0')),'')})
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
                        cells[(rownum, column)] = {'value': value, 'number_format':style.get('number_format',''),'visible': sheet.get('state', 'visible') == 'visible' and row_visible and column not in hidden_columns and style['visible'], 'editable': not sheet_protected or not style['locked'], 'formula': cell.find(S + 'f') is not None, 'kind': kind, 'address': address}
                result.append({'name': sheet.get('name'), 'state': sheet.get('state', 'visible'), 'cells': cells})
            return result
    except (KeyError, ET.ParseError, ValueError, TypeError, IndexError, AttributeError, OverflowError, EOFError, zlib.error, struct.error, NotImplementedError) as exc:
        if isinstance(exc, (CandidateError, TrustedEvidenceError)):
            raise
        raise CandidateError('invalid native XLSX package: ' + str(exc)) from exc


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
        if isinstance(exc, (CandidateError, TrustedEvidenceError)):
            raise
        raise CandidateError('invalid native DOCX package: ' + str(exc)) from exc


