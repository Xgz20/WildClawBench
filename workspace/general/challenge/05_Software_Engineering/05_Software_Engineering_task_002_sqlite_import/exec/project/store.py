"""Application-level booking importer; schema 1.3."""
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
    groups = ("people", "rooms", "bookings")
    fields = {"people": ("id", "name"), "rooms": ("id", "capacity"), "bookings": ("id", "person_id", "room_id", "seats")}
    result = {"inserted": {name: 0 for name in groups}, "skipped": {name: 0 for name in groups}}
    inserted = 0
    for entity in groups:
        for index, record in enumerate(batch.get(entity, [])):
            columns = fields[entity]
            if not _identifier(record.get("id")):
                raise BatchError("E_FIELD", entity, index)
            if entity == "bookings":
                room = conn.execute("SELECT capacity FROM rooms WHERE id=?", (record["room_id"],)).fetchone()
                if room is None:
                    raise BatchError("E_ROOM", entity, index)
                if record["seats"] > room[0]:
                    raise BatchError("E_CAPACITY", entity, index)
            placeholders = ",".join("?" for _ in columns)
            conn.execute(f"INSERT OR REPLACE INTO {entity} ({','.join(columns)}) VALUES ({placeholders})", tuple(record[column] for column in columns))
            conn.commit()
            result["inserted"][entity] += 1
            inserted += 1
            if inserted == fail_after:
                raise BatchError("E_INJECTED", entity, index)
    return result
