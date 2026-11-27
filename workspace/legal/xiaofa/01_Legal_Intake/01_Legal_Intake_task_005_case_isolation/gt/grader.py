"""Self-contained, evaluator-only checks. Copied into each workspace/gt.

No candidate code is imported or executed. Legal semantics are judged separately.
"""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root, name):
    p = root / name
    return p if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve()) else None


def equal(actual, expected):
    if isinstance(expected, bool) or expected is None:
        return actual is expected
    if isinstance(expected, (int, float)):
        return type(actual) in (int, float) and math.isfinite(actual) and abs(actual - expected) <= 0.005
    if isinstance(expected, list):
        # Set-valued fields: order independent, duplicate entries still fail.
        return isinstance(actual, list) and sorted(map(lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False), actual)) == sorted(map(lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False), expected))
    return type(actual) is type(expected) and actual == expected


def inspect_artifact(p, spec):
    if not p or p.stat().st_size == 0:
        return False
    kind = spec.get('kind', p.suffix.lstrip('.'))
    try:
        if kind == 'docx':
            with zipfile.ZipFile(p) as z:
                doc = ET.fromstring(z.read('word/document.xml'))
                text = ''.join(n.text or '' for n in doc.iter(W + 't'))
                if len(text) < spec.get('min_chars', 80):
                    return False
                if any(s not in text for s in spec.get('contains', [])):
                    return False
                if any(s in text for s in spec.get('excludes', [])):
                    return False
                if spec.get('tables', 0) > len(list(doc.iter(W + 'tbl'))):
                    return False
                if spec.get('comments'):
                    comments = ET.fromstring(z.read('word/comments.xml'))
                    ids = {n.get(W+'id') for n in comments.iter(W+'comment')}
                    starts = {n.get(W+'id') for n in doc.iter(W+'commentRangeStart')}
                    ends = {n.get(W+'id') for n in doc.iter(W+'commentRangeEnd')}
                    refs = {n.get(W+'id') for n in doc.iter(W+'commentReference')}
                    rels = ET.fromstring(z.read('word/_rels/document.xml.rels'))
                    if len(ids) < spec['comments'] or not ids.issubset(starts & ends & refs):
                        return False
                    if not any(n.get('Type','').endswith('/comments') and n.get('Target','').endswith('comments.xml') for n in rels):
                        return False
                if spec.get('tracked') and not (list(doc.iter(W+'ins')) and list(doc.iter(W+'del'))):
                    return False
                if spec.get('clean') and (list(doc.iter(W+'ins')) or list(doc.iter(W+'del'))):
                    return False
            return True
        if kind == 'json':
            return isinstance(json.loads(p.read_text('utf-8')), (dict, list))
        if kind == 'pdf':
            data = p.read_bytes()
            return data.startswith(b'%PDF-') and b'%%EOF' in data[-1024:]
        if kind == 'png':
            return p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        text = p.read_text('utf-8')
        return len(text.strip()) >= spec.get('min_chars', 80) and all(s in text for s in spec.get('contains', [])) and not any(s in text for s in spec.get('excludes', []))
    except (ValueError, KeyError, OSError, UnicodeError, zipfile.BadZipFile, ET.ParseError):
        return False


