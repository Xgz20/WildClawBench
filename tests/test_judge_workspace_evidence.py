from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.utils.workspace_evidence import collect_workspace_evidence


class JudgeWorkspaceEvidenceTest(unittest.TestCase):
    def test_declared_then_output_dirs_then_automatic_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project").mkdir()
            (root / "project/fix.py").write_text("declared", encoding="utf-8")
            (root / "results").mkdir()
            (root / "results/answer.md").write_text("result", encoding="utf-8")
            (root / "output").mkdir()
            (root / "output/summary.txt").write_text("output", encoding="utf-8")
            (root / "aaa-temp.html").write_text("temporary", encoding="utf-8")

            evidence = collect_workspace_evidence(
                str(root),
                {
                    "required": [{"path": "project/fix.py", "role": "deliverable"}],
                    "references": [],
                },
            )

        selected = evidence["metadata"]["selected"]
        self.assertEqual(
            [item["path"] for item in selected],
            [
                "project/fix.py",
                "output/summary.txt",
                "results/answer.md",
                "aaa-temp.html",
            ],
        )
        self.assertEqual(selected[0]["selection_reason"], "judge_evidence.required")
        self.assertEqual(selected[1]["priority"], 2)
        self.assertEqual(selected[-1]["selection_reason"], "automatic_discovery")

    def test_output_artifacts_are_not_displaced_by_first_twelve_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(20):
                (root / f"pipl_{index:02d}.html").write_text(
                    f"temporary-{index}", encoding="utf-8"
                )
            (root / "results").mkdir()
            (root / "results/pipl_article13.json").write_text("{}", encoding="utf-8")
            (root / "results/review_note.md").write_text("review", encoding="utf-8")

            evidence = collect_workspace_evidence(str(root))

        paths = [item["path"] for item in evidence["metadata"]["selected"]]
        self.assertEqual(paths[:2], [
            "results/pipl_article13.json",
            "results/review_note.md",
        ])
        self.assertGreater(len(paths), 12)

    def test_truncation_keeps_head_and_tail_and_records_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "results").mkdir()
            content = "H" * 16_000 + "T" * 4_000
            (root / "results/long.md").write_text(content, encoding="utf-8")

            evidence = collect_workspace_evidence(
                str(root), max_chars=10_000, per_file_max_chars=10_000
            )

        selected = evidence["metadata"]["selected"][0]
        self.assertTrue(selected["truncated"])
        self.assertEqual(selected["included_ranges"], [[0, 7_500], [17_500, 20_000]])
        self.assertIn("H" * 100, evidence["text"])
        self.assertIn("T" * 100, evidence["text"])

    def test_manifest_records_missing_and_unsupported_declared_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "results").mkdir()
            (root / "results/deck.pptx").write_bytes(b"not text")

            evidence = collect_workspace_evidence(
                str(root),
                {
                    "required": [
                        {"path": "results/deck.pptx", "role": "deliverable"},
                        {"path": "results/missing.md", "role": "deliverable"},
                    ],
                    "references": [],
                },
            )

        self.assertEqual(
            evidence["metadata"]["missing_required"],
            [{"path": "results/missing.md", "role": "deliverable"}],
        )
        deck = next(
            item for item in evidence["metadata"]["manifest"]
            if item["path"] == "results/deck.pptx"
        )
        self.assertEqual(deck["status"], "omitted")
        self.assertEqual(deck["reason"], "unsupported_text_extension")


if __name__ == "__main__":
    unittest.main()
