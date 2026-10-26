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


class RegisteredCaseGeneratorTest(unittest.TestCase):
    """Reuse the legacy fixture to prove writes stay in the new family."""

    def setUp(self) -> None:
        WildClawBenchCaseGeneratorTest.setUp(self)
        self.base = self.repo / "datasets/sample"
        self.base.mkdir(parents=True)
        self.task_id = "sample_research_task_001_local_fact_summary"
        self.family = {
            "schema_version": 1, "series_id": "sample", "task_id_prefix": "sample_",
            "task_root": "datasets/sample/tasks", "workspace_root": "datasets/sample/workspace",
            "source_registry": "datasets/sample/task_sources.yaml", "capability_map": "datasets/sample/checkpoint_capability_map7.yaml",
            "required_tags": ["custom", "sample"], "exclude_tags": ["invalid"],
            "categories": {"research": {"name": "研究"}}, "default_release": "sample-v1",
            "releases": {"sample-v1": {"status": "building", "created_at": "2026-10-26T00:00:00+08:00",
                "manifest": "datasets/sample/manifests/sample-v1.json", "task_ids": [self.task_id],
                "expected_statistics": {"task_count": 1, "category_counts": {"research": 1},
                    "grading_type_counts": {"automated": 1}, "difficulty_counts": {"L2": 1}, "timeout_counts": {"180": 1}}}},
        }
        self.save_family()
        (self.repo / "datasets/catalog.yaml").write_text(yaml.safe_dump({"schema_version": 1,
            "datasets": {"sample": {"definition": "datasets/sample/dataset.yaml"}}}), encoding="utf-8")
        (self.repo / "input.md").write_text("甲的数值为2。", encoding="utf-8")
        (self.repo / "expected.json").write_text('{"value": 2}', encoding="utf-8")

    def save_family(self) -> None:
        (self.base / "dataset.yaml").write_text(yaml.safe_dump(self.family, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def tearDown(self) -> None:
        WildClawBenchCaseGeneratorTest.tearDown(self)

    def spec(self) -> dict:
        spec = automated_spec()
        spec.update({"dataset_id": "sample", "category": "research",
            "prompt": "读取 /tmp_workspace/input.md，在 /tmp_workspace/results/summary.md 写事实摘要。",
            "workspace": {"exec": [{"source": "input.md", "target": "input.md"}],
                          "gt": [{"source": "expected.json", "target": "expected.json"}]},
            "judge_evidence": {"required": [{"path": "results/summary.md", "role": "candidate_deliverable"}]},
            "source": {"origin": {"mode": "constructed", "production_refs": []}, "network": {"mode": "offline"},
                       "attributes": {"requires_visual_input": False, "coding_primary": False, "retrieval_group": "local_evidence"}}})
        return spec

    def install_validator_wrapper(self, *, fail: bool = False) -> None:
        target = self.repo / "tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        source = REPO_ROOT / "tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py"
        code = ("raise SystemExit(1)\n" if fail else
                "import sys, runpy\nsys.path.insert(0, " + repr(str(REPO_ROOT)) + ")\nrunpy.run_path(" + repr(str(source)) + ", run_name='__main__')\n")
        target.write_text(code, encoding="utf-8")

    def test_registered_dry_run_is_read_only_and_uses_the_planned_namespace(self):
        before = (self.registry_path.read_bytes(), self.map_path.read_bytes())
        result = generator.assemble_case(self.spec(), repo_root=self.repo, spec_dir=self.repo, dry_run=True)
        self.assertEqual(result["task_id"], self.task_id)
        self.assertEqual(Path(result["workspace_path"]), (self.base / "workspace/research" / self.task_id).resolve())
        self.assertFalse((self.base / "task_sources.yaml").exists())
        self.assertFalse((self.base / "tasks").exists())
        self.assertEqual(before, (self.registry_path.read_bytes(), self.map_path.read_bytes()))

    def test_registered_creation_passes_the_real_validator_and_preserves_legacy_sources(self):
        before = (self.registry_path.read_bytes(), self.map_path.read_bytes())
        self.install_validator_wrapper()
        result = generator.assemble_case(self.spec(), repo_root=self.repo, spec_dir=self.repo)
        self.assertEqual(result["validation"], "PASS")
        parsed = parse_task_md(Path(result["task_path"]))
        self.assertEqual(parsed["category"], "research")
        text = Path(result["task_path"]).read_text()
        self.assertIn("candidate_deliverable", text)
        self.assertIn("  - custom\n  - sample", text)
        registry = yaml.safe_load((self.base / "task_sources.yaml").read_text())
        self.assertEqual(registry["registry_contract"]["category_task_counts"], {"research": 1})
        self.assertEqual(registry["tasks"][0]["task_id"], self.task_id)
        self.assertEqual(before, (self.registry_path.read_bytes(), self.map_path.read_bytes()))

    def test_registered_conflicting_plans_and_frozen_numbers_are_reserved(self):
        spec = self.spec()
        spec.update({"number": 1, "slug": "other"})
        with self.assertRaisesRegex(generator.SpecError, "保留"):
            generator.assemble_case(spec, repo_root=self.repo, spec_dir=self.repo, dry_run=True)
        self.family["releases"]["sample-v1"]["status"] = "frozen"
        self.save_family()
        with self.assertRaisesRegex(generator.SpecError, "保留"):
            generator.assemble_case({**self.spec(), "number": 1}, repo_root=self.repo, spec_dir=self.repo, dry_run=True)
        # New source-pool cases may be added without modifying the frozen list.
        result = generator.assemble_case({**self.spec(), "slug": "increment"}, repo_root=self.repo, spec_dir=self.repo, dry_run=True)
        self.assertEqual(result["task_id"], "sample_research_task_002_increment")
        self.assertEqual(self.family["releases"]["sample-v1"]["task_ids"], [self.task_id])

    def test_registered_rollback_removes_new_registry_and_mapping(self):
        self.install_validator_wrapper(fail=True)
        with self.assertRaisesRegex(generator.SpecError, "已回滚"):
            generator.assemble_case(self.spec(), repo_root=self.repo, spec_dir=self.repo)
        self.assertFalse((self.base / "task_sources.yaml").exists())
        self.assertFalse((self.base / "checkpoint_capability_map7.yaml").exists())
        self.assertFalse((self.base / "tasks/research" / f"{self.task_id}.md").exists())
        self.assertFalse((self.base / "workspace/research" / self.task_id).exists())

    def test_registered_visual_gt_and_evidence_requirements_fail_before_writing(self):
        spec = self.spec()
        spec["modality"] = "multimodal"
        with self.assertRaisesRegex(generator.SpecError, "requires_visual_input"):
            generator.assemble_case(spec, repo_root=self.repo, spec_dir=self.repo, dry_run=True)
        spec = self.spec()
        spec["workspace"]["gt"] = []
        with self.assertRaisesRegex(generator.SpecError, "真实workspace.gt"):
            generator.assemble_case(spec, repo_root=self.repo, spec_dir=self.repo, dry_run=True)
        spec = self.spec()
        spec["judge_evidence"]["required"][0]["path"] = "gt/expected.json"
        with self.assertRaisesRegex(generator.SpecError, "results"):
            generator.assemble_case(spec, repo_root=self.repo, spec_dir=self.repo, dry_run=True)

    def test_office_requirement_uses_boolean_scoring_metadata(self):
        for requirement in ({"office": "true"}, {"office": 1}, {"unknown": True}, {"office_render": True},
                            {"office": False, "office_render": True}, {"office": True, "office_render": "true"}):
            with self.subTest(requirement=requirement), self.assertRaisesRegex(generator.SpecError, "scoring_runtime"):
                generator.assemble_case({**self.spec(), "scoring_runtime": requirement},
                    repo_root=self.repo, spec_dir=self.repo, dry_run=True)
        self.install_validator_wrapper()
        result = generator.assemble_case({**self.spec(), "scoring_runtime": {"office": True, "office_render": True}},
            repo_root=self.repo, spec_dir=self.repo)
        metadata = yaml.safe_load(Path(result["task_path"]).read_text(encoding="utf-8").split("---", 2)[1])
        self.assertEqual(metadata["scoring_runtime"], {"office": True, "office_render": True})

    def test_rejects_symbolic_material_source_and_module_level_network_import(self):
        (self.repo / "linked.md").symlink_to("input.md")
        spec = self.spec()
        spec["workspace"]["exec"][0]["source"] = "linked.md"
        with self.assertRaisesRegex(generator.SpecError, "符号链接源"):
            generator.assemble_case(spec, repo_root=self.repo, spec_dir=self.repo, dry_run=True)
        spec = self.spec()
        spec["automated_checks"] = "import requests\n" + spec["automated_checks"]
        with self.assertRaisesRegex(generator.SpecError, "禁止导入"):
            generator.assemble_case(spec, repo_root=self.repo, spec_dir=self.repo, dry_run=True)


if __name__ == "__main__":
    unittest.main()
