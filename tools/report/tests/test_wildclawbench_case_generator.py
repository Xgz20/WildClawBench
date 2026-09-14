from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml

from src.utils.task_parser import parse_task_md


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / "tools"
    / "report"
    / "skills"
    / "wildclawbench-case-generator"
    / "scripts"
    / "assemble_case.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("wcb_case_generator", SCRIPT)
assert MODULE_SPEC and MODULE_SPEC.loader
generator = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(generator)


def automated_spec() -> dict:
    return {
        "name": "本地事实摘要",
        "category": "01_Productivity_Flow",
        "slug": "local_fact_summary",
        "timeout_seconds": 180,
        "difficulty": "L2",
        "grading_type": "automated",
        "prompt": "读取已有材料并将摘要写入 /tmp_workspace/results/summary.md。",
        "expected_behavior": "忠实提取事实并交付结构化摘要。",
        "grading_criteria": {
            "automated": [
                {"key": "summary_exists", "description": "摘要文件存在且非空"}
            ],
            "llm_judge": [],
        },
        "automated_checks": """def grade(**kwargs) -> dict:
    score = 1.0
    return {"summary_exists": score, "overall_score": score}
""",
        "llm_judge_rubric": [],
        "skills": [],
        "env": [],
        "warmup": [],
        "workspace": {"exec": [], "gt": []},
        "source": {
            "design_origin": {
                "type": "constructed",
                "verification_status": "constructed_from_user_query",
                "human_authorship": "user_provided",
                "request_summary": "把本地材料整理成摘要。",
                "adaptation_note": "收敛输出位置并增加可判定的文件检查。",
                "references": [],
            },
            "runtime_sources": [],
        },
        "checkpoint_capabilities": {
            "summary_exists": ["verification_delivery"]
        },
    }


class WildClawBenchCaseGeneratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        (self.repo / "tasks" / "extension" / "01_Productivity_Flow").mkdir(
            parents=True
        )
        (self.repo / "tasks" / "01_Productivity_Flow").mkdir(parents=True)
        (self.repo / "tasks" / "TASK_TEMPLATE_v2.md").write_text(
            "template", encoding="utf-8"
        )
        (self.repo / "src" / "utils").mkdir(parents=True)
        (self.repo / "src" / "utils" / "task_parser.py").write_text(
            "# marker\n", encoding="utf-8"
        )
        registry = {
            "schema_version": 1,
            "registry_contract": {
                "active_task_count": 1,
                "category_task_counts": {
                    "01_Productivity_Flow": 1,
                    "02_Code_Intelligence": 0,
                    "03_Social_Interaction": 0,
                    "04_Search_Retrieval": 0,
                    "05_Creative_Synthesis": 0,
                    "06_Safety_Alignment": 0,
                },
                "reserved_invalid_short_ids": ["01-002"],
            },
            "tasks": [
                {
                    "short_id": "01-001",
                    "task_id": "01_Productivity_Flow_task_001_existing",
                    "design_origin": {},
                    "runtime_sources": [],
                }
            ],
            "excluded_tasks": [
                {
                    "short_id": "01-002",
                    "task_id": "01_Productivity_Flow_task_002_removed",
                    "status": "invalid",
                    "number_reserved": True,
                }
            ],
        }
        self.registry_path = self.repo / "tasks" / "extension" / "task_sources.yaml"
        self.registry_path.write_text(
            yaml.safe_dump(registry, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        (self.repo / "tasks" / "extension" / "01_Productivity_Flow" / "01_Productivity_Flow_task_101_local.md").write_text(
            "local fixture", encoding="utf-8"
        )
        self.map_path = (
            self.repo
            / "tools"
            / "report"
            / "data"
            / "checkpoint_capability_map7.yaml"
        )
        self.map_path.parent.mkdir(parents=True)
        self.map_path.write_text(
            "01_Productivity_Flow_task_001_existing:\n"
            "  existing: [verification_delivery]\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_assigns_lowest_unoccupied_number_and_registers_all_artifacts(self):
        result = generator.assemble_case(
            automated_spec(),
            repo_root=self.repo,
            spec_dir=self.repo,
            run_validation=False,
        )

        self.assertEqual(
            result["task_id"], "01_Productivity_Flow_task_003_local_fact_summary"
        )
        task = Path(result["task_path"])
        workspace = Path(result["workspace_path"])
        self.assertTrue(task.is_file())
        self.assertTrue((workspace / "exec" / ".gitkeep").is_file())
        self.assertTrue((workspace / "gt" / ".gitkeep").is_file())
        content = task.read_text(encoding="utf-8")
        self.assertIn("grading_type: automated", content)
        self.assertIn("## LLM Judge Rubric\n\n## Workspace Path", content)
        self.assertIn("## Skills\n\n## Env", content)
        self.assertIn("## Env\n\n## Warmup", content)
        registry = yaml.safe_load(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(registry["registry_contract"]["active_task_count"], 2)
        self.assertEqual(
            registry["registry_contract"]["category_task_counts"][
                "01_Productivity_Flow"
            ],
            2,
        )
        self.assertEqual(registry["tasks"][-1]["short_id"], "01-003")
        capability_map = yaml.safe_load(self.map_path.read_text(encoding="utf-8"))
        self.assertEqual(
            capability_map[result["task_id"]],
            {"summary_exists": ["verification_delivery"]},
        )

    def test_hybrid_requires_prefixed_capability_keys_and_renders_rubric(self):
        spec = automated_spec()
        spec["grading_type"] = "hybrid"
        spec["grading_weights"] = {"automated": 0.6, "llm_judge": 0.4}
        spec["grading_criteria"]["llm_judge"] = [
            {"key": "factual_quality", "description": "事实表达准确清晰"}
        ]
        spec["llm_judge_rubric"] = [
            {
                "key": "factual_quality",
                "name": "事实质量",
                "weight": 1.0,
                "description": "摘要是否忠实且可追溯。",
                "levels": [
                    {"score": 1.0, "description": "事实完整准确并可追溯。"},
                    {"score": 0.5, "description": "存在少量遗漏但无关键错误。"},
                    {"score": 0.0, "description": "关键事实错误或没有交付。"},
                ],
            }
        ]
        spec["checkpoint_capabilities"] = {
            "automated.summary_exists": ["verification_delivery"],
            "llm_judge.factual_quality": ["data_processing"],
        }

        normalized = generator.normalize_spec(
            spec, repo_root=self.repo, spec_dir=self.repo
        )
        content = generator.render_task(
            normalized,
            "01_Productivity_Flow_task_003_local_fact_summary",
            "workspace/extension/01_Productivity_Flow/task_003_local_fact_summary",
        )

        self.assertIn(
            "### Criterion 1: 事实质量 (key: factual_quality, weight: 1.0)", content
        )
        self.assertNotIn("primary:", content)
        self.assertIn("automated: 0.6", content)
        self.assertIn("tags:\n  - custom", content)
        self.assertIn("**Score 1.0**", content)
        self.assertIn("**Score 0.0**", content)
        task_path = (
            self.repo
            / "tasks"
            / "extension"
            / "01_Productivity_Flow"
            / "01_Productivity_Flow_task_003_local_fact_summary.md"
        )
        task_path.write_text(content, encoding="utf-8")
        parsed = parse_task_md(task_path)
        self.assertEqual(parsed["grading_type"], "hybrid")
        self.assertEqual(
            [criterion["key"] for criterion in parsed["rubric_criteria"]],
            ["factual_quality"],
        )

    def test_rejects_specialized_tags_and_missing_prompt_inputs(self):
        web_spec = automated_spec()
        web_spec["tags"] = ["custom", "web-site-gen"]
        with self.assertRaisesRegex(generator.SpecError, "专项 tag"):
            generator.normalize_spec(web_spec, repo_root=self.repo, spec_dir=self.repo)

        missing_input = automated_spec()
        missing_input["prompt"] = (
            "读取 /tmp_workspace/input.csv 并写入 /tmp_workspace/results/summary.md。"
        )
        with self.assertRaisesRegex(generator.SpecError, "workspace.exec"):
            generator.assemble_case(
                missing_input,
                repo_root=self.repo,
                spec_dir=self.repo,
                dry_run=True,
                run_validation=False,
            )

    def test_rejects_missing_declared_prerequisites_and_network_grader(self):
        missing_skill = automated_spec()
        missing_skill["skills"] = ["not-installed-for-test"]
        with self.assertRaisesRegex(generator.SpecError, "声明的 Skill 不存在"):
            generator.normalize_spec(
                missing_skill, repo_root=self.repo, spec_dir=self.repo
            )

        missing_env = automated_spec()
        missing_env["env"] = ["WCB_CASE_GENERATOR_TEST_MISSING_ENV_7F32"]
        with self.assertRaisesRegex(generator.SpecError, "当前环境缺少声明的 Env"):
            generator.normalize_spec(
                missing_env, repo_root=self.repo, spec_dir=self.repo
            )

        network_grader = automated_spec()
        network_grader["automated_checks"] = """def grade(**kwargs) -> dict:
    import requests
    return {"summary_exists": 1.0, "overall_score": 1.0}
"""
        with self.assertRaisesRegex(generator.SpecError, "禁止导入"):
            generator.normalize_spec(
                network_grader, repo_root=self.repo, spec_dir=self.repo
            )

    def test_rolls_back_every_file_when_final_validation_fails(self):
        validator = (
            self.repo
            / "tools"
            / "report"
            / "skills"
            / "validate-eval-dataset"
            / "scripts"
            / "validate_eval_dataset.py"
        )
        validator.parent.mkdir(parents=True)
        validator.write_text(
            "import sys\nprint('intentional validation failure')\nsys.exit(1)\n",
            encoding="utf-8",
        )
        registry_before = self.registry_path.read_bytes()
        map_before = self.map_path.read_bytes()

        with self.assertRaisesRegex(generator.SpecError, "已回滚"):
            generator.assemble_case(
                automated_spec(),
                repo_root=self.repo,
                spec_dir=self.repo,
                run_validation=True,
            )

        self.assertEqual(self.registry_path.read_bytes(), registry_before)
        self.assertEqual(self.map_path.read_bytes(), map_before)
        self.assertFalse(
            (
                self.repo
                / "tasks"
                / "extension"
                / "01_Productivity_Flow"
                / "01_Productivity_Flow_task_003_local_fact_summary.md"
            ).exists()
        )
        self.assertFalse(
            (
                self.repo
                / "workspace"
                / "extension"
                / "01_Productivity_Flow"
                / "task_003_local_fact_summary"
            ).exists()
        )


class WildClawBenchCaseGeneratorDistributionTest(unittest.TestCase):
    def test_codex_and_claude_links_are_relative_and_resolve_to_source(self):
        source = (
            REPO_ROOT
            / "tools"
            / "report"
            / "skills"
            / "wildclawbench-case-generator"
        ).resolve()
        for relative in (
            ".agents/skills/wildclawbench-case-generator",
            ".claude/skills/wildclawbench-case-generator",
        ):
            with self.subTest(relative=relative):
                link = REPO_ROOT / relative
                self.assertTrue(link.is_symlink())
                self.assertFalse(Path(link.readlink()).is_absolute())
                self.assertEqual(link.resolve(), source)


if __name__ == "__main__":
    unittest.main()
