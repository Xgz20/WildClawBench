"""H030 answer-free offline readers; portable generic H029 helpers plus H030 mappings. No source facts or reference-answer reads."""
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
                        cells[(rownum, column)] = {'value': value, 'visible': sheet.get('state', 'visible') == 'visible' and row_visible and column not in hidden_columns and style['visible'], 'editable': not sheet_protected or not style['locked'], 'formula': cell.find(S + 'f') is not None, 'kind': kind, 'address': address}
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
        selected_entry = [row for row in entries if isinstance(row, dict) and row.get('path') == 'results/evidence_matrix.json']
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
        # Inline markup/rendering may insert whitespace just inside parentheses.
        # Keep every word, digit, sign and parenthesis, and never cross a node.
        value = re.sub(r'(?<=\()\s+|\s+(?=\))', '', value)
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



# H030 additions: representation normalization, not scientific eligibility.
import copy
from email.utils import parsedate_to_datetime

CONTENT_FIELDS = ('research_task', 'input_data', 'method', 'evaluation', 'results', 'limitations')
FLOW_KEYS = ('records', 'unresolved_records', 'duplicate_version_records', 'works', 'included', 'excluded', 'pending')
FIELD_ALIASES = {
 'work_id': ['工作编号', '工作ID', '作品ID', '作品编号', '工作标识'],
 'record_id': ['记录编号', '报告ID', '报告编号', '记录ID', '报告标识'],
 'title': ['题名', '标题', '论文题名', '报告描述', '题名或报告描述'],
 'selected_record_id': ['所选报告ID', '选定报告', '所选记录', '选定记录ID'],
 'report_version': ['所选版本', '所读版本', '报告版本', '版本', 'selected_version'],
 'decision': ['筛选结论', '决策', '纳入状态', '筛选决定', '纳入/排除/待决', '纳入排除待决'],
 'decision_reason': ['判断理由', '具体理由', '理由', '筛选理由', '决定理由'],
 'report_date': ['报告日期', '发表日期', '日期', '报告时间'],
 'date_basis': ['日期口径', '日期依据', '时间口径', 'basis'],
 'source': ['来源', '来源ID', '来源URL', '来源链接', 'source_id', 'url', 'sources'],
}


def nonnegative_integer(value):
    return type(value) is int and value >= 0


def normalize_pmid(value):
    if value is None:
        return None
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r'[0-9]+', value.strip()) and int(value.strip()) > 0:
        return str(int(value.strip()))
    raise CandidateError('PMID must be a positive integer or its decimal string; bool is invalid')


def pointer_tokens(pointer):
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise CandidateError('supports_fields requires a non-root JSON Pointer')
    if re.search(r'~(?![01])', pointer):
        raise CandidateError('invalid RFC6901 escape')
    return [token.replace('~1', '/').replace('~0', '~') for token in pointer[1:].split('/')]


def resolve_pointer(document, pointer):
    value = document
    for token in pointer_tokens(pointer):
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token) or int(token) >= len(value):
                raise CandidateError('JSON Pointer array index absent/invalid')
            value = value[int(token)]
        elif isinstance(value, dict) and token in value:
            value = value[token]
        else:
            raise CandidateError('JSON Pointer target absent')
    return value


def pointer_overlaps(left, right):
    a, b = pointer_tokens(left), pointer_tokens(right)
    return a[:len(b)] == b or b[:len(a)] == a


def normalize_identifier(kind, value):
    if kind == 'pmid':
        return normalize_pmid(value)
    if value is None:
        return None
    if not string(value):
        raise CandidateError('identifier must be a nonempty string or null')
    if kind == 'doi':
        value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)', '', value.strip(), flags=re.I)
        return value.casefold()
    return value.strip()


def calendar_token(value, precision=None):
    """Parse unambiguous date spellings without inventing missing precision."""
    if not string(value):
        return None
    raw = value.strip()
    if any(ch in raw for ch in '年月日'):
        raw = re.sub(r'\s+', '', raw)
    aware = None
    try:
        if re.match(r'^\d{4}-\d\d-\d\d[T ]\d\d:', raw):
            point = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
            if point.tzinfo is None:
                return None
            aware = point.isoformat()
            raw = point.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
            precision = 'day'
        elif re.search(r'\d{1,2}:\d{2}(?::\d{2})?\s*(?:UTC|GMT|[+-]\d{4})$', raw, re.I):
            point = parsedate_to_datetime(raw)
            if point.tzinfo is None:
                return None
            aware = point.isoformat(); raw = point.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat(); precision = 'day'
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return None
    parts = re.fullmatch(r'(\d{4})(?:[-/年](\d{1,2})(?:[-/月](\d{1,2})日?)?月?)?年?', raw)
    if parts:
        year, month, day = (int(x) if x is not None else None for x in parts.groups())
    else:
        year = month = day = None
        for fmt in ('%d %B %Y', '%d %b %Y', '%B %d, %Y', '%b %d, %Y', '%B %d %Y', '%b %d %Y', '%B %Y', '%b %Y'):
            try:
                parsed = dt.datetime.strptime(raw, fmt)
                year, month = parsed.year, parsed.month
                day = None if fmt in ('%B %Y', '%b %Y') else parsed.day
                break
            except ValueError:
                pass
        if year is None:
            months = {name.casefold():index for index in range(1,13) for name in (calendar.month_name[index],calendar.month_abbr[index])}
            months['sept']=9
            words = re.findall(r'[A-Za-z]+|[0-9]+',raw)
            named = [months[x.casefold()] for x in words if x.casefold() in months]
            years = [int(x) for x in words if re.fullmatch(r'\d{4}',x)]
            days = [int(x) for x in words if re.fullmatch(r'\d{1,2}',x)]
            allowed = all(x.isdigit() or x.casefold() in months for x in words)
            if allowed and len(named)==1 and len(years)==1 and len(days)<=1:
                year,month,day=years[0],named[0],days[0] if days else None
            else:
                return None
    if month is not None and not 1 <= month <= 12 or day is not None and day < 1:
        return None
    observed_precision = 'day' if day is not None else 'month' if month is not None else 'year'
    if precision is not None and precision not in {observed_precision, 'date' if observed_precision == 'day' else observed_precision}:
        return None
    try:
        start = dt.date(year, month or 1, day or 1)
        end = dt.date(year, month or 12, day if day is not None else calendar.monthrange(year, month)[1] if month else 31)
    except (ValueError, TypeError):
        return None
    label = f'{year:04d}' + (f'-{month:02d}' if month else '') + (f'-{day:02d}' if day else '')
    return {'value': label, 'precision': observed_precision, 'start': start.isoformat(), 'end': end.isoformat(), 'timestamp': aware, 'raw': value}


def date_parts_token(parts):
    if not isinstance(parts, dict) or not re.fullmatch(r'\d{4}', str(parts.get('year', ''))):
        return None
    year = parts['year']; month = parts.get('month'); day = parts.get('day')
    if day and not month:
        return None
    if month and not str(month).isdigit():
        lookup = {n.casefold(): i for i in range(1, 13) for n in (calendar.month_name[i], calendar.month_abbr[i])}
        month = lookup.get(str(month).casefold().rstrip('.'), 9 if str(month).casefold().rstrip('.')=='sept' else None)
        if month is None:
            return None
    return calendar_token(str(year) + (f'-{int(month):02d}' if month else '') + (f'-{int(day):02d}' if day else ''))


def date_object(value):
    if isinstance(value, dict):
        if value.get('status') == 'unknown' or value.get('value', MISSING) is None:
            return None
        candidates=[calendar_token(value[k],value.get('precision')) for k in ('timestamp','value','date','time','submitted','posted','version_date') if k in value and string(value[k])]
        candidates=[t for t in candidates if t is not None]
        if not candidates:
            candidates=[calendar_token(v,value.get('precision')) for v in value.values() if string(v)]
            candidates=[t for t in candidates if t is not None]
        return candidates[0] if candidates and all(t['value']==candidates[0]['value'] for t in candidates) else None
    return calendar_token(value)


