"""Persistent event worker with a JSONL command-line interface."""

import argparse
import json
from pathlib import Path
import sqlite3


class PipelineError(ValueError):
    pass


class EventPipeline:
    def __init__(self, database_path):
        self.connection = sqlite3.connect(database_path)
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS aggregate_state (
                aggregate_id TEXT PRIMARY KEY,
                last_sequence INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS effects (
                effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
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

    def ingest(self, event):
        aggregate_id = event["aggregate_id"]
        sequence = event["sequence"]
        row = self.connection.execute(
            "SELECT last_sequence FROM aggregate_state WHERE aggregate_id = ?",
            (aggregate_id,),
        ).fetchone()
        last_sequence = row[0] if row else 0
        if sequence <= last_sequence:
            return
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO aggregate_state VALUES (?, ?)",
                (aggregate_id, sequence),
            )
            self.connection.execute(
                "INSERT INTO effects(event_id, aggregate_id, sequence, event_json) VALUES (?, ?, ?, ?)",
                (event["event_id"], aggregate_id, sequence, json.dumps(event, sort_keys=True)),
            )

    def process_events(self, events):
        for event in events:
            self.ingest(event)

    def deliver(self):
        return None

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
