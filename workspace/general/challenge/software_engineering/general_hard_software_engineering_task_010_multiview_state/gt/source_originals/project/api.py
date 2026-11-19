"""Original prototype: page-local filtering and counts cause disappearing records."""
def query_records(records, query, snapshot_version):
    status = query.get('status', 'all')
    term = query.get('term', '').strip().lower()
    page = max(1, query.get('page', 1))
    size = query.get('pageSize', 3)
    subset = records[(page-1)*size:page*size]
    matching = [row for row in subset if not term or term in row['title'].lower() or term in row['owner'].lower()]
    counts = {name: sum(name == 'all' or row['status'] == name for row in matching) for name in ('all','pending','approved')}
    items = [row for row in matching if status == 'all' or row['status'] == status]
    return {'query': {'status':status,'term':term,'page':page,'pageSize':size}, 'items':items,
            'total':len(items),'counts':counts,'page':page,'pageSize':size,'lastPage':1,'version':snapshot_version}
