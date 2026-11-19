"""H003 deterministic legal patch scope and native relationship checks."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import runpy


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(root):
    root = Path(root).resolve(); gt = root / 'gt'
    expected = read(gt / 'expected.json')
    source = read(gt / 'source_contract.json')
    oracle = read(gt / 'business_oracle.json')
    boundaries = read(gt / 'counterexamples.json')
    artifacts = read(gt / 'artifact_contract.json')
    protected = read(gt / 'protected_sha256.json')
    evidence = read(gt / 'evidence_requirements.json')
    helper = runpy.run_path(str(gt / 'docx_model.py'))
    norm, authored = helper['norm'], helper['authored']
    unique_clause, unique_table, cell_value = helper['unique_clause'], helper['unique_table'], helper['cell_value']
    if {label['id'] for label in expected['changes']} != {f'C{i:02d}' for i in range(1, 8)} or len(source['clauses']) != 12:
        raise ValueError('H003 private oracle incomplete')
    intact = all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name) == digest for name, digest in protected.items())
    output = root / artifacts['contract']
    model, parse_error = None, None
    try:
        model = helper['load_docx'](output)
    except (helper['DocxModelError'], OSError) as exc:
        parse_error = str(exc)

    def clause_stream(title):
        clause = unique_clause(model, title) if model else None
        return ''.join(clause['stream']) if clause else ''

    def number_continuity():
        return bool(model and model['clauses'] and [item['number'] for item in model['clauses']] == list(range(1, len(model['clauses'])+1)))

    checks = {}
    labels = {item['id']: item for item in expected['changes']}
    for identity, label in labels.items():
        tests = []
        if identity == 'C03':
            new_clause = unique_clause(model, label['new_title']) if model else None
            delivery = unique_clause(model, label['after_title']) if model else None
            tests.append(bool(new_clause and ''.join(new_clause['paragraphs']) == authored(''.join(label['new_body']))))
            tests.append(authored(label['added_link']) in clause_stream(label['after_title']))
            titles = [item['title'] for item in model['clauses']] if model else []
            tests.append(bool(new_clause and delivery and titles.index(new_clause['title']) == titles.index(delivery['title'])+1
                              and new_clause['number'] == delivery['number']+1 and number_continuity()))
            required = {('clause:交付安排', '交付确认'), ('clause:交付确认', '验收')}
            valid_edges = {(field['location'], field.get('target_title')) for field in model['fields'] if field.get('kind') == 'REF' and field.get('valid')} if model else set()
            tests.append(bool(required <= valid_edges and all(field.get('valid') for field in model['fields'] if field['kind'] == 'REF')))
        elif identity == 'C06':
            tests.append(bool(model and unique_clause(model, label['deleted_title']) is None
                              and all(clause['title'] != norm(label['deleted_title']) for clause in model['clauses'])))
            tests.append(bool(model and '现场培训' not in clause_stream('服务支持')
                              and not any(field.get('target_title') == '现场培训' or field.get('target_title', '').startswith('?') for field in model['fields'] if field['kind'] == 'REF')))
        elif identity == 'C07':
            value = cell_value(model, 'services', '合同通知', '渠道') if model else None
            email = label['email']
            tests.append(bool(value == email or value and re.fullmatch(r'\[\[LINK:[^|]*\|' + re.escape(email) + r'\]\]', value)))
            table = unique_table(model, 'services') if model else None
            row_indices = [i for i, row in enumerate(table['rows']) if row and row[0] == norm('合同通知')] if table else []
            column_indices = [i for i, value in enumerate(table['rows'][0]) if value == norm('渠道')] if table and table['rows'] else []
            location = f'table:services/row:{row_indices[0]}/col:{column_indices[0]}' if len(row_indices) == len(column_indices) == 1 else None
            tests.append(bool(model and location and any(link['location'] == location and link['valid_relationship']
                              and norm(link['display']) == email and link['target'] == 'mailto:' + email for link in model['links'])))
        else:
            for target in label.get('paragraphs', []):
                tests.append(authored(target['text']) in clause_stream(target['clause']))
            for target in label.get('cells', []):
                tests.append(bool(model and cell_value(model, target['table'], target['row'], target['column']) == authored(target['text'])))
        checks[identity] = {'requirements': tests, 'score': sum(tests) / len(tests)}
    business = sum(checks[key]['score'] * weight for key, weight in oracle['change_weights'].items()) / sum(oracle['change_weights'].values())

    # Scope whitelist uses original OR approved wording. A missed requested edit
    # loses its business point without erasing unrelated preservation points.
    # Reference identity/cache is scored separately from visible legal wording.
    def wording_pattern(value):
        fragments = re.split(r'(\[\[REF:[^\]]+\]\])', value)
        return ''.join(r'(?:\[\[REF:[^\]]+\]\]|[0-9]+)' if fragment.startswith('[[REF:') else re.escape(fragment) for fragment in fragments)

    def cell_wording(value):
        return re.sub(r'\[\[LINK:[^|]*\|([^\]]*)\]\]', r'\1', value) if isinstance(value, str) else value

    alternate_paragraphs, alternate_cells = {}, {}
    for label in expected['changes']:
        for item in label.get('paragraphs', []): alternate_paragraphs[item['key']] = item['text']
        for item in label.get('cells', []): alternate_cells[(item['table'], item['row'], item['column'])] = item['text']
    preservation = {}
    for clause in source['clauses']:
        actual = unique_clause(model, clause['title']) if model else None
        parts = []
        for block in clause['blocks']:
            if block['kind'] == 'table':
                parts.append(re.escape('[[TABLE:' + block['key'] + ']]'))
            else:
                options = {authored(block['text'])}
                if block['key'] in alternate_paragraphs: options.add(authored(alternate_paragraphs[block['key']]))
                if block['key'] == 'support.training': options.add('')
                parts.append('(?:' + '|'.join(wording_pattern(value) for value in sorted(options)) + ')')
                if block['key'] == 'delivery.p1':
                    parts.append('(?:' + wording_pattern(authored(labels['C03']['added_link'])) + ')?')
        preservation['clause:' + clause['title']] = bool(actual and re.fullmatch(''.join(parts), ''.join(actual['stream'])))
        if clause['key'] == 'training' and not actual and model:
            preservation['clause:' + clause['title']] = True
    if model and unique_clause(model, '交付确认'):
        preservation['inserted_clause_scope'] = bool(re.fullmatch(wording_pattern(authored(''.join(labels['C03']['new_body']))), ''.join(unique_clause(model, '交付确认')['paragraphs'])))
    known_titles = {norm(clause['title']) for clause in source['clauses']} | {norm('交付确认')}
    preservation['no_unapproved_clause'] = bool(model and all(item['title'] in known_titles for item in model['clauses']))
    preservation['front'] = bool(model and ''.join(model['front']) == authored(''.join(source['front_matter'])))
    preservation['header'] = bool(model and model['headers'] and all(value == norm(source['header']) for value in model['headers']))
    scope_checks = dict(preservation)
    # A broken/missing header relationship is a native delivery defect, not
    # proof that the legal wording itself was rewritten.
    if model and not model['headers']: scope_checks.pop('header', None)
    for key, table in source['tables'].items():
        for row in table['rows']:
            for header, original in zip(table['headers'], row):
                options = {authored(original)}
                alternative = alternate_cells.get((key, row[0], header))
                if alternative is not None: options.add(authored(alternative))
                actual_cell = cell_value(model, key, row[0], header) if model else None
                preserved = actual_cell in options
                if header == '含税金额元':
                    try: preserved = Decimal((actual_cell or '').replace(',', '')) == Decimal(original)
                    except InvalidOperation: preserved = False
                preservation['cell:' + key + '/' + row[0] + '/' + header] = bool(preserved)
                if actual_cell is not None:
                    if header == '含税金额元':
                        scoped = preserved
                    else:
                        target_values = {cell_wording(value) for value in options}
                        scoped = any(re.fullmatch(wording_pattern(value), cell_wording(actual_cell)) for value in target_values)
                    scope_checks['cell:' + key + '/' + row[0] + '/' + header] = bool(scoped)
    scope_unchanged = all(scope_checks.values())
    preservation_score = sum(preservation.values()) / len(preservation)
    expected_edges = Counter(tuple(edge) for edge in boundaries['reference_edges'])
    all_edges, valid_edges = Counter(), Counter()
    if model:
        for field in model['fields']:
            if field['kind'] != 'REF': continue
            origin = field['location'].split('/')[0]
            edge = (origin, field['target_title']); all_edges[edge] += 1
            if field['valid']: valid_edges[edge] += 1
    extra = sum((all_edges - expected_edges).values())
    covered = sum(min(valid_edges[edge], count) for edge, count in expected_edges.items())
    reference_score = (float(number_continuity()) + covered / (sum(expected_edges.values()) + extra)) / 2 if model else 0.0
    table_checks = {}
    for key, shape in boundaries['table_shapes'].items():
        table = unique_table(model, key) if model else None
        headers = [norm(value) for value in source['tables'][key]['headers']]
        table_checks[key] = bool(table and len(table['rows']) == shape[0] and all(len(row) == shape[1] for row in table['rows'])
                                 and table['grid_columns'] == shape[1] and not table['merged_cells'] and table['rows'][0] == headers)
    table_score = sum(table_checks.values()) / len(table_checks)
    if model and len(model['tables']) != 2: table_score = 0.0
    group_scores = {'preservation': preservation_score, 'native_references': reference_score, 'table_structure': table_score}
    boundary = sum(group_scores[key] * weight for key, weight in boundaries['group_weights'].items())
    if not scope_unchanged:
        business = 0.0
        group_scores['preservation'] = 0.0
        boundary = sum(group_scores[key] * weight for key, weight in boundaries['group_weights'].items())

    # P01/P02 are explicit immutable legal nodes. Normalize harmless numeric
    # formatting in these paragraphs; do not treat a different price/cap as style.
    def numeric_text(value):
        def replace(match):
            try: return format(Decimal(match[0].replace(',', '')).normalize(), 'f')
            except InvalidOperation: return match[0]
        return re.sub(r'[0-9]+(?:[,.][0-9]+)*', replace, value)
    original_paragraphs = {block['key']: authored(block['text']) for clause in source['clauses'] for block in clause['blocks'] if block['kind'] == 'paragraph'}
    price_ok = numeric_text(original_paragraphs['fees.p1']) in numeric_text(clause_stream('费用与付款'))
    for row in source['tables']['milestones']['rows']:
        actual = cell_value(model, 'milestones', row[0], '含税金额元') if model else None
        try: price_ok &= Decimal((actual or '').replace(',', '')) == Decimal(row[2])
        except InvalidOperation: price_ok = False
    cap_ok = numeric_text(original_paragraphs['liability.p1']) in numeric_text(clause_stream('违约与责任'))
    immutable_ok = bool(price_ok and cap_ok)
    if not immutable_ok: business, boundary = 0.0, 0.0

    audit_path = root / artifacts['audit']; audit = None
    if audit_path.is_file() and not audit_path.is_symlink() and audit_path.stat().st_size <= 1_000_000:
        try: audit = read(audit_path)
        except (ValueError, UnicodeError, OSError): pass
    entries = audit.get('changes') if isinstance(audit, dict) else None
    entries = entries if isinstance(entries, list) else []
    counts = Counter(item['change_id'] for item in entries if isinstance(item, dict) and isinstance(item.get('change_id'), str))
    indexed = {item['change_id']: item for item in entries if isinstance(item, dict) and isinstance(item.get('change_id'), str) and item['change_id'] in labels and counts[item['change_id']] == 1}
    audit_schema = bool(isinstance(audit, dict) and all(key in audit for key in artifacts['audit_root_fields']) and len(entries) == len(labels) and set(counts) == set(labels)
                        and all(count == 1 for count in counts.values()) and all(all(key in item for key in artifacts['audit_item_fields']) for item in indexed.values()))
    file_binding = bool(model and isinstance(audit, dict) and audit.get('source_sha256') == protected['contract.docx'] and audit.get('result_sha256') == model['source_sha256'])

    def resolve(location, candidate):
        if not isinstance(location, str): return False
        if location.startswith('clause:'):
            if candidate: return bool(model and unique_clause(model, location[7:]))
            return location[7:] in {clause['title'] for clause in source['clauses']}
        if location.startswith('absent:'):
            return bool(candidate and model and not any(item['title'] == norm(location[7:]) for item in model['clauses']))
        if location.startswith('table:'):
            parts = location[6:].split('/')
            if len(parts) != 3: return False
            key = next((key for key, table in source['tables'].items() if table['title'] == parts[0]), None)
            if key is None: return False
            if candidate: return bool(model and cell_value(model, key, parts[1], parts[2]) is not None)
            table = source['tables'][key]
            return parts[2] in table['headers'] and any(row[0] == parts[1] for row in table['rows'])
        return False
    mappings = {}
    for identity, label in labels.items():
        item = indexed.get(identity, {})
        starts, ends = item.get('source_locations'), item.get('result_locations')
        mappings[identity] = bool(item.get('action') == label['action'] and isinstance(item.get('summary'), str) and item['summary'].strip()
            and isinstance(starts, list) and isinstance(ends, list) and all(isinstance(value, str) for value in starts+ends)
            and set(label['source_locations']) <= set(starts) and set(label['result_locations']) <= set(ends)
            and all(resolve(value, False) for value in starts) and all(resolve(value, True) for value in ends))
    evidence_score = evidence['file_binding_weight'] * file_binding + evidence['change_mapping_weight'] * sum(mappings.values())/len(mappings)
    final_titles = [norm(title) for title in expected['final_clause_titles']]
    structure = bool(model and [clause['title'] for clause in model['clauses']] == final_titles and number_continuity()
                     and len(model['tables']) == 2 and all(table_checks.values()))
    clean = bool(model and not model['issues'] and not model['tracked_changes'] and not model['drawings'])
    delivery = (float(model is not None) + float(audit_schema) + float(structure) + float(clean) + float(intact)) / 5
    if model is None and not audit_schema: delivery = 0.0
    if not intact: boundary, delivery, evidence_score = 0.0, 0.0, 0.0
    scores = {'business_correctness': business, 'boundary_cases': boundary, 'delivery_integrity': delivery, 'evidence_binding': evidence_score}
    scores['overall_score'] = min(1.0, sum(scores[key] * weight for key, weight in oracle['checkpoint_weights'].items()))
    return {'scores': scores, 'observations': {'case_checks': checks, 'boundary_groups': group_scores, 'preservation_checks': preservation,
        'table_checks': table_checks, 'scope_unchanged': scope_unchanged, 'scope_checks': scope_checks,
        'P01_unchanged': bool(price_ok), 'P02_unchanged': bool(cap_ok), 'input_unchanged': intact,
        'number_continuity': number_continuity(), 'reference_edges_covered': covered, 'reference_edges_required': sum(expected_edges.values()),
        'file_binding': file_binding, 'mapping_checks': mappings, 'parse_error': parse_error, 'audit_schema_valid': audit_schema,
        'native_clean': clean, 'native_issues': model['issues'] if model else []}}


def grade(root):
    result = evaluate(root)
    print(json.dumps({'kind': 'h003-rule-observations/v1', **result['observations']}, ensure_ascii=False))
    return result['scores']
