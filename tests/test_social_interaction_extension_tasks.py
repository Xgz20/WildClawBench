"""Executable checks for the seven remaining Social Interaction extension tasks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
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


CATEGORY = "03_Social_Interaction"
TASKS = {
    "03_Social_Interaction_task_003_colleague_leave_reply": (
        "03_Social_Interaction_task_003_colleague_leave_reply.md",
        "task_003_colleague_leave_reply",
    ),
    "03_Social_Interaction_task_004_angry_customer_first_response": (
        "03_Social_Interaction_task_004_angry_customer_first_response.md",
        "task_004_angry_customer_first_response",
    ),
    "03_Social_Interaction_task_006_interview_slot_coordination": (
        "03_Social_Interaction_task_006_interview_slot_coordination.md",
        "task_006_interview_slot_coordination",
    ),
    "03_Social_Interaction_task_007_community_thread_deescalation": (
        "03_Social_Interaction_task_007_community_thread_deescalation.md",
        "task_007_community_thread_deescalation",
    ),
    "03_Social_Interaction_task_008_incident_handoff_update": (
        "03_Social_Interaction_task_008_incident_handoff_update.md",
        "task_008_incident_handoff_update",
    ),
    "03_Social_Interaction_task_009_release_expectation_alignment": (
        "03_Social_Interaction_task_009_release_expectation_alignment.md",
        "task_009_release_expectation_alignment",
    ),
    "03_Social_Interaction_task_010_vendor_delay_stakeholder_comms": (
        "03_Social_Interaction_task_010_vendor_delay_stakeholder_comms.md",
        "task_010_vendor_delay_stakeholder_comms",
    ),
}

AUTO_TASK_IDS = tuple(task_id for task_id in TASKS if "task_00" in task_id and task_id.split("_task_")[1][:3] in {"006", "007", "008", "009"}) + (
    "03_Social_Interaction_task_010_vendor_delay_stakeholder_comms",
)

EXPECTED_METADATA = {
    "03_Social_Interaction_task_003_colleague_leave_reply": ("L1", "llm_judge", 0.0, 1.0),
    "03_Social_Interaction_task_004_angry_customer_first_response": ("L1", "llm_judge", 0.0, 1.0),
    "03_Social_Interaction_task_006_interview_slot_coordination": ("L2", "hybrid", 0.7, 0.3),
    "03_Social_Interaction_task_007_community_thread_deescalation": ("L2", "hybrid", 0.4, 0.6),
    "03_Social_Interaction_task_008_incident_handoff_update": ("L3", "hybrid", 0.4, 0.6),
    "03_Social_Interaction_task_009_release_expectation_alignment": ("L3", "hybrid", 0.4, 0.6),
    "03_Social_Interaction_task_010_vendor_delay_stakeholder_comms": ("L4", "hybrid", 0.4, 0.6),
}

EXPECTED_JUDGE_WEIGHTS = {
    "03_Social_Interaction_task_003_colleague_leave_reply": {
        "context_and_request_coverage": 0.25,
        "empathy_and_role_fit": 0.25,
        "privacy_and_commitment_boundary": 0.30,
        "ready_to_send": 0.20,
    },
    "03_Social_Interaction_task_004_angry_customer_first_response": {
        "concern_acknowledgement": 0.15,
        "deescalation": 0.20,
        "safe_containment": 0.20,
        "diagnostic_questions": 0.20,
        "support_boundaries": 0.15,
        "first_reply_readiness": 0.10,
    },
    "03_Social_Interaction_task_006_interview_slot_coordination": {
        "candidate_message_fidelity": 0.40,
        "candidate_message_readiness": 0.60,
    },
    "03_Social_Interaction_task_007_community_thread_deescalation": {
        "public_notice_quality": 0.40,
        "private_message_quality": 0.35,
        "neutrality_and_deescalation": 0.25,
    },
    "03_Social_Interaction_task_008_incident_handoff_update": {
        "handoff_prioritization": 0.55,
        "operational_caution": 0.45,
    },
    "03_Social_Interaction_task_009_release_expectation_alignment": {
        "customer_update_quality": 0.55,
        "alignment_note_quality": 0.45,
    },
    "03_Social_Interaction_task_010_vendor_delay_stakeholder_comms": {
        "decision_brief_quality": 0.40,
        "stakeholder_tailoring": 0.40,
        "uncertainty_and_escalation": 0.20,
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


def load_expected(root: Path) -> dict:
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
        float(value)
        for key, value in scores.items()
        if key != "overall_score"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ]
    return sum(values) / len(values) if values else 0.0


def write_full(task_id: str, root: Path) -> None:
    expected = load_expected(root)
    results = root / "results"
    results.mkdir()
    if task_id.endswith("interview_slot_coordination"):
        plan = {
            key: expected[key]
            for key in (
                "request_id", "proposed_start", "proposed_end", "timezone",
                "duration_minutes", "interviewer_ids", "host_count", "status",
            )
        }
        plan["selection_reason"] = "候选人的首个可行时段；主持人按当前分配量和轮值顺序选择。"
        (results / "interview_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (results / "candidate_reply.md").write_text(
            "周岚你好，建议将面试安排在2026年9月8日09:00–09:45（北京时间，Asia/Shanghai）。"
            "目前该时段仍待你确认，请回复是否方便；如不合适，我们再从你提供的其他时段协调。\n",
            encoding="utf-8",
        )
    elif task_id.endswith("community_thread_deescalation"):
        plan = {key: expected[key] for key in expected["plan_fields"]}
        (results / "moderation_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (results / "public_notice.md").write_text(
            "本讨论已出现针对参与者的人身评价，不符合R1。建议暂时关闭4小时。完成旗标审核、"
            "相应内容处理、清除旗标并发布工作人员说明后可重开。请继续讨论发布说明中实验标记的呈现方式，"
            "针对观点而不是参与者。此内容为待审核草稿。\n",
            encoding="utf-8",
        )
        (results / "private_messages.md").write_text(
            "## P02作者\n你的P02包含针对参与者的直接侮辱，违反R1。鉴于30天内已有一次同类记录，"
            "本草案建议移除内容并作正式警告。后续请只讨论观点。\n\n"
            "## P03作者\n你的P03以人身评价回应他人，违反R1。本次为首次记录，草案建议移除内容并友好提醒。"
            "请将意见改写为对方案本身的讨论。\n",
            encoding="utf-8",
        )
    elif task_id.endswith("incident_handoff_update"):
        handoff = {
            key: expected[key]
            for key in expected["handoff_fields"]
        }
        (results / "handoff.json").write_text(
            json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (results / "handoff_message.md").write_text(
            "INC-742 remains SEV-2, mitigated/monitoring, and is not resolved. Rollback completed at 21:26 UTC. "
            "The 21:48 snapshot shows 1.3% checkout errors versus a 0.4% baseline; the cache pool is still saturated. "
            "Next: CACHE-SRE inspect the cache pool by 22:15; SRE-NEXT watch the two-window error gate by 22:20; "
            "PAY-ONCALL reconcile payments by 22:30. Release 4.18.0 is only a suspected cause. Payment impact remains "
            "unconfirmed, and the resolution gate is unmet because there are no qualifying windows and reconciliation is incomplete.\n",
            encoding="utf-8",
        )
    elif task_id.endswith("release_expectation_alignment"):
        alignment = {
            key: expected[key]
            for key in expected["alignment_fields"]
        }
        (results / "release_alignment.json").write_text(
            json.dumps(alignment, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (results / "customer_update.md").write_text(
            "我们理解此前9月18日的工作目标被视为上线预期。目前尚没有已批准的上线日期；"
            "9月24日20:00也只是内部最早条件性窗口，不是承诺。我们会在9月18日17:00前提供下一次状态更新，"
            "说明安全审查、负载测试和回滚演练的进展。\n",
            encoding="utf-8",
        )
        (results / "internal_alignment.md").write_text(
            "统一口径：9月18日是此前工作目标，9月24日为条件性内部窗口，均非客户承诺。"
            "SEC-LEAD、PERF-LEAD、SRE-LEAD分别按表中期限完成安全审查、4倍负载测试和回滚演练；"
            "发布经理书面批准前不承诺日期。客户下一次更新截止9月18日17:00，沟通保持中性。\n",
            encoding="utf-8",
        )
    elif task_id.endswith("vendor_delay_stakeholder_comms"):
        plan = {
            key: expected[key]
            for key in expected["plan_fields"]
        }
        (results / "impact_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (results / "decision_brief.md").write_text(
            "建议缩小试点至120件、首批600件加急并采购备选200件，不使用120件支持库存。"
            "增量成本13,900元，需Program Director和CFO批准。10月16日前预计可用920件，区域上线仍以QA和批准完成为条件；"
            "10月23日GA在全部1,200件到货、QA和最终批准前不承诺。\n",
            encoding="utf-8",
        )
        (results / "vendor_escalation_draft.md").write_text(
            "请书面确认首批600件10月10日发货及预计10月13日到货，并提供余下600件的到货承诺。"
            "若首批发货、预计到货或10月15日QA节点偏离，或10月16日前仍无余批到货承诺，我们将升级处理。\n",
            encoding="utf-8",
        )
        (results / "internal_update.md").write_text(
            "当前建议成本13,900元，等待Program Director和CFO批准。试点缩至120件；区域上线取决于920件完成QA及批准。"
            "GA未承诺。负责人应跟踪首批发货、到货、QA和余批到货承诺四个触发点。\n",
            encoding="utf-8",
        )
        (results / "customer_update.md").write_text(
            "关键硬件供应计划发生变化，我们正在通过缩小试点和补充供货降低影响。区域上线仍取决于硬件到货、QA和内部批准；"
            "10月23日全面上线目前尚未确认。我们会在供应商和QA节点更新后提供下一次状态说明。\n",
            encoding="utf-8",
        )


def write_partial(task_id: str, root: Path) -> None:
    write_full(task_id, root)
    expected = load_expected(root)
    results = root / "results"
    if task_id.endswith("interview_slot_coordination"):
        path = results / "interview_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["interviewer_ids"] = expected["interviewer_ids"][:2]
        data["host_count"] = 2
    elif task_id.endswith("community_thread_deescalation"):
        path = results / "moderation_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["post_actions"][1]["user_action"] = "friendly_reminder"
    elif task_id.endswith("incident_handoff_update"):
        path = results / "handoff.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["latest_monitoring"]["checkout_error_rate_percent"] = 0.7
        data["pending_actions"] = data["pending_actions"][:2]
    elif task_id.endswith("release_expectation_alignment"):
        path = results / "release_alignment.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["blocking_gates"] = data["blocking_gates"][:2]
    else:
        path = results / "impact_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["total_incremental_cost_cny"] = 8400
        data["trigger_conditions"] = data["trigger_conditions"][:2]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SocialInteractionExtensionTaskTest(unittest.TestCase):
    def test_metadata_matches_design_matrix_and_group_weights(self):
        for task_id, wanted in EXPECTED_METADATA.items():
            with self.subTest(task_id=task_id):
                difficulty, grading_type, auto_weight, judge_weight = wanted
                actual = metadata(task_id)
                self.assertEqual(actual["difficulty"], difficulty)
                self.assertEqual(actual["grading_type"], grading_type)
                self.assertAlmostEqual(actual["grading_weights"]["automated"], auto_weight)
                self.assertAlmostEqual(actual["grading_weights"]["llm_judge"], judge_weight)

    def test_static_validator_accepts_current_repository(self):
        self.assertEqual(validate_repository(REPO_ROOT, allow_incomplete=True), [])
        strict = validate_repository(REPO_ROOT)
        self.assertEqual([issue for issue in strict if issue.code != "task.missing"], [])
        registry = yaml.safe_load(
            (REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8")
        )
        registered_ids = {item["task_id"] for item in registry["tasks"]}
        present_ids = {path.stem for path in (REPO_ROOT / "tasks/extension").glob("*/*.md")}
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
                    with tempfile.TemporaryDirectory(prefix="social-grade-") as temporary:
                        root = Path(temporary)
                        copy_workspace(task_id, root)
                        if tier == "full":
                            write_full(task_id, root)
                        elif tier == "partial":
                            write_partial(task_id, root)
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
                    wanted = {f"llm_judge.{key}" for key in judge_keys}
                self.assertEqual(set(mapping[task_id]), wanted)
                capabilities = {label for labels in mapping[task_id].values() for label in labels}
                self.assertGreaterEqual(len(capabilities), 2)
                self.assertLessEqual(len(capabilities), 4)
                self.assertTrue(all(1 <= len(labels) <= 2 for labels in mapping[task_id].values()))

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
                declared = expected.get("exec_file_sha256", {})
                self.assertEqual(set(attachments), set(declared))
                total_size = 0
                for relative, path in attachments.items():
                    total_size += path.stat().st_size
                    self.assertFalse(path.is_symlink())
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), declared[relative])
                    self.assertNotIn(path.suffix.lower(), {".html", ".htm", ".mhtml", ".pdf"})
                self.assertLessEqual(total_size, metadata(task_id)["attachment_size_limit_mb"] * 1024 * 1024)

    def test_sources_and_prompts_have_no_runtime_network_dependency(self):
        registry = yaml.safe_load(
            (REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8")
        )
        records = {item["task_id"]: item for item in registry["tasks"] if item["task_id"] in TASKS}
        self.assertEqual(set(records), set(TASKS))
        for task_id, record in records.items():
            with self.subTest(task_id=task_id):
                self.assertEqual(record["runtime_sources"], [])
                prompt = parse_task_md(task_path(task_id))["prompt"]
                self.assertNotIn("http://", prompt)
                self.assertNotIn("https://", prompt)

    def test_report_and_low_score_tools_discover_all_tasks(self):
        report = load_module(
            "social_interaction_report",
            REPO_ROOT / "tools/report/scripts/generate_eval_report.py",
        )
        manifest = load_module(
            "social_interaction_manifest",
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

    def test_prompts_are_user_facing_and_result_paths_are_bounded(self):
        forbidden = ("评分点", "能力维度", "LLM Judge", "Auto评分", "评测框架")
        prompt_only = {
            "03_Social_Interaction_task_003_colleague_leave_reply",
            "03_Social_Interaction_task_004_angry_customer_first_response",
        }
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                prompt = parse_task_md(task_path(task_id))["prompt"]
                self.assertFalse(any(term in prompt for term in forbidden))
                self.assertNotIn("/tmp_workspace/result/", prompt)
                if task_id not in prompt_only:
                    self.assertIn("/tmp_workspace/results/", prompt)


if __name__ == "__main__":
    unittest.main()
