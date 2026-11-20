"""Protected local database constructor, not a network or external DB adapter."""
from pathlib import Path
import json
import sqlite3

def open_database(root):
    root=Path(root)
    connection=sqlite3.connect(':memory:')
    connection.executescript((root/'fixtures/schema.sql').read_text(encoding='utf-8'))
    data=json.loads((root/'fixtures/data.json').read_text(encoding='utf-8'))
    for table,rows in data.items():
        for row in rows:
            names=list(row)
            sql='INSERT INTO "'+table+'" ('+','.join('"'+name+'"' for name in names)+') VALUES ('+','.join('?' for _ in names)+')'
            connection.execute(sql,[row[name] for name in names])
    connection.commit()
    connection.execute('PRAGMA query_only=ON')
    return connection
