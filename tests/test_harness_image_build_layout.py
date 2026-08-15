import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ASTRONCODE_DIR = REPO_ROOT / "docker" / "astroncode"
CODEX_DIR = REPO_ROOT / "docker" / "codex"
ASTRONCODE_BUILD = ASTRONCODE_DIR / "build.sh"
CODEX_BUILD = CODEX_DIR / "build.sh"
ASTRONCODE_MANIFEST = ASTRONCODE_DIR / "versions.json"
CODEX_MANIFEST = CODEX_DIR / "versions.json"
ASTRONCODE_WRAPPER = REPO_ROOT / "script" / "build-astroncode-image.sh"
CODEX_WRAPPER = REPO_ROOT / "script" / "build-codex-image.sh"

BUILD_ENV_NAMES = (
    "ASTRONCODE_DOCKER_VARIANT",
    "ASTRON_CODE_VERSION",
    "SEARCH_UPDATER_VERSION",
    "CODEX_VERSION",
    "EVAL_BASE_IMAGE",
    "IMAGE_TAG",
    "NPM_REGISTRY",
    "HTTP_PROXY_INNER",
    "HTTPS_PROXY_INNER",
    "NO_PROXY_INNER",
    "SKIP_SAVE",
    "WCB_LEGACY_BUILD_WRAPPER",
)


class ImageVersionManifestTest(unittest.TestCase):
    def test_astroncode_manifest_binds_official_tags_to_version_contexts(self):
        manifest = self._load_manifest(ASTRONCODE_MANIFEST)
        self.assertEqual("v0.4-ppt", manifest["default"])
        expected_contexts = {
            "v0.1-test.8": "v1",
            "v0.2": "v2",
            "v0.3": "v3",
            "v0.4-ppt": "v4",
        }
        expected_args = {
            "v0.1-test.8": {"ASTRON_CODE_VERSION": "0.0.5-test.8"},
            "v0.2": {"ASTRON_CODE_VERSION": "0.0.6"},
            "v0.3": {"ASTRON_CODE_VERSION": "0.0.13"},
            "v0.4-ppt": {
                "ASTRON_CODE_VERSION": "0.0.13",
                "SEARCH_UPDATER_VERSION": "0.1.17",
            },
        }
        self.assertEqual(set(expected_args), set(manifest["versions"]))

        for version, build_args in expected_args.items():
            with self.subTest(version=version):
                entry = manifest["versions"][version]
                self.assertEqual(
                    f"wildclawbench-astroncode-ubuntu:{version}",
                    entry["image"],
                )
                context = expected_contexts[version]
                self.assertEqual(context, entry["context"])
                self.assertEqual(f"{context}/Dockerfile", entry["dockerfile"])
                self.assertEqual(build_args, entry["build_args"])
                self.assertTrue((ASTRONCODE_DIR / entry["dockerfile"]).is_file())

    def test_codex_manifest_binds_v01_to_pinned_cli_and_base(self):
        manifest = self._load_manifest(CODEX_MANIFEST)
        self.assertEqual("v0.1", manifest["default"])
        self.assertEqual({"v0.1"}, set(manifest["versions"]))
        entry = manifest["versions"]["v0.1"]
        self.assertEqual("wildclawbench-codex-ubuntu:v0.1", entry["image"])
        self.assertEqual("v1", entry["context"])
        self.assertEqual("v1/Dockerfile", entry["dockerfile"])
        self.assertEqual(
            {
                "CODEX_VERSION": "0.146.0",
                "EVAL_BASE_IMAGE": "wildclawbench-codex-ubuntu:v0.0",
            },
            entry["build_args"],
        )
        self.assertTrue((CODEX_DIR / entry["dockerfile"]).is_file())

    def test_harness_directories_do_not_duplicate_version_contexts_under_releases(self):
        self.assertFalse((ASTRONCODE_DIR / "releases").exists())
        self.assertFalse((CODEX_DIR / "releases").exists())

    def test_canonical_builders_are_executable_and_export_capable(self):
        for build_script in (ASTRONCODE_BUILD, CODEX_BUILD):
            with self.subTest(build_script=build_script):
                self.assertTrue(build_script.is_file())
                self.assertTrue(os.access(build_script, os.X_OK))
                source = build_script.read_text(encoding="utf-8")
                self.assertIn("versions.json", source)
                self.assertIn("docker save", source)
                self.assertIn("SKIP_SAVE", source)

    def test_legacy_scripts_only_mark_compatibility_and_exec_canonical_builder(self):
        expected = {
            ASTRONCODE_WRAPPER: "docker/astroncode/build.sh",
            CODEX_WRAPPER: "docker/codex/build.sh",
        }
        for wrapper, canonical_path in expected.items():
            with self.subTest(wrapper=wrapper):
                source = wrapper.read_text(encoding="utf-8")
                self.assertIn('WCB_LEGACY_BUILD_WRAPPER="1"', source)
                self.assertIn(canonical_path, source)
                self.assertRegex(source, r'exec\s+"\$\{REPO_ROOT\}/docker/.+/build\.sh"\s+"\$@"')
                self.assertNotIn("docker build", source)
                self.assertNotIn("docker save", source)

    def _load_manifest(self, path):
        self.assertTrue(path.is_file(), f"missing {path}")
        return json.loads(path.read_text(encoding="utf-8"))


