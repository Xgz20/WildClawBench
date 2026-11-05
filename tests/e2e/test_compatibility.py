from pathlib import Path
import tempfile
import unittest
import zipfile

from src.e2e.common import E2EError, atomic_json, file_sha256
from src.e2e.compatibility import verify_installed


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.batch = Path(self.temp.name)
        packages = self.batch / "packages"
        packages.mkdir()
        archive = packages / "skill.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("skill/SKILL.md", "frozen skill")
        manifest = packages / "skills-build-manifest.json"
        atomic_json(manifest, {"skills": [{"name": "skill", "archive": "skill.zip", "zip_sha256": file_sha256(archive)}]})
        installed = self.batch / "installed/skill"
        installed.mkdir(parents=True)
        (installed / "SKILL.md").write_text("frozen skill")
        self.assets = {"packages": "packages", "installed_skills": "installed", "build_manifest_sha256": file_sha256(manifest)}

    def tearDown(self):
        self.temp.cleanup()

    def test_frozen_installed_skill_is_replayed_against_archive(self):
        verify_installed(self.batch, "web", self.assets)
        (self.batch / "installed/skill/SKILL.md").write_text("changed")
        with self.assertRaisesRegex(E2EError, "INSTALLED_SKILL_DRIFT"):
            verify_installed(self.batch, "web", self.assets)

    def test_python_cache_is_allowed_but_extra_source_is_rejected(self):
        cache = self.batch / "installed/skill/__pycache__"
        cache.mkdir()
        (cache / "module.pyc").write_bytes(b"generated cache")
        verify_installed(self.batch, "web", self.assets)
        (self.batch / "installed/skill/extra.py").write_text("unexpected source")
        with self.assertRaisesRegex(E2EError, "INSTALLED_SKILL_DRIFT"):
            verify_installed(self.batch, "web", self.assets)


if __name__ == "__main__":
    unittest.main()
