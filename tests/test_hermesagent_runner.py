from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from eval import run_batch
from src.agents.base import AgentTaskSpec
from src.agents.hermesagent import bench_runner
from src.agents.hermesagent.runner import HermesAgentAgent


class _FinishedProcess:
    returncode = 0

    def wait(self, timeout=None):
        _ = timeout
        return 0


class _FailedProcess(_FinishedProcess):
    returncode = 7


class _TimedOutProcess:
    returncode = None

    def __init__(self):
        self.killed = False

    def wait(self, timeout=None):
        if timeout is not None and not self.killed:
            raise subprocess.TimeoutExpired("hermes", timeout)
        self.returncode = -9
        return self.returncode

    def kill(self):
        self.killed = True


class HermesAgentBenchRunnerTest(unittest.TestCase):
    def test_passes_max_tokens_and_writes_structured_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            result_path = root / "result.json"
            config_path.write_text(json.dumps({
                "config": {
                    "model": "xopglm52",
                    "api_key": "test-key",
                    "base_url": "https://example.invalid/v2",
                    "max_iterations": 90,
                    "max_tokens": 8192,
                    "reasoning_config": {"enabled": True, "effort": "high"},
                },
                "prompt": "test prompt",
            }), encoding="utf-8")
            captured = {}

            class FakeAIAgent:
                def __init__(self, **kwargs):
                    captured.update(kwargs)

                def run_conversation(self, prompt):
                    self.prompt = prompt
                    return {
                        "completed": False,
                        "partial": True,
                        "error": "Response truncated due to output length limit",
                        "api_calls": 12,
                        "messages": [{"role": "user", "content": "not exported"}],
                    }

            fake_module = types.SimpleNamespace(AIAgent=FakeAIAgent)
            with (
                patch.object(bench_runner, "BENCH_CONFIG_PATH", str(config_path)),
                patch.object(bench_runner, "BENCH_RESULT_PATH", str(result_path), create=True),
                patch.object(bench_runner, "HERMES_INSTALL_DIR", temp_dir),
                patch.dict(sys.modules, {"run_agent": fake_module}),
            ):
                self.assertEqual(bench_runner.main(), 0)

            self.assertEqual(captured["max_tokens"], 8192)
            self.assertEqual(json.loads(result_path.read_text(encoding="utf-8")), {
                "completed": False,
                "partial": True,
                "error": "Response truncated due to output length limit",
                "api_calls": 12,
            })


