from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_SKILLS_ROOT = REPO_ROOT / "tools/report/skills/web-e2e"
WEB_SKILLS = (
    "prepare-web-e2e-workspaces",
    "execute-web-e2e",
    "orchestrate-web-e2e",
    "score-web-e2e",
    "report-web-e2e",
    "run-web-e2e",
)
SKILL_BUILDER = REPO_ROOT / "tools/e2e-build/build_skill_packages.py"
FIXED_REVISION = "1" * 40


def load_skill_builder():
    spec = importlib.util.spec_from_file_location(
        "web_e2e_skill_builder_for_layout_test", SKILL_BUILDER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WebE2ESkillLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_builder = load_skill_builder()

    def test_canonical_sources_are_grouped_without_legacy_duplicates(self):
        self.assertEqual(
            sorted(path.name for path in WEB_SKILLS_ROOT.iterdir() if path.is_dir()),
            sorted(WEB_SKILLS),
        )
        for name in WEB_SKILLS:
            canonical = WEB_SKILLS_ROOT / name
            self.assertTrue((canonical / "SKILL.md").is_file(), name)
            self.assertFalse((REPO_ROOT / "tools/report/skills" / name).exists(), name)

    def test_repository_discovery_links_resolve_to_grouped_sources(self):
        for name in WEB_SKILLS:
            link = REPO_ROOT / ".agents/skills" / name
            self.assertTrue(link.is_symlink(), name)
            self.assertEqual(link.resolve(), (WEB_SKILLS_ROOT / name).resolve())
            self.assertEqual(
                link.readlink().as_posix(),
                f"../../tools/report/skills/web-e2e/{name}",
            )

    def test_skill_identity_is_unchanged(self):
        for name in WEB_SKILLS:
            skill_text = (WEB_SKILLS_ROOT / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"name: {name}", skill_text.split("---", 2)[1])
            metadata_path = WEB_SKILLS_ROOT / name / "skill-metadata.json"
            if metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["name"], name)

    def test_independent_zip_top_level_remains_skill_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest = self.skill_builder.build_skill_packages(
                REPO_ROOT,
                temp_root,
                skill_names=WEB_SKILLS,
                source_revision=FIXED_REVISION,
            )
            self.skill_builder.verify_build_manifest(
                temp_root / "skills-build-manifest.json",
                temp_root,
            )
            rows = {row["name"]: row for row in manifest["skills"]}
            for name in WEB_SKILLS:
                archive_path = temp_root / rows[name]["archive"]
                with zipfile.ZipFile(archive_path) as archive:
                    members = archive.namelist()
                self.assertIn(f"{name}/SKILL.md", members)
                self.assertIn(f"{name}/bundled-components.json", members)
                self.assertTrue(members)
                self.assertTrue(
                    all(member.startswith(f"{name}/") for member in members),
                    name,
                )
                self.assertFalse(
                    any(member.startswith("web-e2e/") for member in members),
                    name,
                )


if __name__ == "__main__":
    unittest.main()