def window_relation(token):
    if token is None:
        return 'unknown'
    if token['start'] >= '2021-01-01' and token['end'] <= '2026-09-30':
        return 'inside'
    if token['end'] < '2021-01-01' or token['start'] > '2026-09-30':
        return 'outside'
    return 'overlap'


_BASE_READ_BOOK = read_book

def _serial_label(value, date1904, code, builtin):
    cleaned = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', code).lower()
    if builtin in set(range(14, 23)) | {27, 30, 36, 50, 57}:
        precision = 'day'
    elif 'y' in cleaned or 'd' in cleaned:
        precision = 'day' if 'd' in cleaned else 'month' if 'm' in cleaned else 'year'
    else:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return None
    if not date1904 and 60 <= value < 61:
        return {'value': '1900-02-29 [Excel fictitious leap day]', 'precision': 'invalid', 'serial': value}
    epoch = dt.datetime(1904, 1, 1) if date1904 else dt.datetime(1899, 12, 31)
    offset = value if date1904 or value < 60 else value - 1
    try:
        day = (epoch + dt.timedelta(days=offset)).date()
    except (ValueError, OverflowError):
        return None
    return {'value': day.isoformat()[:4 if precision == 'year' else 7 if precision == 'month' else 10], 'precision': precision, 'serial': value}


