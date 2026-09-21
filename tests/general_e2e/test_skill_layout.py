from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eval_general_e2e.layout import inspect_repository_layout
from eval_general_e2e.stages import GENERAL_E2E_SKILLS, get_skill_spec


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_NAMES = (
    "prepare-general-e2e-workspaces",
    "execute-general-e2e",
    "collect-general-e2e",
    "orchestrate-general-e2e",
    "score-general-e2e",
    "report-general-e2e",
    "run-general-e2e",
)


class GeneralE2ESkillLayoutTests(unittest.TestCase):
    def test_locked_registry_has_seven_unique_public_names(self) -> None:
        names = tuple(spec.name for spec in GENERAL_E2E_SKILLS)
        self.assertEqual(names, EXPECTED_NAMES)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(
            get_skill_spec("collect-general-e2e").stages,
            ("collect-evidence",),
        )
        self.assertIn("import-return", get_skill_spec("run-general-e2e").stages)
        self.assertEqual(
            (
                get_skill_spec("prepare-general-e2e-workspaces").version,
                get_skill_spec("prepare-general-e2e-workspaces").implementation_status,
            ),
            ("0.2.0", "operational"),
        )
        self.assertEqual(
            (
                get_skill_spec("execute-general-e2e").version,
                get_skill_spec("execute-general-e2e").implementation_status,
            ),
            ("0.10.4", "operational"),
        )
        self.assertEqual(
            (
                get_skill_spec("collect-general-e2e").version,
                get_skill_spec("collect-general-e2e").implementation_status,
            ),
            ("0.7.1", "operational"),
        )
        self.assertEqual(
            (
                get_skill_spec("orchestrate-general-e2e").version,
                get_skill_spec("orchestrate-general-e2e").implementation_status,
            ),
            ("0.9.2", "operational"),
        )
        self.assertEqual(
            (
                get_skill_spec("score-general-e2e").version,
                get_skill_spec("score-general-e2e").implementation_status,
            ),
            ("0.8.1", "operational"),
        )
        self.assertEqual(
            (
                get_skill_spec("run-general-e2e").version,
                get_skill_spec("run-general-e2e").implementation_status,
            ),
            ("0.5.0", "operational"),
        )
        self.assertEqual(
            (
                get_skill_spec("report-general-e2e").version,
                get_skill_spec("report-general-e2e").implementation_status,
            ),
            ("0.4.0", "operational"),
        )
        self.assertTrue(
            all(
                spec.implementation_status == "operational"
                for spec in GENERAL_E2E_SKILLS
            )
        )

    def test_canonical_metadata_discovery_and_legacy_layout_pass(self) -> None:
        report = inspect_repository_layout(REPO_ROOT)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["expected_skill_count"], 7)
        self.assertTrue(report["legacy_eval_e2e"]["preserved"])
        self.assertEqual(report["shared_components"]["status"], "PASS")
        self.assertEqual(len(report["shared_components"]["components"]), 12)
        self.assertTrue(all(item["valid"] for item in report["skills"]))

    def test_cli_exposes_machine_readable_registry(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "eval_general_e2e", "skills", "--json"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["skill_count"], 7)
        self.assertEqual(
            [item["name"] for item in payload["skills"]],
            list(EXPECTED_NAMES),
        )

    def test_cli_layout_check_is_the_formal_repository_gate(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "eval_general_e2e",
                "check-layout",
                "--repo-root",
                str(REPO_ROOT),
                "--json",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["errors"], [])

    def test_layout_gate_fails_closed_for_an_empty_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = inspect_repository_layout(temp_dir)
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("SKILL_SET_MISMATCH", codes)
        self.assertIn("SKILL_LAYOUT_INVALID", codes)
        self.assertIn("LEGACY_EVAL_E2E_MISSING", codes)

    def test_legacy_eval_e2e_public_modules_still_import(self) -> None:
        import eval_e2e.collect_runs  # noqa: F401
        import eval_e2e.e2e_manifest  # noqa: F401
        import eval_e2e.grade_runs  # noqa: F401
        import eval_e2e.prepare_workspaces  # noqa: F401


if __name__ == "__main__":
    unittest.main()
