from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from eval_general_e2e.adapters import (
    EXPECTED_COMPONENTS,
    inspect_shared_component_layout,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERAL_ADAPTER = REPO_ROOT / "eval_general_e2e/adapters/astronstudio/components.mjs"


def run_node(source: str, *args: str) -> dict:
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", source, *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


class SharedComponentTests(unittest.TestCase):
    def test_source_catalog_and_astronstudio_binding_are_fixed(self) -> None:
        report = inspect_shared_component_layout(REPO_ROOT)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(
            {item["name"]: item["version"] for item in report["components"]},
            {item.name: item.version for item in EXPECTED_COMPONENTS},
        )

    def test_general_adapter_binds_only_canonical_shared_sources(self) -> None:
        source = GENERAL_ADAPTER.read_text(encoding="utf-8")
        self.assertIn("tools/report/e2e-shared", source)
        self.assertNotIn("skills/web-e2e", source)
        payload = run_node(
            f"""
import {{ ASTRONSTUDIO_SHARED_COMPONENTS, nativeResourceParsers }} from {json.dumps(GENERAL_ADAPTER.as_uri())};
process.stdout.write(JSON.stringify({{
  components: ASTRONSTUDIO_SHARED_COMPONENTS,
  schema: nativeResourceParsers.empty().collection.schema_version,
  scope: nativeResourceParsers.empty().collection.scope,
}}));
"""
        )
        self.assertEqual(
            payload["components"],
            {
                "desktop-runtime": "1.0.0",
                "resource-metrics": "1.0.0",
                "workspace-integrity": "1.0.0",
            },
        )
        self.assertEqual(
            payload["schema"],
            "wildclawbench.general-e2e-native-resource-observation/v1",
        )
        self.assertEqual(payload["scope"], "primary-attempt")

    def test_general_workspace_policy_is_explicit_and_not_web_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()
            (root / ".git/config").write_text("fixture", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules/module.js").write_text("fixture", encoding="utf-8")
            payload = run_node(
                f"""
import {{ createGeneralWorkspaceIntegrity }} from {json.dumps(GENERAL_ADAPTER.as_uri())};
let missingPolicy = null;
try {{ createGeneralWorkspaceIntegrity({{}}); }} catch (error) {{ missingPolicy = error.message; }}
const integrity = createGeneralWorkspaceIntegrity({{ ignoredDirectories: [], forbiddenDirectories: [] }});
process.stdout.write(JSON.stringify({{ missingPolicy, snapshot: integrity.snapshotWorkspace(process.argv[1]) }}));
""",
                str(root),
            )
        self.assertIn("explicitly provide", payload["missingPolicy"])
        self.assertEqual(payload["snapshot"]["file_count"], 2)
        self.assertEqual(payload["snapshot"]["forbidden_directories"], [])
        self.assertEqual(payload["snapshot"]["ignored_runtime_directories"], [])

    def test_shared_process_helpers_are_cross_platform_injectable_primitives(self) -> None:
        module = REPO_ROOT / "tools/report/e2e-shared/desktop-runtime/process.mjs"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file = root / "file.txt"
            file.write_text("fixture", encoding="utf-8")
            payload = run_node(
                f"""
import {{ stat }} from "node:fs/promises";
import {{ isDirectory, isFile, runCapture }} from {json.dumps(module.as_uri())};
const result = await runCapture(process.execPath, ["-e", "process.stdout.write('ok')"]);
process.stdout.write(JSON.stringify({{
  command: result,
  file: await isFile(process.argv[1], stat),
  directory: await isDirectory(process.argv[2], stat),
  missing: await isFile(process.argv[3], stat),
}}));
""",
                str(file),
                str(root),
                str(root / "missing"),
            )
        self.assertEqual(payload["command"], {"code": 0, "stdout": "ok", "stderr": ""})
        self.assertTrue(payload["file"])
        self.assertTrue(payload["directory"])
        self.assertFalse(payload["missing"])

    def test_web_vendored_snapshots_match_canonical_sources(self) -> None:
        copies = (
            ("desktop-runtime/process.mjs", "execute-web-e2e/vendor/e2e-shared/desktop-runtime/process.mjs"),
            ("resource-metrics/native-parsers.mjs", "execute-web-e2e/vendor/e2e-shared/resource-metrics/native-parsers.mjs"),
            ("resource-metrics/trace-io.mjs", "execute-web-e2e/vendor/e2e-shared/resource-metrics/trace-io.mjs"),
            ("desktop-runtime/process.mjs", "orchestrate-web-e2e/vendor/e2e-shared/desktop-runtime/process.mjs"),
            ("handoff/workspace-integrity.mjs", "orchestrate-web-e2e/vendor/e2e-shared/handoff/workspace-integrity.mjs"),
            ("handoff/workspace-integrity.mjs", "score-web-e2e/vendor/e2e-shared/handoff/workspace-integrity.mjs"),
        )
        canonical_root = REPO_ROOT / "tools/report/e2e-shared"
        web_root = REPO_ROOT / "tools/report/skills/web-e2e"
        for canonical, vendored in copies:
            with self.subTest(vendored=vendored):
                self.assertEqual(
                    (canonical_root / canonical).read_bytes(),
                    (web_root / vendored).read_bytes(),
                )

    def test_web_adapters_preserve_web_metric_and_integrity_profiles(self) -> None:
        parser = REPO_ROOT / "tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/parsers.mjs"
        orchestrate = REPO_ROOT / "tools/report/skills/web-e2e/orchestrate-web-e2e/scripts/workspace-integrity.mjs"
        score = REPO_ROOT / "tools/report/skills/web-e2e/score-web-e2e/scripts/workspace-integrity.mjs"
        payload = run_node(
            f"""
import {{ empty }} from {json.dumps(parser.as_uri())};
import {{ runtimeDirectoryPolicy as orchestratePolicy }} from {json.dumps(orchestrate.as_uri())};
import {{ runtimeDirectoryPolicy as scorePolicy }} from {json.dumps(score.as_uri())};
process.stdout.write(JSON.stringify({{
  metrics: empty().collection,
  orchestrate: orchestratePolicy(),
  score: scorePolicy(),
}}));
"""
        )
        self.assertEqual(
            payload["metrics"]["schema_version"],
            "wildclawbench.web-e2e-resource-collection/v1",
        )
        self.assertEqual(payload["metrics"]["version"], "1.1.3")
        self.assertEqual(payload["orchestrate"], payload["score"])
        self.assertEqual(payload["score"]["ignored_directories"], [".cache", ".vite", "node_modules"])
        self.assertEqual(payload["score"]["forbidden_directories"], [".git"])


if __name__ == "__main__":
    unittest.main()