def read_book(path):
    book = _BASE_READ_BOOK(path)
    with _package(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        prop = workbook.find(S + 'workbookPr')
        date1904 = prop is not None and prop.get('date1904') in {'1', 'true'}
        relationships = {n.get('Id'): posixpath.normpath(posixpath.join('xl', n.get('Target', ''))) if not n.get('Target', '').startswith('/') else n.get('Target').lstrip('/') for n in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        styles = []
        if 'xl/styles.xml' in archive.namelist():
            sty = ET.fromstring(archive.read('xl/styles.xml'))
            formats = {int(n.get('numFmtId')): n.get('formatCode', '') for n in sty.findall(S + 'numFmts/' + S + 'numFmt')}
            styles = [(int(n.get('numFmtId', '0')), formats.get(int(n.get('numFmtId', '0')), '')) for n in sty.findall(S + 'cellXfs/' + S + 'xf')]
        for sheet_node, sheet in zip(workbook.findall(S + 'sheets/' + S + 'sheet'), book):
            part = relationships[sheet_node.get(R + 'id')]
            tree = ET.fromstring(archive.read(part))
            relpart = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
            rels = {n.get('Id'): n for n in ET.fromstring(archive.read(relpart))} if relpart in archive.namelist() else {}
            hyperlinks = {}
            for h in tree.findall(S + 'hyperlinks/' + S + 'hyperlink'):
                relation = rels.get(h.get(R + 'id'))
                target = relation.get('Target') if relation is not None and relation.get('Type', '').endswith('/hyperlink') else h.get('location')
                if target:
                    hyperlinks[h.get('ref')] = target
            nodes = {n.get('r'): n for n in tree.findall(S + 'sheetData/' + S + 'row/' + S + 'c')}
            for cell in sheet['cells'].values():
                node = nodes[cell['address']]
                cell['hyperlink'] = hyperlinks.get(cell['address'])
                cell['raw_value'] = cell['value']; cell['date1904'] = date1904
                kind = node.get('t')
                style = styles[int(node.get('s', '0'))] if styles else (0, '')
                cell['numFmtId'], cell['formatCode'] = style
                if kind == 'd':
                    try:
                        point = dt.datetime.fromisoformat(str(cell['value']).replace('Z', '+00:00'))
                        label = (point.astimezone(ZoneInfo('Asia/Shanghai')) if point.tzinfo else point).date().isoformat()
                    except ValueError:
                        label = str(cell['value'])
                    date = calendar_token(label)
                else:
                    date = _serial_label(cell['value'], date1904, style[1], style[0])
                if date:
                    cell['value'] = date['value']; cell['date_precision'] = date['precision']
    return book


def extract_screening(book):
    aliases = {norm(alias): field for field, alts in FIELD_ALIASES.items() for alias in (field, *alts)}
    traces = []; conflicts = []; work_view = {}; report_view = {}
    # An explicit two-cell canonical-name / displayed-header mapping is optional.
    for sheet in book:
        rows = {}
        for (r, c), cell in sheet['cells'].items():
            if cell['visible'] and cell['editable']:
                rows.setdefault(r, {})[c] = cell
        for row in rows.values():
            ordered = [row[k]['value'] for k in sorted(row)]
            if len(ordered) == 2 and ordered[0] in FIELD_ALIASES and string(ordered[1]):
                key = norm(ordered[1]); field = ordered[0]
                if key in aliases and aliases[key] != field:
                    conflicts.append({'mapping': ordered})
                else:
                    aliases[key] = field
    def merge(row, origins):
        wid = row.get('work_id'); rid = row.get('record_id')
        targets = []
        if string(wid): targets.append((work_view, wid))
        if string(rid): targets.append((report_view, rid))
        for target, identity in targets:
            current = target.setdefault(identity, {})
            for key, value in row.items():
                if value is None or value == '': continue
                if key in current and norm(current[key]) != norm(value):
                    # Different records of one work need not have the same report fields.
                    if target is work_view and key in {'record_id', 'title', 'report_version', 'report_date', 'date_basis', 'source'}:
                        continue
                    conflicts.append({'id': identity, 'field': key, 'values': [current[key], value]})
                    current[key] = {'conflicting_values': [current[key], value]}
                else: current[key] = value
        traces.append({'origin': origins, 'values': row})
    for sheet in book:
        cells = {(r, c): cell for (r, c), cell in sheet['cells'].items() if cell['visible'] and cell['editable']}
        if not cells: continue
        maxr = max(r for r,c in cells); maxc = max(c for r,c in cells)
        if maxr * maxc > 2000000:
            raise CandidateError('screening layout exceeds deterministic mapping limit')
        for transpose in (False, True):
            grid = {(c,r) if transpose else (r,c): cell for (r,c),cell in cells.items()}
            lines = sorted({r for r,c in grid})
            headers = []
            for r in lines:
                mapping = {c: aliases[norm(cell['value'])] for (rr,c),cell in grid.items() if rr==r and norm(cell['value']) in aliases}
                if len(set(mapping.values()))>=2 and {'work_id','record_id'} & set(mapping.values()):
                    headers.append((r,mapping))
            for index,(r,mapping) in enumerate(headers):
                stop=headers[index+1][0] if index+1<len(headers) else max(rr for rr,c in grid)+1
                for rr in range(r+1,stop):
                    row={}; origins=[]
                    for c,field in mapping.items():
                        cell=grid.get((rr,c))
                        if cell is None: continue
                        value=cell['hyperlink'] if field=='source' and cell.get('hyperlink') else cell['value']
                        row[field]=value; origins.append({'sheet':sheet['name'],'cell':cell['address']})
                    if string(row.get('work_id')) or string(row.get('record_id')):
                        merge(row,origins)
    return {'works':work_view,'records':report_view,'mappings':traces,'conflicts':conflicts}


_BASE_LOCATE = locate

def locate(projection, locator):
    if isinstance(locator, dict) and projection.get('xml_nodes'):
        nodes=projection['xml_nodes']; text=projection['records'][0]['text']
        target=next((locator[k] for k in ('xpath','node','path','field','metadata_key') if k in locator),None)
        if isinstance(target,str):
            namespaces=locator.get('namespaces',{})
            if not isinstance(namespaces,dict): return '',False,'invalid XML namespace mapping'
            attrs=dict(locator.get('attributes',{})) if isinstance(locator.get('attributes',{}),dict) else {}
            attr_match=re.search(r"\[@([\w:.-]+)=[\"']([^\"']*)[\"']\]$",target)
            if attr_match:
                attrs[attr_match[1]]=attr_match[2]; target=target[:attr_match.start()]
            def expand(match):
                prefix,local=match[2],match[3]
                return match[1]+'{'+namespaces[prefix]+'}'+local if prefix in namespaces and isinstance(namespaces[prefix],str) else match[0]
            expanded=re.sub(r'(^|/)([A-Za-z_][\w.-]*):([A-Za-z_][\w.-]*)',expand,target)
            bare=lambda path:re.sub(r'\[1\](?=/|$)','',path)
            chosen=[]
            for node in nodes:
                paths={node['path'],node['namespace_path']}
                exact=target in paths or expanded in paths or bare(target) in {bare(p) for p in paths} or bare(expanded) in {bare(p) for p in paths}
                descendant=expanded.startswith(('.//','//')) and any(bare(p).endswith('/'+bare(expanded.lstrip('./'))) for p in paths)
                field=target==node['local_name']
                namespace=locator.get('namespace')
                if (exact or descendant or field) and all(node['attributes'].get(k)==v for k,v in attrs.items()) and (namespace is None or node['tag'].startswith('{'+str(namespace)+'}')):
                    chosen.append(node)
            record=locator.get('record',locator.get('record_id'))
            if record is not None:
                raw=record.get('pmid') if isinstance(record,dict) else record
                wanted=re.sub(r'^PMID\s*:\s*','',str(raw),flags=re.I)
                matches=[r for r in projection.get('metadata',{}).get('observations',[]) if r.get('property')=='PMID' and str(r.get('value'))==wanted]
                containers=[]
                for match in matches:
                    containers.extend(n for n in nodes if n['local_name'] in ('PubmedArticle','PubmedBookArticle') and match['path'].startswith(n['path']+'/'))
                if not containers and type(record) is int and record>=1:
                    articles=[n for n in nodes if n['local_name'] in ('PubmedArticle','PubmedBookArticle')]
                    containers=articles[record-1:record]
                if not containers: return '',False,'XML record identifier/ordinal absent'
                chosen=[n for n in chosen if any(n['path']==a['path'] or n['path'].startswith(a['path']+'/') for a in containers)]
            if chosen:
                return '\n'.join(text[n['text_start']:n['text_end']] for n in chosen), False, 'actual XML node span'
            return '',False,'XML node/field/namespace/attribute not found'
    return _BASE_LOCATE(projection,locator)


def discovery_shape(value):
    d=value if isinstance(value,dict) else {}
    site=d.get('site'); url=d.get('record_url')
    if site not in ('arxiv','pubmed') or not string(url) or not string(d.get('context')):
        return False
    try: parsed=urllib.parse.urlsplit(url)
    except ValueError: return False
    host=(parsed.hostname or '').lower()
    return parsed.scheme in ('http','https') and (host=='arxiv.org' or host.endswith('.arxiv.org') if site=='arxiv' else host=='pubmed.ncbi.nlm.nih.gov')


def has_unknown_explanation(value):
    return isinstance(value,dict) and any(string(value.get(k)) for k in ('unknown_reason','reason','note','version_note','version_date_reason','explanation'))


def report_date_shape(value):
    if not isinstance(value,dict) or not all(k in value for k in ('value','precision','basis','status')) or not string(value.get('basis')):
        return False
    if value.get('status')=='unknown':
        return value.get('value') is None and value.get('precision')=='unknown' and string(value.get('reason'))
    return value.get('status')=='documented' and value.get('precision') in ('year','month','day') and string(value.get('value'))


def record_shape(value):
    if not isinstance(value,dict) or not all(k in value for k in ('record_id','work_id','title','authors','identifiers','discovery','report_version','report_date','version_date')):
        return False
    authors=value.get('authors'); ids=value.get('identifiers')
    if not string(value.get('title')) or not string(value.get('report_version')) or not (string(authors) or isinstance(authors,list) and all(string(x) for x in authors)) or not isinstance(ids,dict):
        return False
    try:
        for kind,item in ids.items(): normalize_identifier(kind,item)
    except CandidateError:
        return False
    version=value.get('version_date')
    return report_date_shape(value.get('report_date')) and (version is None or string(version) or isinstance(version,dict) and bool(version))


def claim_shape(value):
    if not isinstance(value,dict): return 0.0
    status=value.get('status')
    return mean((True,status in ('documented','unknown','inference') and string(value.get('text')),
                 string(value.get('reason')) if status=='unknown' else string(value.get('text')) if status=='inference' else status=='documented'))


def citation_shape(value):
    if not isinstance(value,dict): return False
    return string(value.get('citation_id')) and string(value.get('quote')) and isinstance(value.get('locator'),dict) and bool(value['locator']) and isinstance(value.get('supports_fields'),list) and bool(value['supports_fields'])


def source_shape(value):
    if not isinstance(value,dict): return False
    url=value.get('url')
    if not string(value.get('source_id')) or not string(value.get('title')) or not string(url): return False
    try: parsed=urllib.parse.urlsplit(url)
    except ValueError: return False
    time=value.get('accessed_at')
    try: valid_time=time is None and string(value.get('unknown_reason')) or _get_time(time,'accessed_at') is not None
    except TrustedEvidenceError: valid_time=False
    return bool(parsed.scheme in ('http','https') and parsed.hostname and value.get('access_status') in ('read_full','read_excerpt','search_only','unavailable') and valid_time and isinstance(value.get('citations'),list) and all(citation_shape(c) for c in value['citations']))


def number_shape(number):
    if not isinstance(number,dict) or not all(k in number for k in ('metric','value','unit','direction','condition')): return False
    value=number['value']; condition=number['condition']
    scalar=type(value) in (int,float) and math.isfinite(value) or string(value)
    return string(number['metric']) and scalar and string(number['unit']) and number['direction'] in ('higher_better','lower_better','not_applicable','unknown') and (string(condition) or isinstance(condition,dict) and bool(condition))


def epistemic_numeric_shape(value,field,trace=False):
    if not isinstance(value,dict): return 0.0
    shape=claim_shape(value)
    numbers=value.get('numbers',[]) if isinstance(value,dict) else []
    numeric=field!='results' or isinstance(numbers,list) and all(number_shape(n) for n in numbers)
    return mean((shape==1.0,bool(trace),numeric))


def decision_equivalent(left,right):
    mapping={'纳入':'include','排除':'exclude','待决':'pending','待定':'pending','include':'include','exclude':'exclude','pending':'pending'}
    return mapping.get(norm(left))==right and right in ('include','exclude','pending')


def docx_structure(docx,ledger):
    text=norm(docx.get('text','')) if isinstance(docx,dict) else ''
    def anyword(words): return any(norm(w) in text for w in words)
    return {'discovery_process':bool(text) and anyword(('检索','搜索','导航','search','discover','arxiv','pubmed')),
            'screening_process':bool(text) and anyword(('筛选','纳入','排除','screen','inclusion','decision')),
            'dedup_version':bool(text) and anyword(('去重','版本','工作身份','同一工作','duplicate','dedup','version')),
            'flow_count_scope':bool(text) and anyword(('流程','计数','报告记录','独立工作','flow','records','included')),
            'scope_limits':bool(text) and anyword(('范围','限制','未知','局限','scope','limit','unknown','uncertain'))}


def flow_checks(ledger):
    records=ledger.get('records') if isinstance(ledger.get('records'),list) else []
    works=ledger.get('works') if isinstance(ledger.get('works'),list) else []
    flow=ledger.get('flow') if isinstance(ledger.get('flow'),dict) else {}
    R=len(records); Wn=len(works); U=sum(isinstance(r,dict) and r.get('work_id') is None for r in records)
    wids=[w.get('work_id') for w in works if isinstance(w,dict) and string(w.get('work_id'))]
    assigned=[sum(isinstance(r,dict) and r.get('work_id')==wid for r in records) for wid in wids]
    D=sum(max(0,n-1) for n in assigned)
    counts={decision:sum(isinstance(w,dict) and w.get('decision')==decision for w in works) for decision in ('include','exclude','pending')}
    computed=dict(zip(FLOW_KEYS,(R,U,D,Wn,counts['include'],counts['exclude'],counts['pending'])))
    result={key:nonnegative_integer(flow.get(key)) and flow[key]==computed[key] for key in FLOW_KEYS}
    graph=all(isinstance(r,dict) and (r.get('work_id') is None or string(r.get('work_id')) and wids.count(r['work_id'])==1) for r in records) and len(wids)==len(works) and len(set(wids))==len(wids) and all(n>=1 for n in assigned)
    result.update({'membership_graph':graph,'R=D+U+W':graph and R==D+U+Wn,'W=I+E+P':Wn==sum(counts.values()),'W>=6':Wn>=6,'I>=4':counts['include']>=4})
    return result


def date_literal_binding(value,resolution,source):
    expected=date_object(value)
    if expected is None: return False
    selected=resolution.get('selected_text','')
    quote=resolution.get('quote')
    actual=quote if string(quote) else selected
    observed=[]; aware_spans=[]
    aware_patterns=(r'\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)',
                    r'(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+)?\d{1,2}\s+[A-Za-z]+\s+\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:UTC|GMT|[+-]\d{4})')
    for pattern in aware_patterns:
        for match in re.finditer(pattern,actual,re.I):
            token=calendar_token(match.group())
            if token:
                observed.append(token);aware_spans.append(match.span())
    # Do not reinterpret a timestamp's UTC date substring as an independent
    # timezone-free calendar date; that would lose an actual boundary crossing.
    for pattern in (r'\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b',r'\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?',r'\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b',r'\b[A-Za-z]+\s+\d{1,2},?\s+\d{4}\b',r'\b[A-Za-z]+\s+\d{4}\b',r'\b\d{4}\b'):
        for match in re.finditer(pattern,actual):
            if any(left<=match.start() and match.end()<=right for left,right in aware_spans): continue
            token=calendar_token(match.group())
            if token: observed.append(token)
    projection=source.get('_derived',{}) if isinstance(source,dict) else {}
    xmltext=projection.get('records',[{}])[0].get('text','') if projection.get('xml_nodes') else ''
    for row in projection.get('metadata',{}).get('observations',[]):
        if row.get('observed_type')=='xml_date_parts':
            raw=xmltext[row['text_start']:row['text_end']]
            node_path=resolution.get('selected_node_path')
            same_selected_node=string(node_path) and (row.get('path')==node_path or row.get('path','').startswith(node_path+'/'))
            if raw and (same_selected_node or raw in selected and (not string(quote) or quote_match(quote,raw) or quote_match(raw,quote))):
                token=date_parts_token(row.get('parts'))
                if token: observed.append(token)
    matches=[token for token in observed if token['value']==expected['value'] and token['precision']==expected['precision']]
    if not matches: return False
    matching_aware=[t for t in matches if t.get('timestamp')]
    if matching_aware and all(t.get('timestamp') for t in matches):
        declared_timestamp=value.get('timestamp') if isinstance(value,dict) else value
        declared=calendar_token(declared_timestamp)
        if declared is None or not declared.get('timestamp'): return False
        return any(dt.datetime.fromisoformat(declared['timestamp'])==dt.datetime.fromisoformat(t['timestamp']) for t in matching_aware)
    return True


_BASE_LOCATOR_ALIASES=locator_aliases

def locator_aliases(locator):
    value=_BASE_LOCATOR_ALIASES(locator)
    if isinstance(value,dict) and 'section' in value and 'heading' not in value:
        value['heading']=value['section']
    return value


# Strict JSON avoids silent duplicate IDs/fields and NaN scalar loopholes.
def read_ledger(path):
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out: raise CandidateError('duplicate JSON object field: '+key)
            out[key]=value
        return out
    def constant(value): raise CandidateError('non-JSON numeric constant: '+value)
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,parse_constant=constant)
    except (ValueError,UnicodeError,OSError) as exc:
        raise CandidateError('evidence_matrix.json must be readable strict UTF-8 JSON: '+str(exc)) from exc
    if not isinstance(value,dict): raise CandidateError('evidence_matrix.json root must be object')
    return value


def calendar_cell(value):
    token=date_object(value)
    if token is not None or not string(value): return token
    found=[]
    for pattern in (r'\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?',r'\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?'):
        for match in re.finditer(pattern,value):
            item=calendar_token(match.group())
            if item and all(item['value']!=x['value'] for x in found): found.append(item)
    return found[0] if len(found)==1 else None


def calendar_cell_unknown(value):
    return unknown(value) or string(value) and calendar_cell(value) is None and bool(re.search(r'unknown|未知|未核实|未确认|不详',value,re.I))


def basis_in_text(basis,text):
    names={'first_online':('first_online','first online','首次在线','首次online'),
           'issue_only':('issue_only','仅卷期','卷期后备','卷期日期'),
           'arxiv_v1_submitted':('arxiv_v1_submitted','v1submitted','v1提交','v1官方submitted')}
    return string(basis) and any(norm(label) in norm(text) for label in names.get(basis,(basis,)))

# Portable DOM/ElementPath resolution. No optional host libraries or source facts.
class _NativeHTMLTree(HTMLParser):
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self,text):
        super().__init__(convert_charrefs=True)
        self.original=text; self.document=ET.Element('__document__');self.stack=[self.document]
        self.positions={};self.line_offsets=[0]
        for match in re.finditer('\n',text):self.line_offsets.append(match.end())
    def _character_offset(self):
        line,column=self.getpos();return self.line_offsets[line-1]+column
    def handle_starttag(self,tag,attrs):
        node=ET.SubElement(self.stack[-1],tag,dict((k,v or '') for k,v in attrs))
        start=self._character_offset();self.positions[id(node)]={'raw_char_start':start,'raw_start_tag_end':start+len(self.get_starttag_text() or ''),'raw_char_end':start+len(self.get_starttag_text() or '')}
        if tag not in self.VOID:self.stack.append(node)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.VOID:self.handle_endtag(tag)
    def handle_endtag(self,tag):
        found=next((i for i in range(len(self.stack)-1,0,-1) if self.stack[i].tag==tag),None)
        if found is None:return
        end=self.original.find('>',self._character_offset())
        for node in self.stack[found:]:self.positions[id(node)]['raw_char_end']=end+1 if end>=0 else len(self.original)
        del self.stack[found:]
    def handle_data(self,text):
        node=self.stack[-1]
        if len(node):node[-1].tail=(node[-1].tail or '')+text
        else:node.text=(node.text or '')+text


