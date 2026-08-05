"""Executable checks for the nine remaining Search Retrieval extension tasks."""

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


CATEGORY = "04_Search_Retrieval"
TASKS = {
    "04_Search_Retrieval_task_004_pipl_article13_verification": (
        "04_Search_Retrieval_task_004_pipl_article13_verification.md",
        "task_004_pipl_article13_verification",
    ),
    "04_Search_Retrieval_task_005_apple_2023_segment_revenue": (
        "04_Search_Retrieval_task_005_apple_2023_segment_revenue.md",
        "task_005_apple_2023_segment_revenue",
    ),
    "04_Search_Retrieval_task_006_rfc_http_obsolescence": (
        "04_Search_Retrieval_task_006_rfc_http_obsolescence.md",
        "task_006_rfc_http_obsolescence",
    ),
    "04_Search_Retrieval_task_007_census_province_change": (
        "04_Search_Retrieval_task_007_census_province_change.md",
        "task_007_census_province_change",
    ),
    "04_Search_Retrieval_task_008_procurement_clause_version_lookup": (
        "04_Search_Retrieval_task_008_procurement_clause_version_lookup.md",
        "task_008_procurement_clause_version_lookup",
    ),
    "04_Search_Retrieval_task_009_sse_annual_report_metrics": (
        "04_Search_Retrieval_task_009_sse_annual_report_metrics.md",
        "task_009_sse_annual_report_metrics",
    ),
    "04_Search_Retrieval_task_010_node_statfs_release_trace": (
        "04_Search_Retrieval_task_010_node_statfs_release_trace.md",
        "task_010_node_statfs_release_trace",
    ),
    "04_Search_Retrieval_task_011_nist_sha1_transition": (
        "04_Search_Retrieval_task_011_nist_sha1_transition.md",
        "task_011_nist_sha1_transition",
    ),
    "04_Search_Retrieval_task_012_personal_pension_policy_timeline": (
        "04_Search_Retrieval_task_012_personal_pension_policy_timeline.md",
        "task_012_personal_pension_policy_timeline",
    ),
}

EXPECTED_METADATA = {
    "04_Search_Retrieval_task_004_pipl_article13_verification": ("L2", "hybrid", 0.7, 0.3),
    "04_Search_Retrieval_task_005_apple_2023_segment_revenue": ("L3", "hybrid", 0.7, 0.3),
    "04_Search_Retrieval_task_006_rfc_http_obsolescence": ("L2", "hybrid", 0.7, 0.3),
    "04_Search_Retrieval_task_007_census_province_change": ("L3", "hybrid", 0.7, 0.3),
    "04_Search_Retrieval_task_008_procurement_clause_version_lookup": ("L2", "automated", 1.0, 0.0),
    "04_Search_Retrieval_task_009_sse_annual_report_metrics": ("L3", "hybrid", 0.7, 0.3),
    "04_Search_Retrieval_task_010_node_statfs_release_trace": ("L3", "hybrid", 0.7, 0.3),
    "04_Search_Retrieval_task_011_nist_sha1_transition": ("L4", "hybrid", 0.4, 0.6),
    "04_Search_Retrieval_task_012_personal_pension_policy_timeline": ("L4", "hybrid", 0.4, 0.6),
}

EXPECTED_AUTO_KEYS = {
    "04_Search_Retrieval_task_004_pipl_article13_verification": {
        "document_identity_and_dates", "seven_legal_bases", "consent_flags", "structured_delivery"
    },
    "04_Search_Retrieval_task_005_apple_2023_segment_revenue": {
        "filing_identity", "sales_values", "share_calculation", "structured_delivery"
    },
    "04_Search_Retrieval_task_006_rfc_http_obsolescence": {
        "source_identity", "replacement_map", "scope_and_dates", "structured_delivery"
    },
    "04_Search_Retrieval_task_007_census_province_change": {
        "official_sources", "population_values", "change_calculations", "structured_delivery"
    },
    "04_Search_Retrieval_task_008_procurement_clause_version_lookup": {
        "applicable_document_chain", "effective_clause_and_approvals", "excluded_version_reason",
        "evidence_paths", "structured_delivery",
    },
    "04_Search_Retrieval_task_009_sse_annual_report_metrics": {
        "report_identity", "reported_metrics", "ratio_calculation", "structured_delivery"
    },
    "04_Search_Retrieval_task_010_node_statfs_release_trace": {
        "source_chain_identity", "pull_request_timeline", "api_names",
        "release_versions_and_dates", "structured_delivery",
    },
    "04_Search_Retrieval_task_011_nist_sha1_transition": {
        "publication_identity", "signature_status_matrix", "non_signature_condition", "structured_delivery"
    },
    "04_Search_Retrieval_task_012_personal_pension_policy_timeline": {
        "document_identity", "milestone_dates", "coverage_and_effect", "structured_delivery"
    },
}

