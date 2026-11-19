"""Trusted action driver; contains no expected answers and sees only a staged store."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys


def load_store(path):
    spec = importlib.util.spec_from_file_location("store", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def snapshot(conn):
    return {table: [list(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
            for table in ("people", "rooms", "bookings")}


def run(store, scenario, path):
    conn = sqlite3.connect(path)
    store.create_schema(conn)
    for table, rows in scenario.get("seed", {}).items():
        for row in rows:
            conn.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in row)})", row)
    conn.commit()
    events = []
    for action in scenario["actions"]:
        kind = action["kind"]
        if kind == "import":
            before = snapshot(conn)
            try:
                value = store.import_batch(conn, action["batch"], fail_after=action.get("fail_after"))
            except store.BatchError as exc:
                value = {"error": {"code": exc.code, "entity": exc.entity, "index": exc.index}}
            events.append({"label": action.get("label", "import"), "before": before, "after": snapshot(conn),
                           "result": value, "in_transaction": conn.in_transaction})
        elif kind == "caller_person":
            conn.execute("INSERT INTO people VALUES (?,?)", action["row"])
        elif kind == "begin":
            conn.execute("BEGIN")
        elif kind == "commit":
            conn.commit()
        elif kind == "rollback":
            conn.rollback()
        elif kind == "schema_again":
            store.create_schema(conn)
        elif kind == "snapshot":
            events.append({"label": action["label"], "state": snapshot(conn), "in_transaction": conn.in_transaction})
        elif kind == "external":
            external = sqlite3.connect(path)
            try:
                events.append({"label": action["label"], "state": snapshot(external)})
            finally:
                external.close()
        else:
            raise ValueError("unknown driver action")
    schema = {table: [[row[1], row[2], row[3], row[5]] for row in conn.execute(f"PRAGMA table_info({table})")]
              for table in ("people", "rooms", "bookings")}
    fks = {table: conn.execute(f"PRAGMA foreign_key_list({table})").fetchall() for table in schema}
    triggers = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    conn.close()
    return {"events": events, "schema": schema, "foreign_keys": fks, "triggers": triggers, "tables": tables}


if __name__ == "__main__":
    scenario = json.loads(sys.stdin.read())
    result = run(load_store(Path(__file__).with_name("store.py")), scenario, Path(__file__).with_name("scratch.sqlite"))
    print(json.dumps(result, ensure_ascii=False))
