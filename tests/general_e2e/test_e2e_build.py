from __future__ import annotations

import copy
import importlib.util
import json
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO_ROOT / "tools/e2e-build/build_skill_packages.py"
FIXED_REVISION = "1" * 40
EXPECTED_SKILLS = {
    "prepare-web-e2e-workspaces",
    "execute-web-e2e",
    "orchestrate-web-e2e",
    "score-web-e2e",
    "report-web-e2e",
    "run-web-e2e",
    "prepare-general-e2e-workspaces",
    "execute-general-e2e",
    "collect-general-e2e",
    "orchestrate-general-e2e",
    "score-general-e2e",
    "report-general-e2e",
    "run-general-e2e",
}


def load_builder():
    spec = importlib.util.spec_from_file_location("wildclawbench_e2e_build", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load builder: {BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = load_builder()


class E2EBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="general-e2e-build-test-")
        cls.temp_root = Path(cls.temp_dir.name)
        cls.first_output = cls.temp_root / "first"
        cls.manifest = BUILD.build_skill_packages(
            REPO_ROOT,
            cls.first_output,
            source_revision=FIXED_REVISION,
        )
        cls.rows = {row["name"]: row for row in cls.manifest["skills"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def archive_path(self, skill_name: str) -> Path:
        return self.first_output / self.rows[skill_name]["archive"]

    def test_build_plan_covers_all_thirteen_scene_skills(self) -> None:
        components, skills = BUILD._load_configuration(REPO_ROOT)
        self.assertEqual(set(skills), EXPECTED_SKILLS)
        self.assertEqual(len(skills), 13)
        self.assertEqual(
            set(components),
            {
                "desktop-runtime",
                "task-process-cleanup",
                "desktop-app-discovery",
                "desktop-debug",
                "resource-metrics",
                "workbuddy-jsonl-metrics",
                "report-reference-data",
                "workspace-integrity",
                "dataset-bundle-verifier",
                "grading-core",
                "general-contracts",
                "workbuddy-evidence",
            },
        )
        self.assertEqual(self.manifest["skill_count"], 13)
        self.assertEqual(set(self.rows), EXPECTED_SKILLS)
        self.assertEqual(
            {
                name: row["development_repository_references"]
                for name, row in self.rows.items()
                if row["development_repository_references"]
            },
            {
                "prepare-web-e2e-workspaces": [
                    "scripts/prepare_web_e2e_workspaces.py"
                ]
            },
        )

    def test_component_manifest_and_vendoring_match_canonical_sources(self) -> None:
        catalog, _ = BUILD._load_configuration(REPO_ROOT)
        for skill_name, row in self.rows.items():
            with self.subTest(skill=skill_name):
                with zipfile.ZipFile(self.archive_path(skill_name)) as archive:
                    bundled = json.loads(
                        archive.read(f"{skill_name}/bundled-components.json")
                    )
                    self.assertEqual(
                        bundled["schema_version"], BUILD.BUNDLED_COMPONENTS_SCHEMA
                    )
                    self.assertEqual(bundled["skill_name"], skill_name)
                    self.assertEqual(bundled["source_revision"], FIXED_REVISION)
                    self.assertEqual(bundled["components"], row["components"])
                    self.assertEqual(
                        bundled["development_repository_references"],
                        row["development_repository_references"],
                    )
                    for component_row in bundled["components"]:
                        component = catalog[component_row["name"]]
                        canonical_root = REPO_ROOT / component["source_root"]
                        self.assertEqual(
                            component_row["content_sha256"],
                            BUILD.tree_content_sha256(canonical_root),
                        )
                        for source in BUILD.regular_files(canonical_root):
                            relative = source.relative_to(canonical_root).as_posix()
                            archived = (
                                f"{skill_name}/{component['vendor_root']}/{relative}"
                            )
                            self.assertEqual(archive.read(archived), source.read_bytes())

    def test_report_reference_snapshot_is_standalone_without_pyyaml(self) -> None:
        root = BUILD._safe_extract(self.archive_path("report-general-e2e"), self.temp_root / "report-references")
        helper = root / "scripts/report_views.py"
        completed = subprocess.run(
            [sys.executable, "-I", "-S", "-c",
             "import runpy,sys,json; module=runpy.run_path(sys.argv[1]); data=module['load_references'](); print(json.dumps(data['sources'],sort_keys=True))", str(helper)],
            capture_output=True, text=True, check=True,
        )
        sources = json.loads(completed.stdout)
        for name, digest in sources.items():
            self.assertEqual(digest, hashlib.sha256((REPO_ROOT / "tools/report/data" / name).read_bytes()).hexdigest())
        snapshot = json.loads((root / "data/report-reference.json").read_text())
        self.assertEqual(snapshot["models"]["xopglm52"], "GLM-5.2")
        self.assertIn("01_Productivity_Flow_task_003_retro_agenda", snapshot["capabilities"])

    def test_general_orchestrator_vendors_managed_macos_restart(self) -> None:
        with zipfile.ZipFile(self.archive_path("orchestrate-general-e2e")) as archive:
            names = set(archive.namelist())
            self.assertIn(
                "orchestrate-general-e2e/scripts/restart_macos_desktop_debug.sh",
                names,
            )
            self.assertIn(
                "orchestrate-general-e2e/vendor/e2e-shared/desktop-debug/"
                "restart_macos_desktop_debug.sh",
                names,
            )
        detached = self.temp_root / "detached-general-restart"
        detached.mkdir()
        root = BUILD._safe_extract(
            self.archive_path("orchestrate-general-e2e"),
            detached / "installed",
        )
        completed = subprocess.run(
            [
                "/bin/bash",
                str(root / "scripts/restart_macos_desktop_debug.sh"),
                "--help",
            ],
            cwd=detached,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("KeepAlive=false", completed.stdout)

    def test_build_is_byte_deterministic_and_uses_portable_zip_metadata(self) -> None:
        second_output = self.temp_root / "second"
        second = BUILD.build_skill_packages(
            REPO_ROOT,
            second_output,
            source_revision=FIXED_REVISION,
        )
        second_rows = {row["name"]: row for row in second["skills"]}
        self.assertEqual(
            (self.first_output / "skills-build-manifest.json").read_bytes(),
            (second_output / "skills-build-manifest.json").read_bytes(),
        )
        for skill_name, row in self.rows.items():
            with self.subTest(skill=skill_name):
                other = second_output / second_rows[skill_name]["archive"]
                self.assertEqual(
                    self.archive_path(skill_name).read_bytes(),
                    other.read_bytes(),
                )
                with zipfile.ZipFile(other) as archive:
                    for info in archive.infolist():
                        self.assertEqual(info.date_time, BUILD.FIXED_ZIP_TIMESTAMP)
                        self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                        mode = (info.external_attr >> 16) & 0o777
                        suffix = PurePosixPath(info.filename).suffix.lower()
                        expected_mode = (
                            0o755
                            if suffix in BUILD.ARCHIVE_EXECUTABLE_SUFFIXES
                            else 0o644
                        )
                        self.assertEqual(mode, expected_mode)

    def test_manifest_hashes_verify_and_tampering_fails_closed(self) -> None:
        verification = BUILD.verify_build_manifest(
            self.first_output / "skills-build-manifest.json"
        )
        self.assertEqual(verification["status"], "PASS")
        self.assertEqual(verification["skill_count"], 13)

        original_row = self.rows["score-web-e2e"]
        original_archive = self.archive_path("score-web-e2e")
        tamper_root = self.temp_root / "tamper"
        tamper_root.mkdir()
        extracted = BUILD._safe_extract(original_archive, tamper_root / "extract")
        skill_md = extracted / "SKILL.md"
        skill_md.write_bytes(skill_md.read_bytes() + b"\n<!-- tampered -->\n")
        tampered_archive = tamper_root / original_archive.name
        BUILD.write_deterministic_zip(extracted, tampered_archive)

        with self.assertRaisesRegex(BUILD.BuildError, "ZIP_HASH_MISMATCH"):
            BUILD.verify_skill_package(tampered_archive, original_row)

        expected = copy.deepcopy(original_row)
        expected["zip_sha256"] = BUILD.sha256_file(tampered_archive)
        with self.assertRaisesRegex(BUILD.BuildError, "CONTENT_HASH_MISMATCH"):
            BUILD.verify_skill_package(tampered_archive, expected)

        tampered_manifest = copy.deepcopy(self.manifest)
        tampered_manifest["source_revision"] = "2" * 40
        tampered_manifest_path = tamper_root / "skills-build-manifest.json"
        BUILD.write_json(tampered_manifest_path, tampered_manifest)
        with self.assertRaisesRegex(BUILD.BuildError, "BUILD_MANIFEST_REVISION_MISMATCH"):
            BUILD.verify_build_manifest(
                tampered_manifest_path,
                package_dir=self.first_output,
            )

    def test_dependency_escape_fails_closed(self) -> None:
        root = self.temp_root / "dependency-escape"
        skill = root / "skill"
        skill.mkdir(parents=True)
        (root / "outside.mjs").write_text("export const value = 1;\n", encoding="utf-8")
        (skill / "index.mjs").write_text(
            'import { value } from "../outside.mjs";\nexport { value };\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BUILD.BuildError, "RELATIVE_IMPORT_ESCAPES_SKILL"):
            BUILD.validate_dependency_closure(skill)

    def test_source_symlink_fails_closed(self) -> None:
        symlink_root = self.temp_root / "source-symlink"
        symlink_root.mkdir()
        target = symlink_root / "target.txt"
        target.write_text("fixture", encoding="utf-8")
        link = symlink_root / "link.txt"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("symbolic links are unavailable on this platform")
        with self.assertRaisesRegex(BUILD.BuildError, "SYMLINK_NOT_ALLOWED"):
            BUILD.regular_files(symlink_root)

    def test_build_rejects_embedded_checkout_absolute_path(self) -> None:
        skill = self.temp_root / "absolute-checkout-path"
        skill.mkdir()
        (skill / "script.py").write_text(
            f'REPOSITORY = {str(REPO_ROOT)!r}\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BUILD.BuildError, "REPOSITORY_PATH_REFERENCE"):
            BUILD.validate_dependency_closure(
                skill,
                forbidden_repository_roots=(REPO_ROOT,),
            )

    def test_archive_path_traversal_backslash_and_symlink_fail_closed(self) -> None:
        fixtures = self.temp_root / "unsafe-archives"
        fixtures.mkdir()

        traversal = fixtures / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr("skill/SKILL.md", "fixture")
            archive.writestr("skill/../../escape.txt", "escape")
        with self.assertRaisesRegex(BUILD.BuildError, "UNSAFE_ARCHIVE_PATH"):
            BUILD._safe_extract(traversal, fixtures / "traversal-output")

        backslash = fixtures / "backslash.zip"
        with zipfile.ZipFile(backslash, "w") as archive:
            archive.writestr("skill/SKILL.md", "fixture")
            archive.writestr("skill\\..\\escape.txt", "escape")
        with self.assertRaisesRegex(BUILD.BuildError, "UNSAFE_ARCHIVE_PATH"):
            BUILD._safe_extract(backslash, fixtures / "backslash-output")

        symlink = fixtures / "symlink.zip"
        link_info = zipfile.ZipInfo("skill/link")
        link_info.create_system = 3
        link_info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(symlink, "w") as archive:
            archive.writestr("skill/SKILL.md", "fixture")
            archive.writestr(link_info, "../outside")
        with self.assertRaisesRegex(BUILD.BuildError, "ARCHIVE_SYMLINK_NOT_ALLOWED"):
            BUILD._safe_extract(symlink, fixtures / "symlink-output")

        duplicate = fixtures / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.writestr("skill/SKILL.md", "first")
                archive.writestr("skill/SKILL.md", "second")
        with self.assertRaisesRegex(BUILD.BuildError, "ARCHIVE_DUPLICATE_PATH"):
            BUILD._safe_extract(duplicate, fixtures / "duplicate-output")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_web_runtime_modules_load_outside_checkout(self) -> None:
        detached = self.temp_root / "detached"
        detached.mkdir()
        roots = {
            name: BUILD._safe_extract(self.archive_path(name), detached / name)
            for name in (
                "execute-web-e2e",
                "orchestrate-web-e2e",
                "score-web-e2e",
            )
        }
        modules = {
            "execute": roots["execute-web-e2e"] / "drivers/metrics/parsers.mjs",
            "orchestrate": roots["orchestrate-web-e2e"] / "scripts/workspace-integrity.mjs",
            "score": roots["score-web-e2e"] / "scripts/workspace-integrity.mjs",
        }
        source = f"""
import {{ empty }} from {json.dumps(modules['execute'].as_uri())};
import {{ runtimeDirectoryPolicy as orchestratePolicy }} from {json.dumps(modules['orchestrate'].as_uri())};
import {{ runtimeDirectoryPolicy as scorePolicy }} from {json.dumps(modules['score'].as_uri())};
process.stdout.write(JSON.stringify({{
  schema: empty().collection.schema_version,
  orchestrate: orchestratePolicy(),
  score: scorePolicy(),
}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", source],
            cwd=detached,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(
            payload["schema"], "wildclawbench.web-e2e-resource-collection/v1"
        )
        self.assertEqual(payload["orchestrate"], payload["score"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_general_execute_entrypoints_load_outside_checkout(self) -> None:
        detached = self.temp_root / "detached-general-execute"
        detached.mkdir()
        root = BUILD._safe_extract(
            self.archive_path("execute-general-e2e"),
            detached / "installed",
        )
        probe = root / "scripts/probe_astronstudio_macos.mjs"
        execute = root / "scripts/execute_astronstudio_macos.mjs"
        batch = root / "scripts/run_astronstudio_macos_batch.mjs"
        self.assertTrue(probe.is_file())
        self.assertTrue(execute.is_file())
        self.assertTrue(batch.is_file())
        self.assertTrue(
            (root / "vendor/e2e-shared/desktop-runtime/process.mjs").is_file()
        )
        completed = subprocess.run(
            ["node", str(probe), "--help"],
            cwd=detached,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "macOS 只读探针",
            completed.stdout,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertNotIn(str(REPO_ROOT), completed.stdout + completed.stderr)
        completed = subprocess.run(
            ["node", str(batch), "--help"],
            cwd=detached,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("串行队列 Worker", completed.stdout)
        self.assertNotIn(str(REPO_ROOT), completed.stdout + completed.stderr)
        for driver, script, expected in (
            ("workbuddy", "execute.mjs", "--resume"),
            ("workbuddy", "batch.mjs", "--queue-id"),
            ("qwenwork", "driver.mjs", "--resume"),
            ("qwenwork", "probe.mjs", "--endpoint"),
        ):
            with self.subTest(driver=driver, script=script):
                driver_root = root / "drivers" / driver
                self.assertTrue((driver_root / "package-lock.json").is_file())
                completed = subprocess.run(
                    ["node", str(driver_root / script), "--help"],
                    cwd=detached,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn(expected, completed.stdout)
                self.assertNotIn(str(REPO_ROOT), completed.stdout + completed.stderr)
        execution_help = subprocess.run(
            ["node", str(execute), "--help"],
            cwd=detached,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(execution_help.returncode, 0, execution_help.stderr)
        self.assertIn("macOS 单题执行器", execution_help.stdout)
        self.assertNotIn(str(REPO_ROOT), execution_help.stdout + execution_help.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_general_collect_entrypoints_load_outside_checkout(self) -> None:
        detached = self.temp_root / "detached-general-collect"
        detached.mkdir()
        root = BUILD._safe_extract(
            self.archive_path("collect-general-e2e"),
            detached / "installed",
        )
        archive = root / "scripts/archive_astronstudio_trace.mjs"
        query = root / "scripts/query_trace.mjs"
        resources = root / "scripts/collect_astronstudio_resource_metrics.mjs"
        finalizer = root / "scripts/finalize_astronstudio_execution.mjs"
        self.assertTrue(archive.is_file())
        self.assertTrue(query.is_file())
        self.assertTrue(resources.is_file())
        self.assertTrue(finalizer.is_file())
        self.assertTrue(
            (root / "vendor/e2e-shared/resource-metrics/trace-io.mjs").is_file()
        )
        self.assertTrue(
            (root / "vendor/e2e-shared/desktop-runtime/process.mjs").is_file()
        )
        self.assertTrue(
            (root / "vendor/e2e-shared/handoff/workspace-integrity.mjs").is_file()
        )
        for entrypoint, marker in (
            (root / "drivers/workbuddy/collector.mjs", "WorkBuddy"),
            (root / "drivers/workbuddy/finalize.mjs", "WorkBuddy"),
            (archive, "轨迹归档器"),
            (query, "只读检索"),
            (resources, "资源指标采集器"),
            (finalizer, "正式收口器"),
        ):
            completed = subprocess.run(
                ["node", str(entrypoint), "--help"],
                cwd=detached,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(marker, completed.stdout)
            self.assertNotIn(str(REPO_ROOT), completed.stdout + completed.stderr)

    def test_general_grading_core_loads_outside_checkout(self) -> None:
        detached = self.temp_root / "detached-general-score"
        detached.mkdir()
        root = BUILD._safe_extract(
            self.archive_path("score-general-e2e"),
            detached / "installed",
        )
        vendor_parent = root / "vendor/e2e-shared"
        package = vendor_parent / "wildclawbench_grading_core"
        self.assertTrue((package / "__init__.py").is_file())
        self.assertTrue((package / "rule-runtime-dependencies.json").is_file())
        runtime_script = root / "scripts/score_general_e2e.py"
        self.assertTrue(runtime_script.is_file())
        self.assertTrue((root / "scripts/rule_worker.py").is_file())
        self.assertTrue((root / "references/scoring-runtime-lock.json").is_file())
        self.assertTrue(
            (root / "references/scoring-runtime-requirements.txt").is_file()
        )
        source = """
import json
import sys
sys.path.insert(0, sys.argv[1])
import wildclawbench_grading_core as core
payload = core.inspect_rule_dependencies('import yaml\\nimport playwright.sync_api')
print(json.dumps({'version': core.CORE_VERSION, 'external': payload['external']}))
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-c", source, str(vendor_parent)],
            cwd=detached,
            env={"PATH": ""},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["version"], "0.2.0")
        self.assertEqual(
            {item["distribution"] for item in payload["external"]},
            {"PyYAML", "playwright"},
        )
        self.assertNotIn(str(REPO_ROOT), completed.stdout + completed.stderr)

        runtime_source = """
import importlib.util
import json
import sys
spec = importlib.util.spec_from_file_location('detached_score_runtime', sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
run_rules, error_type = module._import_grading_core()
print(json.dumps({'run_rules': run_rules.__name__, 'error': error_type.__name__}))
"""
        runtime_completed = subprocess.run(
            [sys.executable, "-I", "-c", runtime_source, str(runtime_script)],
            cwd=detached,
            env={"PATH": ""},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(runtime_completed.returncode, 0, runtime_completed.stderr)
        self.assertEqual(
            json.loads(runtime_completed.stdout),
            {"run_rules": "run_rules", "error": "GradingCoreError"},
        )
        self.assertNotIn(
            str(REPO_ROOT), runtime_completed.stdout + runtime_completed.stderr
        )

    def test_general_report_entrypoint_loads_outside_checkout(self) -> None:
        detached = self.temp_root / "detached-general-report"
        detached.mkdir()
        root = BUILD._safe_extract(
            self.archive_path("report-general-e2e"),
            detached / "installed",
        )
        entrypoint = root / "scripts/report_general_e2e.py"
        renderer = root / "scripts/render_general_e2e_excel.mjs"
        contracts = root / "vendor/e2e-shared/general-contracts/validator.py"
        self.assertTrue(entrypoint.is_file())
        self.assertTrue(renderer.is_file())
        self.assertTrue(contracts.is_file())
        completed = subprocess.run(
            [sys.executable, "-I", str(entrypoint), "--help"],
            cwd=detached,
            env={"PATH": ""},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("General E2E 独立报告生成器", completed.stdout)
        self.assertNotIn(str(REPO_ROOT), completed.stdout + completed.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_general_orchestrator_entrypoints_load_outside_checkout(self) -> None:
        detached = self.temp_root / "detached-general-orchestrator"
        detached.mkdir()
        root = BUILD._safe_extract(
            self.archive_path("orchestrate-general-e2e"),
            detached / "installed",
        )
        controller = root / "scripts/orchestrate_general_e2e.py"
        registrar = root / "drivers/codex-desktop/register-projects.mjs"
        self.assertTrue(controller.is_file())
        self.assertTrue(registrar.is_file())
        self.assertTrue(
            (root / "vendor/e2e-shared/desktop-runtime/process.mjs").is_file()
        )
        self.assertTrue(
            (root / "vendor/e2e-shared/handoff/workspace-integrity.mjs").is_file()
        )
        controller_help = subprocess.run(
            [sys.executable, "-I", str(controller), "--help"],
            cwd=detached,
            env={"PATH": ""},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(controller_help.returncode, 0, controller_help.stderr)
        self.assertIn("General E2E Codex", controller_help.stdout)
        registrar_help = subprocess.run(
            ["node", str(registrar), "--help"],
            cwd=detached,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(registrar_help.returncode, 0, registrar_help.stderr)
        self.assertIn("Codex Desktop 项目注册器", registrar_help.stdout)
        self.assertNotIn(
            str(REPO_ROOT),
            controller_help.stdout
            + controller_help.stderr
            + registrar_help.stdout
            + registrar_help.stderr,
        )

    def test_general_execution_schema_and_validation_work_outside_checkout(self) -> None:
        detached = self.temp_root / "detached-general-state"
        detached.mkdir()
        installed = BUILD._safe_extract(self.archive_path("run-general-e2e"), detached / "installed")
        bundled = json.loads((installed / "bundled-components.json").read_text())
        self.assertEqual(bundled["skill_version"], "0.5.1")
        component = next(item for item in bundled["components"] if item["name"] == "general-contracts")
        self.assertEqual(component["version"], "1.2.0")
        for relative in ("execution_state.py", "schemas/general-execution-state-v1.schema.json"):
            self.assertEqual(
                (installed / "vendor/e2e-shared/general-contracts" / relative).read_bytes(),
                (REPO_ROOT / "eval_general_e2e/contracts" / relative).read_bytes(),
            )
        fixture_spec = importlib.util.spec_from_file_location(
            "general_state_build_fixture", REPO_ROOT / "tests/general_e2e/test_run_general_e2e.py"
        )
        fixture = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixture)
        unit, state_path = fixture.create_general_execution_state(detached / "fixture", "qwenwork", "macos")
        command = [sys.executable, "-I", str(installed / "scripts/run_general_e2e.py"),
                   "record-execution", "--root", str(unit), "--state", str(state_path)]
        completed = subprocess.run(command, cwd=detached, env={"PATH": ""}, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["state"]["stages"]["execute"], "COMPLETED")
        value = json.loads(state_path.read_text())
        value["driver"]["platform"] = "windows"
        state_path.write_text(json.dumps(value))
        rejected = subprocess.run(command, cwd=detached, env={"PATH": ""}, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("EXECUTION_DRIVER_BINDING_MISMATCH", rejected.stderr + rejected.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_generic_collection_and_trace_v2_run_from_detached_skill(self) -> None:
        detached = self.temp_root / "detached-general-collection-v2"
        detached.mkdir()
        installed = BUILD._safe_extract(self.archive_path("collect-general-e2e"), detached / "installed")
        bundled = json.loads((installed / "bundled-components.json").read_text())
        self.assertEqual(bundled["skill_version"], "0.7.3")
        component = next(item for item in bundled["components"] if item["name"] == "general-contracts")
        self.assertEqual(component["version"], "1.2.0")
        for relative in ("collection_validation.py", "schemas/trace-index-v2.schema.json"):
            self.assertEqual(
                (installed / "vendor/e2e-shared/general-contracts" / relative).read_bytes(),
                (REPO_ROOT / "eval_general_e2e/contracts" / relative).read_bytes(),
            )
        fixture_uri = (REPO_ROOT / "tests/general_e2e/helpers/general-collection-fixture.mjs").as_uri()
        entry_uri = (installed / "scripts/finalize_general_execution.mjs").as_uri()
        source = f"""
import {{ fixture, fixtureHook }} from {json.dumps(fixture_uri)};
import {{ finalizeGeneralExecution }} from {json.dumps(entry_uri)};
const value = await fixture({{ parent: {json.dumps(str(detached))} }});
value.options.pythonExecutable = {json.dumps(sys.executable)};
const result = await finalizeGeneralExecution(value.options, {{ processCleanup: fixtureHook() }});
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run([shutil.which("node"), "--input-type=module", "-e", source],
            cwd=detached, env={"PATH": ""}, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["receipt_status"], "completed")
        help_result = subprocess.run([shutil.which("node"), str(installed / "scripts/finalize_general_execution.mjs"), "--help"],
            cwd=detached, env={"PATH": ""}, capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)

    def test_general_run_entrypoint_loads_outside_checkout(self) -> None:
        detached = self.temp_root / "detached-general-run"
        detached.mkdir()
        root = BUILD._safe_extract(
            self.archive_path("run-general-e2e"),
            detached / "installed",
        )
        controller = root / "scripts/run_general_e2e.py"
        self.assertTrue(controller.is_file())
        self.assertTrue(
            (root / "vendor/e2e-shared/general-contracts/validator.py").is_file()
        )
        completed = subprocess.run(
            [sys.executable, "-I", str(controller), "--help"],
            cwd=detached,
            env={"PATH": ""},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("General E2E", completed.stdout)
        self.assertNotIn(str(REPO_ROOT), completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
