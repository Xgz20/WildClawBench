"""H029 standalone automatic component; semantic assessment is separate.

grade() never accesses reference answers, networks, models, or candidate caches.
Its overall_score is the automatic component A, not .40*A+.60*S.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import runpy


def grade(transcript=None, workspace_path=None, **kwargs):
    gt = Path(__file__).resolve().parent
    if not workspace_path:
        raise RuntimeError('H029 workspace_path is required')
    root = Path(workspace_path).resolve()

    def load(name):
        try:
            value = json.loads((gt / name).read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeError) as exc:
            raise RuntimeError('H029 private material missing/invalid: ' + name) from exc
        if not isinstance(value, dict):
            raise RuntimeError('H029 private material must be an object: ' + name)
        return value

    binding = load('scoring_contract.json')
    hashes = binding.get('private_sha256')
    if not isinstance(hashes, dict) or not hashes:
        raise RuntimeError('H029 private bindings missing')
    for name, digest in hashes.items():
        if not isinstance(name, str) or Path(name).name != name or name == 'scoring_contract.json':
            raise RuntimeError('H029 private binding filename invalid')
        path = gt / name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('H029 private material drift: ' + name)
    contract = load('artifact_contract.json')
    runtime = load('runtime_contract.json')
    protected = load('protected_sha256.json')
    public = contract.get('public_contract')
    if not isinstance(public, dict) or contract.get('expected_event_count') != 4 or contract.get('no_answer_names_or_URLs_for_automatic_matching') is not True:
        raise RuntimeError('H029 open answer artifact contract invalid')
    if binding.get('grading_type') != 'hybrid' or runtime.get('semantic_judge_required') is not True or binding.get('automatic_weight') != .4 or binding.get('semantic_weight') != .6:
        raise RuntimeError('H029 hybrid scoring boundary invalid')
    if binding.get('checkpoint_weights') != {'record_contract': .2, 'time_and_scope': .25, 'citation_resolution': .4, 'protected_delivery': .15}:
        raise RuntimeError('H029 automatic checkpoint allocation drift')
    io = runpy.run_path(str(gt / 'native_io.py'))
    office = runpy.run_path(str(gt / 'office_runtime.py'))
    projector = runpy.run_path(str(gt / 'source_projection.py'))
    mean, refs, string = io['mean'], io['refs'], io['string']
    if not os.environ.get('GENERAL_E2E_OFFICE_LOCK') or not os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR'):
        raise RuntimeError('H029 managed Office/evidence runtime context missing')
    try:
        lock = json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RuntimeError('H029 Office runtime lock missing/invalid') from exc
    office['validate_office_lock'](lock)
    evidence = Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if evidence == root or root in evidence.parents or evidence == gt or gt in evidence.parents:
        raise RuntimeError('H029 derived evidence must remain outside frozen Workspace and GT')
    errors = {}
    recalculation = None

    def attempt(name, action):
        try:
            return action()
        except io['CandidateError'] as exc:
            errors[name] = str(exc)
            return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in {'OFFICE_INPUT_INVALID', 'OFFICE_INPUT_LIMIT', 'OFFICE_ACTIVE_CONTENT_UNSUPPORTED', 'OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:
                raise
            errors[name] = str(exc)
            return None

    def workbook():
        nonlocal recalculation
        path = io['candidate_path'](root, 'results/event_matrix.xlsx')
        office['_clean_package'](path.read_bytes())
        original = io['read_book'](path)
        if not any(c['formula'] for sheet in original for c in sheet['cells'].values()):
            return original
        recalculation = office['recalculate_xlsx'](path, lock, evidence / 'recalculated', timeout_seconds=90)
        book = io['read_book'](recalculation['path'])
        prior = {s['name']: s for s in original}
        for sheet in book:
            if sheet['name'] not in prior:
                raise RuntimeError('H029 Office unexpectedly changed worksheet identities')
            for position, cell in sheet['cells'].items():
                old = prior[sheet['name']]['cells'].get(position, {'visible': prior[sheet['name']]['state'] == 'visible', 'editable': True})
                cell['visible'] &= old['visible']
                cell['editable'] &= old['editable']
        return book

    book = attempt('workbook', workbook)
    ledger = attempt('ledger', lambda: io['read_ledger'](io['candidate_path'](root, 'results/source_ledger.json')))
    docx = attempt('brief', lambda: io['read_docx'](io['candidate_path'](root, 'results/brief.docx')))
    manifest, bundle = io['load_bundle'](ledger, ledger_path=root / 'results/source_ledger.json')
    if manifest.get('collector_sha256') != runtime.get('source_collector_sha256'):
        raise io['TrustedEvidenceError']('H029 production source collector SHA/version drift')
    if manifest.get('bindings', {}).get('policy_sha256') != io['sha'](gt / 'research_source_policy.json'):
        raise io['TrustedEvidenceError']('H029 research source policy binding drift')
    if ledger is None and manifest.get('candidate_input_status') == 'valid':
        raise io['TrustedEvidenceError']('trusted collector did not bind candidate ledger failure')
    bundle_root = Path(os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE']).resolve()
    if evidence == bundle_root or bundle_root in evidence.parents:
        raise io['TrustedEvidenceError']('derived evidence must remain outside source bundle')
    evidence.mkdir(parents=True, exist_ok=True)
    derived_receipts = []
    for index, (sid, source) in enumerate(bundle.items(), 1):
        if source.get('status') != 'acquired':
            continue
        media = source.get('media_type', '')
        if not isinstance(media, str):
            raise io['TrustedEvidenceError']('trusted source media type invalid: ' + sid)
        mime = media.split(';', 1)[0].strip().lower()
        effective_media = 'application/pdf' if source['_body'].startswith(b'%PDF-') else 'text/html' if source['_body'].lstrip().lower().startswith((b'<!doctype html', b'<html')) else media
        effective_mime = effective_media.split(';', 1)[0].strip().lower()
        if effective_mime in {'text/html', 'application/xhtml+xml', 'application/pdf'}:
            projection = projector['project_source'](source['_body'], effective_media, source['_text'])
            projection['provenance']['production_media_type_observed'] = media
        elif mime.startswith('text/') or mime in {'application/json', 'application/xml'}:
            original_records = source['_text'].get('records')
            metadata = source['_text'].get('raw_metadata', {})
            if not isinstance(original_records, list) or not original_records or not all(isinstance(row, dict) and isinstance(row.get('text'), str) and isinstance(row.get('locator'), dict) for row in original_records) or not isinstance(metadata, dict):
                raise io['TrustedEvidenceError']('trusted production text projection malformed: ' + sid)
            projection = {'schema_version': projector['SCHEMA_VERSION'], 'complete': True, 'records': original_records, 'metadata': {'complete': True, 'observations': [{'observed_type': 'production_raw_metadata', 'property': key, 'value': value} for key, value in metadata.items()], 'policy': 'Only actual production raw metadata; body date roles require Judge'}, 'errors': [], 'warnings': [], 'provenance': {'body_sha256': source['body_sha256'], 'body_bytes': len(source['_body']), 'media_type_observed': media, 'projection_method': 'SHA-verified-production-text-projection-passthrough', 'production_projection_sha256': source['projection_sha256'], 'production_projection_engine': source['_text'].get('engine'), 'network_used': False, 'javascript_executed': False}}
        else:
            raise io['TrustedEvidenceError']('trusted collector acquired unsupported projection media: ' + sid)
        projection['attempt_binding'] = {
            'source_id': sid,
            'source_body_sha256': source['body_sha256'],
            'source_bundle_manifest_sha256': os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256'],
            'bundle_acquisition_identity': manifest.get('acquisition_identity'),
            'bundle_bindings': manifest.get('bindings'),
            'bundle_candidate_original_sha256': manifest.get('bindings', {}).get('candidate_sha256') if isinstance(manifest.get('bindings'), dict) else None,
            'candidate_ledger_sha256': io['sha'](root / 'results/source_ledger.json') if ledger is not None else None,
            'rule_source_sha256': io['sha'](gt / 'source_projection.py'),
            'source_acquisition': source.get('_acquisition'),
            'projection_boundary': 'Raw body and existing page projection came only from the verified production source bundle; no candidate source cache accepted',
        }
        receipt = projector['write_derived_projection'](projection, evidence / 'sources', stem='source-' + str(index))
        derived_receipts.append(dict(receipt, source_id=sid, body_sha256=source['body_sha256'], source_acquisition=source.get('_acquisition')))
        if projection.get('complete') is not True:
            raise io['TrustedEvidenceError']('H029 source body projection unresolved: ' + sid + ': ' + json.dumps(projection.get('errors'), ensure_ascii=False))
        source['_derived'] = projection
    view = io['ledger_records'](ledger)
    maps = view['maps']
    duplicates = view['duplicates']
    extracted = io['extract_events'](book or [], public)
    slots = extracted['slots']
    event_ids = [e['event_id'] for e in slots if isinstance(e, dict)]
    sections = maps['brief_sections']
    blocks = io['brief_blocks'](docx, sections)

    def roles(observation):
        value = observation.get('role') if isinstance(observation, dict) else None
        return refs(value)

    citation_checks = {}
    for cid, (sid, citation) in maps['citations'].items():
        checked = io['resolve_citation'](bundle.get(sid), citation)
        if cid in duplicates['citations']:
            checked = dict(checked, resolved=False, reason='citation_id duplicated')
        citation_checks[cid] = dict(checked, source_id=sid)

    def all_known(cids):
        return bool(cids) and all(cid in maps['citations'] and cid not in duplicates['citations'] for cid in cids)

    def all_resolved(cids):
        return bool(cids) and all(cid in citation_checks and citation_checks[cid]['resolved'] for cid in cids)

    def valid_access(source):
        if not isinstance(source, dict):
            return False
        status = source.get('access_status')
        if not isinstance(status, str) or status not in {'read_full', 'read_excerpt', 'search_only', 'unavailable'}:
            return False
        try:
            value = dt.datetime.fromisoformat(str(source.get('accessed_at', '')).replace('Z', '+00:00'))
            return value.tzinfo is not None
        except ValueError:
            return source.get('accessed_at') is None and status in {'search_only', 'unavailable'} and (any(string(source.get(k)) for k in ('access_reason', 'discovery_reason', 'limitations', 'unavailable_reason')) or isinstance(ledger, dict) and 'limitations' in ledger)

    source_shapes = []
    citation_shapes = []
    for source in view['sources']:
        valid = isinstance(source, dict)
        if valid:
            valid = all(k in source for k in public['sources']['required_fields']) and string(source.get('source_id')) and string(source.get('url')) and isinstance(source.get('title'), str) and isinstance(source.get('citations'), list) and valid_access(source)
        source_shapes.append(bool(valid))
        if isinstance(source, dict) and isinstance(source.get('citations'), list):
            for citation in source['citations']:
                citation_shapes.append(isinstance(citation, dict) and all(k in citation for k in public['sources']['citations_fields']) and string(citation.get('citation_id')) and string(citation.get('quote')) and isinstance(citation.get('locator'), dict) and bool(citation.get('locator')))
    claim_shapes = []
    for claim in view['claims']:
        valid = isinstance(claim, dict)
        if valid:
            kind = claim.get('claim_kind')
            fields = refs(claim.get('supports_fields'))
            valid = all(k in claim for k in public['claims']['fields']) and string(claim.get('claim_id')) and bool(refs(claim.get('event_id_or_section_id'))) and string(claim.get('claim_text')) and isinstance(kind, str) and kind in set(public['claims']['claim_kind']) and bool(fields) and all(f in public['claims']['supports_fields'] for f in fields) and all_known(refs(claim.get('citation_ids')))
        claim_shapes.append(bool(valid))
    date_shapes = []
    for observation in view['date_evidence']:
        valid = isinstance(observation, dict)
        if valid:
            precision = observation.get('precision')
            absence = observation.get('absence_check')
            explicit_absence = precision == 'unknown' and isinstance(absence, dict) and string(absence.get('checked')) and string(observation.get('unknown_reason'))
            valid = all(k in observation for k in public['date_evidence']['fields']) and string(observation.get('date_id')) and string(observation.get('source_id')) and observation['source_id'] in maps['sources'] and bool(roles(observation)) and set(roles(observation)) <= io['DATE_ROLES'] and isinstance(precision, str) and precision in io['PRECISIONS'] and (all_known(refs(observation.get('citation_ids'))) or explicit_absence)
        date_shapes.append(bool(valid))
    def has_reason(row, keys):
        return any(string(row.get(key)) or isinstance(row.get(key), (dict, list)) and bool(row[key]) for key in keys)

    discovery_rows = view['discovery_candidates']
    discovery_checks = []
    for row in discovery_rows:
        decision = row.get('decision', row.get('discovery_decision')) if isinstance(row, dict) else None
        discovery_checks.append(isinstance(row, dict) and isinstance(decision, str) and decision in {'selected', 'rejected', 'unresolved'} and has_reason(row, ('reason', 'decision_reason', 'discovery_reason')))
    source_discovery = []
    for source in view['sources']:
        decision = source.get('discovery_decision', source.get('decision')) if isinstance(source, dict) else None
        source_discovery.append(isinstance(source, dict) and isinstance(decision, str) and decision in {'selected', 'rejected', 'unresolved'} and has_reason(source, ('discovery_reason', 'reason', 'decision_reason')))
    discovery_structure = bool(discovery_rows and all(discovery_checks) or source_discovery and all(source_discovery))
    lineage_checks = []
    lineage_covered = set()
    for edge in view['lineage_edges']:
        if not isinstance(edge, dict):
            lineage_checks.append(False)
            continue
        sid = edge.get('source_id', edge.get('from_source_id'))
        upstream = edge.get('upstream_source_id', edge.get('to_upstream_source_id'))
        relation = edge.get('relation')
        valid = string(sid) and sid in maps['sources'] and string(relation)
        unknown_relation = relation == 'unknown'
        valid = valid and (unknown_relation and has_reason(edge, ('reason', 'unknown_reason', 'basis')) or all_known(refs(edge.get('basis_citation_ids'))) and (upstream is None or string(upstream)))
        lineage_checks.append(bool(valid))
        if valid:
            lineage_covered.add(sid)
    source_lineage = []
    for source in view['sources']:
        if not isinstance(source, dict):
            source_lineage.append(False)
            continue
        sid = source.get('source_id')
        role = source.get('source_role')
        explicit = isinstance(role, str) and role in {'first_party', 'independent_reporting', 'derivative', 'unknown'}
        if role == 'unknown':
            explicit &= has_reason(source, ('lineage_reason', 'independence_basis', 'unknown_reason'))
        embedded = source.get('lineage')
        embedded_relation = isinstance(embedded, dict) and string(embedded.get('relation')) and (has_reason(embedded, ('reason', 'basis', 'unknown_reason')) or all_known(refs(embedded.get('basis_citation_ids'))))
        source_lineage.append(bool(sid in lineage_covered if isinstance(sid, str) else False) or explicit or embedded_relation or has_reason(source, ('lineage_reason', 'independence_basis')))
    lineage_structure = bool(source_lineage and all(source_lineage) and all(lineage_checks))
    source_schema = bool(ledger is not None and isinstance(ledger.get('sources'), list) and view['sources'] and 'limitations' in ledger and all(source_shapes) and all(citation_shapes) and all(claim_shapes) and all(date_shapes) and not any(duplicates.values()) and discovery_structure and lineage_structure)

    def business_slot(owner, field, claim_ids, parent_citations, doc_block=None):
        connected = io['claim_slot_graph'](owner, field, claim_ids, parent_citations, maps, duplicates)
        claims, cids, graph = connected['claims'], connected['citation_ids'], connected['id_graph']
        if doc_block is not None:
            graph &= any(io['contains_id'](text, owner) and any(io['contains_id'](text, claim['claim_id']) for claim in claims) and any(io['contains_id'](text, cid) for cid in cids) and any(io['contains_id'](text, eid) for eid in event_ids) for text in doc_block)
        independent = bool(graph and all(bundle.get(maps['citations'][cid][0], {}).get('status') == 'acquired' for cid in cids))
        located = bool(graph and all_resolved(cids))
        access = bool(graph and all(valid_access(maps['sources'].get(maps['citations'][cid][0])) for cid in cids) and all_resolved(cids))
        return {'owner_id': owner, 'field': field, 'claim_ids': [c['claim_id'] for c in claims], 'citation_ids': cids, 'id_graph': bool(graph), 'independent_source_binding': independent, 'quote_and_locator_resolution': located, 'access_level_and_original_quote': access, 'semantic_support': 'NEEDS_INDEPENDENT_JUDGE'}

    business_slots = []
    event_structures = []
    time_checks = []
    window = runtime.get('research_window')
    if not isinstance(window, dict) or not all(k in window for k in ('start_inclusive', 'end_exclusive')):
        raise RuntimeError('H029 frozen research window missing')
    dates = {did: io['date_check'](item, maps, bundle, citation_checks, window) for did, item in maps['date_evidence'].items()}
    for index, event in enumerate(slots, 1):
        if event is None:
            event_structures.append({'slot': index, 'present': False, 'score': 0.0})
            business_slots.extend(business_slot('missing-event-' + str(index), field, [], []) for field in io['SLOT_FIELDS'])
            time_checks.append({'slot': index, 'event_id': None, 'independent_dual_time_binding': False, 'precision_and_normalization': False, 'window_arithmetic': False, 'scope_version_evidence_trace': False})
            continue
        eid = event['event_id']
        stage = event.get('stage')
        region = event.get('provider_region')
        required_present = mean(int(field in event) for field in io['EVENT_FIELDS'])
        scalar_fields = ('event_id', 'change_group_id', 'product_id', 'product_name', 'provider_name', 'change_summary', 'availability', 'user_impact')
        # Descriptive cells may contain a small native record/list (for example
        # structured platform/plan limitations); only identifiers need strings.
        meaningful = mean(int(string(event.get(key)) or key not in {'event_id', 'change_group_id', 'product_id'} and isinstance(event.get(key), (dict, list)) and bool(event[key])) for key in scalar_fields)
        enums = isinstance(stage, str) and stage in public['products_and_event_groups']['stage_values'] and isinstance(region, str) and region in public['products_and_event_groups']['region_policy']['values']
        relation_shape = bool(refs(event.get('claim_ids')) and all(cid in maps['claims'] for cid in refs(event.get('claim_ids'))) and all_known(refs(event.get('citation_ids'))))
        event_structures.append({'slot': index, 'event_id': eid, 'present': True, 'fields_present': required_present, 'native_values': meaningful, 'declared_enum_values': bool(enums), 'cross_ids': relation_shape, 'unambiguous_merge': not event['_conflicts'], 'visible_editable': event['_visible'] and event['_editable'], 'locations': event['_locations'], 'score': mean([required_present, meaningful, float(enums), float(relation_shape), float(not event['_conflicts']), float(event['_visible'] and event['_editable'])])})
        current = [business_slot(eid, field, refs(event.get('claim_ids')), refs(event.get('citation_ids'))) for field in io['SLOT_FIELDS']]
        business_slots.extend(current)
        role_refs = {role: refs(event.get(key)) for role, key in (('event', 'event_date_ids'), ('publication', 'publication_date_ids'), ('planned', 'planned_date_ids'))}
        # An observed source publication can be reused by any event citing it.
        if not role_refs['publication']:
            source_ids = {maps['citations'][cid][0] for cid in refs(event.get('citation_ids')) if cid in maps['citations']}
            role_refs['publication'] = sorted({did for sid in source_ids for did in refs(maps['sources'].get(sid, {}).get('publication_date_ids'))})
        required_dates = role_refs['event'] + role_refs['publication'] + role_refs['planned']
        role_bound = bool(role_refs['event'] and role_refs['publication'] and 'planned_date_ids' in event and all(did in dates and did not in duplicates['date_evidence'] and role in roles(maps['date_evidence'][did]) and dates[did]['bound'] for role, values in role_refs.items() for did in values))
        precision = bool(role_refs['event'] and role_refs['publication'] and all(did in dates and dates[did]['bound'] and dates[did]['precision'] for did in required_dates))
        arithmetic = bool(role_refs['event'] and all(did in dates and dates[did]['bound'] and dates[did]['arithmetic'] for did in role_refs['event']))
        scope = all(s['id_graph'] and s['quote_and_locator_resolution'] for s in current)
        time_checks.append({'slot': index, 'event_id': eid, 'date_ids_by_declared_role': role_refs, 'independent_dual_time_binding': role_bound, 'precision_and_normalization': precision, 'window_arithmetic': arithmetic, 'scope_version_evidence_trace': scope, 'semantic_event_eligibility': 'NEEDS_INDEPENDENT_JUDGE'})
    brief_checks = []
    bykind = {kind: [s for s in sections.values() if isinstance(s.get('kind'), str) and s['kind'] == kind] for kind in ('trend', 'action')}
    for kind, number, field in (('trend', 2, 'trend_basis'), ('action', 1, 'action_basis')):
        for index in range(number):
            section = bykind[kind][index] if index < len(bykind[kind]) else None
            if section is None:
                checked = business_slot('missing-' + kind + '-' + str(index + 1), field, [], [], doc_block=[])
                brief_checks.append({'kind': kind, 'present': False, 'linked_visible_body': False})
            else:
                sid = section['section_id']
                checked = business_slot(sid, field, refs(section.get('claim_ids')), refs(section.get('citation_ids')), doc_block=blocks.get(sid, []))
                brief_checks.append({'kind': kind, 'section_id': sid, 'present': True, 'linked_visible_body': checked['id_graph']})
            business_slots.append(checked)
    if len(business_slots) != 23 or len(time_checks) != 4:
        raise RuntimeError('H029 fixed business denominator drift')
    selection = extracted['selection_unambiguous'] and len(bykind['trend']) == 2 and len(bykind['action']) == 1
    structure_score = .2 * mean([float(book is not None), float(ledger is not None), float(docx is not None)]) + .4 * mean(x['score'] for x in event_structures) + .2 * float(source_schema) + .15 * mean(float(x['linked_visible_body']) for x in brief_checks) + .05 * float(selection)
    time_score = mean(.3 * float(x['independent_dual_time_binding']) + .3 * float(x['precision_and_normalization']) + .2 * float(x['window_arithmetic']) + .2 * float(x['scope_version_evidence_trace']) for x in time_checks)
    citation_components = {key: mean(float(x[key]) for x in business_slots) for key in ('id_graph', 'independent_source_binding', 'quote_and_locator_resolution', 'access_level_and_original_quote')}
    citation_score = .25 * citation_components['id_graph'] + .25 * citation_components['independent_source_binding'] + .35 * citation_components['quote_and_locator_resolution'] + .15 * citation_components['access_level_and_original_quote']
    if not protected or not all(isinstance(name, str) and Path(name).name == name and isinstance(digest, str) and len(digest) == 64 for name, digest in protected.items()):
        raise RuntimeError('H029 protected SHA baseline invalid')
    input_checks = {name: (root / name).is_file() and not (root / name).is_symlink() and io['sha'](root / name) == digest for name, digest in protected.items()}
    native_validity = {'xlsx_open': book is not None, 'ledger_open': ledger is not None, 'docx_open': docx is not None, 'xlsx_visible_editable': bool(book and extracted['events'] and all(e['_visible'] and e['_editable'] for e in extracted['events'])), 'docx_visible_editable': bool(docx and docx['visible_native'] and docx['editable'])}
    delivery_score = float(all(input_checks.values())) * mean(float(v) for v in native_validity.values())
    scores = {key: round(float(value), 12) for key, value in {'record_contract': structure_score, 'time_and_scope': time_score, 'citation_resolution': citation_score, 'protected_delivery': delivery_score}.items()}
    scores['overall_score'] = round(sum(scores[key] * weight for key, weight in binding['checkpoint_weights'].items()), 12)
    if not all(0 <= value <= 1 for value in scores.values()):
        raise RuntimeError('H029 automatic score outside [0,1]')
    # Complete source text already exists in the bound source/derived files.
    # Do not replicate a whole long source for every quotation in the audit.
    reported_citations = {cid: {key: value for key, value in checked.items() if key != 'selected_text'} for cid, checked in citation_checks.items()}
    observations = {'schema_version': 'h029-rule-observations/v1', 'scores': scores, 'fixed_event_denominator': 4, 'fixed_claim_denominator': 23, 'candidate_errors': errors, 'protected_inputs': input_checks, 'native_delivery': native_validity, 'event_structure': event_structures, 'native_header_mappings': extracted['headers'], 'explicit_header_mappings': extracted['explicit_header_mappings'], 'header_alias_conflicts': extracted['header_alias_conflicts'], 'record_selection_unambiguous': selection, 'ledger_schema_valid': source_schema, 'ledger_aux_structure': {'discovery': discovery_structure, 'lineage': lineage_structure}, 'ledger_duplicate_ids': duplicates, 'brief_structure': brief_checks, 'date_observations': dates, 'time_and_scope': time_checks, 'business_citation_slots': business_slots, 'citation_components': citation_components, 'citation_checks': reported_citations, 'office_recalculation': recalculation, 'derived_source_receipts': derived_receipts, 'source_acquisition_summary': manifest.get('acquisition_summary'), 'source_bundle_manifest_sha256': os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256'], 'private_contract_sha256': io['sha'](gt / 'scoring_contract.json'), 'semantic_status': 'NEEDS_INDEPENDENT_JUDGE', 'semantic_score': None, 'formal_hybrid_score': None, 'semantic_boundary': runtime['semantic_boundary'], 'automatic_full_score_does_not_establish_event_identity_stage_time_relation_or_support': True}
    with (evidence / 'h029-observations.json').open('x', encoding='utf-8') as handle:
        json.dump(observations, handle, ensure_ascii=False, indent=2, default=str)
        handle.write('\n')
    return scores