EXPECTED_JUDGE_WEIGHTS = {
    "04_Search_Retrieval_task_004_pipl_article13_verification": {
        "consent_rule_explanation": 0.60, "review_note_usability": 0.40,
    },
    "04_Search_Retrieval_task_005_apple_2023_segment_revenue": {
        "table_interpretation": 0.55, "correction_readiness": 0.45,
    },
    "04_Search_Retrieval_task_006_rfc_http_obsolescence": {
        "replacement_reasoning": 0.60, "migration_note_usability": 0.40,
    },
    "04_Search_Retrieval_task_007_census_province_change": {
        "methodology_and_interpretation": 1.0,
    },
    "04_Search_Retrieval_task_008_procurement_clause_version_lookup": {},
    "04_Search_Retrieval_task_009_sse_annual_report_metrics": {
        "metric_distinction": 0.60, "note_usability": 0.40,
    },
    "04_Search_Retrieval_task_010_node_statfs_release_trace": {"trace_explanation": 1.0},
    "04_Search_Retrieval_task_011_nist_sha1_transition": {
        "standards_scope_reasoning": 0.40,
        "archive_transition_plan": 0.35,
        "uncertainty_and_claim_boundary": 0.25,
    },
    "04_Search_Retrieval_task_012_personal_pension_policy_timeline": {
        "stage_distinction": 0.40,
        "direct_answer_quality": 0.35,
        "date_scope_boundary": 0.25,
    },
}


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


def expected(root: Path) -> dict:
    return json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))


def load_grader(task_id: str):
    parsed = parse_task_md(task_path(task_id))
    namespace: dict = {}
    exec(compile(parsed["automated_checks"], str(task_path(task_id)), "exec"), namespace)
    grade = namespace.get("grade")
    if not callable(grade):
        raise AssertionError(f"grade() missing for {task_id}")
    return grade


