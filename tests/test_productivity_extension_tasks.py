"""Executable checks for the seven remaining Productivity Flow tasks."""

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


CATEGORY = "01_Productivity_Flow"
TASKS = {
    "01_Productivity_Flow_task_003_retro_agenda": "01_Productivity_Flow_task_003_retro_agenda.md",
    "01_Productivity_Flow_task_004_timezone_scheduler": "01_Productivity_Flow_task_004_timezone_scheduler.md",
    "01_Productivity_Flow_task_005_support_handoff": "01_Productivity_Flow_task_005_support_handoff.md",
    "01_Productivity_Flow_task_007_sec_filing_preread": "01_Productivity_Flow_task_007_sec_filing_preread.md",
    "01_Productivity_Flow_task_008_paper_reading_pack": "01_Productivity_Flow_task_008_paper_reading_pack.md",
    "01_Productivity_Flow_task_009_action_reconciliation": "01_Productivity_Flow_task_009_action_reconciliation.md",
    "01_Productivity_Flow_task_010_launch_program_pack": "01_Productivity_Flow_task_010_launch_program_pack.md",
}
AUTO_TASK_IDS = tuple(task_id for task_id in TASKS if "task_003_" not in task_id)
EXPECTED_URLS = {
    "https://www.sec.gov/Archives/edgar/data/789019/000095017023035122/msft-20230630.htm",
    "https://arxiv.org/abs/1706.03762v7",
}
EXPECTED_JUDGE_WEIGHTS = {
    "01_Productivity_Flow_task_003_retro_agenda": {
        "fixed_context_coverage": 0.25,
        "agenda_timing": 0.25,
        "blameless_action_orientation": 0.30,
        "invitation_quality": 0.20,
    },
    "01_Productivity_Flow_task_004_timezone_scheduler": {},
    "01_Productivity_Flow_task_005_support_handoff": {"handoff_note_quality": 1.0},
    "01_Productivity_Flow_task_007_sec_filing_preread": {"preread_quality": 1.0},
    "01_Productivity_Flow_task_008_paper_reading_pack": {"reading_pack_quality": 1.0},
    "01_Productivity_Flow_task_009_action_reconciliation": {
        "handoff_and_uncertainty_quality": 1.0
    },
    "01_Productivity_Flow_task_010_launch_program_pack": {
        "program_plan_quality": 0.5,
        "risk_rollback_and_comms": 0.5,
    },
}
EXPECTED_METADATA = {
    "01_Productivity_Flow_task_003_retro_agenda": ("L1", "llm_judge"),
    "01_Productivity_Flow_task_004_timezone_scheduler": ("L2", "automated"),
    "01_Productivity_Flow_task_005_support_handoff": ("L2", "hybrid"),
    "01_Productivity_Flow_task_007_sec_filing_preread": ("L3", "hybrid"),
    "01_Productivity_Flow_task_008_paper_reading_pack": ("L3", "hybrid"),
    "01_Productivity_Flow_task_009_action_reconciliation": ("L3", "hybrid"),
    "01_Productivity_Flow_task_010_launch_program_pack": ("L4", "hybrid"),
}


def task_path(task_id: str) -> Path:
    return REPO_ROOT / "tasks" / "extension" / CATEGORY / TASKS[task_id]


def task_metadata(task_id: str) -> dict:
    text = task_path(task_id).read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        raise AssertionError(f"frontmatter missing for {task_id}")
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        raise AssertionError(f"frontmatter is not a mapping for {task_id}")
    return metadata


def copy_workspace(task_id: str, destination: Path) -> None:
    parsed = parse_task_md(task_path(task_id))
    source = Path(parsed["workspace_path"])
    shutil.copytree(source / "exec", destination, dirs_exist_ok=True)
    shutil.copytree(source / "gt", destination / "gt")


def expected(root: Path) -> dict:
    return json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))


def load_grader(task_id: str):
    namespace: dict = {}
    code = parse_task_md(task_path(task_id))["automated_checks"]
    exec(compile(code, str(task_path(task_id)), "exec"), namespace)
    return namespace["grade"]


def automatic_score(scores: dict) -> float:
    value = scores.get("overall_score")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    values = [
        float(value)
        for key, value in scores.items()
        if key != "overall_score"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ]
    return sum(values) / len(values) if values else 0.0


