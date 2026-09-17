from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
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
                "resource-metrics",
                "workspace-integrity",
                "dataset-bundle-verifier",
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
    def test_general_execute_probe_loads_outside_checkout(self) -> None:
        detached = self.temp_root / "detached-general-execute"
        detached.mkdir()
        root = BUILD._safe_extract(
            self.archive_path("execute-general-e2e"),
            detached / "installed",
        )
        probe = root / "scripts/probe_astronstudio_macos.mjs"
        self.assertTrue(probe.is_file())
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


if __name__ == "__main__":
    unittest.main()
