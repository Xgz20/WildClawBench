from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from src.e2e.agentcube import AgentCubeConfig
from src.e2e.common import read_json
from src.e2e.engine import run_batch
from src.e2e.handoff import prepare_scoring_context
from src.e2e.preparation import prepare_batch
from src.e2e.pipeline import init_orchestration
from src.e2e.packages import export_package, import_package
from src.e2e.store import BatchStore
from tests.e2e.test_scheduler import FakeDriver, Provider


class GeneralImportTests(unittest.TestCase):
    def test_file_candidate_modes_survive_import_and_scoring_prepare(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = Path(__file__).resolve().parents[2]
            task_id = "02_Code_Intelligence_task_001_temperature_cli_fix"
            batch = prepare_batch(repo, root, {
                "batch_id": "general-file-import", "selection": {"scenario": "general",
                    "dataset": "general-custom60-v1", "task_ids": [task_id]},
                "units": [{"harness": "astronstudio", "model": "spark-x2.6", "reasoning_effort": "high"}]})
            provider = Provider()

            class FileDriver(FakeDriver):
                def execute(self):
                    outcome = super().execute()
                    outcome["cleanup"].update(workspace=r"C:\ProgramData\WGUI\workspace\project",
                                              before=[], root_pid=None, disposition="already_exited")
                    project = self.staging / "collect/workspace/project"
                    project.mkdir()
                    (project / "answer.py").write_text("print('answer')\n")
                    evidence = self.staging / "collect/evidence"
                    evidence.mkdir()
                    (evidence / "diagnostics.json").write_text(json.dumps({"product_version": "synthetic"}))
                    return outcome

            def factory(**kwargs):
                task = kwargs["task"]
                prompt = (batch / task["input_root"] / "execution/PROMPT.md").read_text()
                return FileDriver(**{**kwargs, "task": {**task, "prompt": prompt}}, provider=provider)

            try:
                run_batch(batch, AgentCubeConfig(user_id="synthetic", auth_token="synthetic"), driver_factory=factory)
                archive = root / "result.zip"
                export_package(batch, archive, purpose="scoring")
                imported = import_package(archive, None, root / "recipient")
                context = imported["scoring_contexts"][0]
                context_root = Path(context["context_root"])
                project = next((context_root / "unit").glob("evidence/tasks/*/*/candidate/workspace/project"))
                self.assertEqual(project.stat().st_mode & 0o777, 0o555)
                project.chmod(0o755)
                import_package(archive, None, root / "recipient")
                self.assertEqual(project.stat().st_mode & 0o777, 0o555)
                skills = Path(context["installed_skills"])
                result = subprocess.run([sys.executable, str(skills / "orchestrate-general-e2e/scripts/orchestrate_general_e2e.py"),
                    "init", "--unit-root", str(context_root / context["unit_root"]),
                    "--scoring-package", str(context_root / context["scoring_package"]),
                    "--report-config", str(context_root / context["report_config"]),
                    "--score-skill-dir", str(skills / "score-general-e2e"), "--output-root", str(root / "scores"),
                    "--orchestration-id", "file-import-score"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                for path in root.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o700)


class WebHandoffTests(unittest.TestCase):
    def test_canonical_web_handoff_preserves_execution_trace_and_known_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(__file__).resolve().parents[2]
            task_id = "07_Website_Generation_task_002_focus_pomodoro_clock"
            batch = prepare_batch(repo, Path(directory), {
                "batch_id": "synthetic-web-handoff", "selection": {"scenario": "web", "task_ids": [task_id]},
                "units": [{"harness": "astronstudio", "model": "spark-x2.6", "reasoning_effort": "high"}]})
            provider = Provider()

            def factory(**kwargs):
                task = kwargs["task"]
                prompt = (batch / task["input_root"] / "execution/PROMPT.md").read_text()
                return FakeDriver(**{**kwargs, "task": {**task, "prompt": prompt}}, provider=provider)

            try:
                result = run_batch(batch, AgentCubeConfig(user_id="synthetic", auth_token="synthetic"), driver_factory=factory)
                self.assertEqual(result["status"], "COMPLETED")
                store = BatchStore(batch)
                claim = store.claim_score("synthetic-test", 3, mode="streaming")
                context = prepare_scoring_context(batch, claim["key"], claim["claim_id"])
                root = Path(context["context_root"]) / "unit/score/tasks" / task_id
                record = read_json(root / "execution_record.json")
                self.assertEqual(record["execution"]["status"], "completed")
                self.assertEqual(record["usage"]["input_tokens"], 100)
                self.assertEqual(record["usage"]["total_tokens"], 110)
                self.assertIsNone(record["usage"]["request_count"])
                self.assertEqual(record["tools"]["call_count"], 1)
                self.assertEqual(record["usage"]["collection"]["scope"], "primary-task")
                self.assertTrue((root / record["artifacts"]["harness_transcript"]).is_file())
                self.assertTrue((root / "trace/raw/rollout-test.jsonl").is_file())
                self.assertTrue(init_orchestration(batch, claim["key"], claim["claim_id"]))
                current = store.scoring_rows()[0]
                self.assertEqual(current["phase"], "RUNNING")
                self.assertTrue(Path(current["orchestration"]["state_file"]).is_file())
                archive = Path(directory) / "download.zip"
                export_package(batch, archive, purpose="scoring")
                imported = import_package(archive, None, Path(directory) / "recipient")
                self.assertEqual(imported["scoring_contexts"][0]["scene"], "web")
                report_config = Path(imported["local_reports"][0]["path"])
                self.assertTrue(report_config.is_file())
                self.assertIn("web-e2e-detailed-v1", report_config.read_text())
            finally:
                for path in Path(directory).rglob("*"):
                    if path.is_dir():
                        path.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
