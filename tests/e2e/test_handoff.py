from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile

from src.e2e.agentcube import AgentCubeConfig
from src.e2e.common import read_json
from src.e2e.engine import run_batch
from src.e2e.handoff import prepare_scoring_context
from src.e2e.preparation import prepare_batch
from src.e2e.pipeline import init_orchestration
from src.e2e.packages import export_package, import_package
from src.e2e.store import BatchStore
from src.e2e.preprocessing import augment_prompt, frozen_prompt_directives, frozen_recipe
from tests.e2e.test_scheduler import FakeDriver, Provider


class GeneralImportTests(unittest.TestCase):
    def test_file_candidate_modes_survive_import_and_scoring_prepare(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = Path(__file__).resolve().parents[2]
            task_id = "02_Code_Intelligence_task_001_temperature_cli_fix"
            batch = prepare_batch(repo, root, {
                "batch_id": "general-file-import", "selection": {"scenario": "general",
                    "dataset": "general-custom60-v1", "task_ids": [task_id, "03_Social_Interaction_task_003_colleague_leave_reply"]},
                "units": [{"harness": "astronstudio", "model": "spark-x2.6", "reasoning_effort": "high"}]})
            provider = Provider()

            class FileDriver(FakeDriver):
                def execute(self):
                    self.store.update(self.item['key'], 'PREPARING', prompt=self.prompt_metadata)
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
                from src.e2e.backend import AStudioSandboxDriver
                task = kwargs["task"]
                prompt = (batch / task["input_root"] / "execution/PROMPT.md").read_text()
                driver = FileDriver(**{**kwargs, "task": {**task, "prompt": prompt}}, provider=provider)
                driver.product = 'astudio'; driver.key = driver.item['key']
                payload, driver.prompt_metadata = AStudioSandboxDriver._prompt_input(driver, freeze=True)
                driver.task['prompt'] = payload.decode()
                return driver

            try:
                run_batch(batch, AgentCubeConfig(user_id="synthetic", auth_token="synthetic"), driver_factory=factory)
                archive = root / "result.zip"
                export_package(batch, archive, purpose="scoring",
                               verification_skill=repo / "tools/report/skills/general-e2e/collect-general-e2e")
                imported = import_package(archive, None, root / "recipient")
                context = next(c for c in imported["scoring_contexts"]
                               if read_json(Path(c["context_root"]) / "unit/manifest.json")["task_ids"] == [task_id])
                parent_report = imported["parent_reports"][0]
                self.assertEqual(parent_report["coverage_status"], "complete")
                self.assertEqual(len(read_json(Path(parent_report["path"]) / "manifest.json")["task_ids"]), 2)
                self.assertTrue(parent_report["report_only"])
                context_root = Path(context["context_root"])
                execution = read_json(context_root / context['execution_record'])
                unit_manifest = read_json(context_root / 'unit/manifest.json')
                prompt_meta = unit_manifest['tasks'][0]['prompt']
                self.assertEqual(prompt_meta['sent_sha256'], execution['prompt']['sha256'])
                self.assertNotEqual(execution['prompt']['base_sha256'], execution['prompt']['sha256'])
                self.assertTrue((context_root / 'unit' / Path(prompt_meta['path']).parent / 'base-PROMPT.md').is_file())
                receipt = next((context_root / 'unit/evidence').rglob('metadata/prompt.json'))
                self.assertEqual(read_json(receipt)['prompt_transport']['profile'], 'astudio-environment-card-title/v1')
                self.assertIsNotNone(context["supplemental_verifier"])
                self.assertTrue((context_root / context["supplemental_verifier"]["path"]).is_dir())
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
        self.check_web_handoff(False)

    def test_web_plugin_prompt_survives_scoring_handoff_and_versioned_export(self):
        self.check_web_handoff(True)

    def check_web_handoff(self, mention):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(__file__).resolve().parents[2]
            task_id = "07_Website_Generation_task_002_focus_pomodoro_clock"
            unit = {"harness": "astronstudio", "model": "spark-x2.6", "reasoning_effort": "high"}
            assets = Path(directory) / 'assets';assets.mkdir()
            if mention:
                import hashlib
                package = assets / 'sites.zip'
                with zipfile.ZipFile(package, 'w') as archive:
                    archive.writestr('.codex-plugin/plugin.json', '{"name":"sites-skills","version":"1.0.17"}')
                checksum = hashlib.sha256(package.read_bytes()).hexdigest()
                size = package.stat().st_size;package.rename(assets / checksum)
                unit['preprocessing'] = {'default': {'version_id': 1, 'version': 1, 'name': 'Sites', 'steps': [
                    {'kind': 'plugin', 'target': 'sites-skills', 'marketplace': 'astron-plugin-hub', 'timeout': 20,
                     'asset': {'kind': 'plugin', 'name': 'sites.zip', 'size': size, 'sha256': checksum}}]},
                    'overrides': {}, 'prompt_directives': {'default': ['sites-skills'], 'overrides': {}}}
            batch = prepare_batch(repo, Path(directory), {
                "batch_id": "synthetic-web-handoff", "selection": {"scenario": "web", "task_ids": [task_id]},
                "units": [unit]}, preprocess_asset_dir=assets)
            provider = Provider()

            class PromptDriver(FakeDriver):
                def execute(self):
                    if mention:
                        from src.e2e.common import atomic_json
                        self.store.update(self.item['key'], 'PREPARING', prompt=metadata)
                        atomic_json(self.staging / 'metadata/prompt.json', metadata)
                        (self.staging / 'metadata/effective-prompt.md').write_bytes(self.task['prompt'].encode())
                    outcome = super().execute()
                    if mention:
                        row = self.store.get(self.item['key'])
                        witness = {'status': 'passed', 'verified_after_execution': True,
                            'session_id': row['session_id'], 'attempt_id': row['attempt_id'],
                            'plugin_mentions': ['sites-skills'], 'plugins': [
                                {'name': 'sites-skills', 'version': '1.0.17', 'tree_sha256': 'a' * 64}]}
                        atomic_json(self.staging / 'metadata/prompt-plugins.json', witness)
                        self.store.update(self.item['key'], row['phase'], prompt_plugin_witness=witness)
                    return outcome

            def factory(**kwargs):
                task = kwargs["task"]
                prompt = (batch / task["input_root"] / "execution/PROMPT.md").read_bytes().decode()
                nonlocal metadata
                prompt, metadata = augment_prompt(prompt,
                    frozen_prompt_directives(batch, kwargs['unit']['unit_id'], task_id),
                    frozen_recipe(batch, kwargs['unit']['unit_id'], task_id))
                return PromptDriver(**{**kwargs, "task": {**task, "prompt": prompt}}, provider=provider)

            metadata = None
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
                if mention:
                    self.assertEqual(record['prompt']['sha256'], metadata['effective_prompt_sha256'])
                    self.assertEqual(record['prompt']['plugin_mentions'], ['sites-skills'])
                    self.assertIn('@sites-skills', (root / 'PROMPT.md').read_text())
                    source = Path(context['context_root']) / 'unit/execution/tasks' / task_id
                    self.assertNotIn('@sites-skills', (source / 'base-PROMPT.md').read_text())
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
