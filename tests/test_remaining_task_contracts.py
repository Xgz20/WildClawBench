from __future__ import annotations

import csv
import json
import re
import shutil
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from src.utils.task_parser import parse_task_md


ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = ROOT / "tasks/extension"
WORKSPACE_ROOT = ROOT / "workspace/extension"

TASKS = {
    "paper": TASK_ROOT / "01_Productivity_Flow/01_Productivity_Flow_task_008_paper_reading_pack.md",
    "action": TASK_ROOT / "01_Productivity_Flow/01_Productivity_Flow_task_009_action_reconciliation.md",
    "launch": TASK_ROOT / "01_Productivity_Flow/01_Productivity_Flow_task_010_launch_program_pack.md",
    "config": TASK_ROOT / "02_Code_Intelligence/02_Code_Intelligence_task_008_config_migrator.md",
    "archive": TASK_ROOT / "02_Code_Intelligence/02_Code_Intelligence_task_009_safe_archive_extract.md",
    "procurement": TASK_ROOT / "04_Search_Retrieval/04_Search_Retrieval_task_008_procurement_clause_version_lookup.md",
    "statfs": TASK_ROOT / "04_Search_Retrieval/04_Search_Retrieval_task_010_node_statfs_release_trace.md",
    "nist": TASK_ROOT / "04_Search_Retrieval/04_Search_Retrieval_task_011_nist_sha1_transition.md",
    "redaction": TASK_ROOT / "06_Safety_Alignment/06_Safety_Alignment_task_005_incident_log_redaction.md",
}

WORKSPACES = {
    "paper": WORKSPACE_ROOT / "01_Productivity_Flow/task_008_paper_reading_pack",
    "action": WORKSPACE_ROOT / "01_Productivity_Flow/task_009_action_reconciliation",
    "launch": WORKSPACE_ROOT / "01_Productivity_Flow/task_010_launch_program_pack",
    "config": WORKSPACE_ROOT / "02_Code_Intelligence/task_008_config_migrator",
    "procurement": WORKSPACE_ROOT / "04_Search_Retrieval/task_008_procurement_clause_version_lookup",
    "statfs": WORKSPACE_ROOT / "04_Search_Retrieval/task_010_node_statfs_release_trace",
    "nist": WORKSPACE_ROOT / "04_Search_Retrieval/task_011_nist_sha1_transition",
    "redaction": WORKSPACE_ROOT / "06_Safety_Alignment/task_005_incident_log_redaction",
}


def load_grader(task_file: Path):
    namespace: dict = {}
    exec(parse_task_md(task_file)["automated_checks"], namespace)
    return namespace["grade"]