def write_timezone(root: Path, partial: bool = False) -> None:
    data = expected(root)
    views = list(data["participant_local_times"])
    if partial:
        views = views[:-1]
    result = {
        "meeting_id": data["meeting_id"],
        "title": data["title"],
        "start_utc": data["start_utc"],
        "end_utc": data["end_utc"],
        "duration_minutes": data["duration_minutes"],
        "participant_local_times": views,
    }
    results = root / "results"
    results.mkdir()
    (results / "meeting.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (results / "meeting.ics").write_text(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//WildClawBench//EN\r\n"
        "BEGIN:VEVENT\r\nUID:GLOBAL-SYNC-0916@wildclawbench.local\r\n"
        "DTSTART:20260916T090000Z\r\nDTEND:20260916T100000Z\r\n"
        "SUMMARY:Global release readiness sync\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n",
        encoding="utf-8",
    )


def write_support(root: Path, partial: bool = False) -> None:
    data = expected(root)
    rows = data["active_rows"][:2] if partial else data["active_rows"]
    results = root / "results"
    results.mkdir()
    with (results / "handoff.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=data["csv_header"])
        writer.writeheader()
        writer.writerows(rows)
    (results / "handoff_note.md").write_text(
        "P1 T-1002 is UNASSIGNED and overdue; assign an incident owner and begin triage.\n"
        "P2 T-1001 remains with Alice; backend log review is pending before 22:00 UTC.\n"
        "T-1004 and T-1005 remain lower-priority follow-ups. No customer commitment has been made.\n",
        encoding="utf-8",
    )


def write_sec(root: Path, partial: bool = False) -> None:
    data = expected(root)
    source = {key: data["source"][key] for key in ("accession", "url", "fiscal_year_end", "unit")}
    financials = dict(data["financials"])
    financials["segment_revenue_2023"] = dict(financials["segment_revenue_2023"])
    yoy = dict(data["yoy_percent"])
    if partial:
        financials["total_assets_2023"] = 0
        yoy["intelligent_cloud_revenue"] = 0.0
    results = root / "results"
    results.mkdir()
    (results / "facts.json").write_text(
        json.dumps({"source": source, "financials": financials, "yoy_percent": yoy}, indent=2),
        encoding="utf-8",
    )
    (results / "microsoft_2023_preread.md").write_text(
        "Accession 0000950170-23-035122.\n\n"
        "1. Revenue grew while net income was nearly flat.\n"
        "2. Intelligent Cloud was the largest reportable segment by revenue.\n"
        "3. R&D expense increased faster than total revenue.\n\n"
        "Questions: Which investments explain the difference? Which operating gates should leadership monitor?\n",
        encoding="utf-8",
    )


def write_paper(root: Path, partial: bool = False) -> None:
    data = expected(root)
    authors = list(data["authors"])
    reported = dict(data["reported_results"])
    if partial:
        authors = authors[:-1]
        reported["english_french_training_gpus"] = 4
    card = {
        "source": data["source"],
        "title": data["title"],
        "authors": authors,
        "first_submitted": data["first_submitted"],
        "version_revised": data["version_revised"],
        "reported_results": reported,
    }
    results = root / "results"
    results.mkdir()
    (results / "paper_card.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (results / "reading_pack.md").write_text(
        "本文在序列转换中以注意力机制替代循环和卷积，改善并行训练。引用：arXiv:1706.03762v7。\n\n"
        "议程：背景10分钟；架构20分钟；实验15分钟；讨论12分钟；总结3分钟。\n\n"
        "问题：位置编码如何影响顺序信息？多头注意力承担什么角色？实验还需要哪些消融？\n",
        encoding="utf-8",
    )


def write_reconciliation(root: Path, partial: bool = False) -> None:
    data = expected(root)
    identity = data["identity_chain_rows"][:1] if partial else data["identity_chain_rows"]
    exceptions = data["exception_rows"][:1] if partial else data["exception_rows"]
    results = root / "results"
    results.mkdir()
    with (results / "identity_chain.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=data["identity_chain_header"])
        writer.writeheader()
        writer.writerows(identity)
    with (results / "exceptions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=data["exceptions_header"])
        writer.writeheader()
        writer.writerows(exceptions)
    (results / "handoff_plan.md").write_text(
        "Keep ORD-1003, ORD-1004 and ORD-1005 blocked. Production Lead must supply the missing case, "
        "Order Operations must confirm the canceled queues remain voided, and Fulfillment Lead must "
        "reconcile CS-5005-A against CS-9999. These are evidence gaps, not assumed matches; no shipment is authorized.",
        encoding="utf-8",
    )


def write_launch(root: Path, partial: bool = False) -> None:
    data = expected(root)
    phases = {"M1": "Plan", "M2": "Prepare", "M3": "Validate", "M4": "Validate", "M5": "Validate", "M6": "Pilot", "M7": "Launch"}
    gates = {
        "M1": "Approved scope baseline", "M2": "Migration rehearsal passes",
        "M3": "Written security sign-off", "M4": "Peak-load acceptance",
        "M5": "Successful rollback rehearsal", "M6": "Pilot acceptance recorded",
        "M7": "Release Manager written approval",
    }
    with (root / "milestone_plan.csv").open(encoding="utf-8", newline="") as handle:
        source = {row["milestone_id"]: row for row in csv.DictReader(handle)}
    ids = data["required_milestones"][:-1] if partial else data["required_milestones"]
    rows = []
    for milestone_id in ids:
        item = data["milestones"][milestone_id]
        src = source[milestone_id]
        rows.append({
            "phase": phases[milestone_id], "milestone_id": milestone_id,
            "milestone_name": src["milestone_name"], "start_date": item["start_date"],
            "end_date": item["end_date"], "owner": src["owner"],
            "dependencies": src["dependencies"], "planned_cost_usd": item["cost"],
            "acceptance_gate": gates[milestone_id], "status": "planned",
        })
    results = root / "results"
    results.mkdir()
    with (results / "launch_plan.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=data["launch_plan_header"])
        writer.writeheader()
        writer.writerows(rows)
    with (results / "risk_register.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=data["risk_register_header"])
        writer.writeheader()
        writer.writerows([
            {"risk_id": "R1", "risk": "Security gate slips", "trigger": "No sign-off by Oct 23", "owner": "Security Lead", "response": "Hold pilot and escalate", "severity": "high"},
            {"risk_id": "R2", "risk": "Load target fails", "trigger": "Peak validation misses threshold", "owner": "Performance Lead", "response": "Remediate and rerun", "severity": "high"},
            {"risk_id": "R3", "risk": "Rollback is not proven", "trigger": "Rehearsal fails", "owner": "SRE Lead", "response": "Block pilot and production", "severity": "critical"},
        ])
    (results / "decision_log.md").write_text(
        "The requested 2026-11-06 production date is not approved because pilot acceptance and Release "
        "Manager approval must precede production. Required milestones total USD 175,000, so the USD "
        "25,000 OPT-ANALYTICS request is excluded under the USD 180,000 hard budget.\n",
        encoding="utf-8",
    )
    (results / "comms_draft.md").write_text(
        "The current conditional plan targets production after security sign-off, rollback rehearsal, "
        "pilot acceptance and written release approval. November 6 is not a committed launch date. "
        "We will update stakeholders after the pilot decision point; no deployment or spend is approved by this draft.\n",
        encoding="utf-8",
    )


FULL_WRITERS = {
    "01_Productivity_Flow_task_004_timezone_scheduler": write_timezone,
    "01_Productivity_Flow_task_005_support_handoff": write_support,
    "01_Productivity_Flow_task_007_sec_filing_preread": write_sec,
    "01_Productivity_Flow_task_008_paper_reading_pack": write_paper,
    "01_Productivity_Flow_task_009_action_reconciliation": write_reconciliation,
    "01_Productivity_Flow_task_010_launch_program_pack": write_launch,
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ProductivityExtensionTaskTest(unittest.TestCase):
    def test_metadata_matches_design_matrix(self):
        for task_id, (difficulty, grading_type) in EXPECTED_METADATA.items():
            with self.subTest(task_id=task_id):
                metadata = task_metadata(task_id)
                self.assertEqual(metadata["difficulty"], difficulty)
                self.assertEqual(metadata["grading_type"], grading_type)

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
        for task_id in AUTO_TASK_IDS:
            with self.subTest(task_id=task_id):
                grade = load_grader(task_id)
                tier_scores = {}
                for tier in ("full", "partial", "zero"):
                    with tempfile.TemporaryDirectory(prefix="productivity-grade-") as tmp:
                        root = Path(tmp)
                        copy_workspace(task_id, root)
                        if tier != "zero":
                            FULL_WRITERS[task_id](root, partial=tier == "partial")
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
            (REPO_ROOT / "tools/report/data/checkpoint_capability_map7.yaml").read_text(encoding="utf-8")
        )
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                parsed = parse_task_md(task_path(task_id))
                namespace = {}
                auto_keys = set()
                if parsed["automated_checks"].strip():
                    exec(compile(parsed["automated_checks"], str(task_path(task_id)), "exec"), namespace)
                    source = parsed["automated_checks"]
                    auto_keys = {
                        key for key in re.findall(r'["\']([a-z][a-z0-9_]+)["\']', source)
                        if key in mapping[task_id] or f"automated.{key}" in mapping[task_id]
                    }
                judge_keys = {item["key"] for item in parsed["rubric_criteria"]}
                if parsed["grading_type"] == "hybrid":
                    wanted = {f"automated.{key}" for key in auto_keys} | {f"llm_judge.{key}" for key in judge_keys}
                elif parsed["grading_type"] == "llm_judge":
                    wanted = {f"llm_judge.{key}" for key in judge_keys}
                else:
                    wanted = auto_keys
                self.assertEqual(set(mapping[task_id]), wanted)

    def test_attachment_hash_size_and_ground_truth_consistency(self):
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                parsed = parse_task_md(task_path(task_id))
                root = Path(parsed["workspace_path"])
                data = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
                files = {
                    path.relative_to(root / "exec").as_posix(): path
                    for path in (root / "exec").rglob("*")
                    if path.is_file() and path.name != ".gitkeep"
                }
                self.assertEqual(set(files), set(data.get("exec_file_sha256", {})))
                for relative, path in files.items():
                    self.assertLessEqual(path.stat().st_size, 5 * 1024 * 1024)
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), data["exec_file_sha256"][relative])

        sec = json.loads((REPO_ROOT / "workspace/extension/01_Productivity_Flow/task_007_sec_filing_preread/gt/expected.json").read_text())
        values = sec["financials"]
        self.assertAlmostEqual(round((values["total_revenue_2023"] / values["total_revenue_2022"] - 1) * 100, 1), sec["yoy_percent"]["total_revenue"])
        self.assertAlmostEqual(round((values["segment_revenue_2023"]["Intelligent Cloud"] / values["intelligent_cloud_revenue_2022"] - 1) * 100, 1), sec["yoy_percent"]["intelligent_cloud_revenue"])
        self.assertAlmostEqual(round((values["research_and_development_2023"] / values["research_and_development_2022"] - 1) * 100, 1), sec["yoy_percent"]["research_and_development"])

        paper = json.loads((REPO_ROOT / "workspace/extension/01_Productivity_Flow/task_008_paper_reading_pack/gt/expected.json").read_text())
        self.assertEqual(len(paper["authors"]), 8)
        launch = json.loads((REPO_ROOT / "workspace/extension/01_Productivity_Flow/task_010_launch_program_pack/gt/expected.json").read_text())
        self.assertEqual(sum(item["cost"] for item in launch["milestones"].values()), launch["planned_total_cost"])

    def test_runtime_sources_match_prompts(self):
        registry = yaml.safe_load((REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8"))
        records = {item["task_id"]: item for item in registry["tasks"] if item["task_id"] in TASKS}
        self.assertEqual(set(records), set(TASKS))
        urls = {source["url"] for record in records.values() for source in record["runtime_sources"]}
        self.assertEqual(urls, EXPECTED_URLS)
        for task_id, record in records.items():
            prompt = parse_task_md(task_path(task_id))["prompt"]
            for source in record["runtime_sources"]:
                self.assertIn(source["url"], prompt)

    @unittest.skipUnless(
        os.environ.get("WILDCLAW_RUN_NETWORK_TESTS") == "1",
        "set WILDCLAW_RUN_NETWORK_TESTS=1 for host-side URL checks",
    )
    def test_fixed_runtime_urls_are_reachable_from_host(self):
        for url in sorted(EXPECTED_URLS):
            with self.subTest(url=url):
                completed = subprocess.run(
                    [
                        "/usr/bin/curl", "--location", "--silent", "--show-error",
                        "--output", "/dev/null", "--write-out", "%{http_code}",
                        "--connect-timeout", "15", "--max-time", "45",
                        "--user-agent", "WildClawBench/1.0 evaluation@example.com",
                        url,
                    ],
                    capture_output=True, text=True, timeout=50,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertTrue(completed.stdout.strip().isdigit(), completed.stdout)
                self.assertGreaterEqual(int(completed.stdout.strip()), 200)
                self.assertLess(int(completed.stdout.strip()), 400)

    def test_report_and_low_score_tools_discover_all_tasks(self):
        report = load_module("productivity_report", REPO_ROOT / "tools/report/scripts/generate_eval_report.py")
        manifest = load_module(
            "productivity_manifest",
            REPO_ROOT / "tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py",
        )
        metadata = report.load_all_task_meta(REPO_ROOT / "tasks")
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                self.assertIn(task_id, metadata)
                self.assertEqual(metadata[task_id]["suite"], CATEGORY)
                located = manifest.locate_task_file(REPO_ROOT / "tasks", CATEGORY, task_id)
                self.assertEqual(Path(located), task_path(task_id))

    def test_output_paths_follow_results_convention(self):
        for task_id in TASKS:
            prompt = parse_task_md(task_path(task_id))["prompt"]
            self.assertNotIn("/tmp_workspace/result/", prompt)
            if task_id != "01_Productivity_Flow_task_003_retro_agenda":
                self.assertIn("/tmp_workspace/results/", prompt)


if __name__ == "__main__":
    unittest.main()