def _dom_index(source):
    cached=source.get('_native_dom_index')
    if cached is not None:return cached
    body=source.get('_body');media=source.get('media_type','')
    if not isinstance(body,bytes):raise TrustedEvidenceError('DOM original bytes missing')
    xml=bool(source.get('_derived',{}).get('xml_nodes')) or 'xml' in media.lower() and 'xhtml' not in media.lower()
    positions={};decoded=None;encoding=None
    if xml:
        if re.search(br'<!\s*ENTITY\b',body.replace(b'\x00',b''),re.I):raise TrustedEvidenceError('UNSUPPORTED_XML_ENTITY: safe node indexing refuses entity declarations')
        try:root=ET.fromstring(body)
        except ET.ParseError as exc:raise TrustedEvidenceError('UNSUPPORTED_XML_TREE: '+str(exc)) from exc
        document=ET.Element('__document__');document.append(root)
    else:
        charset=re.search(r'charset\s*=\s*["\']?([^;\s"\']+)',media,re.I)
        if charset:encoding=charset[1]
        else:
            meta=re.search(br'<meta\b[^>]*charset\s*=\s*["\']?([A-Za-z0-9_-]+)',body[:8192],re.I)
            encoding=meta[1].decode('ascii') if meta else 'utf-8-sig'
        try:
            decoded=body.decode(encoding,errors='strict');parser=_NativeHTMLTree(decoded);parser.feed(decoded);parser.close()
        except (UnicodeError,LookupError,ValueError,RecursionError) as exc:raise TrustedEvidenceError('UNSUPPORTED_HTML_TREE: '+str(exc)) from exc
        document=parser.document;positions=parser.positions
        roots=[n for n in document if n.tag=='html']
        root=roots[0] if len(roots)==1 else document
    records={};parents={child:parent for parent in document.iter() for child in parent};pieces=[];size=0
    def add(value):
        nonlocal size
        if value:pieces.append(value);size+=len(value)
    def visit(node,path,excluded=False):
        if len(records)>100000:raise TrustedEvidenceError('DOM node index exceeds evaluator capacity')
        excluded=excluded or not xml and node.tag in {'script','style','noscript','template'}
        start=size
        if not excluded:add(node.text)
        counts={}
        for child in node:
            counts[child.tag]=counts.get(child.tag,0)+1
            visit(child,path+'/'+child.tag+f'[{counts[child.tag]}]',excluded)
            if not excluded:add(child.tail)
        records[id(node)]={'path':path,'tag':node.tag,'attributes':dict(node.attrib),'text_start':start,'text_end':size,**positions.get(id(node),{})}
    visit(document,'')
    index={'xml':xml,'root':root,'document':document,'records':records,'parents':parents,'text':''.join(pieces),'encoding':encoding,'decoded':decoded}
    source['_native_dom_index']=index
    return index


