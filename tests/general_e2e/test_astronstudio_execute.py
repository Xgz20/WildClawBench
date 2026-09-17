from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
NODE_TEST = REPO_ROOT / "tests/general_e2e/astronstudio_execute.test.mjs"


class AstronStudioMacosExecutionTests(unittest.TestCase):
    def test_node_execution_contract_suite(self) -> None:
        completed = subprocess.run(
            ["node", "--test", str(NODE_TEST)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