def automatic_score(scores: dict) -> float:
    overall = scores.get("overall_score")
    if isinstance(overall, (int, float)) and not isinstance(overall, bool):
        return float(overall)
    values = [
        float(value) for key, value in scores.items()
        if key != "overall_score" and isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return sum(values) / len(values) if values else 0.0


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_full(task_id: str, root: Path) -> None:
    data = expected(root)
    results = root / "results"
    results.mkdir()
    if task_id.endswith("pipl_article13_verification"):
        answer = {key: data[key] for key in (
            "law_name", "presidential_order", "adopted_date", "effective_date", "legal_bases", "source_urls"
        )}
        (results / "pipl_article13.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
        (results / "review_note.md").write_text(
            "原说法不准确。第十三条第一项以取得个人同意为依据；第二至第七项是在各自法定条件成立时，"
            "不需另行取得个人同意的处理依据，不能扩大为一般豁免。本说明只核对条文，不判断具体业务。\n"
            + "\n".join(data["source_urls"]) + "\n", encoding="utf-8"
        )
    elif task_id.endswith("apple_2023_segment_revenue"):
        answer = {
            "fiscal_year": data["fiscal_year"], "unit": data["unit"],
            "greater_china_net_sales": data["greater_china_net_sales"],
            "total_net_sales": data["total_net_sales"], "share_percent": data["share_percent"],
            "formula": "72,559 / 383,285 * 100", "accession": data["accession"],
            "source_table": data["source_table"],
        }
        (results / "apple_sales_check.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")
        (results / "brief_correction.md").write_text(
            "The statement is supported: 72,559 / 383,285 = 18.9308%, or 18.9% rounded. "
            "Greater China is a geographic reportable segment in FY2023, not a product category or profit measure.\n",
            encoding="utf-8",
        )
    elif task_id.endswith("rfc_http_obsolescence"):
        answer = {"records": data["records"], "source_urls": data["source_urls"]}
        (results / "rfc_replacement_map.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")
        (results / "migration_note.md").write_text(
            "Replace RFC 7231 semantics references with RFC 9110. Split RFC 7230 references: cite RFC 9110 for HTTP "
            "semantics and RFC 9112 for HTTP/1.1 message syntax. Both replacements were published in June 2022.\n",
            encoding="utf-8",
        )
    elif task_id.endswith("census_province_change"):
        rows = [{**row, "percent_change": f'{row["percent_change"]:.2f}'} for row in data["rows"]]
        write_csv(results / "province_change.csv", [
            "province", "population_2010", "population_2020", "absolute_change", "percent_change"
        ], rows)
        (results / "calculation_note.md").write_text(
            "使用第六次和第七次全国人口普查省级人口表。绝对变化=2020人口-2010人口；百分比变化="
            "绝对变化/2010人口*100。广东、浙江增加，黑龙江减少，不据此推断原因。\n"
            + "\n".join(data["source_urls"]) + "\n", encoding="utf-8"
        )
    elif task_id.endswith("procurement_clause_version_lookup"):
        answer = {key: data[key] for key in (
            "request_id", "submission_date", "applicable_base_version", "applicable_amendment", "clause_id",
            "effective_clause_text", "required_approvals", "excluded_version", "exclusion_reason", "evidence_paths"
        )}
        (results / "clause_lookup.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
    elif task_id.endswith("sse_annual_report_metrics"):
        answer = {
            "security_code": data["security_code"], "report_year": data["report_year"],
            "disclosure_date": data["disclosure_date"], "unit": data["unit"],
            "total_operating_revenue": data["total_operating_revenue"],
            "net_profit_attributable_to_listed_company_shareholders": data["net_profit_attributable_to_listed_company_shareholders"],
            "research_and_development_expense": data["research_and_development_expense"],
            "ratio_formula": "157,371,873.01 / 150,560,330,316.45 * 100",
            "ratio_percent": data["ratio_percent"], "source_url": data["source_url"],
        }
        (results / "moutai_metrics.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
        (results / "metric_note.md").write_text(
            "本题分子取合并利润表（年报第63页）的研发费用157,371,873.01元，分母取营业总收入"
            "150,560,330,316.45元，结果为0.10%。年报第11页的研发投入合计621,507,535.87元及0.42%"
            "属于另一披露口径，不能替代利润表研发费用。\n", encoding="utf-8"
        )
    elif task_id.endswith("node_statfs_release_trace"):
        write_csv(results / "statfs_timeline.csv", ["date", "event", "identifier", "evidence_url"], data["rows"])
        (results / "statfs_trace.md").write_text(
            "PR #31351 opened the proposal and was later stalled and closed. PR #46358 was its replacement and revival, "
            "merged through commit f145766011a9b600ff7c4fea043f435f70f6d0bf. The public APIs are fs.statfs(), "
            "fs.statfsSync(), and fsPromises.statfs(). v19.6.0 first shipped them on Current; v18.15.0 carried the LTS backport.\n",
            encoding="utf-8",
        )
    elif task_id.endswith("nist_sha1_transition"):
        write_csv(results / "sha1_use_matrix.csv", [
            "use_case", "nist_status", "conditions", "primary_source", "section_or_table"
        ], data["rows"])
        (results / "transition_memo.md").write_text(
            "NIST SP 800-131A Rev. 2 (March 2019), DOI 10.6028/NIST.SP.800-131Ar2, is the primary source. "
            "FIPS 186-5 is transition context only. Stop generating new SHA-1 signatures except where NIST protocol-specific "
            "guidance expressly permits it. Retain controlled verification of already-generated signatures as Legacy use, "
            "with validation logs and a migration plan. Non-signature use is Acceptable only when collision resistance is not required. "
            "This does not assert support by every product or protocol.\n" + "\n".join(data["source_urls"]) + "\n",
            encoding="utf-8",
        )
    else:
        write_csv(results / "pension_timeline.csv", [
            "stage", "document_number", "document_date", "published_or_effective_date", "coverage", "source_url"
        ], data["rows"])
        (results / "answer.md").write_text(
            "“开始”取决于所问阶段：2022年4月建立制度框架，2022年10月形成实施办法，2022年11月在36个城市"
            "或地区先行实施，2024年12月15日起全国实施。因此运行层面可说2022年11月先行开始；若问全国可参加，"
            "则是2024年12月15日。政策发布不等于全国实施。\n", encoding="utf-8"
        )


def write_partial(task_id: str, root: Path) -> None:
    write_full(task_id, root)
    results = root / "results"
    if task_id.endswith("pipl_article13_verification"):
        path = results / "pipl_article13.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["legal_bases"][6]["basis"] = "错误概括"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif task_id.endswith("apple_2023_segment_revenue"):
        path = results / "apple_sales_check.json"
        data = json.loads(path.read_text(encoding="utf-8")); data["share_percent"] = 17.0
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    elif task_id.endswith("rfc_http_obsolescence"):
        path = results / "rfc_replacement_map.json"
        data = json.loads(path.read_text(encoding="utf-8")); data["records"][0]["replacements"] = data["records"][0]["replacements"][:1]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    elif task_id.endswith("census_province_change"):
        path = results / "province_change.csv"
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream); columns = reader.fieldnames; rows = list(reader)
        rows[0]["population_2020"] = "126012509"
        write_csv(path, columns, rows)
    elif task_id.endswith("procurement_clause_version_lookup"):
        path = results / "clause_lookup.json"
        data = json.loads(path.read_text(encoding="utf-8")); data["required_approvals"] = data["required_approvals"][:2]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif task_id.endswith("sse_annual_report_metrics"):
        path = results / "moutai_metrics.json"
        data = json.loads(path.read_text(encoding="utf-8")); data["ratio_percent"] = 0.42
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif task_id.endswith("node_statfs_release_trace"):
        path = results / "statfs_timeline.csv"
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream); columns = reader.fieldnames; rows = list(reader)
        rows[-1]["date"] = "2023-03-08"
        write_csv(path, columns, rows)
    elif task_id.endswith("nist_sha1_transition"):
        path = results / "sha1_use_matrix.csv"
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream); columns = reader.fieldnames; rows = list(reader)
        rows[-1]["nist_status"] = "Disallowed"
        write_csv(path, columns, rows)
    else:
        path = results / "pension_timeline.csv"
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream); columns = reader.fieldnames; rows = list(reader)
        rows[-1]["published_or_effective_date"] = "2024-12-16"
        write_csv(path, columns, rows)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SearchRetrievalExtensionTaskTest(unittest.TestCase):
    def test_metadata_matches_design_matrix_and_group_weights(self):
        for task_id, wanted in EXPECTED_METADATA.items():
            with self.subTest(task_id=task_id):
                difficulty, grading_type, auto_weight, judge_weight = wanted
                actual = metadata(task_id)
                self.assertEqual(actual["difficulty"], difficulty)
                self.assertEqual(actual["grading_type"], grading_type)
                self.assertAlmostEqual(actual["grading_weights"]["automated"], auto_weight)
                self.assertAlmostEqual(actual["grading_weights"]["llm_judge"], judge_weight)

    def test_static_validator_accepts_current_repository_and_preserves_invalid_numbers(self):
        self.assertEqual(validate_repository(REPO_ROOT, allow_incomplete=True), [])
        strict = validate_repository(REPO_ROOT)
        self.assertEqual([issue for issue in strict if issue.code != "task.missing"], [])
        registry = yaml.safe_load((REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8"))
        excluded = set(registry["registry_contract"]["reserved_invalid_short_ids"])
        self.assertIn("04-001", excluded)
        self.assertIn("04-002", excluded)
        present = {path.stem for path in (REPO_ROOT / "tasks/extension").glob("*/*.md")}
        registered = {item["task_id"] for item in registry["tasks"]}
        self.assertEqual(sum(issue.code == "task.missing" for issue in strict), len(registered - present))

    def test_automated_graders_have_full_partial_and_zero_tiers(self):
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                grade = load_grader(task_id)
                tier_scores = {}
                for tier in ("full", "partial", "zero"):
                    with tempfile.TemporaryDirectory(prefix="search-grade-") as temporary:
                        root = Path(temporary)
                        copy_workspace(task_id, root)
                        if tier == "full":
                            write_full(task_id, root)
                        elif tier == "partial":
                            write_partial(task_id, root)
                        result = grade(transcript=[], workspace_path=str(root))
                        self.assertEqual(set(result) - {"overall_score"}, EXPECTED_AUTO_KEYS[task_id])
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
                if wanted:
                    self.assertAlmostEqual(sum(actual.values()), 1.0, places=6)
                for key, weight in wanted.items():
                    self.assertAlmostEqual(actual[key], weight, places=6)
                for criterion in criteria:
                    self.assertEqual(set(pattern.findall(criterion["rubric"])), required)

    def test_capability_mapping_exactly_matches_checkpoints(self):
        mapping = yaml.safe_load((REPO_ROOT / "tools/report/data/checkpoint_capability_map7.yaml").read_text(encoding="utf-8"))
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                judge_keys = set(EXPECTED_JUDGE_WEIGHTS[task_id])
                if EXPECTED_METADATA[task_id][1] == "hybrid":
                    wanted = {f"automated.{key}" for key in EXPECTED_AUTO_KEYS[task_id]} | {
                        f"llm_judge.{key}" for key in judge_keys
                    }
                else:
                    wanted = EXPECTED_AUTO_KEYS[task_id]
                self.assertEqual(set(mapping[task_id]), wanted)
                for labels in mapping[task_id].values():
                    self.assertTrue(labels)

    def test_attachment_hash_size_and_ground_truth_consistency(self):
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                ws = workspace_path(task_id)
                self.assertTrue((ws / "gt/expected.json").is_file())
                files = [p for p in (ws / "exec").rglob("*") if p.is_file() and p.name != ".gitkeep"]
                if task_id.endswith("procurement_clause_version_lookup"):
                    data = json.loads((ws / "gt/expected.json").read_text(encoding="utf-8"))
                    self.assertEqual(len(files), 6)
                    self.assertLess(sum(p.stat().st_size for p in files), 5 * 1024 * 1024)
                    actual = {
                        str(path.relative_to(ws / "exec")): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in files
                    }
                    self.assertEqual(actual, data["exec_file_sha256"])
                else:
                    self.assertEqual(files, [])
                forbidden = [p for p in ws.rglob("*") if p.is_file() and p.suffix.lower() in {".html", ".htm", ".pdf", ".warc"}]
                self.assertEqual(forbidden, [])

    def test_runtime_sources_match_registry_and_prompts(self):
        registry = yaml.safe_load((REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8"))
        records = {item["task_id"]: item for item in registry["tasks"] if item["task_id"] in TASKS}
        self.assertEqual(set(records), set(TASKS))
        runtime_urls = set()
        for task_id, record in records.items():
            prompt = parse_task_md(task_path(task_id))["prompt"]
            urls = [source["url"] for source in record["runtime_sources"]]
            runtime_urls.update(urls)
            for url in urls:
                self.assertIn(url, prompt)
            if task_id.endswith("procurement_clause_version_lookup"):
                self.assertEqual(urls, [])
                self.assertNotIn("https://", prompt)
            else:
                self.assertGreater(len(urls), 0)
        self.assertEqual(len(runtime_urls), 22)

    @unittest.skipUnless(
        os.environ.get("WILDCLAW_RUN_NETWORK_TESTS") == "1",
        "set WILDCLAW_RUN_NETWORK_TESTS=1 for host-side URL checks",
    )
    def test_fixed_runtime_urls_are_reachable_from_host(self):
        registry = yaml.safe_load((REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8"))
        urls = sorted({
            source["url"]
            for item in registry["tasks"] if item["task_id"] in TASKS
            for source in item["runtime_sources"]
        })
        for url in urls:
            with self.subTest(url=url):
                completed = subprocess.run(
                    [
                        "/usr/bin/curl", "--location", "--silent", "--show-error", "--output", "/dev/null",
                        "--write-out", "%{http_code}", "--connect-timeout", "15", "--max-time", "45",
                        "--user-agent", "WildClawBench/1.0 evaluation@example.com", url,
                    ],
                    capture_output=True, text=True, timeout=50,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertTrue(completed.stdout.strip().isdigit(), completed.stdout)
                status = int(completed.stdout.strip())
                self.assertGreaterEqual(status, 200)
                self.assertLess(status, 400)

    def test_report_and_low_score_tools_discover_all_tasks(self):
        report = load_module("search_retrieval_report", REPO_ROOT / "tools/report/scripts/generate_eval_report.py")
        manifest = load_module(
            "search_retrieval_manifest",
            REPO_ROOT / "tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py",
        )
        metadata_rows = report.load_all_task_meta(REPO_ROOT / "tasks")
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                self.assertIn(task_id, metadata_rows)
                self.assertEqual(metadata_rows[task_id]["suite"], CATEGORY)
                located = manifest.locate_task_file(REPO_ROOT / "tasks", CATEGORY, task_id)
                self.assertEqual(Path(located), task_path(task_id))

    def test_prompts_are_user_facing_and_result_paths_are_bounded(self):
        banned = ("评测框架", "评分点", "能力维度", "llm judge", "auto评分")
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                prompt = parse_task_md(task_path(task_id))["prompt"]
                lowered = prompt.lower()
                for term in banned:
                    self.assertNotIn(term, lowered)
                self.assertIn("/tmp_workspace/results/", prompt)
                self.assertNotIn("/tmp_workspace/result/", prompt)


if __name__ == "__main__":
    unittest.main()