def _elementpath(index,expression,namespaces=None):
    """ElementPath subset: root/relative/descendant, names/*, [N], attributes,
    supported stdlib predicates, terminal @attribute or text(). No axes/union/
    extension functions/network/DTD. Unsupported forms are evaluator errors.
    """
    if not string(expression):raise TrustedEvidenceError('UNSUPPORTED_XPATH: nonempty expression required')
    expression=expression.strip();attribute=None;text_only=False
    if len(expression)>16384:raise TrustedEvidenceError('UNSUPPORTED_XPATH: evaluator expression capacity exceeded')
    match=re.search(r'/@([A-Za-z_][\w:.-]*)$',expression)
    if match:attribute=match[1];expression=expression[:match.start()]
    elif expression.startswith('@'):attribute=expression[1:];expression='.'
    elif expression.endswith('/text()'):text_only=True;expression=expression[:-7]
    syntax=re.sub(r"'[^']*'|\"[^\"]*\"",'',expression)
    if '::' in syntax or '|' in syntax:
        raise TrustedEvidenceError('UNSUPPORTED_XPATH: axes/union outside the portable subset')
    context=index['root']
    if expression.startswith('/'):
        context=index['document'];expression='.'+expression
    if expression=='./' or expression=='':expression='.'
    try:
        if re.search(r'[A-Za-z_]\w*\s*\(',syntax):nodes=_portable_xpath_nodes(index,context,expression,namespaces or {})
        else:nodes=context.findall(expression,namespaces or {})
    except (SyntaxError,KeyError,TypeError) as exc:
        try:nodes=_portable_xpath_nodes(index,context,expression,namespaces or {})
        except TrustedEvidenceError:raise TrustedEvidenceError('UNSUPPORTED_XPATH: '+str(exc)) from exc
    selected=[]
    for node in nodes:
        if attribute is not None:
            name=attribute
            if ':' in name:
                prefix,local=name.split(':',1)
                if prefix not in (namespaces or {}):raise TrustedEvidenceError('UNSUPPORTED_XPATH: namespace prefix missing')
                name='{'+namespaces[prefix]+'}'+local
            if name not in node.attrib:continue
            selected.append((node,node.attrib[name],'attribute:'+name))
        else:
            row=index['records'].get(id(node))
            if row is None:raise TrustedEvidenceError('XPath result absent from actual node lineage')
            value=(node.text or '') if text_only else index['text'][row['text_start']:row['text_end']]
            selected.append((node,value,'text()' if text_only else 'element'))
    return selected


def _ancestor_sections(index,node):
    result=[];current=node
    while current is not None:
        if current.tag=='section':
            headings=[child for child in current if re.fullmatch(r'h[1-6]',str(child.tag))]
            if headings:
                row=index['records'][id(headings[0])];result.append(index['text'][row['text_start']:row['text_end']])
        current=index['parents'].get(current)
    return list(reversed(result))


def _css_nodes(index,selector):
    """Bounded static CSS subset over the same original DOM node index.

    Supports type/*, ID, class, attribute presence/equality, descendant/child
    combinators and positive integer nth-of-type/first-of-type/last-of-type.
    Unsupported syntax is an evaluator error, never a candidate miss/fallback.
    """
    def unsupported():raise TrustedEvidenceError('UNSUPPORTED_CSS: static selector subset required: '+repr(selector))
    if index['xml'] or not isinstance(selector,str) or not selector.strip() or len(selector)>2048 or '\\' in selector:unsupported()
    text=selector.strip();position=0;steps=[];relation=None
    while position<len(text):
        start=position;brackets=0;parens=0;quote=None
        while position<len(text):
            char=text[position]
            if quote:
                if char==quote:quote=None
            elif char in ('"',"'"):
                if not brackets:unsupported()
                quote=char
            elif char=='[':brackets+=1
            elif char==']':
                brackets-=1
                if brackets<0:unsupported()
            elif not brackets and char=='(':parens+=1
            elif not brackets and char==')':
                parens-=1
                if parens<0:unsupported()
            elif not brackets and not parens and (char.isspace() or char=='>'):break
            position+=1
        if quote or brackets or parens or start==position:unsupported()
        compound=text[start:position];cursor=0;tag='*';tests=[]
        match=re.match(r'(?:[A-Za-z_][A-Za-z0-9_-]*|\*)',compound)
        if match:tag=match[0].lower();cursor=match.end()
        while cursor<len(compound):
            token=compound[cursor:]
            if token[0] in '#.':
                match=re.match(r'([#.])([A-Za-z_][A-Za-z0-9_-]*)',token)
                if not match:unsupported()
                tests.append(('id' if match[1]=='#' else 'class',match[2]));cursor+=match.end()
            elif token[0]=='[':
                match=re.match(r'''\[\s*([A-Za-z_][A-Za-z0-9_:.-]*)\s*(?:=\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_-]+)))?\s*\]''',token)
                if not match:unsupported()
                value=next((v for v in match.groups()[1:] if v is not None),None)
                tests.append(('attr',(match[1].lower(),value)));cursor+=match.end()
            else:
                match=re.match(r':nth-of-type\(\s*([1-9][0-9]*)\s*\)',token)
                if match:tests.append(('nth',int(match[1])));cursor+=match.end();continue
                match=re.match(r':(first|last)-of-type\b',token)
                if not match:unsupported()
                tests.append(('nth',1 if match[1]=='first' else -1));cursor+=match.end()
        if not match and not tests:unsupported()
        steps.append((relation,tag,tests));space=False
        while position<len(text) and text[position].isspace():space=True;position+=1
        if position==len(text):break
        if text[position]=='>':
            relation='child';position+=1
            while position<len(text) and text[position].isspace():position+=1
            if position==len(text) or text[position]=='>':unsupported()
        elif space:relation='descendant'
        else:unsupported()
    selected=[]
    for step,(relation,tag,tests) in enumerate(steps):
        candidates=list(index['document'].iter()) if step==0 else [node for parent in selected for node in (list(parent) if relation=='child' else list(parent.iter())[1:])]
        seen=set();selected=[]
        for node in candidates:
            if node is index['document'] or id(node) in seen or tag!='*' and node.tag!=tag:continue
            seen.add(id(node));accepted=True
            for kind,value in tests:
                if kind=='id':accepted &= node.get('id')==value
                elif kind=='class':accepted &= value in node.get('class','').split()
                elif kind=='attr':accepted &= value[0] in node.attrib and (value[1] is None or node.get(value[0])==value[1])
                else:
                    parent=index['parents'].get(node);siblings=[n for n in parent if n.tag==node.tag] if parent is not None else []
                    accepted &= bool(siblings) and (siblings[-1] is node if value==-1 else len(siblings)>=value and siblings[value-1] is node)
            if accepted:selected.append(node)
    return selected