def grade(workspace):
    root = Path(workspace)
    # Infrastructure errors deliberately propagate. Missing/corrupt GT is not candidate failure.
    oracle = json.loads((root / 'gt/oracle.json').read_text('utf-8'))
    expected = oracle['facts']
    if not expected or not oracle['input_hashes'] or not oracle['deliverables']:
        raise ValueError('incomplete evaluator oracle')
    answer = {}
    p = safe_file(root, 'results/facts.json')
    try:
        answer = json.loads(p.read_text('utf-8')) if p else {}
    except (ValueError, OSError, UnicodeError):
        pass
    if not isinstance(answer, dict):
        answer = {}
    facts = answer.get('facts', {})
    facts = facts if isinstance(facts, dict) else {}
    correct = {k: equal(facts.get(k), v) and k in facts for k, v in expected.items()}
    bindings = answer.get('sources', {})
    bindings = bindings if isinstance(bindings, dict) else {}
    hashes = answer.get('input_sha256', {})
    hashes = hashes if isinstance(hashes, dict) else {}
    source_ok = {}
    for key, names in oracle['fact_sources'].items():
        rows = bindings.get(key, [])
        # Each atomic fact must bind to an allowed original, with a meaningful locator.
        source_ok[key] = isinstance(rows, list) and any(
            isinstance(r, dict) and r.get('file') in names and isinstance(r.get('locator'), str)
            and len(r['locator'].strip()) >= 2
            and hashes.get(r['file']) == oracle['input_hashes'].get(r['file'])
            for r in rows)
    preserved = {name: bool((p := safe_file(root, name)) and digest(p) == sha)
                 for name, sha in oracle['input_hashes'].items()}
    artifacts = {s['path']: inspect_artifact(safe_file(root, s['path']), s) for s in oracle['deliverables']}
    for target, origin in oracle.get('unchanged_doc_body', {}).items():
        try:
            def text_nodes(path):
                with zipfile.ZipFile(path) as z:
                    doc = ET.fromstring(z.read('word/document.xml'))
                    return [''.join(n.text or '' for n in p.iter(W+'t')) for p in doc.iter(W+'p')]
            p = safe_file(root, target)
            artifacts[target] = bool(artifacts.get(target) and p and text_nodes(p) == text_nodes(root/origin))
        except (ValueError, KeyError, OSError, zipfile.BadZipFile, ET.ParseError):
            artifacts[target] = False
    if 'comment_update' in oracle:
        rule = oracle['comment_update']
        try:
            def comments(path):
                with zipfile.ZipFile(path) as z:
                    tree = ET.fromstring(z.read('word/comments.xml'))
                    return {n.get(W+'id'): ''.join(t.text or '' for t in n.iter(W+'t')) for n in tree.iter(W+'comment')}
            p = safe_file(root, rule['target'])
            before, after = comments(root/rule['source']), comments(p) if p else {}
            # IDs may be reassigned by Office; match visible C01/C02 labels instead.
            old_c2 = next(v for v in before.values() if v.startswith('C02'))
            new_c1 = [v for v in after.values() if v.startswith('C01')]
            ok = len(after)==2 and old_c2 in after.values() and len(new_c1)==1
            ok = ok and all(x in new_c1[0] for x in rule['contains']) and not any(x in new_c1[0] for x in rule['excludes'])
            artifacts[rule['target']] = bool(artifacts.get(rule['target']) and ok)
        except (ValueError, KeyError, OSError, StopIteration, zipfile.BadZipFile, ET.ParseError):
            artifacts[rule['target']] = False
    for target, origin in oracle.get('copies', {}).items():
        p = safe_file(root, target)
        artifacts[target] = bool(p and digest(p) == oracle['input_hashes'][origin])
    # Evidence tasks: claimed hashes must bind to the actual delivered copies.
    for key, target in oracle.get('result_hash_fields', {}).items():
        p = safe_file(root, target)
        correct[key] = bool(p and facts.get(key) == digest(p))
    scores = {
        'fact_accuracy': sum(correct.values()) / len(correct),
        'delivery_integrity': sum(artifacts.values()) / len(artifacts),
        'evidence_binding': sum(source_ok.values()) / len(source_ok),
        'input_preservation': float(all(preserved.values())),
    }
    scores['overall_score'] = sum(scores[k] * w for k, w in
        [('fact_accuracy', .5), ('delivery_integrity', .2), ('evidence_binding', .2), ('input_preservation', .1)])
    print(json.dumps({'fact_checks': correct, 'artifact_checks': artifacts,
                      'source_checks': source_ok, 'input_checks': preserved}, ensure_ascii=False))
    return scores
