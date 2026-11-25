from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

import yaml

from eval_general_e2e.datasets.bundle import (
    build_registered_bundle, compile_dataset, freeze_registered_manifest,
    load_manifest_lock, verify_dataset_bundle, write_manifest_lock,
)
from eval_general_e2e.datasets.catalog import CatalogError, load_catalog, load_registered_dataset
from eval_general_e2e.datasets.discovery import discover_frozen_tasks
from eval_general_e2e.datasets.capability_audit import generate_capability_matrix, render_markdown
from tools.report.lib.eval_dataset.selectors import select_task_files


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_REVISION = "a" * 40


class DatasetCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "datasets/sample"
        self.ids = [f"sample_research_task_{n:03d}_case" for n in (1, 2)]
        self.family = {
            "schema_version": 1, "series_id": "sample", "task_id_prefix": "sample_",
            "task_root": "datasets/sample/tasks", "workspace_root": "datasets/sample/workspace",
            "source_registry": "datasets/sample/task_sources.yaml",
            "capability_map": "datasets/sample/checkpoint_capability_map7.yaml",
            "required_tags": ["custom", "sample"], "exclude_tags": ["invalid"],
            "categories": {"research": {"name": "研究"}}, "default_release": "sample-v1",
            "releases": {"sample-v1": {
                "status": "building", "created_at": "2026-10-26T00:00:00+08:00",
                "manifest": "datasets/sample/manifests/sample-v1.json", "task_ids": self.ids,
                "expected_statistics": {"task_count": 2, "category_counts": {"research": 2},
                    "grading_type_counts": {"automated": 2}, "difficulty_counts": {"L3": 2},
                    "timeout_counts": {"900": 2}},
                "constraints": {"multimodal_exact": 0, "multimodal_max_ratio": 0.1,
                    "production_backed_min": 1, "coding_primary_max": 0, "controlled_network_max": 0,
                    "research_retrieval_group_counts": {"local_evidence": 2}},
            }},
        }
        self.registry = {"schema_version": 1, "tasks": []}
        self.capabilities = {}
        for task_id in self.ids:
            self.add_task(task_id)
        self.save_sources()
        self.dump(self.root / "datasets/catalog.yaml", {
            "schema_version": 1, "datasets": {"sample": {"definition": "datasets/sample/dataset.yaml"}}})

    def dump(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def save_sources(self) -> None:
        self.dump(self.base / "dataset.yaml", self.family)
        self.dump(self.base / "task_sources.yaml", self.registry)
        self.dump(self.base / "checkpoint_capability_map7.yaml", self.capabilities)

    def add_task(self, task_id: str) -> Path:
        workspace = f"datasets/sample/workspace/research/{task_id}"
        for tree, filename, content in (("exec", "input.txt", "candidate input"),
                                        ("gt", "expected.json", '{"answer": 2}')):
            path = self.root / workspace / tree / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        task_path = self.base / "tasks/research" / f"{task_id}.md"
        task_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {"id": task_id, "name": "本地取证", "category": "research", "difficulty": "L3",
                    "modality": "pure-text", "timeout_seconds": 900, "grading_type": "automated",
                    "tags": ["custom", "sample"]}
        report = {"schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "sample",
                  "category": "research", "category_name": "研究", "category_order": 0,
                  "checkpoint_capabilities": {"correct": ["retrieval_verification"]}}
        task_path.write_text("---\n" + yaml.safe_dump(metadata) + "dataset_report: " + json.dumps(report, ensure_ascii=False) + "\n---\n"
            "## Prompt\nRead input.txt and write results/answer.json.\n"
            "## Expected Behavior\nAnswer matches private expected.json.\n"
            "## Grading Criteria\n- [ ] `correct`: Business correctness.\n"
            "## Automated Checks\n```python\ndef grade(**kwargs):\n    return {'correct': 1.0, 'overall_score': 1.0}\n```\n"
            f"## Workspace Path\n{workspace}\n## Skills\n## Env\n## Warmup\n", encoding="utf-8")
        self.registry["tasks"].append({"task_id": task_id,
            "attributes": {"requires_visual_input": False, "coding_primary": False,
                           "retrieval_group": "local_evidence"},
            "network": {"mode": "offline"},
            "origin": {"production_refs": [{"review": "accepted_intent_prototype", "query_hash": "f" * 64}]}})
        self.capabilities[task_id] = {"correct": ["retrieval_verification"]}
        return task_path

    def compile(self):
        selected = load_registered_dataset(self.root, "sample")
        return compile_dataset(self.root, definition=selected.definition, source_revision=SOURCE_REVISION)

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def commit_sources(self) -> str:
        if not (self.root / ".git").exists():
            self.git("init", "-q")
        self.git("add", "datasets")
        self.git("-c", "user.name=Dataset Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
                 "commit", "-qm", "test(dataset): 固定隔离测试数据")
        return self.git("rev-parse", "HEAD")

    def test_series_and_release_resolve_to_the_same_explicit_selection(self) -> None:
        series = load_registered_dataset(self.root, "sample")
        release = load_registered_dataset(self.root, "sample-v1")
        self.assertEqual(series, release)
        self.assertEqual(series.definition.task_ids, tuple(self.ids))
        self.assertEqual(series.definition.category_labels, {"research": "研究"})
        manifest, _ = self.compile()
        self.assertEqual(manifest["task_count"], 2)
        self.assertEqual(manifest["selection"]["task_root"], "datasets/sample/tasks")
        self.assertEqual(manifest["statistics"]["category_counts"], {"research": 2})

    def test_dataset_selector_requires_the_explicit_release_without_selecting_legacy_or_new_tasks(self) -> None:
        self.add_task("sample_research_task_003_new")
        legacy = self.root / "tasks/extension/research/legacy.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("---\nid: legacy\n---\n")
        selected = select_task_files(self.root, dataset_id="sample-v1")
        self.assertFalse(selected.issues)
        self.assertEqual({path.stem for path in selected.files}, set(self.ids))
        missing = self.base / "tasks/research" / f"{self.ids[0]}.md"
        missing.unlink()
        result = select_task_files(self.root, dataset_id="sample")
        self.assertEqual([(issue.code, issue.task_id) for issue in result.issues], [("TASK_ID_NOT_FOUND", self.ids[0])])
        outside = select_task_files(self.root, dataset_id="sample", task_paths=[legacy])
        self.assertEqual(outside.files, [])
        self.assertEqual(outside.issues[0].code, "DATASET_TASK_OUTSIDE_ROOT")
        unknown = select_task_files(self.root, dataset_id="unknown")
        self.assertEqual(unknown.files, [])
        self.assertEqual(unknown.issues[0].code, "DATASET_DEFINITION_INVALID")

    def test_registered_static_validator_checks_source_labels_mapping_and_material_isolation(self) -> None:
        script = REPO_ROOT / "tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py"
        spec = importlib.util.spec_from_file_location("registered_validator_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        selected = select_task_files(self.root, dataset_id="sample").files
        self.assertEqual(module.validate_registered_registry(self.root, selected), [])
        self.registry["tasks"].pop()
        self.capabilities[self.ids[0]] = {"other": ["retrieval_verification"]}
        self.save_sources()
        issues = module.validate_registered_registry(self.root, selected)
        self.assertEqual({issue.code for issue in issues}, {"DATASET_SOURCE_MISSING", "DATASET_CAPABILITY_MAP_INVALID", "DATASET_REPORT_METADATA_INVALID"})
        workspace = self.base / "workspace/research" / self.ids[0]
        (workspace / "exec/input.txt").unlink()
        (workspace / "exec").rmdir()
        (workspace / "exec").symlink_to("gt", target_is_directory=True)
        issues = module.validate_registered_registry(self.root, [selected[0]])
        self.assertEqual([issue.code for issue in issues], ["DATASET_MATERIAL_ISOLATION_INVALID"])

    def test_full_static_cli_checks_release_quotas_without_executing_grading_code(self) -> None:
        script = REPO_ROOT / "tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py"
        spec = importlib.util.spec_from_file_location("release_validator_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Valid syntax that would fail if a supposedly static check ran grade().
        for path in (self.base / "tasks/research").glob("*.md"):
            path.write_text(path.read_text().replace("def grade(**kwargs):", "def grade(**kwargs):\n    raise AssertionError('must not execute')"))
        args = ["--repo-root", str(self.root), "--dataset-id", "sample-v1", "--output-dir", str(self.root / "reports")]
        output = io.StringIO()
        with redirect_stdout(output):
            code = module.main(args)
        self.assertEqual(code, 0)
        self.family["releases"]["sample-v1"]["constraints"]["multimodal_exact"] = 1
        self.save_sources()
        output = io.StringIO()
        with redirect_stdout(output):
            code = module.main(args)
        self.assertEqual(code, 1)
        report = json.loads((Path(output.getvalue().strip()) / "report.json").read_text())
        self.assertIn("DATASET_RELEASE_CONTRACT_INVALID", {issue["code"] for issue in report["issues"]})

    def test_action_summary_counts_match_lists_with_missing_ids_outside_existing_tasks(self) -> None:
        script = REPO_ROOT / "tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py"
        spec = importlib.util.spec_from_file_location("action_summary_validator_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        failed_id = "sample_research_task_003_fail"
        review_id = "sample_research_task_004_review"
        missing_id = "sample_research_task_999_missing"
        self.add_task(failed_id)
        self.add_task(review_id)
        task_ids = [*self.ids, failed_id, review_id, self.ids[0]]
        issues = [
            module.Issue(module.FAIL, "FRONTMATTER_FIELD_MISSING", "existing task failed", task_id=failed_id),
            module.Issue(module.REVIEW, "BOUNDARY_REVIEW", "existing task needs review", task_id=review_id),
            module.Issue(module.FAIL, "TASK_ID_NOT_FOUND", "selected ID is not materialized", task_id=missing_id),
        ]
        original_task_ids, original_issues = list(task_ids), deepcopy(issues)

        summary = module.build_action_summary(task_ids, issues)

        self.assertEqual(summary["tasks_pass"], self.ids)
        self.assertEqual([item["task_id"] for item in summary["tasks_to_fix"]], [failed_id, missing_id])
        self.assertEqual([item["task_id"] for item in summary["tasks_for_review"]], [review_id])
        self.assertEqual(summary["counts"], {"tasks_to_fix": 2, "tasks_for_review": 1, "tasks_pass": 2})
        for key, items in (("tasks_to_fix", summary["tasks_to_fix"]),
                           ("tasks_for_review", summary["tasks_for_review"]),
                           ("tasks_pass", summary["tasks_pass"])):
            self.assertEqual(summary["counts"][key], len(items))
        self.assertNotIn(missing_id, task_ids)
        self.assertFalse((self.base / "tasks/research" / f"{missing_id}.md").exists())
        self.assertEqual(module.status_for_issues(issues), module.FAIL)
        self.assertEqual(summary["decision"], "先修复需要修改的用例，再重新运行静态校验。")
        self.assertEqual(task_ids, original_task_ids)
        self.assertEqual(issues, original_issues)

    def test_missing_selected_tasks_and_missing_required_tags_fail_closed(self) -> None:
        path = self.base / "tasks/research" / f"{self.ids[0]}.md"
        original = path.read_text()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "release tasks missing"):
            self.compile()
        path.write_text(original.replace("- sample\n", "- other\n"))
        with self.assertRaisesRegex(ValueError, "excluded by required tags"):
            self.compile()

    def test_new_tasks_and_registry_counters_cannot_expand_or_rehash_a_release(self) -> None:
        original, original_members = self.compile()
        self.add_task("sample_research_task_003_new")
        self.registry["registry_contract"] = {"active_task_count": 3}
        self.save_sources()
        actual, actual_members = self.compile()
        self.assertEqual(original, actual)
        self.assertEqual(original_members, actual_members)
        # A second family and an unrelated release are equally outside v1.
        v2 = deepcopy(self.family["releases"]["sample-v1"])
        v2["manifest"] = "datasets/sample/manifests/sample-v2.json"
        self.family["releases"]["sample-v2"] = v2
        self.save_sources()
        self.assertEqual(original, self.compile()[0])

    def test_unselected_malformed_source_cannot_invalidate_a_frozen_selection(self) -> None:
        original, members = self.compile()
        unrelated = self.base / "tasks/research/sample_research_task_999_unrelated.md"
        unrelated.write_text("---\ninvalid: [unfinished YAML\n---\n")
        actual, actual_members = self.compile()
        self.assertEqual(actual, original)
        self.assertEqual(actual_members, members)

    def test_selected_provenance_capability_and_scoring_changes_are_locked(self) -> None:
        before = self.compile()[0]
        self.registry["tasks"][0]["origin"]["note"] = "review changed"
        self.save_sources()
        provenance = self.compile()[0]
        self.assertNotEqual(before["dataset_digest"], provenance["dataset_digest"])
        self.capabilities[self.ids[0]]["correct"] = ["data_processing"]
        self.save_sources()
        with self.assertRaisesRegex(ValueError, "report metadata disagrees"):
            self.compile()
        path = self.base / "tasks/research" / f"{self.ids[0]}.md"
        path.write_text(path.read_text().replace('"correct": ["retrieval_verification"]', '"correct": ["data_processing"]'))
        mapping = self.compile()[0]
        self.assertNotEqual(provenance["dataset_digest"], mapping["dataset_digest"])
        gt = self.base / "workspace/research" / self.ids[0] / "gt/expected.json"
        gt.write_text('{"answer": 3}')
        self.assertNotEqual(mapping["dataset_digest"], self.compile()[0]["dataset_digest"])

    def test_dataset_paths_and_symlinks_cannot_escape_the_family(self) -> None:
        for bad in ("../outside", "/outside", "datasets/sample/../../outside", "datasets/other/tasks"):
            with self.subTest(path=bad):
                self.family["task_root"] = bad
                self.save_sources()
                with self.assertRaises(CatalogError):
                    load_registered_dataset(self.root, "sample")
        self.family["task_root"] = "datasets/sample/tasks"
        self.save_sources()
        outside = self.root / "outside"
        outside.mkdir()
        (self.base / "evil").symlink_to(outside, target_is_directory=True)
        self.family["task_root"] = "datasets/sample/evil"
        self.save_sources()
        with self.assertRaisesRegex(CatalogError, "inside its dataset"):
            load_registered_dataset(self.root, "sample")

    def test_workspace_path_must_include_its_own_category_and_task_id(self) -> None:
        path = self.base / "tasks/research" / f"{self.ids[0]}.md"
        path.write_text(path.read_text().replace(f"workspace/research/{self.ids[0]}", f"workspace/research/{self.ids[1]}"))
        with self.assertRaisesRegex(ValueError, "workspace must match"):
            self.compile()

    def test_exec_cannot_alias_private_scoring_materials(self) -> None:
        workspace = self.base / "workspace/research" / self.ids[0]
        (workspace / "exec/input.txt").unlink()
        (workspace / "exec").rmdir()
        (workspace / "exec").symlink_to("gt", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "must be separate"):
            self.compile()

    def test_empty_gt_and_missing_source_or_capability_entries_are_rejected(self) -> None:
        original = deepcopy(self.registry)
        self.registry["tasks"].pop()
        self.save_sources()
        with self.assertRaisesRegex(ValueError, "missing from task_sources"):
            self.compile()
        self.registry = original
        self.capabilities.pop(self.ids[0])
        self.save_sources()
        with self.assertRaisesRegex(ValueError, "lacks capability"):
            self.compile()
        self.capabilities[self.ids[0]] = {"correct": ["retrieval_verification"]}
        self.save_sources()
        (self.base / "workspace/research" / self.ids[0] / "gt/expected.json").unlink()
        (self.base / "workspace/research" / self.ids[0] / "gt/.gitkeep").write_text("")
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            self.compile()

    def test_visual_network_and_production_constraints_use_reviewed_source_attributes(self) -> None:
        self.registry["tasks"][0]["attributes"]["requires_visual_input"] = True
        self.save_sources()
        with self.assertRaisesRegex(ValueError, "visual attribute disagrees"):
            self.compile()
        self.registry["tasks"][0]["attributes"]["requires_visual_input"] = False
        for entry in self.registry["tasks"]:
            entry["origin"]["production_refs"][0]["review"] = "unreviewed"
        self.save_sources()
        with self.assertRaisesRegex(ValueError, "production_backed_min failed"):
            self.compile()

    def test_catalog_rejects_duplicate_keys_bool_schema_and_namespace_collisions(self) -> None:
        path = self.base / "dataset.yaml"
        path.write_text(path.read_text() + "\nseries_id: sample\n")
        with self.assertRaisesRegex(CatalogError, "duplicate YAML key"):
            load_registered_dataset(self.root, "sample")
        self.family["schema_version"] = True
        self.save_sources()
        with self.assertRaisesRegex(CatalogError, "schema/series mismatch"):
            load_registered_dataset(self.root, "sample")
        self.dump(self.root / "datasets/catalog.yaml", {"schema_version": 1, "datasets": {
            "sample-a": {"definition": "datasets/sample-a/dataset.yaml"},
            "sample_a": {"definition": "datasets/sample_a/dataset.yaml"}}})
        with self.assertRaisesRegex(CatalogError, "unique task ID namespaces"):
            load_catalog(self.root)

    def test_building_release_cannot_freeze_or_distribute(self) -> None:
        with self.assertRaisesRegex(ValueError, "only a ready"):
            freeze_registered_manifest(self.root, "sample")
        with self.assertRaisesRegex(ValueError, "only a frozen"):
            build_registered_bundle(self.root, "sample", self.root / "out.zip")
        self.assertFalse((self.base / "manifests/sample-v1.json").exists())

    def test_ready_freeze_requires_committed_sources_and_never_overwrites(self) -> None:
        self.family["releases"]["sample-v1"]["status"] = "ready"
        self.save_sources()
        with self.assertRaisesRegex(ValueError, "commit the dataset"):
            freeze_registered_manifest(self.root, "sample")
        revision = self.commit_sources()
        material = self.base / "workspace/research" / self.ids[0] / "exec/input.txt"
        original = material.read_text()
        material.write_text("uncommitted change")
        with self.assertRaisesRegex(ValueError, "commit the dataset"):
            freeze_registered_manifest(self.root, "sample")
        material.write_text(original)
        with self.assertRaisesRegex(ValueError, "source_revision does not match"):
            freeze_registered_manifest(self.root, "sample", source_revision="b" * 40)
        path = freeze_registered_manifest(self.root, "sample", source_revision=revision)
        locked = load_manifest_lock(path)
        self.assertEqual(locked["source"]["revision"], revision)
        with self.assertRaises(FileExistsError):
            freeze_registered_manifest(self.root, "sample")

    def test_registered_bundle_is_independently_verified_and_detects_selected_drift(self) -> None:
        manifest, _ = self.compile()
        write_manifest_lock(manifest, self.base / "manifests/sample-v1.json")
        self.family["releases"]["sample-v1"]["status"] = "frozen"
        self.save_sources()
        self.add_task("sample_research_task_003_later")
        self.save_sources()
        output = self.root / "sample.zip"
        result = build_registered_bundle(self.root, "sample-v1", output)
        self.assertEqual(result["task_count"], 2)
        self.assertEqual(verify_dataset_bundle(output)["dataset_digest"], manifest["dataset_digest"])
        first = output.read_bytes()
        build_registered_bundle(self.root, "sample", output)
        self.assertEqual(output.read_bytes(), first)
        (self.base / "workspace/research" / self.ids[0] / "exec/input.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "sources do not match"):
            build_registered_bundle(self.root, "sample", output)
        self.assertEqual(output.read_bytes(), first)

    def test_frozen_source_discovery_is_isolated_and_carries_release_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a frozen"):
            discover_frozen_tasks(self.root, "sample")
        manifest, _ = self.compile()
        write_manifest_lock(manifest, self.base / "manifests/sample-v1.json")
        self.family["releases"]["sample-v1"]["status"] = "frozen"
        self.add_task("sample_research_task_003_later")
        self.save_sources()
        selected = discover_frozen_tasks(self.root, "sample-v1")
        self.assertEqual([task["task_id"] for task in selected.tasks], self.ids)
        self.assertEqual(selected.identity["dataset_digest"], manifest["dataset_digest"])
        for task in selected.tasks:
            self.assertEqual(task["dataset_selection"], selected.identity)
            self.assertTrue(Path(task["workspace_path"]).is_relative_to(self.base.resolve()))
        (self.base / "workspace/research" / self.ids[0] / "gt/expected.json").write_text('{"answer": 99}')
        with self.assertRaisesRegex(ValueError, "differ from the frozen"):
            discover_frozen_tasks(self.root, "sample")

    def test_registered_capability_audit_uses_frozen_open_search_and_visual_declarations(self) -> None:
        self.registry["tasks"][0]["network"]["mode"] = "open_public_search"
        self.registry["tasks"][0]["attributes"]["retrieval_group"] = "open_search"
        self.registry["tasks"][1]["attributes"]["requires_visual_input"] = True
        path = self.base / "tasks/research" / f"{self.ids[1]}.md"
        path.write_text(path.read_text().replace("modality: pure-text", "modality: multimodal"))
        constraints = self.family["releases"]["sample-v1"]["constraints"]
        constraints.update({"controlled_network_max": 1, "multimodal_exact": 1, "multimodal_max_ratio": 0.5,
                            "research_retrieval_group_counts": {"open_search": 1, "local_evidence": 1}})
        self.save_sources()
        with self.assertRaisesRegex(ValueError, "requires a frozen"):
            generate_capability_matrix(self.root, dataset_id="sample")
        manifest, _ = self.compile()
        write_manifest_lock(manifest, self.base / "manifests/sample-v1.json")
        self.family["releases"]["sample-v1"]["status"] = "frozen"
        self.save_sources()
        audit = generate_capability_matrix(self.root, dataset_id="sample-v1")
        self.assertEqual(audit["summary"]["network_required_task_ids"], [self.ids[0]])
        self.assertEqual(audit["tasks"][0]["network"]["source_urls"], [])
        self.assertIn("network.retrieve", audit["tasks"][0]["execution"]["required_tool_capabilities"])
        self.assertIn("image.understand", audit["tasks"][1]["execution"]["required_tool_capabilities"])
        self.assertIn("1类共2题", render_markdown(audit))

    def test_dataset_report_snapshot_stays_in_private_scoring_package(self) -> None:
        from tests.general_e2e.test_general_release_prepare import PREPARE
        from eval_general_e2e.datasets.bundle import write_dataset_bundle
        manifest, members = self.compile()
        bundle = write_dataset_bundle(manifest, members, self.root / "source.zip")
        catalogue = {"skills": [{"name": name, "version": "1.0.0", "implementation_status": "operational",
                                  "content_sha256": "a" * 64, "zip_sha256": "b" * 64}
                                 for name in dict.fromkeys([*PREPARE.EXECUTION_SKILLS, *PREPARE.SCORING_SKILLS])]}
        unit = {"unit_id": "sample-unit", "task_ids": self.ids, "harness": {"id": "astronstudio"}}
        dataset = {"id": manifest["dataset_id"], "digest": manifest["dataset_digest"], "bundle_sha256": "c" * 64}
        release = {"id": "sample-suite", "catalog_digest": "d" * 64, "catalog_sha256": "e" * 64, "suite_sha256": "f" * 64}
        with zipfile.ZipFile(bundle) as archive:
            execution, scoring = PREPARE._unit_packages(archive, manifest["dataset_id"], manifest, unit,
                "sample-batch", dataset, release, catalogue, self.root)
        with zipfile.ZipFile(execution) as archive:
            self.assertFalse(any(b"dataset_report" in archive.read(name) for name in archive.namelist()))
        with zipfile.ZipFile(scoring) as archive:
            definitions = [name for name in archive.namelist() if name.endswith("/task.md")]
            self.assertEqual(len(definitions), 2)
            self.assertTrue(all(b"dataset_report:" in archive.read(name) for name in definitions))


class RegisteredSourceContractTests(unittest.TestCase):
    def test_general_challenge_frozen_v3_matches_the_approved_60_blueprints(self) -> None:
        source = json.loads((REPO_ROOT / "docs/design/general-e2e/general-hard/60题蓝图.json").read_text())
        aliases = json.loads((REPO_ROOT / "datasets/layout.json").read_text())["task_id_aliases"]
        registered = load_registered_dataset(REPO_ROOT, "general-challenge")
        definition = registered.definition
        self.assertEqual(registered.status, "frozen")
        self.assertEqual(definition.dataset_id, "general-challenge60-v3")
        self.assertEqual(definition.task_ids, tuple(aliases[task["task_id"]] for task in source["tasks"]))
        self.assertEqual(definition.include_tags, ("custom", "general-challenge"))
        self.assertEqual(definition.expected_task_count, 60)
        self.assertEqual(definition.expected_category_counts, source["statistics"]["category_counts"])
        self.assertEqual(definition.constraints["multimodal_exact"], 6)
        self.assertEqual(definition.constraints["research_retrieval_group_counts"],
                         {"open_search": 3, "directed_web_retrieval": 3, "local_evidence": 2})
        manifest = load_manifest_lock(registered.manifest_path)
        # Verify the selected bytes while retaining the release's source pin,
        # as build_registered_bundle does after later repository commits.
        compiled, _ = compile_dataset(REPO_ROOT, definition=definition,
                                      source_revision=manifest["source"]["revision"])
        self.assertEqual(compiled, manifest)
        self.assertEqual(manifest["dataset_id"], definition.dataset_id)
        self.assertCountEqual([task["task_id"] for task in manifest["tasks"]], definition.task_ids)

    def test_legacy_registration_uses_the_existing_manifest_ids(self) -> None:
        registered = load_registered_dataset(REPO_ROOT, "general-custom60-v1")
        manifest = load_manifest_lock(registered.manifest_path)
        compiled, _ = compile_dataset(REPO_ROOT, definition=registered.definition)
        self.assertEqual(compiled, manifest)
        self.assertEqual(registered.definition.task_ids, tuple(task["task_id"] for task in manifest["tasks"]))


if __name__ == "__main__":
    unittest.main()
