import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pipeline import EventPipeline


ROOT = Path(__file__).resolve().parent


def event(event_id, aggregate_id, sequence, delta):
    return {
        "event_id": event_id,
        "aggregate_id": aggregate_id,
        "sequence": sequence,
        "payload": {"delta": delta},
    }


class CrashOncePipeline(EventPipeline):
    def __init__(self, database_path):
        super().__init__(database_path)
        self.should_crash = True

    def _before_delivery_commit(self, event):
        if self.should_crash:
            self.should_crash = False
            raise RuntimeError("simulated delivery crash")


class PipelineTest(unittest.TestCase):
    def test_duplicates_are_harmless_across_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "state.db"
            first = EventPipeline(database)
            first.process_events([event("e1", "a", 1, 2), event("e1", "a", 1, 2)])
            first.deliver()
            first.close()
            second = EventPipeline(database)
            second.process_events([event("e1", "a", 1, 2)])
            second.deliver()
            count = second.connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
            second.close()
            self.assertEqual(count, 1)

    def test_gap_is_deferred_then_applied_in_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            pipeline = EventPipeline(Path(temporary) / "state.db")
            pipeline.ingest(event("e2", "a", 2, 2))
            pipeline.deliver()
            self.assertEqual(
                pipeline.connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0],
                0,
            )
            pipeline.ingest(event("e1", "a", 1, 1))
            pipeline.deliver()
            sequences = [
                row[0]
                for row in pipeline.connection.execute(
                    "SELECT sequence FROM effects ORDER BY effect_id"
                )
            ]
            pipeline.close()
            self.assertEqual(sequences, [1, 2])

    def test_delivery_crash_recovers_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "state.db"
            crashing = CrashOncePipeline(database)
            crashing.ingest(event("e1", "a", 1, 1))
            with self.assertRaises(RuntimeError):
                crashing.deliver()
            crashing.close()
            recovered = EventPipeline(database)
            recovered.deliver()
            recovered.deliver()
            count = recovered.connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
            recovered.close()
            self.assertEqual(count, 1)

    def test_cli_preserves_jsonl_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "state.db"
            effects = Path(temporary) / "effects.jsonl"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "pipeline.py"),
                    "--db",
                    str(database),
                    "--events",
                    str(ROOT / "events.jsonl"),
                    "--effects",
                    str(effects),
                ],
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            rows = [json.loads(line) for line in effects.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                [(row["aggregate_id"], row["sequence"]) for row in rows],
                [("acct-b", 1), ("acct-a", 1), ("acct-a", 2)],
            )


if __name__ == "__main__":
    unittest.main()
