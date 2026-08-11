from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eval_e2e.e2e_manifest import (
    HARNESS_NAME,
    Manifest,
    RunEntry,
    load_manifest,
    resolve_project_dir,
    resolve_repo_path,
    save_manifest,
)


def _entry(**over) -> RunEntry:
    base = dict(
        task_id="02_Code_Intelligence_task_001_temperature_cli_fix",
        category="02_Code_Intelligence",
        task_file="tasks/extension/02_Code_Intelligence/t.md",
        workspace_src="workspace/extension/02_Code_Intelligence/task_001",
        project_dir="xopglm52/02_Code_Intelligence_task_001_temperature_cli_fix/tmp_workspace",
        model="xopglm52",
        reasoning_effort="medium",
        prompt_rewritten=True,
        prompt_rewrite_map={"/tmp_workspace": "/abs/x/tmp_workspace"},
        status="pending",
    )
    base.update(over)
    return RunEntry(**base)


class ManifestTest(unittest.TestCase):
    def test_harness_name_is_astroncode_desktop(self) -> None:
        self.assertEqual(HARNESS_NAME, "astroncode-desktop")

    def test_roundtrip_preserves_all_fields(self) -> None:
        manifest = Manifest(
            e2e_root="eval_out_e2e", created_at="2026-08-10T12:00:00+08:00",
            runs=[_entry()],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            save_manifest(manifest, path)
            loaded = load_manifest(path)
        self.assertEqual(loaded.to_dict(), manifest.to_dict())
        self.assertEqual(loaded.runs[0].prompt_rewrite_map["/tmp_workspace"],
                         "/abs/x/tmp_workspace")

    def test_manifest_stores_relative_project_dir(self) -> None:
        """project_dir 必须是相对路径，保证可移植性。"""
        manifest = Manifest(e2e_root="eval_out_e2e", created_at="x", runs=[_entry()])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            save_manifest(manifest, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(Path(raw["runs"][0]["project_dir"]).is_absolute())

    def test_resolve_project_dir_rebases_on_new_root(self) -> None:
        """换一台机器（换 e2e_root）后路径应重新解析到新根下。"""
        entry = _entry()
        got = resolve_project_dir(entry, Path("/data1/out"))
        self.assertEqual(
            got,
            Path("/data1/out/xopglm52/"
                 "02_Code_Intelligence_task_001_temperature_cli_fix/tmp_workspace"),
        )
        self.assertTrue(got.is_absolute())

    def test_resolve_repo_path_joins_repo_root(self) -> None:
        got = resolve_repo_path("workspace/extension/x", Path("/repo"))
        self.assertEqual(got, Path("/repo/workspace/extension/x"))

    def test_resolve_repo_path_keeps_absolute_input(self) -> None:
        got = resolve_repo_path("/already/abs", Path("/repo"))
        self.assertEqual(got, Path("/already/abs"))


if __name__ == "__main__":
    unittest.main()
