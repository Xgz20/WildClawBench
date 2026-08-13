from __future__ import annotations

import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "script/pack-results.sh"


class PackResultsTest(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        scope = root / "round1"
        run = scope / "model" / "task" / "run"
        results = run / "task_output" / "workspace" / "results"
        results.mkdir(parents=True)
        (run / "score.json").write_text('{"overall_score": 1}', encoding="utf-8")
        (results / "small.txt").write_text("small", encoding="utf-8")
        (results / "large.bin").write_bytes(b"x" * (1024 * 1024 + 1))
        return scope

    def _run(self, scope: Path, out: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), "--scope", str(scope), "--out", str(out), *args],
            capture_output=True,
            text=True,
        )

    def test_max_result_file_mb_excludes_only_oversized_delivery_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = self._fixture(root)
            out = root / "out"

            completed = self._run(scope, out, "--max-result-file-mb", "1")

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            results_archive = next(out.glob("eval_out_results_*.tar.gz"))
            light_archive = next(out.glob("eval_out_light_*.tar.gz"))
            with tarfile.open(results_archive) as archive:
                names = archive.getnames()
            self.assertTrue(any(name.endswith("/small.txt") for name in names))
            self.assertFalse(any(name.endswith("/large.bin") for name in names))
            with tarfile.open(light_archive) as archive:
                light_names = archive.getnames()
            self.assertTrue(any(name.endswith("/score.json") for name in light_names))
            self.assertIn("过滤 1 个超过 1 MiB 的文件", completed.stdout)

    def test_default_keeps_all_result_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = self._fixture(root)
            out = root / "out"

            completed = self._run(scope, out)

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            with tarfile.open(next(out.glob("eval_out_results_*.tar.gz"))) as archive:
                names = archive.getnames()
            self.assertTrue(any(name.endswith("/small.txt") for name in names))
            self.assertTrue(any(name.endswith("/large.bin") for name in names))

    def test_rejects_non_positive_or_non_integer_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scope = self._fixture(Path(tmp))
            for value in ("0", "-1", "1.5", "invalid"):
                with self.subTest(value=value):
                    completed = self._run(scope, Path(tmp) / "out", "--max-result-file-mb", value)
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn("--max-result-file-mb 必须是正整数", completed.stdout)

    def test_dry_run_reports_oversized_files_without_archiving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = self._fixture(root)
            out = root / "out"

            completed = self._run(
                scope, out, "--max-result-file-mb", "1", "--dry-run"
            )

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            self.assertIn("预计过滤 1 个超过 1 MiB 的 results 文件", completed.stdout)
            self.assertEqual(list(out.glob("*.tar.gz")), [])

    def test_no_results_still_skips_results_archive_when_limit_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = self._fixture(root)
            out = root / "out"

            completed = self._run(
                scope, out, "--max-result-file-mb", "1", "--no-results"
            )

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            self.assertEqual(list(out.glob("eval_out_results_*.tar.gz")), [])
            self.assertEqual(len(list(out.glob("eval_out_light_*.tar.gz"))), 1)


if __name__ == "__main__":
    unittest.main()