class HermesAgentRunnerTest(unittest.TestCase):
    def test_backend_is_registered_for_error_grading(self) -> None:
        self.assertIn(HermesAgentAgent, run_batch.GRADE_ON_ERROR_BACKENDS)

    def test_reads_optional_max_tokens_from_environment(self) -> None:
        with patch.dict(os.environ, {"HERMES_MAX_TOKENS": "8192"}, clear=False):
            agent = HermesAgentAgent()
        self.assertEqual(getattr(agent, "max_tokens", None), 8192)

    def test_invalid_max_tokens_keeps_provider_default(self) -> None:
        for raw_value in ("0", "-1", "invalid"):
            with self.subTest(raw_value=raw_value):
                with patch.dict(
                    os.environ, {"HERMES_MAX_TOKENS": raw_value}, clear=False
                ):
                    agent = HermesAgentAgent()
                self.assertIsNone(agent.max_tokens)

    def test_incomplete_harness_result_is_valid_finished_capability_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            workspace = root / "workspace"
            workspace.mkdir()
            spec = AgentTaskSpec(
                task_id="hermes-test",
                task={"env": "", "skills": "", "skills_path": "", "warmup": ""},
                workspace_path=str(workspace),
                prompt="test prompt",
                timeout_seconds=300,
                output_dir=output_dir,
                model="xopglm52",
            )
            agent = HermesAgentAgent()
            agent._read_bench_result = Mock(return_value={
                "completed": False,
                "partial": True,
                "error": "Response truncated due to output length limit",
                "api_calls": 12,
            })

            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_prepare_workspace"),
                patch.object(agent, "_configure_hermes"),
                patch.object(agent, "_write_bench_runner"),
                patch.object(agent, "_run_bench_runner_background", return_value=_FinishedProcess()),
                patch.object(agent, "_cleanup_bench_config"),
                patch.object(agent, "_close_runner_streams"),
                patch.object(agent, "_probe_harness_version", return_value="0.9.0"),
                patch("src.agents.hermesagent.runner.setup_skills"),
                patch("src.agents.hermesagent.runner.run_warmup"),
            ):
                execution = agent.run_task(spec)

            self.assertIsNone(execution.error)
            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["status"], "finished")
            self.assertEqual(status["exit_code"], 0)
            self.assertFalse(status["task_completed"])
            self.assertTrue(status["partial"])
            self.assertEqual(status["termination_reason"], "output_length_limit")
            self.assertEqual(
                status["completion_error"],
                "Response truncated due to output length limit",
            )
            self.assertEqual(status["max_tokens"], None)

    def test_nonzero_harness_exit_is_recorded_as_execution_error(self) -> None:
        execution, status = self._run_with_process(_FailedProcess())

        self.assertEqual(execution.error, "HermesAgent run failed (rc=7)")
        self.assertEqual(status["status"], "error")
        self.assertEqual(status["failure_stage"], "hermesagent_running")
        self.assertEqual(status["exit_code"], 7)
        self.assertFalse(status["timed_out"])

    def test_process_error_includes_log_tail_for_environment_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "agent.log"
            log_path.write_text(
                "OCI runtime error: Cannot connect to the Docker daemon\n",
                encoding="utf-8",
            )

            error = HermesAgentAgent._process_error(125, log_path)

        self.assertTrue(error.startswith("HermesAgent run failed (rc=125)"))
        self.assertIn("Cannot connect to the Docker daemon", error)

    def test_timeout_is_recorded_and_does_not_read_bench_result(self) -> None:
        process = _TimedOutProcess()
        execution, status, agent = self._run_with_process(process, return_agent=True)

        self.assertEqual(execution.error, "HermesAgent run timed out")
        self.assertEqual(status["status"], "timed_out")
        self.assertEqual(status["failure_stage"], "hermesagent_running")
        self.assertTrue(status["timed_out"])
        self.assertTrue(process.killed)
        agent._read_bench_result.assert_not_called()

    def test_missing_bench_result_is_framework_collection_error(self) -> None:
        execution, status = self._run_with_process(
            _FinishedProcess(),
            bench_result_error=RuntimeError("HermesAgent bench result not found"),
        )

        self.assertEqual(execution.error, "HermesAgent bench result not found")
        self.assertEqual(status["status"], "error")
        self.assertEqual(status["failure_stage"], "collecting_artifacts")
        self.assertEqual(status["exit_code"], 0)

    def test_collect_usage_preserves_observed_requests_and_marks_cost_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            (output_dir / "execution_status.json").write_text(json.dumps({
                "status": "finished",
                "api_calls": 12,
                "harness_version": "0.9.0",
            }), encoding="utf-8")
            empty_usage = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "request_count": 0,
            }
            observed_usage = {
                **empty_usage,
                "input_tokens": 300,
                "output_tokens": 50,
                "total_tokens": 350,
                "request_count": 15,
            }
            agent = HermesAgentAgent()

            with (
                patch("src.agents.hermesagent.runner.subprocess.run", return_value=Mock(
                    returncode=1, stderr="missing transcript"
                )),
                patch.object(agent, "_extract_usage_from_session_logs", return_value=empty_usage.copy()),
                patch.object(agent, "_extract_usage_from_agent_log", return_value=observed_usage),
                patch.object(agent, "_copy_session_log"),
                patch.object(agent, "_probe_harness_version") as version_probe,
            ):
                usage = agent.collect_usage("hermes-test", output_dir, 4.5)

            self.assertEqual(usage["request_count"], 15)
            self.assertEqual(usage["cost_status"], "unavailable")
            version_probe.assert_not_called()

    def _run_with_process(
        self,
        process,
        *,
        bench_result_error: Exception | None = None,
        return_agent: bool = False,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            workspace = root / "workspace"
            workspace.mkdir()
            spec = AgentTaskSpec(
                task_id="hermes-test",
                task={"env": "", "skills": "", "skills_path": "", "warmup": ""},
                workspace_path=str(workspace),
                prompt="test prompt",
                timeout_seconds=300,
                output_dir=output_dir,
                model="xopglm52",
            )
            agent = HermesAgentAgent()
            if bench_result_error is None:
                agent._read_bench_result = Mock(return_value={
                    "completed": True,
                    "partial": False,
                    "error": None,
                    "api_calls": 3,
                })
            else:
                agent._read_bench_result = Mock(side_effect=bench_result_error)

            with (
                patch.object(agent, "_start_container"),
                patch.object(agent, "_prepare_workspace"),
                patch.object(agent, "_configure_hermes"),
                patch.object(agent, "_write_bench_runner"),
                patch.object(agent, "_run_bench_runner_background", return_value=process),
                patch.object(agent, "_cleanup_bench_config"),
                patch.object(agent, "_close_runner_streams"),
                patch.object(agent, "_probe_harness_version", return_value="0.9.0"),
                patch("src.agents.hermesagent.runner.setup_skills"),
                patch("src.agents.hermesagent.runner.run_warmup"),
            ):
                execution = agent.run_task(spec)

            status = json.loads(
                (output_dir / "execution_status.json").read_text(encoding="utf-8")
            )
            result = (execution, status, agent) if return_agent else (execution, status)
            return result


if __name__ == "__main__":
    unittest.main()
