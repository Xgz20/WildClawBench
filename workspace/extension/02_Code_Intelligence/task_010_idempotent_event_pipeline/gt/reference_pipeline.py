"""Reference persistent ordered event pipeline."""

import argparse
import json
from pathlib import Path
import sqlite3


class PipelineError(ValueError):
    pass


def _validate_event(event):
    if not isinstance(event, dict):
        raise PipelineError("event must be an object")
    for key in ("event_id", "aggregate_id"):
        if not isinstance(event.get(key), str) or not event[key]:
            raise PipelineError(f"{key} must be a non-empty string")
    sequence = event.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise PipelineError("sequence must be a positive integer")
    if "payload" not in event:
        raise PipelineError("payload is required")


class EventPipeline:
    def __init__(self, database_path):
        self.connection = sqlite3.connect(database_path)
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS inbox (
                event_id TEXT PRIMARY KEY,
                aggregate_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                applied INTEGER NOT NULL DEFAULT 0,
                UNIQUE(aggregate_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS aggregate_state (
                aggregate_id TEXT PRIMARY KEY,
                last_sequence INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                aggregate_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS effects (
                effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                aggregate_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_json TEXT NOT NULL
            );
            """
        )

    def close(self):
        self.connection.close()

    def _before_delivery_commit(self, event):
        """Test hook called before an effect transaction commits."""

    def _apply_ready(self, aggregate_id):
        row = self.connection.execute(
            "SELECT last_sequence FROM aggregate_state WHERE aggregate_id = ?",
            (aggregate_id,),
        ).fetchone()
        expected = (row[0] if row else 0) + 1
        while True:
            pending = self.connection.execute(
                "SELECT event_id, sequence, event_json FROM inbox "
                "WHERE aggregate_id = ? AND sequence = ? AND applied = 0",
                (aggregate_id, expected),
            ).fetchone()
            if pending is None:
                break
            event_id, sequence, event_json = pending
            self.connection.execute(
                "INSERT INTO aggregate_state(aggregate_id, last_sequence) VALUES (?, ?) "
                "ON CONFLICT(aggregate_id) DO UPDATE SET last_sequence = excluded.last_sequence",
                (aggregate_id, sequence),
            )
            self.connection.execute(
                "UPDATE inbox SET applied = 1 WHERE event_id = ?", (event_id,)
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO outbox(event_id, aggregate_id, sequence, event_json) "
                "VALUES (?, ?, ?, ?)",
                (event_id, aggregate_id, sequence, event_json),
            )
            expected += 1

    def ingest(self, event):
        _validate_event(event)
        event_json = json.dumps(event, sort_keys=True, separators=(",", ":"))
        with self.connection:
            existing = self.connection.execute(
                "SELECT event_json FROM inbox WHERE event_id = ?", (event["event_id"],)
            ).fetchone()
            if existing is not None:
                if existing[0] != event_json:
                    raise PipelineError("event_id was reused with different content")
                return
            try:
                self.connection.execute(
                    "INSERT INTO inbox(event_id, aggregate_id, sequence, event_json) VALUES (?, ?, ?, ?)",
                    (
                        event["event_id"],
                        event["aggregate_id"],
                        event["sequence"],
                        event_json,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise PipelineError("aggregate sequence already has another event") from exc
            self._apply_ready(event["aggregate_id"])

    def process_events(self, events):
        for event in events:
            self.ingest(event)

    def deliver(self):
        while True:
            row = self.connection.execute(
                "SELECT event_id, aggregate_id, sequence, event_json FROM outbox "
                "WHERE delivered = 0 ORDER BY effect_id LIMIT 1"
            ).fetchone()
            if row is None:
                return
            event_id, aggregate_id, sequence, event_json = row
            event = json.loads(event_json)
            with self.connection:
                self.connection.execute(
                    "INSERT OR IGNORE INTO effects(event_id, aggregate_id, sequence, event_json) "
                    "VALUES (?, ?, ?, ?)",
                    (event_id, aggregate_id, sequence, event_json),
                )
                self._before_delivery_commit(event)
                self.connection.execute(
                    "UPDATE outbox SET delivered = 1 WHERE event_id = ?", (event_id,)
                )

    def export_effects(self, path):
        rows = self.connection.execute(
            "SELECT event_json FROM effects ORDER BY effect_id"
        ).fetchall()
        Path(path).write_text("".join(row[0] + "\n" for row in rows), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--effects", required=True)
    args = parser.parse_args(argv)
    try:
        events = [
            json.loads(line)
            for line in Path(args.events).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        pipeline = EventPipeline(args.db)
        try:
            pipeline.process_events(events)
            pipeline.deliver()
            pipeline.export_effects(args.effects)
        finally:
            pipeline.close()
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        parser.exit(2, f"pipeline failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
