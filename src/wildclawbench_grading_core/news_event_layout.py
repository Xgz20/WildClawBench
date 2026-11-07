"""Equivalent headings and explicitly scoped category totals; no scoring weights."""
_news_equivalent_headings = {
    'category': ['类别代码'],
    'category_zh': ['类别名称'],
    'alias_seen': ['提及名称/别名'],
    'source_section': ['章节/栏目'],
    'merged_source_count': ['报道片段数合计'],
    'item_id': ['排除ID'],
    'evidence_snippet': ['排除内容/简短片段'],
}
for _news_field, _news_names in _news_equivalent_headings.items():
    COLUMNS[_news_field] = COLUMNS[_news_field] + [v for v in _news_names if v not in COLUMNS[_news_field]]

_news_original_scoped_reader = read_workbook


def read_workbook(data):
    result = _news_original_scoped_reader(data)
    tables = [t for t in result.get('_complete_workbook_cells', [])
              if norm(t['sheet']) in {norm(v) for v in SHEETS['category_summary']}]
    if len(tables) != 1:
        return result
    table = tables[0]
    headers = []
    for row in table['rows'][:15]:
        names = [norm(c['value']) for c in row['cells']]
        if norm('统计维度') in names:
            if names.count(norm('统计维度')) != 1 or names.count(norm('日期')) != 1:
                raise EvidenceError('Ambiguous explicit category-summary scope headings')
            headers.append((row['row'], names.index(norm('统计维度')), names.index(norm('日期'))))
    if not headers:
        return result
    if len(headers) != 1:
        raise EvidenceError('Multiple explicit category-summary scope headings')
    header, scope_col, date_col = headers[0]
    physical = {r['row']: r for r in table['rows']}
    entries = []
    for row in result['category_summary']:
        location = row['_location']
        sheet, number = location.rsplit('!row', 1)
        cells = physical[int(number)]['cells']
        scope = str(cells[scope_col]['value'] or '').strip()
        if scope not in {'日期', '全期'}:
            raise EvidenceError('Unrecognized explicit category-summary scope; review required')
        entries.append((row, scope, cells[date_col]['value']))
    if not any(scope == '全期' for _, scope, _ in entries):
        return result
    selected = []
    projection = []
    for row, scope, period in entries:
        if scope == '全期' and period not in {None, '', '—', '-'}:
            raise EvidenceError('Whole-period summary also states a date; review required')
        aggregate = norm(row.get('category') or row.get('category_zh')) in {
            norm(v) for v in ['合计', '总计', '小计', 'total', 'grandtotal', 'subtotal']}
        included = scope == '全期' and not aggregate
        if included:
            selected.append(row)
        projection.append({'location': row['_location'], 'scope': scope,
                           'explicit_aggregate': aggregate, 'included_in_category_rollup': included})
    result['category_summary'] = selected
    table['category_scope_projection'] = {
        'role': 'grader_generated_extraction', 'policy': 'explicit-whole-period-category-rows/v1',
        'header_row': header, 'rows': projection, 'physical_cells_preserved': True,
        'candidate_values_synthesized': False,
    }
    return result