def _node_selections(index,locator):
    namespaces=locator.get('namespaces',{})
    if not isinstance(namespaces,dict):raise TrustedEvidenceError('UNSUPPORTED_XPATH: namespace mapping must be object')
    explicit=next((locator[k] for k in ('xpath','path','node') if k in locator),None)
    selected=_elementpath(index,explicit,namespaces) if explicit is not None else []
    css_present=any(k in locator for k in ('selector','css_selector','css'))
    if css_present:
        css=next(locator[k] for k in ('selector','css_selector','css') if k in locator)
        nodes=_css_nodes(index,css)
        if explicit is not None:selected=[item for item in selected if item[0] in nodes]
        else:
            selected=[]
            for node in nodes:
                attribute=locator.get('attribute')
                if attribute is None and node.tag=='meta' and locator.get('field',locator.get('metadata_key')):attribute='content'
                if attribute is not None:
                    if not isinstance(attribute,str):raise TrustedEvidenceError('UNSUPPORTED_CSS: attribute must be a name')
                    if attribute in node.attrib:selected.append((node,node.get(attribute),'attribute:'+attribute))
                else:
                    row=index['records'][id(node)];selected.append((node,index['text'][row['text_start']:row['text_end']],'element'))
    exact_requested=explicit is not None or css_present
    identity=next((locator[k] for k in ('html_id','anchor','id') if string(locator.get(k))),None)
    if identity and not index['xml']:
        byid=[(n,index['text'][index['records'][id(n)]['text_start']:index['records'][id(n)]['text_end']],'id') for n in index['root'].iter() if n.get('id')==identity.lstrip('#')]
        if len(byid)>1:raise TrustedEvidenceError('UNSUPPORTED_HTML_LOCATOR: actual ID duplicated')
        if selected and byid:
            owner=byid[0][0]
            compatible=[item for item in selected if item[0] is owner or owner in item[0].iter() or item[0] in owner.iter()]
            if not compatible:raise TrustedEvidenceError('UNSUPPORTED_HTML_LOCATOR: XPath and ID conflict on independent DOM')
            selected=[item for item in selected if item[0] is owner or item[0] in owner.iter()]
        elif byid and not exact_requested:selected=byid
    field=locator.get('field',locator.get('metadata_key'))
    if not selected and not exact_requested and string(field):
        if not index['xml']:
            meta=[n for n in index['root'].iter('meta') if n.get('name')==field or n.get('property')==field or n.get('itemprop')==field]
            selected=[(n,n.get('content',''),'attribute:content') for n in meta if 'content' in n.attrib]
        if not selected:selected=_elementpath(index,'.//'+field,namespaces)
    section=locator.get('section',locator.get('heading'))
    if string(section) and not index['xml']:
        required=[heading_key(p) for p in section.split('>') if p.strip()]
        candidates=[]
        for node in index['root'].iter():
            if not re.fullmatch(r'h[1-6]',str(node.tag)):continue
            row=index['records'][id(node)];title=heading_key(index['text'][row['text_start']:row['text_end']])
            if not required or title!=required[-1]:continue
            owner=index['parents'].get(node)
            if owner is None:continue
            while owner is not None and owner.tag not in ('section','article','main','body'):
                owner=index['parents'].get(owner)
            if owner is None:continue
            chain=[heading_key(x) for x in _ancestor_sections(index,node)]
            position=0
            for title in chain:
                if position<len(required) and title==required[position]:position+=1
            if len(required)>1 and position!=len(required):continue
            row=index['records'][id(owner)];candidates.append((owner,index['text'][row['text_start']:row['text_end']],'section hierarchy'))
        if selected and candidates:
            # Existing exact paragraph/ID must lie in the stated section.
            selected=[item for item in selected if any(item[0] is outer[0] or item[0] in outer[0].iter() for outer in candidates)]
        elif not selected and not exact_requested and identity is None:selected=candidates
    if index['xml'] and ('record' in locator or 'record_id' in locator):
        identity=locator.get('record',locator.get('record_id'));raw=identity.get('pmid') if isinstance(identity,dict) else identity
        wanted=re.sub(r'^PMID\s*:\s*','',str(raw),flags=re.I)
        owners=[]
        for node in index['root'].iter():
            if str(node.tag).rsplit('}',1)[-1]=='PMID' and ''.join(node.itertext()).strip()==wanted:
                parent=node
                while parent is not None and str(parent.tag).rsplit('}',1)[-1] not in ('PubmedArticle','PubmedBookArticle'):parent=index['parents'].get(parent)
                if parent is not None:owners.append(parent)
        if not owners and type(identity) is int and identity>0:
            articles=[n for n in index['root'].iter() if str(n.tag).rsplit('}',1)[-1] in ('PubmedArticle','PubmedBookArticle')];owners=articles[identity-1:identity]
        selected=[item for item in selected if any(item[0] is owner or item[0] in owner.iter() for owner in owners)]
    attrs=locator.get('attributes',{})
    if not isinstance(attrs,dict):raise TrustedEvidenceError('UNSUPPORTED_SOURCE_LOCATOR: attributes must be object')
    selected=[item for item in selected if all(item[0].get(k)==v for k,v in attrs.items())]
    return selected


def _xml_signature(node):
    preserve=node.get('{http://www.w3.org/XML/1998/namespace}space')=='preserve'
    mixed=bool((node.text or '').strip()) and bool(len(node)) or any((child.tail or '').strip() for child in node)
    def piece(value):
        value=value or ''
        if preserve:return value
        if not value.strip():return ''
        if mixed:return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',value))
        return textnorm(value)
    return (node.tag,tuple(sorted(node.attrib.items())),piece(node.text),tuple((_xml_signature(child),piece(child.tail)) for child in node))


def _serialized_xml_match(quote,node):
    if not quote.lstrip().startswith('<'):return False
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b',quote,re.I):raise TrustedEvidenceError('UNSUPPORTED_XML_QUOTE: DTD/entities in quote')
    try:
        root=ET.fromstring('<__quote__>'+quote+'</__quote__>')
    except ET.ParseError as exc:raise TrustedEvidenceError('UNSUPPORTED_XML_QUOTE: fragment needs supported safe serialization: '+str(exc)) from exc
    if (root.text or '').strip() or any((child.tail or '').strip() for child in root):return False
    parts=[_xml_signature(child) for child in root]
    if len(parts)==1 and parts[0]==_xml_signature(node):return True
    # A fragment may be actual contiguous children of this one selected parent.
    # Never combine Year/Month/Day from different date nodes or another source.
    children=[_xml_signature(child) for child in node]
    return len(parts)>1 and any(children[i:i+len(parts)]==parts for i in range(len(children)-len(parts)+1))


_BASE_RESOLVE_CITATION=resolve_citation

