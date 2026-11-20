from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.case_catalog import current_cases
from src.e2e.agentcube import AgentCubeConfig
from src.e2e.backend import AStudioSandboxDriver
from src.e2e.common import E2EError
from src.e2e.preparation import normalize_plan
from src.e2e.protocol import preflight


REPO = Path(__file__).resolve().parents[2]


class ManagedTemplatesTest(unittest.TestCase):
    def unit(self):
        return {
            "harness": "astronstudio",
            "model": "spark-x2.6",
            "template": "new-template",
            "template_binding": {
                "id": 14, "namespace": "managed-windows", "image_digest": "sha256:" + "a" * 64,
                "profile_id": "published-astudio", "waa_revision": "b" * 40,
            },
        }

    def plan(self, scene="general"):
        library = {"general": "general-regression", "web": "web-custom"}[scene]
        task = current_cases(REPO, library)[0]
        return {
            "batch_id": "managed-template-test",
            "selection": {"scenario": scene, "library_dataset": library, "task_ids": [task["task_id"]]},
            "units": [self.unit()],
        }

    def test_managed_template_uses_published_client_profile_and_its_own_namespace(self):
        published = [{
            "harness": "astronstudio", "id": "published-astudio", "enabled": True,
            "template": "previous-template", "scenarios": ["general", "web"],
            "models": [{"id": "spark-x2.6"}], "reasoning_efforts": ["high"],
        }]
        with patch("src.e2e.protocol.profiles", return_value=published):
            for scene in ("general", "web"):
                with self.subTest(scene=scene):
                    result = preflight(REPO, self.plan(scene))
                    self.assertTrue(result["valid"], result["issues"])
                    self.assertEqual(result["plan"]["units"][0]["template_binding"], self.unit()["template_binding"])
        seen = []
        unit = normalize_plan(self.plan())["units"][0]
        with tempfile.TemporaryDirectory() as directory:
            AStudioSandboxDriver(batch_root=Path(directory), store=None,
                                item={"key": "sample", "execution_root": "attempt"}, task={},
                                unit=unit, config=AgentCubeConfig(namespace="default"),
                                stop_event=None, client_factory=seen.append)
        self.assertEqual(seen[0].namespace, "managed-windows")
        self.assertEqual(seen[0].template, "new-template")

    def test_rejects_invalid_template_digest(self):
        plan = self.plan()
        plan["units"][0]["template_binding"]["image_digest"] = "floating-image"
        with self.assertRaisesRegex(E2EError, "AGENTCUBE_TEMPLATE_BINDING_INVALID"):
            normalize_plan(plan)
