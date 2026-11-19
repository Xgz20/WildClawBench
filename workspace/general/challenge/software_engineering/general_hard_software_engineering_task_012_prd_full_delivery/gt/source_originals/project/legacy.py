"""Protected unrelated legacy shape."""
def health():return {'service':'member-demo','status':'ok','api':1}
def export_members(db):
    rows=db.execute("SELECT id,name,email FROM members WHERE status='active' ORDER BY id").fetchall()
    return 'id,name,email\n'+''.join(','.join(str(v) for v in row)+'\n' for row in rows)
