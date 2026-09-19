from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

from eval_general_e2e.adapters.components import inspect_shared_component_layout
from eval_general_e2e.contracts import validate_contract


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests/general_e2e/fixtures/qwenwork"


class QwenWorkAdapterLayoutTests(unittest.TestCase):
    def test_qwenwork_binding_uses_only_declared_shared_components(self) -> None:
        result = inspect_shared_component_layout(REPO_ROOT, adapter="qwenwork")
        self.assertEqual(result["status"], "PASS", result["errors"])
        binding = json.loads(
            (REPO_ROOT / "eval_general_e2e/adapters/qwenwork/components.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            binding["components"],
            {
                "desktop-runtime": "1.0.0",
                "desktop-app-discovery": "1.2.0",
                "resource-metrics": "1.0.0",
                "general-contracts": "1.2.0",
            },
        )

    def test_committed_fixtures_are_redacted_and_use_synthetic_paths(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(FIXTURES.iterdir())
            if path.is_file()
        )
        self.assertIn("[REDACTED_USER_PROMPT]", combined)
        self.assertIn("[REDACTED_TOOL_OUTPUT]", combined)
        self.assertNotIn("/Users/", combined)
        self.assertNotIn("report-workspace", combined)
        self.assertNotIn("debug-workspace", combined)

    def test_generated_resource_metrics_pass_strict_general_contract(self) -> None:
        script = r"""
import { readFile } from "node:fs/promises";
import { buildQwenGeneralResourceMetrics } from "./eval_general_e2e/adapters/qwenwork/index.mjs";
const root = "./tests/general_e2e/fixtures/qwenwork";
const rows = (await readFile(`${root}/segments-redacted.jsonl`, "utf8"))
  .split(/\r?\n/u).filter(Boolean).map(JSON.parse);
const identities = await Promise.all([
  "runtime-current-macos-1.0.6.json",
  "runtime-historical-macos-1.0.5.json",
].map(async (name) => JSON.parse(await readFile(`${root}/${name}`, "utf8"))));
const results = identities.map((runtimeIdentity, index) => buildQwenGeneralResourceMetrics({
  identity: { batch_id: "batch", unit_id: "qwenwork-macos", task_id: "task", attempt_id: `attempt-${index}` },
  segmentRows: rows,
  runtimeIdentity,
  sources: [{ path: "evidence/qwenwork/segments.jsonl", sha256: "1".repeat(64), size: 100 }],
  collectedAt: "2026-09-17T03:01:00Z",
  executionDurationSeconds: 6,
}).resource_metrics);
process.stdout.write(JSON.stringify(results));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        current, historical = json.loads(result.stdout)
        validate_contract(current)
        validate_contract(historical)
        self.assertIsNone(current["metrics"]["usage"]["total_tokens"]["value"])
        self.assertEqual(
            current["metrics"]["usage"]["total_tokens"]["status"],
            "unavailable",
        )
        self.assertEqual(historical["metrics"]["usage"]["total_tokens"]["value"], 300)
        self.assertEqual(historical["metrics"]["usage"]["total_tokens"]["status"], "observed")


if __name__ == "__main__":
    unittest.main()
