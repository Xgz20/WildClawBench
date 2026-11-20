"""Author reference for application-level SQLite association validation."""
import re


class BatchError(ValueError):
    def __init__(self, code, entity="batch", index=None):
        self.code, self.entity, self.index = code, entity, index
        super().__init__(f"{code}: {entity}[{index}]")


def create_schema(conn):
    statements = [
        "CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, name TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, capacity INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS bookings (id TEXT PRIMARY KEY, person_id TEXT NOT NULL, room_id TEXT NOT NULL, seats INTEGER NOT NULL)",
    ]
    for statement in statements:
        conn.execute(statement)


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", value) is not None


def import_batch(conn, batch, *, fail_after=None):
    if fail_after is not None and (type(fail_after) is not int or fail_after < 0):
        raise BatchError("E_CONFIG")
    groups = ("people", "rooms", "bookings")
    if not isinstance(batch, dict) or set(batch) != set(groups) or any(not isinstance(batch[name], list) for name in groups):
        raise BatchError("E_SCHEMA")
    fields = {"people": ("id", "name"), "rooms": ("id", "capacity"), "bookings": ("id", "person_id", "room_id", "seats")}
    result = {"inserted": {name: 0 for name in groups}, "skipped": {name: 0 for name in groups}}
    inserted = 0
    # A savepoint is valid both as an outermost transaction and inside a caller
    # transaction. Releasing it must not commit caller-owned work.
    conn.execute("SAVEPOINT course_batch_import")
    try:
        if fail_after == 0:
            raise BatchError("E_INJECTED")
        for entity in groups:
            columns = fields[entity]
            for index, record in enumerate(batch[entity]):
                if not isinstance(record, dict) or set(record) != set(columns):
                    raise BatchError("E_ROW", entity, index)
                if not _identifier(record["id"]):
                    raise BatchError("E_FIELD", entity, index)
                if entity == "people":
                    valid = isinstance(record["name"], str) and bool(record["name"].strip())
                elif entity == "rooms":
                    valid = type(record["capacity"]) is int and record["capacity"] > 0
                else:
                    valid = (_identifier(record["person_id"]) and _identifier(record["room_id"])
                             and type(record["seats"]) is int and record["seats"] > 0)
                if not valid:
                    raise BatchError("E_FIELD", entity, index)
                values = tuple(record[column] for column in columns)
                existing = conn.execute(f"SELECT {','.join(columns)} FROM {entity} WHERE id = ?", (record["id"],)).fetchone()
                if existing is not None:
                    if tuple(existing) != values:
                        raise BatchError("E_ID_CONFLICT", entity, index)
                    result["skipped"][entity] += 1
                    continue
                if entity == "bookings":
                    if conn.execute("SELECT 1 FROM people WHERE id = ?", (record["person_id"],)).fetchone() is None:
                        raise BatchError("E_PERSON", entity, index)
                    room = conn.execute("SELECT capacity FROM rooms WHERE id = ?", (record["room_id"],)).fetchone()
                    if room is None:
                        raise BatchError("E_ROOM", entity, index)
                    used = conn.execute("SELECT COALESCE(SUM(seats),0) FROM bookings WHERE room_id = ?", (record["room_id"],)).fetchone()[0]
                    if used + record["seats"] > room[0]:
                        raise BatchError("E_CAPACITY", entity, index)
                placeholders = ",".join("?" for _ in columns)
                conn.execute(f"INSERT INTO {entity} ({','.join(columns)}) VALUES ({placeholders})", values)
                result["inserted"][entity] += 1
                inserted += 1
                if inserted == fail_after:
                    raise BatchError("E_INJECTED", entity, index)
        conn.execute("RELEASE SAVEPOINT course_batch_import")
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT course_batch_import")
        conn.execute("RELEASE SAVEPOINT course_batch_import")
        raise
    return result
