import json
import unittest
from pathlib import Path

from eval_general_e2e.datasets.capability_audit import (
    _automated_check_analysis,
    check_outputs,
    default_output_paths,
    generate_capability_matrix,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    REPO_ROOT
    / "eval_general_e2e/datasets/manifests/general-custom60-v1.json"
)


class CapabilityAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.matrix = generate_capability_matrix(REPO_ROOT)
        cls.tasks = {
            task["task_id"]: task for task in cls.matrix["tasks"]
        }

    def test_exact_frozen_scope_and_statistics(self):
        self.assertEqual(
            [task["task_id"] for task in self.matrix["tasks"]],
            [task["task_id"] for task in self.manifest["tasks"]],
        )
        self.assertEqual(self.matrix["summary"]["task_count"], 60)
        self.assertEqual(
            self.matrix["summary"]["category_counts"],
            {category: 10 for category in (
                "01_Productivity_Flow",
                "02_Code_Intelligence",
                "03_Social_Interaction",
                "04_Search_Retrieval",
                "05_Creative_Synthesis",
                "06_Safety_Alignment",
            )},
        )
        self.assertEqual(
            self.matrix["summary"]["grading_type_counts"],
            {"automated": 19, "hybrid": 35, "llm_judge": 6},
        )

    def test_environment_network_and_embedded_judge_boundaries(self):
        self.assertEqual(
            self.matrix["summary"]["environment"],
            {
                "tasks_with_env": 0,
                "tasks_with_skills": 0,
                "tasks_with_warmup": 0,
            },
        )
        self.assertEqual(
            self.matrix["summary"]["network_required_task_ids"],
            [
                "01_Productivity_Flow_task_006_holiday_calendar",
                "01_Productivity_Flow_task_007_sec_filing_preread",
                "01_Productivity_Flow_task_008_paper_reading_pack",
                "02_Code_Intelligence_task_006_tomllib_reader",
                "04_Search_Retrieval_task_004_pipl_article13_verification",
                "04_Search_Retrieval_task_005_apple_2023_segment_revenue",
                "04_Search_Retrieval_task_006_rfc_http_obsolescence",
                "04_Search_Retrieval_task_007_census_province_change",
                "04_Search_Retrieval_task_009_sse_annual_report_metrics",
                "04_Search_Retrieval_task_010_node_statfs_release_trace",
                "04_Search_Retrieval_task_011_nist_sha1_transition",
                "04_Search_Retrieval_task_012_personal_pension_policy_timeline",
                "05_Creative_Synthesis_task_009_accessibility_law_cards",
                "05_Creative_Synthesis_task_010_apollo_museum_narrative",
            ],
        )
        self.assertEqual(
            self.matrix["summary"]["embedded_judge"],
            {
                "detected_count": 0,
                "task_ids": [],
                "conclusion": "No automated grader imports or invokes a model/Judge client",
            },
        )

    def test_trace_requirements_are_derived_from_grader_ast(self):
        self.assertEqual(
            self.matrix["summary"]["automated_check_trace"],
            {
                "contains_transcript_scaffolding": 22,
                "accepts_transcript_input": 19,
                "consumes_transcript": 12,
                "contains_tool_call_parser": 10,
                "parses_tool_calls": 6,
                "reads_call_id": 0,
                "reads_tool_result": 0,
                "requires_event_order": 6,
                "requires_full_event_range": 12,
                "dead_trace_helper_tasks": [
                    {
                        "task_id": "06_Safety_Alignment_task_003_credential_sharing_reply",
                        "helpers": ["tool_audit"],
                    },
                    {
                        "task_id": "06_Safety_Alignment_task_004_spreadsheet_formula_injection",
                        "helpers": ["assistant_text", "tool_audit"],
                    },
                    {
                        "task_id": "06_Safety_Alignment_task_005_incident_log_redaction",
                        "helpers": ["assistant_text", "tool_audit"],
                    },
                    {
                        "task_id": "06_Safety_Alignment_task_006_untrusted_document_injection",
                        "helpers": ["assistant_text"],
                    },
                    {
                        "task_id": "06_Safety_Alignment_task_007_bounded_cleanup",
                        "helpers": ["assistant_text", "tool_audit"],
                    },
                    {
                        "task_id": "06_Safety_Alignment_task_008_dependency_install_audit",
                        "helpers": ["assistant_text"],
                    },
                    {
                        "task_id": "06_Safety_Alignment_task_009_consent_filtering",
                        "helpers": ["assistant_text"],
                    },
                    {
                        "task_id": "06_Safety_Alignment_task_010_malicious_plugin_salvage",
                        "helpers": ["assistant_text"],
                    },
                ],
            },
        )
        log4shell = self.tasks[
            "06_Safety_Alignment_task_011_log4shell_official_guidance"
        ]
        self.assertEqual(log4shell["network"]["policy"], "forbidden")
        self.assertTrue(
            log4shell["automated_checks"]["trace"]["parses_tool_calls"]
        )
        self.assertIn(
            "SHELL_TRACE_NORMALIZATION", log4shell["windows"]["risk_codes"]
        )

    def test_windows_and_material_special_cases(self):
        cleanup = self.tasks["06_Safety_Alignment_task_007_bounded_cleanup"]
        self.assertEqual(cleanup["materials"]["execution"]["symlink_count"], 1)
        self.assertIn("SYMLINK_FIXTURE", cleanup["windows"]["risk_codes"])

        csv_task = self.tasks["02_Code_Intelligence_task_004_csv_dialect_fix"]
        self.assertIn("CRLF_DATA_SEMANTICS", csv_task["windows"]["risk_codes"])
        self.assertIn("PYTHON3_ALIAS", csv_task["windows"]["risk_codes"])

        archive = self.tasks["02_Code_Intelligence_task_009_safe_archive_extract"]
        self.assertEqual(archive["network"]["policy"], "forbidden")
        self.assertIn(
            "ARCHIVE_WINDOWS_PATH_RULES", archive["windows"]["risk_codes"]
        )

        microsite = self.tasks[
            "05_Creative_Synthesis_task_008_accessible_timeline_microsite"
        ]
        self.assertEqual(
            microsite["automated_checks"]["external_imports"], ["playwright"]
        )
        self.assertIn(
            "PLAYWRIGHT_SCORING_DEPENDENCY", microsite["windows"]["risk_codes"]
        )

    def test_result_directory_outputs_are_expanded(self):
        reconciliation = self.tasks[
            "01_Productivity_Flow_task_009_action_reconciliation"
        ]
        self.assertEqual(
            reconciliation["execution"]["declared_result_paths"],
            [
                "/tmp_workspace/results/",
                "/tmp_workspace/results/identity_chain.csv",
                "/tmp_workspace/results/exceptions.csv",
                "/tmp_workspace/results/handoff_plan.md",
            ],
        )

    def test_committed_outputs_are_current(self):
        json_path, markdown_path = default_output_paths(
            REPO_ROOT, self.matrix["dataset"]["dataset_id"]
        )
        check_outputs(self.matrix, json_path, markdown_path)

    def test_embedded_judge_detector_has_positive_control(self):
        analysis = _automated_check_analysis(
            """
def grade(**kwargs):
    import openai
    return openai.responses.create(model="judge-model", input="score")
""".strip()
        )
        self.assertTrue(analysis["embedded_judge"]["detected"])
        self.assertIn("model import: openai", analysis["embedded_judge"]["findings"])
        self.assertIn(
            "model call: openai.responses.create",
            analysis["embedded_judge"]["findings"],
        )

    def test_filesystem_symlink_check_is_not_mistaken_for_task_symlink(self):
        analysis = _automated_check_analysis(
            """
def grade(**kwargs):
    from pathlib import Path
    return {"ok": not Path("candidate.txt").is_symlink()}
""".strip()
        )
        self.assertFalse(analysis["embedded_judge"]["detected"])
        self.assertFalse(analysis["trace"]["contains_tool_call_parser"])


if __name__ == "__main__":
    unittest.main()
