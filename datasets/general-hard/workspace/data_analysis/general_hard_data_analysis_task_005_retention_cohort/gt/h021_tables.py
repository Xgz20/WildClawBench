"""Semantic, order-independent worksheet discovery for retention ledgers."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import datetime as dt
import json
import re
import runpy
import zipfile
import xml.etree.ElementTree as E

_native = runpy.run_path(str(Path(__file__).with_name('xlsx_observations.py')))
CandidateError = _native['CandidateError']
blank = _native['blank']

def read_book(path):
    book = _native['read_book'](path)
    with zipfile.ZipFile(path) as archive:
        workbook = E.fromstring(archive.read('xl/workbook.xml'))
    properties = workbook.find(_native['X'] + 'workbookPr')
    date1904 = properties is not None and properties.get('date1904', '0') in {'1', 'true'}
    for sheet in book:
        sheet['_date1904'] = date1904
    return book

def canon(value):
    return re.sub(r'[\s_()（）/、:：-]', '', str(value or '')).casefold()

def alias(value, mapping):
    matches = [key for key, values in mapping.items() if canon(value) in {canon(v) for v in values}]
    return matches[0] if len(matches) == 1 else None

def identifier(value, prefix):
    text = str(value).strip().upper() if isinstance(value, str) else ''
    return text if re.fullmatch(prefix + r'\d+', text) else None

def date(value):
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value <= 80000:
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(value))).isoformat() if int(value) == value else None
    text = str(value or '').strip()
    match = re.fullmatch(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?', text)
    try:
        return dt.date(*map(int, match.groups())).isoformat() if match else None
    except ValueError:
        return None

def number(value, *, missing=False):
    if blank(value) or str(value).strip().casefold() in {'n/a', 'na', '不适用', '待观察', '未观察', 'null'}:
        return None if missing else 'INVALID'
    if isinstance(value, bool):
        return int(value)
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation:
        return 'INVALID'
    return float(result) if result.is_finite() else 'INVALID'

def ids(value, prefix):
    if blank(value):
        return set()
    if isinstance(value, (list, tuple)):
        values = value
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith('['):
            try:
                values = json.loads(text)
            except ValueError as exc:
                raise CandidateError('invalid ID array') from exc
            if not isinstance(values, list):
                raise CandidateError('ID list required')
        else:
            values = re.split(r'[\s,;，；、|]+', text)
    else:
        raise CandidateError('invalid ID collection')
    result = [identifier(v, prefix) for v in values]
    if any(v is None for v in result):
        raise CandidateError('invalid collection member')
    return set(result)

def bit(value):
    text = str(value).strip().casefold()
    if text in {'1', '1.0', 'true', '是', '已完成', '完成', 'observed', '已返回', '活跃', '已流失'}:
        return 1
    if text in {'0', '0.0', 'false', '否', '待观察', '未完成', 'unobserved', '未返回', '未流失'}:
        return 0
    return None

def discover(book, contract):
    lookup = {canon(v): field for field, values in contract['aliases'].items() for v in values}
    result = {kind: [] for kind in contract['tables']}
    headers = {kind: [] for kind in contract['tables']}
    for sheet in book:
        grid = defaultdict(dict)
        for (row, col), cell in sheet['cells'].items():
            grid[row][col] = cell
        candidates = []
        for rn, cells in sorted(grid.items()):
            found = defaultdict(list)
            for col, cell in cells.items():
                field = lookup.get(canon(cell['value']))
                if field and not cell.get('merged_from'):
                    found[field].append(col)
            for kind, fields in contract['tables'].items():
                if set(fields) <= set(found) and all(len(found[f]) == 1 for f in fields):
                    cols = {f: found[f][0] for f in fields}
                    visible = all(cells[c]['visible'] for c in cols.values())
                    candidates.append((rn, kind, cols, visible))
                    headers[kind].append({'sheet': sheet['name'], 'row': rn, 'visible': visible})
        candidates.sort(key=lambda c: (c[0], c[1]))
        for index, (rn, kind, columns, visible) in enumerate(candidates):
            end = next((r for r, _, _, _ in candidates[index + 1:] if r > rn), 50001)
            primary = {'summaries': 'metric_date', 'memberships': 'user_id', 'user_days': 'user_id', 'audit': 'record_id'}[kind]
            for row_number, cells in sorted(grid.items()):
                if not rn < row_number < end:
                    continue
                values = {f: cells.get(col, {}).get('value') for f, col in columns.items()}
                if sheet.get('_date1904'):
                    for field, value in values.items():
                        if field.endswith('date') and isinstance(value, (int, float)) and not isinstance(value, bool):
                            values[field] = (dt.date(1904, 1, 1) + dt.timedelta(days=int(value))).isoformat() if 0 <= value <= 80000 and value == int(value) else None
                key = identifier(values[primary], 'R' if kind == 'audit' else 'U') if primary != 'metric_date' else date(values[primary])
                if key is None:
                    if not blank(values[primary]) and any(not blank(values[f]) for f in columns if f != primary):
                        result[kind].append({**values, '_visible': False, '_malformed_identity': True})
                    continue
                result[kind].append({**values, '_visible': visible and all(cells.get(c, {'visible': True})['visible'] for c in columns.values()),
                    '_sheet': sheet['name'], '_row': row_number})
    return result, headers

def index_rows(rows, fields, contract):
    out = defaultdict(list)
    for row in rows:
        values = []
        for field in fields:
            value = row.get(field)
            if field.endswith('date'):
                value = date(value)
            elif field == 'cohort':
                value = alias(value, contract['cohort_aliases'])
            elif field.endswith('_id'):
                value = identifier(value, 'R' if field == 'record_id' else 'U')
            values.append(value)
        out[tuple(values)].append(row)
    return out
