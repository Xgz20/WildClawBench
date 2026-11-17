"""Infer visible rate/date axes and verify actual SVG/Canvas strokes and pixels.

No author selectors, viewBox, fixed chart positions or embedded JSON oracle.
Unresolved legal representations raise explicitly instead of inventing zeros.
"""
from pathlib import Path
from collections import defaultdict
import datetime as dt
import json
import math
import re
import runpy

T = runpy.run_path(str(Path(__file__).with_name('h021_tables.py')))

class HtmlUnsupported(RuntimeError):
    pass

def average(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0

def rgb(value):
    value = str(value or '').strip().lower()
    if re.fullmatch(r'#[0-9a-f]{6}', value):
        return tuple(int(value[i:i + 2], 16) for i in [1, 3, 5])
    if re.fullmatch(r'#[0-9a-f]{3}', value):
        return tuple(int(value[i] * 2, 16) for i in [1, 2, 3])
    match = re.match(r'rgba?\(([^)]+)\)', value)
    if match:
        parts = re.split(r'[,\s/]+', match[1].strip())
        try:
            return tuple(round(float(v)) for v in parts[:3]) if len(parts) >= 3 else None
        except ValueError:
            return None
    return {'black': (0, 0, 0), 'red': (255, 0, 0), 'blue': (0, 0, 255), 'green': (0, 128, 0), 'orange': (255, 165, 0)}.get(value)

def painted(pixel, color):
    if not pixel or len(pixel) != 4 or pixel[3] < 128:
        return False
    if max(abs(pixel[i] - color[i]) for i in range(3)) <= 28:
        return True
    # A thin antialiased line can be blended with a light background.
    vector = [255 - color[i] for i in range(3)]
    observed = [255 - pixel[i] for i in range(3)]
    norm = sum(v * v for v in vector)
    if not norm or max(observed) < 16:
        return False
    alpha = sum(a * b for a, b in zip(vector, observed)) / norm
    return .06 <= alpha <= 1.05 and max(abs(observed[i] - alpha * vector[i]) for i in range(3)) <= 16

def text_box(record):
    rects = [r for r in record.get('rects', []) if r['width'] > 0 and r['height'] > 0]
    if not rects:
        return None
    x = min(r['x'] for r in rects);y = min(r['y'] for r in rects)
    right = max(r['x'] + r['width'] for r in rects);bottom = max(r['y'] + r['height'] for r in rects)
    return {'x': x, 'y': y, 'width': right - x, 'height': bottom - y, 'cx': (x + right) / 2, 'cy': (y + bottom) / 2, 'right': right}

def transform(matrix, x, y):
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f

def canvas_point(canvas, point):
    rect = canvas['content_rect']
    return [rect['x'] + point[0] * rect['width'] / canvas['width'], rect['y'] + point[1] * rect['height'] / canvas['height']]

def projection_parts(observation):
    projection = observation['projection']
    texts = []
    shapes = []
    for item in projection['texts']:
        box = text_box(item)
        if item['visible'] and box:
            texts.append({**item, 'box': box})
    for item in projection['svg']:
        color = rgb(item['style'].get('stroke'))
        if item['visible'] and color is not None and float(item['style'].get('strokeWidth', '1').removesuffix('px') or 0) > 0:
            shapes.append({'id': item['id'], 'kind': 'svg', 'color': color, 'points': item['samples'], 'tag': item['tag'], 'rect': item['rect']})
    for canvas in projection['canvases']:
        if not canvas['visible']:
            continue
        if not canvas['css_transform_supported']:
            continue
        for index, item in enumerate(canvas['texts']):
            args = item['args'];m = item['measure']
            if len(args) < 2 or not all(isinstance(v, (int, float)) for v in [m.get('left'), m.get('right'), m.get('ascent'), m.get('descent')]):
                continue
            squeeze = min(1, args[2] / m['width']) if len(args) >= 3 and m['width'] else 1
            corners = [canvas_point(canvas, transform(item['state']['transform'], x, y)) for x in [args[0] - m['left'] * squeeze, args[0] + m['right'] * squeeze] for y in [args[1] - m['ascent'], args[1] + m['descent']]]
            xs = [p[0] for p in corners];ys = [p[1] for p in corners]
            box = {'x': min(xs), 'right': max(xs), 'y': min(ys), 'width': max(xs) - min(xs), 'height': max(ys) - min(ys), 'cx': (max(xs) + min(xs)) / 2, 'cy': (max(ys) + min(ys)) / 2}
            texts.append({'id': canvas['id'] + ':text:' + str(index), 'tag': 'canvas_text', 'text': item['text'], 'box': box, 'style': {'color': item['state'].get('fill')}, 'visible': True})
        for item in canvas['strokes']:
            color = rgb(item['state'].get('stroke'))
            if color is None:
                continue
            points = []
            segments = []
            previous = None
            for command in item['commands'] or []:
                if command['method'] in {'moveTo', 'lineTo'} and len(command['args']) >= 2:
                    point = canvas_point(canvas, transform(command['transform'], *command['args'][:2]))
                    if command['method'] == 'lineTo' and previous is not None:
                        segments.append([previous, point])
                    previous = point
                    points.append(point)
                elif command['method'] == 'closePath':
                    previous = None
            shapes.append({'id': item['id'], 'kind': 'canvas', 'color': color, 'points': points, 'segments': segments,
                'tag': 'path2d' if item['path2d'] else 'canvas-path', 'rect': canvas['content_rect'], 'canvas_id': canvas['id']})
    return texts, shapes

def horizontal_lines(shapes):
    result = []
    for shape in shapes:
        segments = shape.get('segments')
        if segments is None:
            points = shape['points']
            segments = list(zip(points, points[1:]))
            if len(points) > 2 and max(p[1] for p in points) - min(p[1] for p in points) <= .5:
                segments = [[min(points, key=lambda p: p[0]), max(points, key=lambda p: p[0])]]
        for a, b in segments:
            if abs(a[1] - b[1]) <= .5 and abs(a[0] - b[0]) >= 25:
                result.append({'x1': min(a[0], b[0]), 'x2': max(a[0], b[0]), 'y': (a[1] + b[1]) / 2, 'color': shape['color'], 'id': shape['id']})
    return result

def axis_date(text):
    text = text.strip()
    match = re.fullmatch(r'(?:(\d{4})[-/.年])?(\d{1,2})[-/.月](\d{1,2})日?', text)
    if not match:
        return None
    try:
        date = dt.date(int(match[1] or 2026), int(match[2]), int(match[3]))
        return (date - dt.date(2026, 9, 1)).days
    except ValueError:
        return None

def linear_fit(pairs):
    meanx = average(p[0] for p in pairs);meany = average(p[1] for p in pairs)
    denominator = sum((p[0] - meanx) ** 2 for p in pairs)
    if denominator < 1e-12:
        raise HtmlUnsupported('H021_HTML_AXES_UNRESOLVED: distinct tick anchors required')
    slope = sum((x - meanx) * (y - meany) for x, y in pairs) / denominator
    origin = meany - slope * meanx
    error = max(abs(origin + slope * x - y) for x, y in pairs)
    return origin, slope, error

def cohort(text):
    lower = text.lower()
    new = bool(re.search(r'新用户|新增用户|\bnew\b', lower))
    old = bool(re.search(r'老用户|存量用户|\bold\b', lower))
    return 'new' if new and not old else 'old' if old and not new else None

def infer_charts(observation):
    texts, shapes = projection_parts(observation)
    horizontal = horizontal_lines(shapes)
    rate_texts = []
    for text in texts:
        if text['tag'] not in {'text', 'tspan', 'canvas_text'}:
            continue
        match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*[%％]\s*', text['text'])
        if match:
            rate_texts.append({**text, 'rate': float(match[1]) / 100})
    columns = []
    for item in sorted(rate_texts, key=lambda p: p['box']['right']):
        column = next((c for c in columns if abs(c[0]['box']['right'] - item['box']['right']) <= max(6, item['box']['height'] * .4)), None)
        if column is None:
            columns.append([item])
        else:
            column.append(item)
    groups = []
    for column in columns:
        current = []
        for item in sorted(column, key=lambda p: p['box']['cy']):
            if current and item['rate'] >= current[-1]['rate']:
                if len(current) >= 2:
                    groups.append(current)
                current = []
            current.append(item)
        if len(current) >= 2:
            groups.append(current)
    plans = {}
    for ticks in groups:
        anchors = []
        grid = []
        for tick in ticks:
            box = tick['box']
            nearby = [line for line in horizontal if abs(line['y'] - box['cy']) <= max(4, box['height'] * .8) and -box['height'] <= line['x1'] - box['right'] <= max(100, box['height'] * 5)]
            if not nearby:
                continue
            line = max(nearby, key=lambda l: (l['x2'] - l['x1'], -abs(l['y'] - box['cy'])))
            anchors.append((tick['rate'], line['y']));grid.append(line)
        if len(anchors) < 2:
            continue
        y0, ys, error = linear_fit(anchors)
        if error > 1.5 or abs(ys) < 30:
            continue
        xleft = min(l['x1'] for l in grid);xright = max(l['x2'] for l in grid)
        ytop, ybottom = sorted([y0, y0 + ys])
        date_texts = [t for t in texts if t['tag'] in {'text', 'tspan', 'canvas_text'} and axis_date(t['text']) is not None
            and xleft - 10 <= t['box']['cx'] <= xright + 10 and ybottom - 4 <= t['box']['cy'] <= ybottom + max(75, 4 * t['box']['height'])]
        if len(date_texts) < 2:
            continue
        date_texts = [t for t in date_texts if abs(t['box']['cy'] - min(d['box']['cy'] for d in date_texts)) < max(5, t['box']['height'])]
        x0, xs, xerror = linear_fit([(axis_date(t['text']), t['box']['cx']) for t in date_texts])
        if xerror > 2 or xs <= 1:
            continue
        labels = [t for t in texts if cohort(t['text']) and t['tag'] in {'h1', 'h2', 'h3', 'h4', 'span', 'text', 'tspan', 'canvas_text'}
            and xleft - 100 <= t['box']['cx'] <= xright + 100 and 0 <= ytop - t['box']['cy'] <= max(180, (ybottom - ytop) * .8)]
        if not labels:
            continue
        nearest = min(ytop - t['box']['cy'] for t in labels)
        labels = [t for t in labels if ytop - t['box']['cy'] <= nearest + max(7, t['box']['height'] * .6)]
        names = {cohort(t['text']) for t in labels}
        grid_colors = {color for color in {l['color'] for l in grid} if len({round(l['y']) for l in grid if l['color'] == color}) >= 2}
        curves = defaultdict(list)
        for shape in shapes:
            points = shape['points']
            if shape['color'] in grid_colors:
                continue
            if points:
                in_plot = [p for p in points if xleft - 3 <= p[0] <= xright + 3 and ytop - 3 <= p[1] <= ybottom + 3]
                if len(in_plot) < 2 or max(p[0] for p in in_plot) - min(p[0] for p in in_plot) < xs * .4:
                    continue
                if all(abs(p[1] - ybottom) < 1 or abs(p[1] - ytop) < 1 for p in in_plot):
                    continue
            elif shape['tag'] != 'path2d' or not (shape['rect']['x'] <= xleft + 3 and shape['rect']['y'] <= ytop + 3
                and shape['rect']['x'] + shape['rect']['width'] >= xright - 3 and shape['rect']['y'] + shape['rect']['height'] >= ybottom - 3):
                continue
            curves[shape['color']].append(shape['id'])
        if not curves:
            continue
        assignments = {}
        if len(names) == len(curves) == 1:
            assignments[next(iter(names))] = next(iter(curves))
        elif names == {'new', 'old'} and len(curves) == 2:
            for label in labels:
                name = cohort(label['text']);color = rgb(label.get('style', {}).get('color'))
                if color in curves:
                    assignments[name] = color
                    continue
                swatches = [s for s in shapes if s['color'] in curves and s['points'] and all(abs(p[1] - label['box']['cy']) < max(10, label['box']['height']) for p in s['points'])
                    and min(abs(p[0] - label['box']['x']) for p in s['points']) < max(60, label['box']['height'] * 4)]
                colors = {s['color'] for s in swatches}
                if len(colors) == 1:
                    assignments[name] = next(iter(colors))
        for name, color in assignments.items():
            if name in plans:
                raise HtmlUnsupported('H021_HTML_CHART_AMBIGUOUS: multiple rate charts for one cohort')
            plans[name] = {'cohort': name, 'color': list(color), 'targets': sorted(curves[color]), 'x0': x0, 'xs': xs, 'y0': y0, 'ys': ys,
                'plot': {'left': xleft, 'right': xright, 'top': ytop, 'bottom': ybottom}, 'date_ticks': len(date_texts), 'rate_ticks': len(anchors)}
    if set(plans) != {'new', 'old'}:
        raise HtmlUnsupported('H021_HTML_CHART_UNSUPPORTED: visible date/rate axes and cohort-series binding unresolved')
    return plans

def chart_probes(plans, expected):
    probes = []
    contract = []
    for wanted in expected['summaries']:
        plan = plans[wanted['cohort']]
        day = (dt.date.fromisoformat(wanted['metric_date']) - dt.date(2026, 9, 1)).days
        x = plan['x0'] + day * plan['xs']
        prefix = wanted['metric_date'] + ':' + wanted['cohort']
        if wanted['rate'] is not None:
            probe_id = prefix + ':point'
            probes.append({'id': probe_id, 'x': x, 'y': plan['y0'] + wanted['rate'] * plan['ys'], 'radius': 1, 'targets': plan['targets']})
            contract.append({'id': probe_id, 'cohort': wanted['cohort'], 'kind': 'point', 'day': day, 'rate': wanted['rate'], 'x': x, 'y': probes[-1]['y']})
        else:
            # The full vertical slice must be a real gap, not a hidden zero or
            # a line bridging missing/censored observations.
            count = min(120, max(40, math.ceil(abs(plan['ys']) / 2)))
            for index in range(count + 1):
                probe_id = prefix + ':gap:' + str(index)
                probes.append({'id': probe_id, 'x': x, 'y': plan['y0'] + index / count * plan['ys'], 'radius': 1, 'targets': plan['targets']})
                contract.append({'id': probe_id, 'cohort': wanted['cohort'], 'kind': 'gap', 'group': prefix})
    if len(probes) > 512:
        raise HtmlUnsupported('H021_HTML_PROBE_LIMIT: chart height exceeds supported native probe budget')
    return probes, contract

def score_chart(observation, plans, contract):
    indexed = {p['id']: p for p in observation['probes']}
    point_scores = []
    gaps = defaultdict(list)
    details = []
    for wanted in contract:
        actual = indexed[wanted['id']]
        if wanted['kind'] == 'point':
            color = plans[wanted['cohort']]['color']
            hit = any(h.get('css_visible') for h in actual['hits'])
            colors = [color]
            for other in contract:
                if other['kind'] != 'point' or other['cohort'] == wanted['cohort'] or other['day'] != wanted['day']:
                    continue
                if abs(other['x'] - wanted['x']) < 1 and abs(other['y'] - wanted['y']) < 1:
                    colors.append(plans[other['cohort']]['color'])
            pixels = any(painted(p.get('rgba'), candidate_color) for p in actual['page_pixels'] for candidate_color in colors)
            passed = hit and pixels
            point_scores.append(passed)
            details.append({'id': wanted['id'], 'native_hit': hit, 'pixel_agrees': pixels, 'passed': passed})
        else:
            color = plans[wanted['cohort']]['color']
            ink = any(painted(p.get('rgba'), color) for p in actual['page_pixels'])
            gaps[wanted['group']].append(not (ink and any(h.get('css_visible') for h in actual['hits'])))
    return {'points': average(point_scores), 'gaps': average(all(v) for v in gaps.values()), 'point_details': details,
        'gap_details': {key: all(values) for key, values in gaps.items()}}

def table_score(observation, expected, contract):
    aliases = contract['aliases']
    rows = defaultdict(list)
    for table in observation['projection']['tables']:
        if not table['visible']:
            continue
        columns = None
        for row in table['rows']:
            if not row['visible']:
                continue
            cells = row['cells']
            found = {}
            for index, cell in enumerate(cells):
                field = T['alias'](cell['text'], aliases)
                if field:
                    if field in found:
                        found[field] = -1
                    else:
                        found[field] = index
            required = {'metric_date', 'cohort', 'numerator', 'denominator', 'rate', 'observable'}
            if required <= set(found) and all(found[k] >= 0 for k in required) and all(cells[found[k]]['visible'] for k in required):
                columns = {k: found[k] for k in required}
                continue
            if columns is None or len(cells) <= max(columns.values()):
                continue
            values = {k: cells[c]['text'].strip() for k, c in columns.items()}
            key = T['date'](values['metric_date']), T['alias'](values['cohort'], contract['cohort_aliases'])
            if key[0] and key[1]:
                values['_visible'] = all(cells[c]['visible'] for c in columns.values())
                rows[key].append(values)
    scores = []
    details = []
    for wanted in expected['summaries']:
        key = wanted['metric_date'], wanted['cohort']
        actual = rows.get(key, [])
        passed = len(actual) == 1 and actual[0]['_visible']
        if passed:
            actual = actual[0]
            for field in ['denominator', 'numerator', 'rate']:
                value = actual[field]
                if field == 'rate' and value.endswith(('%', '％')):
                    number = T['number'](value[:-1])
                    value = number / 100 if isinstance(number, (int, float)) else 'INVALID'
                else:
                    value = T['number'](value, missing=True)
                passed = passed and (value is None if wanted[field] is None else isinstance(value, (int, float)) and abs(value - wanted[field]) < 1e-6)
            observed = 1 if actual['observable'] in {'空队列', 'empty_cohort'} else T['bit'](actual['observable'])
            passed = passed and observed == wanted['observable']
        scores.append(bool(passed));details.append({'key': key, 'passed': bool(passed)})
    known = {(r['metric_date'], r['cohort']) for r in expected['summaries']}
    extras = sum(len(values) for key, values in rows.items() if key not in known)
    return {'score': average(scores) * 30 / (30 + extras), 'rows': details, 'extra_rows': extras}

def visible_source_evidence(observation, expected):
    texts = [t for t in observation['projection']['texts'] if t['visible'] and text_box(t)]
    headings = []
    for index, item in enumerate(texts):
        if re.fullmatch(r'h[1-6]', item['tag'] or ''):
            headings.append((index, int(item['tag'][1])))
    blocks = []
    for number, level in headings:
        end = next((i for i, next_level in headings if i > number and next_level <= level), len(texts))
        blocks.append((texts[number]['text'], ' '.join(t['text'] for t in texts[number:end])))
    for table in observation['projection']['tables']:
        if table['visible']:
            for row in table['rows']:
                if row['visible'] and all(c['visible'] for c in row['cells']):
                    content = ' '.join(c['text'] for c in row['cells'])
                    blocks.append((content, content))
    trace = {r['trace_id']: r for r in expected['legacy_trace']}
    details = []
    for anomaly in expected['anomalies']:
        role = {'duplicate_event_rows': 'lost', 'utc_day_cutover': 'return_evidence', 'wrong_cohort_denominator': 'denominator'}[anomaly['mechanism']]
        direct = {key for key in anomaly['evidence']['trace_ids'] if trace[key]['role'] == role}
        passed = False
        for label, text in blocks:
            # Only a block tied to the actual anomaly date may supply its
            # numbers and witnesses; a global list of unrelated IDs is not enough.
            date = anomaly['metric_date']
            date_present = date in {T['date'](value) for value in re.findall(r'20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}日?', label)}
            if not date_present:
                continue
            compressed = re.sub(r'\s+', '', text)
            ratios = [str(int(anomaly[k]['numerator'])) + '/' + str(int(anomaly[k]['denominator'])) for k in ['old', 'corrected']]
            if not all(ratio in compressed for ratio in ratios):
                continue
            ids = set(re.findall(r'(?<![A-Z0-9])T\d+(?![A-Z0-9])', text)) & direct
            tokens = set(re.findall(r'(?<![A-Z0-9])[RE]\d+(?![A-Z0-9])', text))
            if any(trace[key]['record_id'] in tokens and trace[key]['event_id'] in tokens for key in ids):
                passed = True
                break
        details.append({'metric_date': anomaly['metric_date'], 'cohort': anomaly['cohort'], 'direct_role': role, 'passed': passed})
    narrative = ' '.join(t['text'] for t in texts if t['tag'] not in {'td', 'th', 'text', 'tspan'})
    cutoff = bool(re.search(r'2026\D*0?9\D*15', narrative)) and bool(re.search(r'23\D*59\D*59', narrative))
    limit = bool(re.search(r'待观察|未完成|未观察|unobserved', narrative, re.I))
    return {'score': average(d['passed'] for d in details), 'anomalies': details, 'cutoff_visible': cutoff, 'observation_limit_visible': limit}

def assess_html(source, lock, derived, expected, contract, *, resource_root=None):
    api = runpy.run_path(str(Path(__file__).with_name(contract['html_helper'])))
    first = api['observe_html'](source, lock, Path(derived) / 'html-discovery', resource_root=resource_root)
    observation = json.loads(Path(first['path']).read_text(encoding='utf-8'))
    visible_table = table_score(observation, expected, contract)
    source_evidence = visible_source_evidence(observation, expected)
    requests_blocked = any(r['result'] == 'blocked' for r in observation['requests']) or bool(observation['websockets'])
    failure = requests_blocked or bool(observation['page_errors'])
    projection = observation['projection']
    if failure or not projection['svg'] and not projection['canvases'] and not any(i['visible'] for i in projection['images']):
        return {'table': visible_table, 'chart': {'points': 0.0, 'gaps': 0.0}, 'offline_dependencies': not requests_blocked,
            'visible_evidence': source_evidence, 'render_usable': not failure, 'known_candidate_render_failure': True, 'receipts': [first['audit_path']]}
    plans = infer_charts(observation)
    probes, probe_contract = chart_probes(plans, expected)
    second = api['observe_html'](source, lock, Path(derived) / 'html-geometry', probes=probes, resource_root=resource_root)
    actual = json.loads(Path(second['path']).read_text(encoding='utf-8'))
    final_plans = infer_charts(actual)
    if plans != final_plans:
        raise HtmlUnsupported('H021_HTML_RENDER_CHANGED: layout/series changed between discovery and native probe capture')
    final_table = table_score(actual, expected, contract)
    if visible_table != final_table:
        raise HtmlUnsupported('H021_HTML_RENDER_CHANGED: visible table changed between captures')
    return {'table': final_table, 'chart': score_chart(actual, plans, probe_contract), 'plans': plans,
        'visible_evidence': visible_source_evidence(actual, expected),
        'offline_dependencies': not any(r['result'] == 'blocked' for r in actual['requests']) and not actual['websockets'],
        'render_usable': not actual['page_errors'], 'receipts': [first['audit_path'], second['audit_path']]}
