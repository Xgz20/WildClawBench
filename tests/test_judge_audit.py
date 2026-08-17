from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.utils import grading
from src.utils.judge_audit import begin_attempt, finish_attempt, write_attempt


class JudgeAuditTest(unittest.TestCase):
    def test_retry_summary_uses_final_attempt_and_retains_history_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            judge_dir = Path(temp)
            request = {
                "mode": "v2",
                "model": "anthropic/claude-test",
                "endpoint_type": "anthropic_messages",
            }
            first = begin_attempt(judge_dir, request)
            finish_attempt(
                judge_dir,
                first,
                {"status": "success", "model": "claude-test"},
                {"schema_status": "parse_error", "schema_error": "empty"},
            )
            second = begin_attempt(judge_dir, request)
            finish_attempt(
                judge_dir,
                second,
                {"status": "success", "model": "claude-test"},
                {"schema_status": "valid", "value": {"scores": {}, "notes": "ok"}},
            )

            summary = json.loads(
                (judge_dir / "summary.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["attempt_count"], 2)
        self.assertEqual(summary["schema_mismatch_count"], 1)
        self.assertEqual(summary["final_schema_status"], "valid")

    def test_write_attempt_redacts_credentials_and_image_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_attempt(
                Path(tmp),
                1,
                {"headers": {"authorization": "Bearer secret", "x-api-key": "raw-secret"}, "messages": [
                    {"role": "user", "content": [
                        {"type": "text", "text": "OPENROUTER_API_KEY=sk-live-secret X_API_TOKEN=plain-token-123 Bearer abc.def.ghi password=Sup3rSecret! client_password:OtherSecret postgres://user:DbSecret@db.example"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    ]}
                ]},
                {"content": [{"type": "text", "text": "endpoint=https://judge.example/v1?token=query-secret"}], "api_key": "secret"},
                {},
            )
            request = json.loads((Path(tmp) / "attempt-001/request.json").read_text())
            response = json.loads((Path(tmp) / "attempt-001/response.json").read_text())
            self.assertEqual(request["headers"]["authorization"], "[REDACTED]")
            self.assertEqual(request["headers"]["x-api-key"], "[REDACTED]")
            self.assertNotIn("sk-live-secret", request["messages"][0]["content"][0]["text"])
            self.assertNotIn("plain-token-123", request["messages"][0]["content"][0]["text"])
            self.assertNotIn("abc.def.ghi", request["messages"][0]["content"][0]["text"])
            self.assertNotIn("Sup3rSecret", request["messages"][0]["content"][0]["text"])
            self.assertNotIn("OtherSecret", request["messages"][0]["content"][0]["text"])
            self.assertNotIn("DbSecret", request["messages"][0]["content"][0]["text"])
            self.assertEqual(request["messages"][0]["content"][1]["image_url"]["url"], "[IMAGE_DATA_OMITTED]")
            self.assertEqual(response["api_key"], "[REDACTED]")
            self.assertNotIn("query-secret", response["content"][0]["text"])

    @patch("src.utils.grading.subprocess.run")
    def test_legacy_grading_collects_in_container_judge_audit(self, run: Mock) -> None:
        run.return_value = Mock(
            returncode=0,
            stdout='{"overall_score": 1.0}',
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            grading._run_grading_legacy(
                "task",
                "def grade(**kwargs): return {'overall_score': 1.0}",
                output_dir,
            )

        exec_calls = [
            call.args[0]
            for call in run.call_args_list
            if call.args and call.args[0][:2] == ["docker", "exec"]
        ]
        self.assertEqual(len(exec_calls), 1)
        self.assertTrue(any(
            arg.startswith("WILDCLAW_JUDGE_AUDIT_DIR=/tmp/wildclaw-judge-audit-")
            for arg in exec_calls[0]
        ))
        self.assertTrue(any(
            call.args
            and call.args[0][:2] == ["docker", "cp"]
            and ":/tmp/wildclaw-judge-audit-" in call.args[0][2]
            and call.args[0][3].endswith("/judge")
            for call in run.call_args_list
        ))

    @patch("src.utils.grading.subprocess.run")
    def test_legacy_grading_stops_when_required_judge_shim_copy_fails(
        self, run: Mock
    ) -> None:
        def result(args, **kwargs):
            if args[:2] == ["docker", "cp"] and args[2].endswith("judge_shim.py"):
                return Mock(returncode=1, stdout="", stderr="copy failed")
            return Mock(returncode=0, stdout='{"overall_score": 1.0}', stderr="")

        run.side_effect = result
        with tempfile.TemporaryDirectory() as temp:
            scores = grading._run_grading_legacy(
                "task",
                "def grade(**kwargs): return {'overall_score': 1.0}",
                Path(temp),
            )

        self.assertIn("judge shim", scores["error"])
        self.assertFalse(any(
            call.args and call.args[0][:2] == ["docker", "exec"]
            for call in run.call_args_list
        ))

    @patch("src.utils.grading.subprocess.run")
    def test_legacy_grading_stops_when_judge_audit_copy_in_times_out(
        self, run: Mock
    ) -> None:
        def result(args, **kwargs):
            if args[:2] == ["docker", "cp"] and args[2].endswith("judge_audit.py"):
                raise subprocess.TimeoutExpired(args, 30)
            return Mock(returncode=0, stdout='{"overall_score": 1.0}', stderr="")

        run.side_effect = result
        with tempfile.TemporaryDirectory() as temp:
            scores = grading._run_grading_legacy(
                "task",
                "def grade(**kwargs): return {'overall_score': 1.0}",
                Path(temp),
            )

        self.assertIn("judge audit", scores["error"])
        self.assertIn("timed out", scores["error"])
        self.assertFalse(any(
            call.args and call.args[0][:2] == ["docker", "exec"]
            for call in run.call_args_list
        ))

    @patch("src.utils.grading.subprocess.run")
    def test_v2_judge_runner_stops_when_required_shim_copy_fails(
        self, run: Mock
    ) -> None:
        def result(args, **kwargs):
            if args[:2] == ["docker", "cp"] and args[2].endswith("judge_shim.py"):
                return Mock(returncode=1, stdout="", stderr="copy failed")
            return Mock(returncode=0, stdout="{}", stderr="")

        run.side_effect = result
        parsed, error = grading._exec_container_python("task", "print('{}')", "")

        self.assertIsNone(parsed)
        self.assertIn("judge shim", error)
        self.assertFalse(any(
            call.args and call.args[0][:2] == ["docker", "exec"]
            for call in run.call_args_list
        ))

    @patch("src.utils.grading.subprocess.run")
    def test_legacy_grading_timeout_marks_audit_failed(
        self, run: Mock
    ) -> None:
        def result(args, **kwargs):
            if (
                args[:2] == ["docker", "exec"]
                and "python3" in args
                and args[-1] == "/tmp/_grade_runner.py"
            ):
                raise subprocess.TimeoutExpired(args, 1)
            if args[:2] == ["docker", "exec"] and "pgrep" in args:
                return Mock(returncode=1, stdout="", stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        run.side_effect = result
        secret = "do-not-persist-this-api-token"
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            "os.environ",
            {
                "WILDCLAW_GRADING_TIMEOUT_SECONDS": "1",
                "OPENROUTER_API_KEY": secret,
            },
            clear=True,
        ):
            scores = grading._run_grading_legacy(
                "task",
                "from openai import OpenAI\ndef grade(**kwargs): return {'overall_score': 1.0}\nclient = OpenAI()\nclient.chat.completions.create(model='anthropic/test', messages=[])",
                Path(temp),
                extra_env="OPENROUTER_API_KEY",
            )
            summary = json.loads(
                (Path(temp) / "judge/summary.json").read_text(encoding="utf-8")
            )

        self.assertIn("timed out", scores["error"])
        self.assertNotIn(secret, json.dumps({"score": scores, "summary": summary}))
        self.assertEqual(summary["status"], "failed")
        self.assertIn("timeout", summary["error"])
        self.assertTrue(any(
            call.args and call.args[0][:2] == ["docker", "exec"]
            and "pkill" in call.args[0]
            for call in run.call_args_list
        ))

    @patch("src.utils.grading.subprocess.run")
    def test_legacy_grading_audit_copy_timeout_is_structured_failure(
        self, run: Mock
    ) -> None:
        def result(args, **kwargs):
            if args[:2] == ["docker", "cp"] and len(args) > 2 and ":/tmp/wildclaw-judge-audit-" in args[2]:
                raise subprocess.TimeoutExpired(args, 30)
            if args[:2] == ["docker", "exec"] and len(args) > 3 and args[3] == "test":
                return Mock(returncode=0, stdout="", stderr="")
            if args[:2] == ["docker", "exec"]:
                return Mock(returncode=0, stdout='{"overall_score": 1.0}', stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        run.side_effect = result
        with tempfile.TemporaryDirectory() as temp:
            scores = grading._run_grading_legacy(
                "task",
                "from openai import OpenAI\ndef grade(**kwargs): return {'overall_score': 1.0}\nclient = OpenAI()\nclient.chat.completions.create(model='anthropic/test', messages=[])",
                Path(temp),
            )
            summary = json.loads(
                (Path(temp) / "judge/summary.json").read_text(encoding="utf-8")
            )

        self.assertIn("audit copy timed out", scores["error"])
        self.assertEqual(summary["status"], "failed")

    @patch("src.utils.grading.subprocess.run")
    def test_legacy_grading_fails_when_judge_audit_copy_fails(
        self, run: Mock
    ) -> None:
        def result(args, **kwargs):
            if args[:2] == ["docker", "cp"] and len(args) > 2 and ":/tmp/wildclaw-judge-audit-" in args[2]:
                return Mock(returncode=1, stdout="", stderr="audit copy failed")
            if args[:2] == ["docker", "exec"]:
                return Mock(returncode=0, stdout='{"overall_score": 1.0}', stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        run.side_effect = result
        with tempfile.TemporaryDirectory() as temp:
            scores = grading._run_grading_legacy(
                "task",
                "from openai import OpenAI\ndef grade(**kwargs): return {'overall_score': 1.0}\nclient = OpenAI()\nclient.chat.completions.create(model='anthropic/test', messages=[])",
                Path(temp),
            )
            summary = json.loads(
                (Path(temp) / "judge/summary.json").read_text(encoding="utf-8")
            )

        self.assertIn("audit copy", scores["error"])
        self.assertEqual(summary["status"], "failed")
        self.assertIn("copy failed", summary["error"])

    @patch("src.utils.grading.subprocess.run")
    def test_legacy_early_return_without_judge_call_keeps_score(
        self, run: Mock
    ) -> None:
        def result(args, **kwargs):
            if args[:2] == ["docker", "cp"] and len(args) > 2 and ":/tmp/wildclaw-judge-audit-" in args[2]:
                judge_dir = Path(args[3])
                judge_dir.mkdir(parents=True, exist_ok=True)
                (judge_dir / "summary.json").write_text(
                    json.dumps({
                        "schema_version": 1,
                        "mode": "legacy",
                        "status": "not_called",
                        "attempt_count": 0,
                    }),
                    encoding="utf-8",
                )
                return Mock(returncode=0, stdout="", stderr="")
            if args[:2] == ["docker", "exec"]:
                return Mock(returncode=0, stdout='{"overall_score": 0.0}', stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        run.side_effect = result
        with tempfile.TemporaryDirectory() as temp:
            scores = grading._run_grading_legacy(
                "task",
                "from openai import OpenAI\ndef grade(**kwargs): return {'overall_score': 0.0}\nclient = OpenAI()\nclient.chat.completions.create(model='anthropic/test', messages=[])",
                Path(temp),
            )

        self.assertEqual(scores["overall_score"], 0.0)
        self.assertNotIn("error", scores)


if __name__ == "__main__":
    unittest.main()