class CanonicalBuildCliTest(unittest.TestCase):
    def test_astroncode_default_build_uses_v4_context_and_pinned_versions(self):
        result, events = self._run_with_docker_stub(
            ["bash", str(ASTRONCODE_BUILD)],
            {"SKIP_SAVE": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        build = self._event(events, "build")
        context = ASTRONCODE_DIR / "v4"
        self.assertEqual(str(context / "Dockerfile"), build[build.index("-f") + 1])
        self.assertEqual(
            "wildclawbench-astroncode-ubuntu:v0.4-ppt",
            build[build.index("-t") + 1],
        )
        self.assertIn("ASTRON_CODE_VERSION=0.0.13", build)
        self.assertIn("SEARCH_UPDATER_VERSION=0.1.17", build)
        self.assertEqual(str(context), build[-1])
        self.assertNotIn("save", [event[0] for event in events])

    def test_astroncode_known_historical_version_has_fixed_tag(self):
        result, events = self._run_with_docker_stub(
            ["bash", str(ASTRONCODE_BUILD), "--version", "v0.3"],
            {"SKIP_SAVE": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        build = self._event(events, "build")
        self.assertEqual(
            "wildclawbench-astroncode-ubuntu:v0.3",
            build[build.index("-t") + 1],
        )
        self.assertIn("ASTRON_CODE_VERSION=0.0.13", build)

    def test_unknown_version_fails_before_docker(self):
        result, events = self._run_with_docker_stub(
            ["bash", str(ASTRONCODE_BUILD), "--version", "v4/../v3"],
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Unknown AstronCode image version", result.stderr)
        self.assertEqual([], events)

    def test_legacy_astroncode_mismatched_variant_and_tag_are_rejected(self):
        result, events = self._run_with_docker_stub(
            ["bash", str(ASTRONCODE_WRAPPER)],
            {
                "ASTRONCODE_DOCKER_VARIANT": "v4",
                "IMAGE_TAG": "v0.4",
                "SKIP_SAVE": "1",
            },
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Unsupported legacy AstronCode build mapping", result.stderr)
        self.assertEqual([], events)

    def test_legacy_astroncode_valid_mapping_reaches_canonical_builder(self):
        result, events = self._run_with_docker_stub(
            ["bash", str(ASTRONCODE_WRAPPER)],
            {
                "ASTRONCODE_DOCKER_VARIANT": "v3",
                "IMAGE_TAG": "v0.3",
                "SKIP_SAVE": "1",
            },
        )
        self.assertEqual(0, result.returncode, result.stderr)
        build = self._event(events, "build")
        self.assertEqual(
            "wildclawbench-astroncode-ubuntu:v0.3",
            build[build.index("-t") + 1],
        )

    def test_pinned_astroncode_version_cannot_be_overridden(self):
        result, events = self._run_with_docker_stub(
            ["bash", str(ASTRONCODE_BUILD), "--version", "v0.3"],
            {"ASTRON_CODE_VERSION": "0.0.99", "SKIP_SAVE": "1"},
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("ASTRON_CODE_VERSION must be 0.0.13", result.stderr)
        self.assertEqual([], events)

    def test_codex_default_build_uses_pinned_tag_cli_and_base(self):
        result, events = self._run_with_docker_stub(
            ["bash", str(CODEX_BUILD)],
            {"SKIP_SAVE": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("image", events[0][0])
        build = self._event(events, "build")
        context = CODEX_DIR / "v1"
        self.assertEqual(str(context / "Dockerfile"), build[build.index("-f") + 1])
        self.assertEqual(
            "wildclawbench-codex-ubuntu:v0.1",
            build[build.index("-t") + 1],
        )
        self.assertIn("CODEX_VERSION=0.146.0", build)
        self.assertIn("EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0", build)
        self.assertEqual(str(context), build[-1])
        self.assertNotIn("save", [event[0] for event in events])

    def test_pinned_codex_base_cannot_be_overridden(self):
        result, events = self._run_with_docker_stub(
            ["bash", str(CODEX_BUILD)],
            {
                "EVAL_BASE_IMAGE": "wildclawbench-codex-ubuntu:custom",
                "SKIP_SAVE": "1",
            },
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "EVAL_BASE_IMAGE must be wildclawbench-codex-ubuntu:v0.0",
            result.stderr,
        )
        self.assertEqual([], events)

    def test_failed_save_does_not_replace_existing_archive(self):
        cases = (
            (
                "astroncode",
                "v0.4-ppt",
                "wildclawbench-astroncode-ubuntu_v0.4-ppt.tar.gz",
            ),
            (
                "codex",
                "v0.1",
                "wildclawbench-codex-ubuntu_v0.1.tar.gz",
            ),
        )
        for harness, version, archive_name in cases:
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as temp_dir:
                repo_root = Path(temp_dir) / "repo"
                harness_dir = repo_root / "docker" / harness
                shutil.copytree(REPO_ROOT / "docker" / harness, harness_dir)
                images_dir = repo_root / "Images"
                images_dir.mkdir()
                archive = images_dir / archive_name
                archive.write_bytes(b"known-good-archive")

                bin_dir = Path(temp_dir) / "bin"
                bin_dir.mkdir()
                docker_stub = bin_dir / "docker"
                docker_stub.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    'case "${1:-}" in\n'
                    "  image|build) exit 0 ;;\n"
                    '  run) printf "version-ok\\n"; exit 0 ;;\n'
                    '  save) printf "partial"; exit 42 ;;\n'
                    "  *) exit 64 ;;\n"
                    "esac\n",
                    encoding="utf-8",
                )
                docker_stub.chmod(0o755)

                environment = os.environ.copy()
                for name in BUILD_ENV_NAMES:
                    environment.pop(name, None)
                environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
                result = subprocess.run(
                    ["bash", str(harness_dir / "build.sh"), "--version", version],
                    cwd=repo_root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertNotEqual(0, result.returncode)
                self.assertEqual(b"known-good-archive", archive.read_bytes())
                self.assertEqual([], list(images_dir.glob(f"{archive_name}.tmp.*")))

    def _run_with_docker_stub(self, command, overrides=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()
            event_log = temp_path / "docker-events.bin"
            docker_stub = bin_dir / "docker"
            docker_stub.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                '{ printf "%s\\000" "$#"; printf "%s\\000" "$@"; } '
                '>> "${DOCKER_EVENT_LOG:?}"\n'
                'case "${1:-}" in\n'
                "  image|build) exit 0 ;;\n"
                '  run) printf "codex-cli 0.146.0\\n"; exit 0 ;;\n'
                '  save) printf "fake image: %s\\n" "${2:-}"; exit 0 ;;\n'
                "  *) exit 64 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            docker_stub.chmod(0o755)

            environment = os.environ.copy()
            for name in BUILD_ENV_NAMES:
                environment.pop(name, None)
            environment.update(overrides or {})
            environment.update(
                {
                    "DOCKER_EVENT_LOG": str(event_log),
                    "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
                }
            )
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            events = self._read_events(event_log) if event_log.exists() else []
            return result, events

    def _event(self, events, command):
        return next(event for event in events if event[0] == command)

    def _read_events(self, event_log):
        fields = event_log.read_bytes().split(b"\0")
        self.assertEqual(b"", fields.pop())
        events = []
        offset = 0
        while offset < len(fields):
            argument_count = int(fields[offset].decode("ascii"))
            event_end = offset + argument_count + 1
            events.append(
                [
                    argument.decode("utf-8")
                    for argument in fields[offset + 1 : event_end]
                ]
            )
            offset = event_end
        return events


if __name__ == "__main__":
    unittest.main()
