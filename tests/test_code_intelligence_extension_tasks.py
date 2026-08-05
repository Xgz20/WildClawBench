"""Executable checks for the seven remaining Code Intelligence extension tasks."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.utils.task_parser import parse_task_md  # noqa: E402
from tools.validate_extension_tasks import validate_repository  # noqa: E402


CATEGORY = "02_Code_Intelligence"
TASKS = {
    "02_Code_Intelligence_task_003_pagination_boundary_fix": (
        "02_Code_Intelligence_task_003_pagination_boundary_fix.md",
        "task_003_pagination_boundary_fix",
    ),
    "02_Code_Intelligence_task_004_csv_dialect_fix": (
        "02_Code_Intelligence_task_004_csv_dialect_fix.md",
        "task_004_csv_dialect_fix",
    ),
    "02_Code_Intelligence_task_005_sql_double_count_fix": (
        "02_Code_Intelligence_task_005_sql_double_count_fix.md",
        "task_005_sql_double_count_fix",
    ),
    "02_Code_Intelligence_task_006_tomllib_reader": (
        "02_Code_Intelligence_task_006_tomllib_reader.md",
        "task_006_tomllib_reader",
    ),
    "02_Code_Intelligence_task_007_async_cache_singleflight": (
        "02_Code_Intelligence_task_007_async_cache_singleflight.md",
        "task_007_async_cache_singleflight",
    ),
    "02_Code_Intelligence_task_008_config_migrator": (
        "02_Code_Intelligence_task_008_config_migrator.md",
        "task_008_config_migrator",
    ),
    "02_Code_Intelligence_task_010_idempotent_event_pipeline": (
        "02_Code_Intelligence_task_010_idempotent_event_pipeline.md",
        "task_010_idempotent_event_pipeline",
    ),
}

EXPECTED_METADATA = {
    "02_Code_Intelligence_task_003_pagination_boundary_fix": ("L1", "automated"),
    "02_Code_Intelligence_task_004_csv_dialect_fix": ("L2", "automated"),
    "02_Code_Intelligence_task_005_sql_double_count_fix": ("L2", "automated"),
    "02_Code_Intelligence_task_006_tomllib_reader": ("L3", "automated"),
    "02_Code_Intelligence_task_007_async_cache_singleflight": ("L3", "automated"),
    "02_Code_Intelligence_task_008_config_migrator": ("L3", "automated"),
    "02_Code_Intelligence_task_010_idempotent_event_pipeline": ("L4", "hybrid"),
}

EXPECTED_JUDGE_WEIGHTS = {
    "02_Code_Intelligence_task_003_pagination_boundary_fix": {},
    "02_Code_Intelligence_task_004_csv_dialect_fix": {},
    "02_Code_Intelligence_task_005_sql_double_count_fix": {},
    "02_Code_Intelligence_task_006_tomllib_reader": {},
    "02_Code_Intelligence_task_007_async_cache_singleflight": {},
    "02_Code_Intelligence_task_008_config_migrator": {},
    "02_Code_Intelligence_task_010_idempotent_event_pipeline": {
        "migration_plan_quality": 0.5,
        "rollback_plan_quality": 0.5,
    },
}

REFERENCE_FILES = {
    "02_Code_Intelligence_task_003_pagination_boundary_fix": (
        "reference_pagination.py",
        "project/pagination.py",
    ),
    "02_Code_Intelligence_task_004_csv_dialect_fix": (
        "reference_csv_parser.py",
        "project/csv_parser.py",
    ),
    "02_Code_Intelligence_task_005_sql_double_count_fix": (
        "reference_report.sql",
        "project/report.sql",
    ),
    "02_Code_Intelligence_task_007_async_cache_singleflight": (
        "reference_cache.py",
        "project/cache.py",
    ),
    "02_Code_Intelligence_task_008_config_migrator": (
        "reference_migrate.py",
        "project/migrate.py",
    ),
    "02_Code_Intelligence_task_010_idempotent_event_pipeline": (
        "reference_pipeline.py",
        "project/pipeline.py",
    ),
}

SOURCE_TARGETS = {
    task_id: destination for task_id, (_, destination) in REFERENCE_FILES.items()
}
RUNTIME_URL = "https://docs.python.org/3.12/library/tomllib.html"


def task_path(task_id: str) -> Path:
    return REPO_ROOT / "tasks" / "extension" / CATEGORY / TASKS[task_id][0]


def workspace_path(task_id: str) -> Path:
    return REPO_ROOT / "workspace" / "extension" / CATEGORY / TASKS[task_id][1]


def metadata(task_id: str) -> dict:
    text = task_path(task_id).read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        raise AssertionError(f"frontmatter missing for {task_id}")
    result = yaml.safe_load(match.group(1))
    if not isinstance(result, dict):
        raise AssertionError(f"frontmatter is not a mapping for {task_id}")
    return result


def copy_workspace(task_id: str, destination: Path) -> None:
    source = workspace_path(task_id)
    shutil.copytree(source / "exec", destination, dirs_exist_ok=True)
    shutil.copytree(source / "gt", destination / "gt")


def load_grader(task_id: str):
    parsed = parse_task_md(task_path(task_id))
    namespace: dict = {}
    exec(compile(parsed["automated_checks"], str(task_path(task_id)), "exec"), namespace)
    grade = namespace.get("grade")
    if not callable(grade):
        raise AssertionError(f"grade() missing for {task_id}")
    return grade


def automatic_score(scores: dict) -> float:
    values = [
        float(value)
        for key, value in scores.items()
        if key != "overall_score"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ]
    return sum(values) / len(values) if values else 0.0


def install_reference(task_id: str, root: Path) -> None:
    if task_id == "02_Code_Intelligence_task_006_tomllib_reader":
        results = root / "results"
        results.mkdir()
        shutil.copy2(root / "gt" / "reference_pyproject_reader.py", results / "pyproject_reader.py")
        (results / "source.json").write_text(
            json.dumps(
                {
                    "url": RUNTIME_URL,
                    "version": "3.12",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return

    reference, destination = REFERENCE_FILES[task_id]
    shutil.copy2(root / "gt" / reference, root / destination)
    if task_id == "02_Code_Intelligence_task_005_sql_double_count_fix":
        results = root / "results"
        results.mkdir()
        with (results / "report.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["property_id", "property_name", "lease_count", "visit_count"])
            writer.writerows(
                [
                    [1, "Harbor House", 2, 3],
                    [2, "Maple Court", 1, 0],
                    [3, "Pine Studios", 0, 1],
                    [4, "Riverside Empty", 0, 0],
                ]
            )
    elif task_id == "02_Code_Intelligence_task_010_idempotent_event_pipeline":
        results = root / "results"
        results.mkdir()
        (results / "migration.md").write_text(
            "Deploy schema first, backfill inbox, aggregate state and outbox identifiers, then canary new workers. "
            "Keep old workers read-only during the compatibility window. Monitor duplicate conflicts, sequence gaps, "
            "pending outbox age and effect counts; pause on divergence.\n",
            encoding="utf-8",
        )
        (results / "rollback.md").write_text(
            "Rollback on count divergence or outbox lag. Stop consumers, retain inbox, aggregate state, outbox and "
            "effects, and drain no rows with an incompatible worker. Verify committed effect IDs, pending gaps and "
            "state sequences before resuming the compatible version.\n",
            encoding="utf-8",
        )


def install_partial(task_id: str, root: Path) -> None:
    if task_id == "02_Code_Intelligence_task_006_tomllib_reader":
        results = root / "results"
        results.mkdir()
        shutil.copy2(root / "gt" / "reference_pyproject_reader.py", results / "pyproject_reader.py")
    elif task_id == "02_Code_Intelligence_task_010_idempotent_event_pipeline":
        results = root / "results"
        results.mkdir()
        (results / "migration.md").write_text("Deploy gradually and observe.\n", encoding="utf-8")
        (results / "rollback.md").write_text("Restore the prior version.\n", encoding="utf-8")


def make_zero(task_id: str, root: Path) -> None:
    if task_id == "02_Code_Intelligence_task_006_tomllib_reader":
        return
    (root / SOURCE_TARGETS[task_id]).unlink()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CodeIntelligenceExtensionTaskTest(unittest.TestCase):
    def test_metadata_matches_design_matrix(self):
        for task_id, (difficulty, grading_type) in EXPECTED_METADATA.items():
            with self.subTest(task_id=task_id):
                task_metadata = metadata(task_id)
                self.assertEqual(task_metadata["difficulty"], difficulty)
                self.assertEqual(task_metadata["grading_type"], grading_type)

    def test_static_validator_accepts_current_repository(self):
        self.assertEqual(validate_repository(REPO_ROOT, allow_incomplete=True), [])
        strict = validate_repository(REPO_ROOT)
        self.assertEqual([issue for issue in strict if issue.code != "task.missing"], [])
        registry = yaml.safe_load(
            (REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8")
        )
        registered_ids = {item["task_id"] for item in registry["tasks"]}
        present_ids = {
            path.stem for path in (REPO_ROOT / "tasks/extension").glob("*/*.md")
        }
        self.assertEqual(
            sum(issue.code == "task.missing" for issue in strict),
            len(registered_ids - present_ids),
        )

    def test_automated_graders_have_full_partial_and_zero_tiers(self):
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                grade = load_grader(task_id)
                tier_scores = {}
                for tier in ("full", "partial", "zero"):
                    with tempfile.TemporaryDirectory(prefix="code-intelligence-grade-") as temporary:
                        root = Path(temporary)
                        copy_workspace(task_id, root)
                        if tier == "full":
                            install_reference(task_id, root)
                        elif tier == "partial":
                            install_partial(task_id, root)
                        else:
                            make_zero(task_id, root)
                        result = grade(transcript=[], workspace_path=str(root))
                        self.assertIsInstance(result, dict)
                        tier_scores[tier] = automatic_score(result)
                self.assertAlmostEqual(tier_scores["full"], 1.0, places=6)
                self.assertGreater(tier_scores["partial"], 0.0)
                self.assertLess(tier_scores["partial"], 1.0)
                self.assertAlmostEqual(tier_scores["zero"], 0.0, places=6)

    def test_judge_rubrics_use_five_bands_and_normalized_weights(self):
        required = {"1.0", "0.75", "0.5", "0.25", "0.0"}
        pattern = re.compile(r"\*\*Score\s+(1\.0|0\.75|0\.5|0\.25|0\.0)\*\*:")
        for task_id, wanted in EXPECTED_JUDGE_WEIGHTS.items():
            with self.subTest(task_id=task_id):
                criteria = parse_task_md(task_path(task_id))["rubric_criteria"]
                actual = {item["key"]: item["weight"] for item in criteria}
                self.assertEqual(set(actual), set(wanted))
                for key, weight in wanted.items():
                    self.assertAlmostEqual(actual[key], weight, places=6)
                if actual:
                    self.assertAlmostEqual(sum(actual.values()), 1.0, places=6)
                for criterion in criteria:
                    self.assertEqual(set(pattern.findall(criterion["rubric"])), required)

    def test_capability_mapping_exactly_matches_checkpoints(self):
        mapping = yaml.safe_load(
            (REPO_ROOT / "tools/report/data/checkpoint_capability_map7.yaml").read_text(
                encoding="utf-8"
            )
        )
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                parsed = parse_task_md(task_path(task_id))
                source = parsed["automated_checks"]
                auto_keys = {
                    key
                    for key in re.findall(r'["\']([a-z][a-z0-9_]+)["\']', source)
                    if key in mapping[task_id] or f"automated.{key}" in mapping[task_id]
                }
                judge_keys = {item["key"] for item in parsed["rubric_criteria"]}
                if parsed["grading_type"] == "hybrid":
                    wanted = {f"automated.{key}" for key in auto_keys} | {
                        f"llm_judge.{key}" for key in judge_keys
                    }
                else:
                    wanted = auto_keys
                self.assertEqual(set(mapping[task_id]), wanted)
                capabilities = set()
                for labels in mapping[task_id].values():
                    self.assertGreaterEqual(len(labels), 1)
                    self.assertLessEqual(len(labels), 2)
                    capabilities.update(labels)
                self.assertGreaterEqual(len(capabilities), 2)
                self.assertLessEqual(len(capabilities), 4)

    def test_attachment_hash_size_and_ground_truth_consistency(self):
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                root = workspace_path(task_id)
                expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
                attachments = {
                    path.relative_to(root / "exec").as_posix(): path
                    for path in (root / "exec").rglob("*")
                    if path.is_file() and path.name != ".gitkeep"
                }
                self.assertEqual(set(attachments), set(expected["exec_file_sha256"]))
                total_size = 0
                for relative, path in attachments.items():
                    total_size += path.stat().st_size
                    self.assertFalse(path.is_symlink())
                    self.assertEqual(
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                        expected["exec_file_sha256"][relative],
                    )
                    self.assertNotIn(path.suffix.lower(), {".html", ".htm", ".mhtml", ".pdf"})
                self.assertLessEqual(total_size, metadata(task_id)["attachment_size_limit_mb"] * 1024 * 1024)

    def test_runtime_source_matches_registry_and_prompt(self):
        registry = yaml.safe_load(
            (REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8")
        )
        records = {item["task_id"]: item for item in registry["tasks"] if item["task_id"] in TASKS}
        self.assertEqual(set(records), set(TASKS))
        for task_id, record in records.items():
            urls = {item["url"] for item in record["runtime_sources"]}
            if task_id == "02_Code_Intelligence_task_006_tomllib_reader":
                self.assertEqual(urls, {RUNTIME_URL})
                self.assertIn(RUNTIME_URL, parse_task_md(task_path(task_id))["prompt"])
            else:
                self.assertEqual(urls, set())

    @unittest.skipUnless(
        os.environ.get("WILDCLAW_RUN_NETWORK_TESTS") == "1",
        "set WILDCLAW_RUN_NETWORK_TESTS=1 for host-side URL checks",
    )
    def test_fixed_runtime_url_is_reachable_from_host(self):
        completed = subprocess.run(
            [
                "/usr/bin/curl",
                "--location",
                "--silent",
                "--show-error",
                "--output",
                "/dev/null",
                "--write-out",
                "%{http_code}",
                "--retry",
                "3",
                "--retry-all-errors",
                "--retry-delay",
                "2",
                "--connect-timeout",
                "20",
                "--max-time",
                "60",
                "--user-agent",
                "WildClawBench/1.0 evaluation@example.com",
                RUNTIME_URL,
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(completed.stdout.strip().isdigit(), completed.stdout)
        self.assertGreaterEqual(int(completed.stdout.strip()), 200)
        self.assertLess(int(completed.stdout.strip()), 400)

    def test_report_and_low_score_tools_discover_all_tasks(self):
        report = load_module(
            "code_intelligence_report",
            REPO_ROOT / "tools/report/scripts/generate_eval_report.py",
        )
        manifest = load_module(
            "code_intelligence_manifest",
            REPO_ROOT
            / "tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py",
        )
        task_root = REPO_ROOT / "tasks"
        all_metadata = report.load_all_task_meta(task_root)
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                self.assertIn(task_id, all_metadata)
                self.assertEqual(all_metadata[task_id]["suite"], CATEGORY)
                located = manifest.locate_task_file(task_root, CATEGORY, task_id)
                self.assertEqual(Path(located), task_path(task_id))

    def test_prompts_are_user_facing_and_output_paths_are_bounded(self):
        forbidden = ("评分点", "能力维度", "LLM Judge", "Auto评分", "评测框架")
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                prompt = parse_task_md(task_path(task_id))["prompt"]
                self.assertFalse(any(term in prompt for term in forbidden))
                self.assertNotIn("/tmp_workspace/result/", prompt)
                paths = re.findall(r"/tmp_workspace/[^\s`，。；：,;]+", prompt)
                for path in paths:
                    if "/results/" in path:
                        self.assertTrue(path.startswith("/tmp_workspace/results/"))


if __name__ == "__main__":
    unittest.main()
