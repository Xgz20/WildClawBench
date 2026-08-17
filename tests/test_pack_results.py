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
        node_modules = results / "node_modules" / "demo-package"
        node_modules.mkdir(parents=True)
        (run / "score.json").write_text('{"overall_score": 1}', encoding="utf-8")
        (results / "small.txt").write_text("small", encoding="utf-8")
        (results / "large.bin").write_bytes(b"x" * (1024 * 1024 + 1))
        (node_modules / "index.js").write_text("module.exports = {}", encoding="utf-8")
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
            self.assertFalse(any("/node_modules/" in name for name in names))

    def test_include_node_modules_exports_dependency_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = self._fixture(root)
            out = root / "out"

            completed = self._run(scope, out, "--include-node-modules")

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            with tarfile.open(next(out.glob("eval_out_results_*.tar.gz"))) as archive:
                names = archive.getnames()
            self.assertTrue(any(name.endswith("/node_modules/demo-package/index.js") for name in names))

    def test_combined_archive_contains_light_and_filtered_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = self._fixture(root)
            out = root / "out"

            completed = self._run(
                scope, out, "--combined", "--include-node-modules", "--max-result-file-mb", "1"
            )

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            combined_archives = list(out.glob("eval_out_combined_*.tar.gz"))
            self.assertEqual(len(combined_archives), 1)
            self.assertEqual(list(out.glob("eval_out_light_*.tar.gz")), [])
            self.assertEqual(list(out.glob("eval_out_results_*.tar.gz")), [])
            with tarfile.open(combined_archives[0]) as archive:
                names = archive.getnames()
            self.assertTrue(any(name.endswith("/score.json") for name in names))
            self.assertTrue(any(name.endswith("/small.txt") for name in names))
            self.assertTrue(any(name.endswith("/node_modules/demo-package/index.js") for name in names))
            self.assertFalse(any(name.endswith("/large.bin") for name in names))

    def test_combined_rejects_no_results_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scope = self._fixture(Path(tmp))
            completed = self._run(scope, Path(tmp) / "out", "--combined", "--no-results")

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("不能与 --no-results 同时使用", completed.stdout)

    def test_only_results_creates_only_results_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = self._fixture(root)
            out = root / "out"

            completed = self._run(scope, out, "--only-results", "--max-result-file-mb", "1")

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            self.assertEqual(list(out.glob("eval_out_light_*.tar.gz")), [])
            results_archives = list(out.glob("eval_out_results_*.tar.gz"))
            self.assertEqual(len(results_archives), 1)
            with tarfile.open(results_archives[0]) as archive:
                names = archive.getnames()
            self.assertTrue(any(name.endswith("/small.txt") for name in names))
            self.assertFalse(any(name.endswith("/large.bin") for name in names))

    def test_only_results_rejects_combined_and_no_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scope = self._fixture(Path(tmp))
            for conflicting_args in (("--combined",), ("--no-results",)):
                with self.subTest(conflicting_args=conflicting_args):
                    completed = self._run(
                        scope, Path(tmp) / ("out-" + conflicting_args[0][2:]),
                        "--only-results", *conflicting_args,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn("--only-results 不能与", completed.stdout)

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