def resolve_citation(source,citation):
    if not isinstance(source,dict) or source.get('status')!='acquired':return {'resolved':False,'reason':'source not independently acquired'}
    if not isinstance(citation,dict) or not string(citation.get('quote')) or not isinstance(citation.get('locator'),dict) or not citation['locator']:
        return {'resolved':False,'reason':'missing quote/structured locator'}
    body=source.get('_body',b'');media=source.get('media_type','').lower();locator=citation['locator'];quote=citation['quote']
    dom=bool(source.get('_derived',{}).get('xml_nodes')) or 'html' in media or 'xml' in media or body.lstrip().lower().startswith((b'<?xml',b'<html',b'<!doctype html'))
    selectors=any(k in locator for k in ('xpath','path','node','field','metadata_key','html_id','anchor','id','section','heading','selector','css_selector','css'))
    if not dom:return _BASE_RESOLVE_CITATION(source,citation)
    if not selectors:
        if not any(k in locator for k in ('paragraph','lines','record','page','physical_page','physical_page_1based','page_1based','table','table_row','cell','href','json_path','json_pointer')):
            raise TrustedEvidenceError('UNSUPPORTED_SOURCE_LOCATOR: actual DOM selector representation not supported')
        return _BASE_RESOLVE_CITATION(source,citation)
    index=_dom_index(source);selected=_node_selections(index,locator)
    checked=[]
    for node,value,kind in selected:
        row=index['records'][id(node)]
        serialization=False
        literal=quote_match(quote,value)
        if not literal and index['xml'] and kind=='element':serialization=_serialized_xml_match(quote,node)
        checked.append({'node_path':row['path'],'tag':node.tag,'attributes':dict(node.attrib),'selected_text_sha256':hashlib.sha256(value.encode()).hexdigest()})
        if not literal and not serialization:continue
        result={'resolved':True,'reason':'original quote at actual independent DOM node/attribute','selected_text':value,'selected_plain_text':value,'selected_text_sha256':hashlib.sha256(value.encode()).hexdigest(),'locator':locator,'selected_node_path':row['path'],'node_tag':node.tag,'node_attributes':dict(node.attrib),'source_body_sha256':source.get('body_sha256'),'source_projection_sha256':source.get('projection_sha256'),'evidence_origin':'stdlib-safe-XML-node-serialization' if serialization else 'stdlib-original-DOM-node','selection_kind':kind,'normalization':'NFKC/whitespace/inside-parenthesis whitespace only; XML serialization preserves same-node tag/attributes/ordered children/text','text_offsets':[row['text_start'],row['text_end']]}
        context_node=index['parents'].get(node)
        while context_node is not None and context_node.tag not in ('tr','p','figcaption','section','article','ArticleDate','PubDate','pub-date'):
            context_node=index['parents'].get(context_node)
        if context_node is not None:
            context_row=index['records'][id(context_node)]
            result['selected_context']={'node_path':context_row['path'],'tag':context_node.tag,'attributes':dict(context_node.attrib),'text':index['text'][context_row['text_start']:context_row['text_end']]}
        if serialization:
            clone=copy.deepcopy(node);clone.tail=None;result['selected_xml_serialization']=ET.tostring(clone,encoding='unicode')
        if 'raw_char_start' in row:
            result['original_character_span']=[row['raw_char_start'],row['raw_char_end']]
            # UTF8-SIG decoding consumed the BOM; use source encoding's codec
            # only once when computing an actual original-byte span.
            codec=(index['encoding'] or 'utf-8').replace('-sig','')
            prefix=3 if body.startswith(b'\xef\xbb\xbf') else 0
            result['original_byte_span']=[prefix+len(index['decoded'][:p].encode(codec)) for p in result['original_character_span']]
        return result
    return {'resolved':False,'reason':'quote absent at actual requested node/attribute' if selected else 'actual locator selects no node/attribute','locator':locator,'selected_nodes':checked,'evidence_origin':'stdlib-original-DOM-node','source_body_sha256':source.get('body_sha256')}


def source_cell_members(value,known_values):
    """Match whole known IDs/URLs. Delimiters never split an internal URL/ID."""
    known={v for v in known_values if string(v)}
    value=parse_value(value)
    if isinstance(value,list):return value if value and all(string(v) and v in known for v in value) else None
    if not string(value):return None
    value=value.strip()
    if value in known:return [value]
    ordered=sorted(known,key=lambda v:(-len(v),v));memo={}
    def parse(offset):
        if offset==len(value):return []
        if offset in memo:return memo[offset]
        for member in ordered:
            if not value.startswith(member,offset):continue
            end=offset+len(member)
            if end==len(value):return [member]
            delimiter=re.match(r'\s*[\n\r;,；，|]+\s*',value[end:])
            if delimiter:
                rest=parse(end+delimiter.end())
                if rest is not None:return [member]+rest
        memo[offset]=None;return None
    return parse(0)


def declared_unknown_version(record):
    if not isinstance(record,dict) or record.get('version_date') is not None:return False
    value=record.get('report_version')
    return string(value) and bool(re.match(r'^\s*(?:unknown\b|未知|未核实|未确认|不详)',value,re.I)) and (has_unknown_explanation(record) or len(value.strip())>len('unknown')+2)


FIELD_ALIASES['decision'].append('决定')
FIELD_ALIASES['title'].extend(['报告题名','所选报告题名'])


def _xpath_steps(query):
    """Split source XPath while preserving nested predicates and quoted literals."""
    query=query.strip();steps=[];axis='child';i=0
    if query.startswith('.//'):i=3;axis='descendant'
    elif query.startswith('./'):i=2
    elif query.startswith('//'):i=2;axis='descendant'
    elif query.startswith('/'):i=1
    start=i;depth=0;brace=0;quote=None
    while i<len(query):
        char=query[i]
        if quote:
            if char==quote:quote=None
        elif char in ('\"',"'"):quote=char
        elif char=='{':brace+=1
        elif char=='}':brace-=1
        elif not brace and char=='[':depth+=1
        elif not brace and char==']':depth-=1
        elif not brace and depth==0 and char=='/':
            if i>start:steps.append((axis,query[start:i]))
            axis='descendant' if i+1<len(query) and query[i+1]=='/' else 'child'
            i+=1 if axis=='child' else 2;start=i;continue
        if depth<0 or brace<0:raise TrustedEvidenceError('UNSUPPORTED_XPATH: unbalanced expression')
        i+=1
    if quote or depth or brace:raise TrustedEvidenceError('UNSUPPORTED_XPATH: unterminated expression')
    if start<len(query):steps.append((axis,query[start:]))
    return steps


def _step_predicates(step):
    match=re.match(r'^(\.|\*|(?:\{[^}]+\})?[A-Za-z_][\w:.-]*)',step)
    if not match:raise TrustedEvidenceError('UNSUPPORTED_XPATH: step name outside supported subset')
    name=match[1];i=match.end();predicates=[]
    while i<len(step):
        if step[i]!='[':raise TrustedEvidenceError('UNSUPPORTED_XPATH: trailing step expression')
        start=i+1;depth=1;quote=None;i+=1
        while i<len(step) and depth:
            char=step[i]
            if quote:
                if char==quote:quote=None
            elif char in ('\"',"'"):quote=char
            elif char=='[':depth+=1
            elif char==']':depth-=1
            i+=1
        if depth:raise TrustedEvidenceError('UNSUPPORTED_XPATH: unterminated predicate')
        predicates.append(step[start:i-1].strip())
    return name,predicates


def _expanded_xpath_name(name,namespaces,html=False):
    if ':' in name and not name.startswith('{'):
        prefix,local=name.split(':',1)
        if prefix not in namespaces:raise TrustedEvidenceError('UNSUPPORTED_XPATH: namespace prefix missing')
        return '{'+namespaces[prefix]+'}'+local
    return name.lower() if html else name