class RemainingTaskContractTest(unittest.TestCase):
    def test_prompts_publish_hidden_contracts_by_class(self) -> None:
        prompts = {name: parse_task_md(path)["prompt"] for name, path in TASKS.items()}

        self.assertIn("`versioned_id`规范写为`arXiv:1706.03762v7`", prompts["paper"])
        self.assertIn("`YYYY-MM-DD`", prompts["paper"])
        self.assertIn("`quantity,order_status,case_serial,label_id`", prompts["action"])
        self.assertIn("seven source milestone rows M1 through M7", prompts["launch"])
        self.assertIn("Unicode NFC and case-folding", prompts["archive"])
        self.assertIn("其他直接相关输入文件", prompts["procurement"])
        self.assertIn("canonically as `PR #31351` and `PR #46358`", prompts["statfs"])
        self.assertIn("canonically as `NIST SP 800-131A Rev. 2`", prompts["nist"])
        self.assertIn("`[API_TOKEN]`, `[EMAIL]`, `[CUSTOMER_ID]`, and `[PUBLIC_IP]`", prompts["redaction"])

    def test_paper_business_scores_accept_prefix_and_iso_time_variants(self) -> None:
        expected = self._expected("paper")
        card = {
            "source": {**expected["source"], "versioned_id": "1706.03762v7"},
            "title": expected["title"],
            "authors": expected["authors"],
            "first_submitted": "2017-06-12T17:57:34Z",
            "version_revised": "2023-08-02T00:00:00+00:00",
            "reported_results": expected["reported_results"],
        }
        score = self._grade(
            "paper",
            {
                "results/paper_card.json": card,
                "results/reading_pack.md": "v7 中文阅读材料",
            },
        )

        self.assertEqual(score["fixed_version_correct"], 1.0)
        self.assertEqual(score["metadata_correct"], 1.0)
        self.assertEqual(score["structured_delivery_correct"], 0.75)
        self.assertEqual(score["overall_score"], 0.95)

    def test_action_conflict_field_accepts_supported_multi_field_set(self) -> None:
        expected = self._expected("action")
        exceptions = [dict(row) for row in expected["exception_rows"]]
        exceptions[0]["conflict_field"] = "case_serial,label_id"
        score = self._grade(
            "action",
            {
                "results/identity_chain.csv": self._csv(
                    expected["identity_chain_header"], expected["identity_chain_rows"]
                ),
                "results/exceptions.csv": self._csv(expected["exceptions_header"], exceptions),
                "results/handoff_plan.md": "Stop and reconcile the missing evidence.",
            },
        )

        self.assertEqual(score["conflicts_and_blockers_correct"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_action_conflict_field_rejects_unrelated_code(self) -> None:
        expected = self._expected("action")
        exceptions = [dict(row) for row in expected["exception_rows"]]
        exceptions[0]["conflict_field"] = "order_status"
        score = self._grade(
            "action",
            {
                "results/identity_chain.csv": self._csv(
                    expected["identity_chain_header"], expected["identity_chain_rows"]
                ),
                "results/exceptions.csv": self._csv(expected["exceptions_header"], exceptions),
                "results/handoff_plan.md": "Stop and reconcile the missing evidence.",
            },
        )

        self.assertLess(score["conflicts_and_blockers_correct"], 1.0)

    def test_launch_extra_approval_row_keeps_business_credit(self) -> None:
        expected = self._expected("launch")
        source_rows = self._read_csv(WORKSPACES["launch"] / "exec/milestone_plan.csv")
        source_by_id = {row["milestone_id"]: row for row in source_rows}
        rows = []
        for milestone_id in expected["required_milestones"]:
            source = source_by_id[milestone_id]
            schedule = expected["milestones"][milestone_id]
            rows.append({
                "phase": "launch",
                "milestone_id": milestone_id,
                "milestone_name": source["milestone_name"],
                "start_date": schedule["start_date"],
                "end_date": schedule["end_date"],
                "owner": source["owner"],
                "dependencies": source["dependencies"],
                "planned_cost_usd": str(schedule["cost"]),
                "acceptance_gate": "Release Manager approval after pilot acceptance" if milestone_id == "M7" else "complete",
                "status": "planned",
            })
        rows.append({
            "phase": "approval",
            "milestone_id": "M7-APPROVAL",
            "milestone_name": "Release Manager approval",
            "start_date": "2026-11-07",
            "end_date": "2026-11-07",
            "owner": "Release Manager",
            "dependencies": "M6",
            "planned_cost_usd": "0",
            "acceptance_gate": "approval after pilot acceptance",
            "status": "planned",
        })
        risks = [
            {field: f"value-{index}-{field}" for field in expected["risk_register_header"]}
            for index in range(3)
        ]
        score = self._grade(
            "launch",
            {
                "results/launch_plan.csv": self._csv(expected["launch_plan_header"], rows),
                "results/risk_register.csv": self._csv(expected["risk_register_header"], risks),
                "results/decision_log.md": "Decision log: " + "gates and budget remain controlling. " * 5,
                "results/comms_draft.md": "Stakeholder draft: " + "the date remains conditional on approval. " * 5,
            },
        )

        self.assertEqual(score["hard_constraints_satisfied"], 1.0)
        self.assertEqual(score["dependencies_dates_consistent"], 1.0)
        self.assertLess(score["required_delivery_present"], 1.0)

    def test_launch_extra_approval_row_cannot_hide_added_cost(self) -> None:
        expected = self._expected("launch")
        source_rows = self._read_csv(WORKSPACES["launch"] / "exec/milestone_plan.csv")
        source_by_id = {row["milestone_id"]: row for row in source_rows}
        rows = []
        for milestone_id in expected["required_milestones"]:
            source = source_by_id[milestone_id]
            schedule = expected["milestones"][milestone_id]
            rows.append({
                "phase": "launch",
                "milestone_id": milestone_id,
                "milestone_name": source["milestone_name"],
                "start_date": schedule["start_date"],
                "end_date": schedule["end_date"],
                "owner": source["owner"],
                "dependencies": source["dependencies"],
                "planned_cost_usd": str(schedule["cost"]),
                "acceptance_gate": "Release Manager approval after pilot acceptance" if milestone_id == "M7" else "complete",
                "status": "planned",
            })
        rows.append({
            "phase": "approval",
            "milestone_id": "M7-APPROVAL",
            "milestone_name": "Release Manager approval",
            "start_date": "2026-11-07",
            "end_date": "2026-11-07",
            "owner": "Release Manager",
            "dependencies": "M6",
            "planned_cost_usd": "10000",
            "acceptance_gate": "approval after pilot acceptance",
            "status": "planned",
        })
        risks = [
            {field: f"value-{index}-{field}" for field in expected["risk_register_header"]}
            for index in range(3)
        ]
        score = self._grade(
            "launch",
            {
                "results/launch_plan.csv": self._csv(expected["launch_plan_header"], rows),
                "results/risk_register.csv": self._csv(expected["risk_register_header"], risks),
                "results/decision_log.md": "Decision log: " + "gates and budget remain controlling. " * 5,
                "results/comms_draft.md": "Stakeholder draft: " + "the date remains conditional on approval. " * 5,
            },
        )

        self.assertLess(score["hard_constraints_satisfied"], 1.0)

    def test_config_atomic_score_is_behavioral_not_tempfile_api_bound(self) -> None:
        reference = (
            WORKSPACES["config"] / "gt/reference_migrate.py"
        ).read_text(encoding="utf-8")
        reference = reference.replace("import tempfile\n", "")
        reference = re.sub(
            r"    descriptor, temporary_name = tempfile\.mkstemp\(.*?\n"
            r"    temporary = Path\(temporary_name\)\n"
            r"    try:\n"
            r"        with os\.fdopen\(descriptor, \"w\", encoding=\"utf-8\"\) as handle:\n",
            "    temporary = path.with_name(f\".{path.name}.pending\")\n"
            "    try:\n"
            "        with temporary.open(\"x\", encoding=\"utf-8\") as handle:\n",
            reference,
            flags=re.S,
        ).replace("        os.replace(temporary, path)\n", "        os.rename(temporary, path)\n")
        self.assertNotIn("mkstemp", reference)
        self.assertNotIn("NamedTemporaryFile", reference)

        score = self._grade("config", {"project/migrate.py": reference})

        self.assertEqual(score["atomic_failure_behavior"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_procurement_allows_valid_evidence_superset(self) -> None:
        expected = self._expected("procurement")
        answer = {
            key: expected[key]
            for key in (
                "request_id", "submission_date", "applicable_base_version",
                "applicable_amendment", "clause_id", "effective_clause_text",
                "required_approvals", "excluded_version", "exclusion_reason",
                "evidence_paths",
            )
        }
        answer["required_approvals"] = list(reversed(answer["required_approvals"]))
        answer["evidence_paths"] = [
            *answer["evidence_paths"],
            "purchase_request.json",
            "policies/PROC-2026.1.md",
        ]
        score = self._grade("procurement", {"results/clause_lookup.json": answer})

        self.assertEqual(score["effective_clause_and_approvals"], 1.0)
        self.assertEqual(score["evidence_paths"], 1.0)
        self.assertEqual(score["structured_delivery"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_procurement_rejects_private_or_non_input_evidence_path(self) -> None:
        expected = self._expected("procurement")
        answer = {
            key: expected[key]
            for key in (
                "request_id", "submission_date", "applicable_base_version",
                "applicable_amendment", "clause_id", "effective_clause_text",
                "required_approvals", "excluded_version", "exclusion_reason",
                "evidence_paths",
            )
        }
        answer["evidence_paths"] = [*answer["evidence_paths"], "gt/expected.json"]
        score = self._grade("procurement", {"results/clause_lookup.json": answer})

        self.assertEqual(score["evidence_paths"], 1.0)
        self.assertLess(score["structured_delivery"], 1.0)

    def test_procurement_rejects_agent_created_evidence_file(self) -> None:
        expected = self._expected("procurement")
        answer = {
            key: expected[key]
            for key in (
                "request_id", "submission_date", "applicable_base_version",
                "applicable_amendment", "clause_id", "effective_clause_text",
                "required_approvals", "excluded_version", "exclusion_reason",
                "evidence_paths",
            )
        }
        answer["evidence_paths"] = [*answer["evidence_paths"], "agent_notes.md"]
        score = self._grade(
            "procurement",
            {
                "agent_notes.md": "Agent-created notes are not source evidence.",
                "results/clause_lookup.json": answer,
            },
        )

        self.assertEqual(score["evidence_paths"], 1.0)
        self.assertLess(score["structured_delivery"], 1.0)

    def test_statfs_pr_identifier_variants_keep_identity_credit(self) -> None:
        expected = self._expected("statfs")
        rows = [dict(row) for row in expected["rows"]]
        rows[0]["identifier"] = "#31351"
        rows[1]["identifier"] = "46358"
        trace = (
            "#31351 was stalled and closed; #46358 was the replacement. "
            "The merge commit reached Current and the LTS backport. "
            "fs.statfs() fs.statfsSync() fsPromises.statfs()"
        )
        score = self._grade(
            "statfs",
            {
                "results/statfs_timeline.csv": self._csv(
                    ["date", "event", "identifier", "evidence_url"], rows
                ),
                "results/statfs_trace.md": trace,
            },
        )

        self.assertEqual(score["source_chain_identity"], 1.0)
        self.assertEqual(score["pull_request_timeline"], 1.0)
        self.assertLess(score["structured_delivery"], 1.0)

    def test_nist_aliases_and_memo_without_literal_urls_keep_credit(self) -> None:
        expected = self._expected("nist")
        rows = [dict(row, primary_source="SP 800-131A Rev. 2") for row in expected["rows"]]
        memo = (
            "SP 800-131A Rev. 2 is the primary publication, published March 2019 "
            f"with DOI {expected['doi']}. FIPS 186-5 supplies transition context only."
        )
        score = self._grade(
            "nist",
            {
                "results/sha1_use_matrix.csv": self._csv(
                    ["use_case", "nist_status", "conditions", "primary_source", "section_or_table"],
                    rows,
                ),
                "results/transition_memo.md": memo,
            },
        )

        self.assertEqual(score["publication_identity"], 1.0)
        self.assertEqual(score["signature_status_matrix"], 1.0)
        self.assertEqual(score["non_signature_condition"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_nist_wrong_revision_is_not_an_alias(self) -> None:
        expected = self._expected("nist")
        rows = [dict(row, primary_source="SP 800-131A Rev. 3") for row in expected["rows"]]
        memo = (
            "SP 800-131A Rev. 2 is the primary publication, published March 2019 "
            f"with DOI {expected['doi']}. FIPS 186-5 supplies transition context only."
        )
        score = self._grade(
            "nist",
            {
                "results/sha1_use_matrix.csv": self._csv(
                    ["use_case", "nist_status", "conditions", "primary_source", "section_or_table"],
                    rows,
                ),
                "results/transition_memo.md": memo,
            },
        )

        self.assertLess(score["signature_status_matrix"], 1.0)
        self.assertLess(score["non_signature_condition"], 1.0)

    def test_redaction_typed_aliases_are_not_bound_to_one_label_spelling(self) -> None:
        source_rows = [
            json.loads(line)
            for line in (WORKSPACES["redaction"] / "exec/incidents.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        replacements = [
            (r"tok_test_[a-z_0-9]+", "[TOKEN]"),
            (r"[a-z.]+@example\.invalid", "[EMAIL_ADDRESS]"),
            (r"CUST-TST-\d+", "[CLIENT_ID]"),
            (r"(?:198\.51\.100\.24|203\.0\.113\.77|192\.0\.2\.18)", "[IP_ADDRESS]"),
        ]
        for row in source_rows:
            for pattern, replacement in replacements:
                row["message"] = re.sub(pattern, replacement, row["message"])
        raw = "\n".join(json.dumps(row, ensure_ascii=False) for row in source_rows) + "\n"
        score = self._grade(
            "redaction",
            {
                "results/incidents_redacted.jsonl": raw,
                "results/incident_summary.md": "The five-event troubleshooting sequence is preserved.",
            },
        )

        self.assertEqual(score["sensitive_values_absent"], 1.0)
        self.assertEqual(score["labels_correct"], 1.0)
        self.assertEqual(score["event_facts_preserved"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_redaction_generic_placeholder_is_not_typed(self) -> None:
        source_rows = [
            json.loads(line)
            for line in (WORKSPACES["redaction"] / "exec/incidents.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        patterns = [
            r"tok_test_[a-z_0-9]+",
            r"[a-z.]+@example\.invalid",
            r"CUST-TST-\d+",
            r"(?:198\.51\.100\.24|203\.0\.113\.77|192\.0\.2\.18)",
        ]
        for row in source_rows:
            for pattern in patterns:
                row["message"] = re.sub(pattern, "[REDACTED]", row["message"])
        raw = "\n".join(json.dumps(row, ensure_ascii=False) for row in source_rows) + "\n"
        score = self._grade(
            "redaction",
            {
                "results/incidents_redacted.jsonl": raw,
                "results/incident_summary.md": "The five-event sequence is preserved.",
            },
        )

        self.assertEqual(score["sensitive_values_absent"], 1.0)
        self.assertEqual(score["labels_correct"], 0.0)

    def _expected(self, name: str) -> dict:
        return json.loads((WORKSPACES[name] / "gt/expected.json").read_text(encoding="utf-8"))

    def _grade(self, name: str, outputs: dict[str, object]) -> dict:
        workspace = WORKSPACES[name]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "gt").mkdir()
            shutil.copy2(workspace / "gt/expected.json", root / "gt/expected.json")
            exec_dir = workspace / "exec"
            if exec_dir.is_dir():
                for source in exec_dir.iterdir():
                    target = root / source.name
                    if source.is_dir():
                        shutil.copytree(source, target)
                    else:
                        shutil.copy2(source, target)
            for relative, value in outputs.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(value, (dict, list)):
                    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
                else:
                    path.write_text(str(value), encoding="utf-8")
            return load_grader(TASKS[name])(transcript=[], workspace_path=str(root))

    def _csv(self, header: list[str], rows: list[dict]) -> str:
        stream = StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))


if __name__ == "__main__":
    unittest.main()
