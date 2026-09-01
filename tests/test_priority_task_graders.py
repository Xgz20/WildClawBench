from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.utils.task_parser import parse_task_md


ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = ROOT / "tasks/extension"
WORKSPACE_ROOT = ROOT / "workspace/extension"

PIPL_TASK = (
    TASK_ROOT
    / "04_Search_Retrieval/04_Search_Retrieval_task_004_pipl_article13_verification.md"
)
PIPL_WORKSPACE = (
    WORKSPACE_ROOT / "04_Search_Retrieval/task_004_pipl_article13_verification"
)
HANDOFF_TASK = (
    TASK_ROOT
    / "03_Social_Interaction/03_Social_Interaction_task_008_incident_handoff_update.md"
)
HANDOFF_WORKSPACE = (
    WORKSPACE_ROOT / "03_Social_Interaction/task_008_incident_handoff_update"
)
COMMUNITY_TASK = (
    TASK_ROOT
    / "03_Social_Interaction/03_Social_Interaction_task_007_community_thread_deescalation.md"
)
COMMUNITY_WORKSPACE = (
    WORKSPACE_ROOT / "03_Social_Interaction/task_007_community_thread_deescalation"
)
RELEASE_TASK = (
    TASK_ROOT
    / "03_Social_Interaction/03_Social_Interaction_task_009_release_expectation_alignment.md"
)
RELEASE_WORKSPACE = (
    WORKSPACE_ROOT / "03_Social_Interaction/task_009_release_expectation_alignment"
)
SUPPORT_TASK = (
    TASK_ROOT
    / "03_Social_Interaction/03_Social_Interaction_task_002_support_ticket_summary.md"
)
SUPPORT_WORKSPACE = (
    WORKSPACE_ROOT / "03_Social_Interaction/task_002_support_ticket_summary"
)
TIMELINE_TASK = (
    TASK_ROOT
    / "05_Creative_Synthesis/05_Creative_Synthesis_task_008_accessible_timeline_microsite.md"
)
TIMELINE_WORKSPACE = (
    WORKSPACE_ROOT / "05_Creative_Synthesis/task_008_accessible_timeline_microsite"
)


def load_grader(task_file: Path):
    namespace: dict = {}
    exec(parse_task_md(task_file)["automated_checks"], namespace)
    return namespace["grade"]