def _portable_xpath_nodes(index,context,query,namespaces):
    if query=='.':return [context]
    syntax=re.sub(r"'[^']*'|\"[^\"]*\"",'',query)
    if '::' in syntax or '|' in syntax:raise TrustedEvidenceError('UNSUPPORTED_XPATH: axes/union not in portable subset')
    current=[context]
    for axis,step in _xpath_steps(query):
        name,predicates=_step_predicates(step);name=_expanded_xpath_name(name,namespaces,not index['xml']);found=[]
        for owner in current:
            parents=list(owner.iter()) if axis=='descendant' else [owner]
            for parent in parents:
                group=[parent] if name=='.' else [child for child in parent if name=='*' or child.tag==name]
                for predicate in predicates:
                    if re.fullmatch(r'\d+',predicate):
                        n=int(predicate);group=group[n-1:n] if n>0 else [];continue
                    last=re.fullmatch(r'last\(\)(?:\s*-\s*(\d+))?',predicate)
                    if last:
                        n=len(group)-int(last[1] or 0);group=group[n-1:n] if n>0 else [];continue
                    attr=re.fullmatch(r'@([\w:.-]+)(?:\s*=\s*([\"\'])(.*?)\2)?',predicate,re.S)
                    if attr:
                        key=_expanded_xpath_name(attr[1],namespaces,not index['xml'])
                        group=[n for n in group if key in n.attrib and (attr[2] is None or n.get(key)==attr[3])];continue
                    normalized=re.fullmatch(r'normalize-space\(\s*\.\s*\)\s*=\s*([\"\'])(.*?)\1',predicate,re.S)
                    if normalized:
                        def val(node):
                            row=index['records'][id(node)];return re.sub(r'[ \t\r\n]+',' ',index['text'][row['text_start']:row['text_end']]).strip()
                        group=[n for n in group if val(n)==normalized[2]];continue
                    # XPath child-expression predicates are existential and
                    # remain local to each current node, never to the document.
                    group=[n for n in group if _portable_xpath_nodes(index,n,predicate,namespaces)]
                for child in group:
                    if child not in found:found.append(child)
        current=found
    return current


_BASE_NATIVE_READ_DOCX=read_docx

def read_docx(path):
    result=_BASE_NATIVE_READ_DOCX(path)
    with _package(path) as archive:
        root=ET.fromstring(archive.read('word/document.xml'));parents={child:parent for parent in root.iter() for child in parent}
        def visible_text(element):
            words=[]
            for run in element.iter(W+'r'):
                parent=run;deleted=False
                while parent is not None:
                    deleted|=parent.tag in (W+'del',W+'moveFrom');parent=parents.get(parent)
                props=run.find(W+'rPr');hidden=False
                if props is not None:
                    hidden=any(n is not None and n.get(W+'val','1') not in ('0','false','off') for n in (props.find(W+'vanish'),props.find(W+'webHidden')))
                    color=props.find(W+'color');hidden|=color is not None and color.get(W+'val','').upper()=='FFFFFF'
                if not deleted and not hidden:words.extend(node.text or '' for node in run.iter(W+'t'))
            return ''.join(words).strip()
        result['tables']=[[[visible_text(cell) for cell in row.findall(W+'tc')] for row in table.findall(W+'tr')] for table in root.iter(W+'tbl')]
    return result


def _flow_label(value):
    value=textnorm(value)
    labels={'R':'records','U':'unresolved_records','D':'duplicate_version_records','W':'works','I':'included','E':'excluded','P':'pending'}
    if value in labels:return labels[value]
    if value in FLOW_KEYS:return value
    strong={'records':('报告记录','报告 R','记录 R'),'unresolved_records':('未解决','未归属','unresolved'),'duplicate_version_records':('额外版本','额外报告','duplicate'),'works':('工作 W','独立工作','works'),'included':('纳入 I','included'),'excluded':('排除 E','excluded'),'pending':('待决 P','pending')}
    for key,names in strong.items():
        if any(norm(name)==norm(value) for name in names):return key
    return None


def docx_flow_observations(docx,ledger):
    observed={};tables=docx.get('tables',[]) if isinstance(docx,dict) else []
    def number(value):
        normalized=unicodedata.normalize('NFKC',str(value)).strip()
        normalized=re.sub(r'\s*(?:条|个|篇|项|records?|works?|reports?)\s*$','',normalized,flags=re.I).strip()
        if re.fullmatch(r'\d+(?:,\d{3})*(?:\.0+)?',normalized):return int(float(normalized.replace(',','')))
        digits={'零':0,'〇':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9};units={'十':10,'百':100,'千':1000}
        if not normalized or any(ch not in digits and ch not in units for ch in normalized):return None
        if not any(ch in units for ch in normalized):return int(''.join(str(digits[ch]) for ch in normalized))
        total=current=0
        for ch in normalized:
            if ch in digits:current=digits[ch]
            else:total+=(current or 1)*units[ch];current=0
        return total+current
    for table_index,table in enumerate(tables):
        for r,row in enumerate(table):
            labels=[_flow_label(value) for value in row]
            if sum(label is not None for label in labels)>=2 and r+1<len(table):
                for col,label in enumerate(labels):
                    if label and col<len(table[r+1]):
                        value=number(table[r+1][col])
                        if value is not None:observed.setdefault(label,[]).append({'value':value,'table':table_index,'row':r+1,'column':col})
            elif len(row)>=2 and labels[0]:
                value=number(row[1])
                if value is not None:observed.setdefault(labels[0],[]).append({'value':value,'table':table_index,'row':r,'column':1})
    text=docx.get('text','') if isinstance(docx,dict) else ''
    names={'records':('R','报告记录','records'),'unresolved_records':('U','未解决记录','未归属记录','unresolved_records'),'duplicate_version_records':('D','额外版本','额外报告','duplicate_version_records'),'works':('W','独立工作','works'),'included':('I','纳入','included'),'excluded':('E','排除','excluded'),'pending':('P','待决','pending')}
    numeric=r'(?:[0-9]+(?:,[0-9]{3})*(?:\.0+)?|[零〇一二两三四五六七八九十百千]+)'
    for key,aliases in names.items():
        for alias in aliases:
            if len(alias)==1:
                pattern=r'(?<![A-Za-z0-9_])'+alias+r'(?![A-Za-z0-9_])\s*[=:：＝]\s*('+numeric+r')(?![0-9.])'
            else:
                pattern=re.escape(alias)+r'(?:数)?\s*(?:[=:：＝]|为|共|计)\s*('+numeric+r')(?![0-9.])'
            for match in re.finditer(pattern,text,re.I):
                value=number(match[1])
                if value is not None:observed.setdefault(key,[]).append({'value':value,'paragraph_character_span':list(match.span()),'literal':match.group()})
    flow=ledger.get('flow',{}) if isinstance(ledger,dict) else {}
    mismatches=[dict(item,field=key,JSON_value=flow[key]) for key,items in observed.items() if type(flow.get(key)) is int for item in items if item['value']!=flow[key]]
    return {'observed':observed,'mismatches':mismatches,'boundary':'Only unambiguous actual labeled counters are compared. No fixed heading/table/order or invented missing zero; prose sufficiency and scope remain Judge.'}


_BASE_DOCX_STRUCTURE=docx_structure

def docx_structure(docx,ledger):
    result=_BASE_DOCX_STRUCTURE(docx,ledger)
    result['flow_count_scope'] &= not docx_flow_observations(docx,ledger)['mismatches']
    return result


def selected_record_matches(work,work_row,selected_row,selected_record):
    selected=work.get('selected_record_id')
    if selected is None:return not string(work_row.get('selected_record_id'))
    explicit=work_row.get('selected_record_id')
    if string(explicit):return explicit==selected
    # An explicit contradictory selection must never be hidden by this fallback.
    return selected_row.get('record_id')==selected and string(selected_row.get('report_version')) and norm(selected_row['report_version'])==norm(selected_record.get('report_version'))
