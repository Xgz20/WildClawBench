from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from eval_e2e.collect_runs import (
    collect_one,
    make_run_slug,
    run_dir_for,
    snapshot_project,
)
from eval_e2e.e2e_manifest import RunEntry

NOW = datetime(2026, 8, 10, 16, 34)


def _entry() -> RunEntry:
    return RunEntry(
        task_id="02_Code_task_001", category="02_Code",
        task_file="tasks/x.md", workspace_src="workspace/02_Code/task_001",
        project_dir="xopglm52/02_Code_task_001/tmp_workspace",
        model="xopglm52", reasoning_effort="medium",
        prompt_rewritten=True, prompt_rewrite_map={}, status="pending",
    )


def _write_trace(root: Path, name: str, cwd: str, ts: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    rows = [
        {"timestamp": ts, "type": "session_meta", "payload": {"cwd": cwd}},
        {"type": "function_call", "payload": {"name": "shell"}},
        {"type": "token_count", "payload": {"total_token_usage": {
            "input_tokens": 10, "output_tokens": 2,
            "cached_input_tokens": 1, "total_tokens": 12}}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


class RunDirTest(unittest.TestCase):
    def test_layout_matches_cli_side_structure(self) -> None:
        got = run_dir_for(Path("/out"), _entry(), "slug1", "round-1")
        self.assertEqual(
            got,
            Path("/out/round-1/xopglm52/astroncode-desktop/02_Code/"
                 "02_Code_task_001/slug1"),
        )

    def test_slug_contains_model_and_timestamp(self) -> None:
        slug = make_run_slug(_entry(), NOW)
        self.assertTrue(slug.startswith("xopglm52_20260810_1634_"))
        self.assertEqual(len(slug.rsplit("_", 1)[-1]), 6)


class SnapshotTest(unittest.TestCase):
    def test_copies_project_files_into_task_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "tmp_workspace" / "project"
            proj.mkdir(parents=True)
            (proj / "converter.py").write_text("y = 2\n", encoding="utf-8")
            run_dir = root / "run"
            run_dir.mkdir()
            snapshot_project(root / "tmp_workspace", run_dir)
            self.assertTrue((run_dir / "task_output" / "project" / "converter.py").is_file())


class CollectOneTest(unittest.TestCase):
    def _setup(self, tmp: str):
        root = Path(tmp)
        e2e_root = root / "e2e"
        entry = _entry()
        proj = e2e_root / entry.project_dir
        (proj / "project").mkdir(parents=True)
        (proj / "project" / "converter.py").write_text("z = 3\n", encoding="utf-8")
        return root, e2e_root, entry, proj

    def test_writes_chat_usage_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, entry, proj = self._setup(tmp)
            trace_root = root / "sessions"
            _write_trace(trace_root, "hit.jsonl", str(proj), "2026-08-10T12:05:00Z")
            got = collect_one(entry, e2e_root, root / "out", trace_root, NOW, "round-1")
            run_dir = Path(got["run_dir"])
            usage = json.loads((run_dir / "usage.json").read_text(encoding="utf-8"))
            self.assertEqual(got["status"], "collected")
            self.assertTrue((run_dir / "chat.jsonl").is_file())
            self.assertTrue((run_dir / "task_output" / "project" / "converter.py").is_file())
            self.assertEqual(usage["tool_calls"], 1)
            self.assertEqual(usage["total_tokens"], 12)

    def test_records_trace_missing_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, entry, _ = self._setup(tmp)
            trace_root = root / "sessions"
            trace_root.mkdir()
            got = collect_one(entry, e2e_root, root / "out", trace_root, NOW, "round-1")
            run_dir = Path(got["run_dir"])
            status = json.loads(
                (run_dir / "execution_status.json").read_text(encoding="utf-8"))
            self.assertEqual(got["status"], "trace_missing")
            self.assertEqual(status["status"], "trace_missing")
            self.assertFalse((run_dir / "chat.jsonl").exists())

    def test_persists_prompt_rewrite_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, entry, proj = self._setup(tmp)
            entry.prompt_rewrite_map = {"/tmp_workspace": str(proj)}
            trace_root = root / "sessions"
            _write_trace(trace_root, "h.jsonl", str(proj), "2026-08-10T12:05:00Z")
            got = collect_one(entry, e2e_root, root / "out", trace_root, NOW, "round-1")
            saved = json.loads((Path(got["run_dir"]) / "manifest_entry.json")
                               .read_text(encoding="utf-8"))
            self.assertTrue(saved["prompt_rewritten"])
            self.assertEqual(saved["prompt_rewrite_map"]["/tmp_workspace"], str(proj))


if __name__ == "__main__":
    unittest.main()