class PriorityTaskGraderTest(unittest.TestCase):
    def test_prompts_publish_new_machine_readable_contracts(self) -> None:
        pipl = parse_task_md(PIPL_TASK)["prompt"]
        handoff = parse_task_md(HANDOFF_TASK)["prompt"]
        community = parse_task_md(COMMUNITY_TASK)["prompt"]
        release = parse_task_md(RELEASE_TASK)["prompt"]

        self.assertIn("JSON整数`1`至`7`", pipl)
        self.assertIn("`action_code,owner,completed_at`", handoff)
        self.assertIn("`elevated_error_rate,cache_pool_saturation", handoff)
        self.assertIn("`temporarily_close`或`keep_open`", community)
        self.assertIn("P01至P04", community)
        self.assertIn("`release_manager_written_approval`", release)
        self.assertIn("只记录工程状态和负责人文件中三个", release)

    def test_pipl_real_result_keeps_business_scores_despite_item_type(self) -> None:
        expected = self._expected(PIPL_WORKSPACE)
        chinese_numbers = ["第一项", "第二项", "第三项", "第四项", "第五项", "第六项", "第七项"]
        bases = []
        for number, wanted in zip(chinese_numbers, expected["legal_bases"]):
            basis = wanted["basis"]
            if wanted["item_number"] in {5, 6}:
                basis = basis.replace("在合理范围内", "在合理的范围内")
            bases.append({
                "item_number": number,
                "basis": basis + "；",
                "requires_consent": wanted["requires_consent"],
            })
        answer = {
            "law_name": expected["law_name"],
            "presidential_order": "第九十一号",
            "adopted_date": expected["adopted_date"],
            "effective_date": expected["effective_date"],
            "legal_bases": bases,
            "source_urls": expected["source_urls"],
        }

        score = self._grade(
            PIPL_TASK,
            PIPL_WORKSPACE,
            {
                "pipl_article13.json": answer,
                "review_note.md": "第十三条有七项处理依据，本说明不构成个案法律意见。",
            },
        )

        self.assertEqual(score["document_identity_and_dates"], 1.0)
        self.assertEqual(score["seven_legal_bases"], 1.0)
        self.assertEqual(score["consent_flags"], 1.0)
        self.assertLess(score["structured_delivery"], 1.0)
        self.assertEqual(score["overall_score"], 0.975)

    def test_pipl_wrong_basis_is_localized_instead_of_zeroing_all(self) -> None:
        expected = self._expected(PIPL_WORKSPACE)
        answer = {
            "law_name": expected["law_name"],
            "presidential_order": expected["presidential_order"],
            "adopted_date": expected["adopted_date"],
            "effective_date": expected["effective_date"],
            "legal_bases": copy.deepcopy(expected["legal_bases"]),
            "source_urls": expected["source_urls"],
        }
        answer["legal_bases"][3]["basis"] = "取得个人同意"

        score = self._grade(
            PIPL_TASK,
            PIPL_WORKSPACE,
            {
                "pipl_article13.json": answer,
                "review_note.md": "核对说明",
            },
        )

        self.assertEqual(score["document_identity_and_dates"], 1.0)
        self.assertEqual(score["consent_flags"], 1.0)
        self.assertEqual(score["seven_legal_bases"], round(6 / 7, 6))
        self.assertGreater(score["overall_score"], 0.9)

    def test_handoff_real_result_accepts_semantic_risks_and_time_aliases(self) -> None:
        expected = self._expected(HANDOFF_WORKSPACE)
        handoff = {
            "incident_id": expected["incident_id"],
            "severity": expected["severity"],
            "status_code": expected["status_code"],
            "resolved": False,
            "latest_monitoring": expected["latest_monitoring"],
            "completed_actions": [{
                "action_code": "rollback_release",
                "owner": "SRE-CUR",
                "status": "completed",
                "at": "2026-09-15T21:26:00Z",
            }],
            "pending_actions": [
                {"action_code": item["action_code"], "owner": item["owner"], "due": item["due_at"]}
                for item in expected["pending_actions"]
            ],
            "active_risks": [
                "checkout error rate 1.3% remains above the 0.8% gate",
                "cache pool still saturated",
                "payment reconciliation not complete; payment impact unquantified",
            ],
            "unconfirmed_hypotheses": [
                "release 4.18.0 regression may be the cause but is not confirmed"
            ],
        }

        score = self._grade(
            HANDOFF_TASK,
            HANDOFF_WORKSPACE,
            {
                "handoff.json": handoff,
                "handoff_message.md": "SEV-2 handoff remains open with three pending actions.",
            },
        )

        self.assertEqual(score["latest_state_reconciled"], 1.0)
        self.assertEqual(score["completed_and_pending_actions"], 1.0)
        self.assertEqual(score["evidence_uncertainty_separated"], 1.0)
        self.assertEqual(score["overall_score"], 0.975)

    def test_community_real_result_is_not_bound_to_hidden_rows_or_enums(self) -> None:
        plan = {
            "thread_id": "COMM-184",
            "thread_action": "temporarily_closed",
            "closure_hours": 4,
            "reopen_conditions": [
                "All flagged posts have been reviewed.",
                "Required content actions are complete.",
                "Flags on reviewed posts are cleared.",
                "A staff public notice has been posted.",
                "At least four hours have elapsed.",
            ],
            "post_actions": [
                {
                    "post_id": "P02",
                    "rule_id": "R1",
                    "content_action": "remove_post",
                    "user_action": "formal_warning",
                },
                {
                    "post_id": "P03",
                    "rule_id": "R1",
                    "content_action": "remove_post",
                    "user_action": "friendly_reminder",
                },
            ],
        }

        score = self._grade(
            COMMUNITY_TASK,
            COMMUNITY_WORKSPACE,
            {
                "moderation_plan.json": plan,
                "public_notice.md": "Return to the release-note topic.",
                "private_messages.md": "Draft messages for U02 and U03.",
            },
        )

        self.assertEqual(score["violation_classification"], 1.0)
        self.assertEqual(score["proportionate_actions"], 1.0)
        self.assertEqual(score["thread_control_and_delivery"], 0.875)
        self.assertEqual(score["overall_score"], 0.9625)

    def test_release_real_result_uses_candidate_approval_evidence(self) -> None:
        expected = self._expected(RELEASE_WORKSPACE)
        alignment = {
            "account_id": expected["account_id"],
            "commitment_status_code": "TARGET_ONLY_NOT_COMMITTED",
            "previous_target_date": expected["previous_target_date"],
            "conditional_internal_window": expected["conditional_internal_window"],
            "next_customer_update_at": expected["next_customer_update_at"],
            "blocking_gates": [
                *expected["blocking_gates"],
                {
                    "gate_id": "release_manager_written_approval",
                    "status": "pending",
                    "owner": "Release Manager",
                    "due_at": None,
                },
            ],
        }

        score = self._grade(
            RELEASE_TASK,
            RELEASE_WORKSPACE,
            {
                "release_alignment.json": alignment,
                "customer_update.md": "No production date is committed.",
                "internal_alignment.md": "All gates and written approval remain pending.",
            },
        )

        self.assertEqual(score["facts_and_gate_state"], 1.0)
        self.assertEqual(score["commitment_boundary_decision"], 1.0)
        self.assertEqual(score["actions_owners_dates"], 1.0)
        self.assertEqual(score["overall_score"], 0.9625)

    def test_release_wrong_candidate_approval_loses_boundary_credit(self) -> None:
        expected = self._expected(RELEASE_WORKSPACE)
        alignment = {
            key: expected[key]
            for key in (
                "account_id",
                "commitment_status_code",
                "previous_target_date",
                "conditional_internal_window",
                "next_customer_update_at",
                "blocking_gates",
            )
        }
        alignment["release_manager_written_approval"] = True

        score = self._grade(
            RELEASE_TASK,
            RELEASE_WORKSPACE,
            {
                "release_alignment.json": alignment,
                "customer_update.md": "No date is committed.",
                "internal_alignment.md": "Approval is pending.",
            },
        )

        self.assertEqual(score["commitment_boundary_decision"], round(2 / 3, 6))

    def test_support_question_is_not_a_resolution_claim(self) -> None:
        answer = self._support_answer(
            "请您安排相关同事重新尝试登录，并告知我们是否恢复正常。如果仍有问题，"
            "请随时回复，我们会继续跟进。"
        )

        score = self._grade(
            SUPPORT_TASK,
            SUPPORT_WORKSPACE,
            {"support_summary.json": answer},
        )

        self.assertEqual(score["reply_draft_quality"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_support_affirmative_resolution_claim_still_fails(self) -> None:
        answer = self._support_answer(
            "问题已解决，服务已经恢复正常。请您安排相关同事完成复测并回复结果，"
            "如果仍有其他情况请一并说明，我们会继续跟进。"
        )

        score = self._grade(
            SUPPORT_TASK,
            SUPPORT_WORKSPACE,
            {"support_summary.json": answer},
        )

        self.assertEqual(score["reply_draft_quality"], 0.75)
        self.assertEqual(score["overall_score"], 0.95)

    def test_support_instruction_to_claim_resolution_is_not_a_question(self) -> None:
        answer = self._support_answer(
            "请告知客户问题已解决，并请相关同事完成复测后回复结果，我们会继续跟进。"
        )

        score = self._grade(
            SUPPORT_TASK,
            SUPPORT_WORKSPACE,
            {"support_summary.json": answer},
        )

        self.assertEqual(score["reply_draft_quality"], 0.75)

    def test_timeline_browser_observation_drives_behavior_scores(self) -> None:
        observation = self._valid_timeline_observation()
        score = self._grade(
            TIMELINE_TASK,
            TIMELINE_WORKSPACE,
            {"index.html": self._timeline_html()},
            _browser_probe=lambda _path, _expected: observation,
        )
        self.assertEqual(score["overall_score"], 1.0)

        broken = copy.deepcopy(observation)
        broken["enterResults"][2] = False
        broken_score = self._grade(
            TIMELINE_TASK,
            TIMELINE_WORKSPACE,
            {"index.html": self._timeline_html()},
            _browser_probe=lambda _path, _expected: broken,
        )
        self.assertEqual(broken_score["keyboard_behavior"], 0.75)
        self.assertLess(broken_score["overall_score"], 1.0)

    def _expected(self, workspace: Path) -> dict:
        return json.loads((workspace / "gt/expected.json").read_text(encoding="utf-8"))

    def _grade(
        self,
        task_file: Path,
        workspace: Path,
        outputs: dict[str, object],
        **kwargs,
    ) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gt").mkdir()
            (root / "results").mkdir()
            shutil.copy2(workspace / "gt/expected.json", root / "gt/expected.json")
            for source in (workspace / "exec").iterdir():
                if source.is_file():
                    shutil.copy2(source, root / source.name)
            for name, value in outputs.items():
                path = root / "results" / name
                if isinstance(value, (dict, list)):
                    path.write_text(
                        json.dumps(value, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                else:
                    path.write_text(str(value), encoding="utf-8")
            return load_grader(task_file)(workspace_path=str(root), **kwargs)

    def _support_answer(self, reply: str) -> dict:
        return {
            "ticket_id": "SUP-CN-1042",
            "product": "云笺企业版",
            "priority": "P2",
            "affected_users": 8,
            "status_code": "awaiting_customer_retest",
            "next_action_code": "ask_customer_retest",
            "issue_summary": (
                "8名用户遭遇SSO登录循环，工程师已修正配置，仍需客户复测，"
                "尚不能确认问题已解决。"
            ),
            "customer_reply_draft": reply,
        }

    def _timeline_html(self) -> str:
        events = self._expected(TIMELINE_WORKSPACE)["events"]
        content = "\n".join(
            f"<section>{event['id']} {event['date']} {event['title']} {event['description']}</section>"
            for event in events
        )
        return (
            "<!doctype html><html><head><style>body{margin:0}</style></head>"
            f"<body><main><h1>Timeline</h1>{content}</main></body></html>"
        )

    def _valid_timeline_observation(self) -> dict:
        size = len(self._expected(TIMELINE_WORKSPACE)["events"])
        return {
            "mapped": [True] * size,
            "semantics": [True] * size,
            "eventFlags": [True] * size,
            "positions": list(range(size)),
            "eventCounts": [1] * size,
            "semanticOutline": True,
            "networkUrls": [],
            "pageErrors": [],
            "initialCollapsed": True,
            "tabOrder": True,
            "focusVisible": [True] * size,
            "enterResults": [True] * size,
            "spaceResults": [True] * size,
            "reducedMotion": True,
            "mobileFits": True,
        }


if __name__ == "__main__":
    unittest.main()
