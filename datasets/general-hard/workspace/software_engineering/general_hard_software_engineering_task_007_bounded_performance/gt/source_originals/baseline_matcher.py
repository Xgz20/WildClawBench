"""Semantically correct baseline with repeated catalog scans."""
def match_records(queries, catalog):
    output = []
    for query in queries:
        matches = []
        matched_by = 'unmatched'
        for kind in ('email', 'phone', 'name_region'):
            target = query.key(kind)
            if target is None:
                continue
            for record in catalog:
                if record.key(kind) == target:
                    matches.append(record.id)
            if matches:
                matched_by = kind
                break
        output.append({'query_id': query.id, 'matched_by': matched_by, 'row_ids': matches})
    return output
