from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from dotenv import load_dotenv

from src.agents.base import AgentExecution, AgentTaskSpec, BaseAgent
from src.agents.claudecode.transcript import convert_claudecode_chat_to_openclaw_jsonl
from src.utils.docker_utils import container_resource_args, run_warmup, setup_skills, snapshot_workspace_state
from src.utils.endpoint_utils import normalize_openrouter_base_url_for_claudecode
from src.utils.model_limits import resolve_maas_max_tokens

load_dotenv()

logger = logging.getLogger(__name__)
CLAUDECODE_SKILLS_DIR = "/root/.claude/skills"
CLAUDECODE_COMPAT_TRANSCRIPT_PATH = "/tmp/claudecode/openclaw_chat.jsonl"
OPENCLAW_COMPAT_TRANSCRIPT_PATH = "/root/.openclaw/agents/main/sessions/chat.jsonl"
DEFAULT_PROGRESS_LOG_INTERVAL_SECONDS = 30.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_agent_log_event(output_dir: Path, event: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    enriched = {"timestamp": _now_iso(), **event}
    with (output_dir / "agent.log").open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(enriched, ensure_ascii=False) + "\n")


def write_execution_status(output_dir: Path, **updates: Any) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "execution_status.json"
    status: dict[str, Any] = {}
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = {}

    previous_stage = str(status.get("status") or "")
    next_status = str(updates.get("status") or "")
    if (
        next_status in {"error", "timed_out"}
        and "failure_stage" not in updates
        and previous_stage
        and previous_stage not in {"error", "timed_out", "finished"}
    ):
        updates["failure_stage"] = previous_stage

    status.update(updates)
    status["updated_at"] = _now_iso()
    status_path.write_text(
        json.dumps(status, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return status


def initialize_host_run_artifacts(
    output_dir: Path,
    task_id: str,
    model: str,
    timeout_seconds: int,
    *,
    image: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "agent.log").touch(exist_ok=True)
    write_execution_status(
        output_dir,
        task_id=task_id,
        harness="claudecode",
        image=image,
        model=model,
        timeout_seconds=timeout_seconds,
        status="created",
        started_at=_now_iso(),
        timed_out=False,
        exit_code=None,
        error=None,
    )
    append_agent_log_event(
        output_dir,
        {
            "type": "runner.status",
            "stage": "created",
            "message": "Host-side run artifacts initialized before container startup.",
        },
    )


class ClaudeCodeAgent(BaseAgent):
    def __init__(
        self,
        image: str | None = None,
        anthropic_api_key: str = "",
        anthropic_base_url: str = "",
        openrouter_base_url: str = "",
    ) -> None:
        self.image = (
            image
            or os.environ.get("DOCKER_IMAGE_CLAUDECODE")
            or os.environ.get("CLAUDECODE_DOCKER_IMAGE")
            or "wildclawbench-claudecode-ubuntu:v0.3"
        )
        explicit_api_key = anthropic_api_key.strip()
        self.api_key = explicit_api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.openrouter_base_url = normalize_openrouter_base_url_for_claudecode(
            openrouter_base_url or os.environ.get("OPENROUTER_BASE_URL", "")
        )
        explicit_base_url = anthropic_base_url.strip()
        self.api_base_url = explicit_base_url.rstrip("/") if explicit_base_url else self.openrouter_base_url

    @property
    def expects_gateway(self) -> bool:
        return False

    @property
    def transcript_container_path(self) -> str:
        return "/claude_code/log/chat.json"

    def prepare_grading_transcript(self, task_id: str) -> str:
        with tempfile.TemporaryDirectory(prefix="claudecode_transcript_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            chat_host = tmp_root / "chat.json"
            compat_host = tmp_root / "chat.jsonl"

            r_cp = subprocess.run(
                ["docker", "cp", f"{task_id}:{self.transcript_container_path}", str(chat_host)],
                capture_output=True,
                text=True,
            )
            if r_cp.returncode != 0:
                logger.warning(
                    "[%s] Failed to copy ClaudeCode transcript for grading: %s",
                    task_id,
                    r_cp.stderr.strip(),
                )
                return self.transcript_container_path

            converted_count = convert_claudecode_chat_to_openclaw_jsonl(chat_host, compat_host)
            container_parent = str(PurePosixPath(CLAUDECODE_COMPAT_TRANSCRIPT_PATH).parent)
            r_mkdir = subprocess.run(
                ["docker", "exec", task_id, "mkdir", "-p", container_parent],
                capture_output=True,
                text=True,
            )
            if r_mkdir.returncode != 0:
                logger.warning(
                    "[%s] Failed to create ClaudeCode compat transcript dir (%s): %s",
                    task_id,
                    container_parent,
                    r_mkdir.stderr.strip(),
                )
                return self.transcript_container_path

            r_push = subprocess.run(
                ["docker", "cp", str(compat_host), f"{task_id}:{CLAUDECODE_COMPAT_TRANSCRIPT_PATH}"],
                capture_output=True,
                text=True,
            )
            if r_push.returncode != 0:
                logger.warning(
                    "[%s] Failed to copy ClaudeCode compat transcript into container: %s",
                    task_id,
                    r_push.stderr.strip(),
                )
                return self.transcript_container_path

            openclaw_parent = str(PurePosixPath(OPENCLAW_COMPAT_TRANSCRIPT_PATH).parent)
            r_openclaw_mkdir = subprocess.run(
                ["docker", "exec", task_id, "mkdir", "-p", openclaw_parent],
                capture_output=True,
                text=True,
            )
            if r_openclaw_mkdir.returncode == 0:
                r_openclaw_push = subprocess.run(
                    ["docker", "cp", str(compat_host), f"{task_id}:{OPENCLAW_COMPAT_TRANSCRIPT_PATH}"],
                    capture_output=True,
                    text=True,
                )
                if r_openclaw_push.returncode != 0:
                    logger.warning(
                        "[%s] Failed to copy ClaudeCode compat transcript to OpenClaw path: %s",
                        task_id,
                        r_openclaw_push.stderr.strip(),
                    )
            else:
                logger.warning(
                    "[%s] Failed to create OpenClaw compat transcript dir (%s): %s",
                    task_id,
                    openclaw_parent,
                    r_openclaw_mkdir.stderr.strip(),
                )

            logger.info(
                "[%s] ClaudeCode transcript normalized for grading (%d messages): %s",
                task_id,
                converted_count,
                CLAUDECODE_COMPAT_TRANSCRIPT_PATH,
            )
            return CLAUDECODE_COMPAT_TRANSCRIPT_PATH

    def run_task(self, spec: AgentTaskSpec) -> AgentExecution:
        elapsed_time = float(spec.timeout_seconds)
        start_time = time.perf_counter()
        task_id = spec.task_id
        initialize_host_run_artifacts(
            output_dir=spec.output_dir,
            task_id=task_id,
            model=spec.model,
            timeout_seconds=spec.timeout_seconds,
            image=self.image,
        )

        try:
            write_execution_status(spec.output_dir, status="starting_container")
            self._start_container(task_id, spec.workspace_path, spec.model)
            write_execution_status(
                spec.output_dir,
                status="container_started",
                harness_version=self._probe_harness_version(task_id),
            )
            write_execution_status(spec.output_dir, status="preparing_workspace")
            self._prepare_workspace(task_id)
            self._copy_tmp_files(task_id, spec.workspace_path)
            write_execution_status(spec.output_dir, status="preparing_skills")
            setup_skills(
                task_id,
                spec.task.get("skills", ""),
                spec.task.get("skills_path", ""),
                container_skills_root=CLAUDECODE_SKILLS_DIR,
            )
            write_execution_status(spec.output_dir, status="preparing_warmup")
            run_warmup(task_id, spec.task.get("warmup", ""))
            write_execution_status(spec.output_dir, status="snapshotting_workspace")
            snapshot_workspace_state(task_id)
            write_execution_status(spec.output_dir, status="preparing_harness_input")
            write_execution_status(spec.output_dir, status="claudecode_running")
            self._run_prompt(
                task_id,
                spec.prompt,
                spec.model,
                spec.timeout_seconds,
                spec.output_dir,
                thinking=spec.thinking,
            )
            elapsed_time = time.perf_counter() - start_time
            write_execution_status(
                spec.output_dir,
                status="finished",
                timed_out=False,
                elapsed_time=round(elapsed_time, 2),
                exit_code=0,
            )
            return AgentExecution(elapsed_time=elapsed_time, error=None, gateway_proc=None, agent_proc=None)
        except subprocess.TimeoutExpired:
            logger.info("[%s] ClaudeCode timed out...", task_id)
            elapsed_time = float(spec.timeout_seconds)
            append_agent_log_event(
                spec.output_dir,
                {
                    "type": "runner.timeout",
                    "message": f"ClaudeCode timed out after {spec.timeout_seconds} seconds.",
                    "timeout_seconds": spec.timeout_seconds,
                    "elapsed_time": elapsed_time,
                },
            )
            write_execution_status(
                spec.output_dir,
                status="timed_out",
                timed_out=True,
                elapsed_time=round(elapsed_time, 2),
                error="ClaudeCode run timed out",
            )
            return AgentExecution(
                elapsed_time=elapsed_time,
                error="ClaudeCode run timed out",
                gateway_proc=None,
                agent_proc=None,
            )
        except Exception as exc:
            logger.error("[%s] ClaudeCode execution error: %s", task_id, exc)
            elapsed_time = time.perf_counter() - start_time
            append_agent_log_event(
                spec.output_dir,
                {
                    "type": "runner.error",
                    "stage": "claudecode_execution",
                    "message": str(exc),
                    "elapsed_time": round(elapsed_time, 2),
                },
            )
            write_execution_status(
                spec.output_dir,
                status="error",
                error=str(exc),
                elapsed_time=round(elapsed_time, 2),
            )
            return AgentExecution(
                elapsed_time=elapsed_time,
                error=str(exc),
                gateway_proc=None,
                agent_proc=None,
            )

    def collect_usage(self, task_id: str, output_dir: Path, elapsed_time: float) -> dict[str, Any]:
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
            "elapsed_time": round(elapsed_time, 2),
        }
        output_dir.mkdir(parents=True, exist_ok=True)

        log_dest = output_dir / "claude_code_log"
        log_dest.mkdir(parents=True, exist_ok=True)
        self._copy_file_from_container(task_id, "/claude_code/log/chat.json", log_dest / "chat.json")
        self._copy_dir_from_container(task_id, "/claude_code/log/.", log_dest)
        self._sync_agent_log_from_claude_logs(task_id, output_dir, log_dest)

        # Keep the native JSONL log under claude_code_log and expose the
        # normalized OpenClaw-shaped transcript at the run root for graders,
        # anomaly scanning, replay, and report generation.
        convert_claudecode_chat_to_openclaw_jsonl(
            log_dest / "chat.json",
            output_dir / "chat.jsonl",
        )

        chat_parsed = self._extract_usage_from_chat_json(log_dest / "chat.json")
        if any(
            chat_parsed.get(key, 0) > 0
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "cost_usd",
            )
        ):
            parsed = chat_parsed
        else:
            parsed = self._extract_usage_from_usage_json(log_dest / "usage.json")

        authoritative_request_count = self._extract_request_count_from_chat_json(
            log_dest / "chat.json"
        )
        if authoritative_request_count > 0:
            parsed["request_count"] = authoritative_request_count

        if not any(
            parsed.get(key, 0) > 0
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "cost_usd",
            )
        ):
            fallback = self._extract_usage_from_logs(log_dest)
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "total_tokens",
                "cost_usd",
                "request_count",
            ):
                parsed_value = parsed.get(key, 0)
                fallback_value = fallback.get(key, 0)
                if (parsed_value is None or parsed_value <= 0) and fallback_value > 0:
                    parsed[key] = fallback_value
            if authoritative_request_count > 0:
                parsed["request_count"] = authoritative_request_count

        usage.update(parsed)
        usage["elapsed_time"] = round(elapsed_time, 2)
        return usage

    def _extract_usage_from_chat_json(self, chat_path: Path) -> dict[str, Any]:
        totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
        }
        if not chat_path.exists():
            return totals

        try:
            content = chat_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return totals

        payloads: list[Any] = []
        try:
            parsed = json.loads(content)
            payloads = parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            for line in content.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    payloads.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        official_usage = self._extract_official_result_usage(payloads)
        if official_usage is not None:
            return official_usage

        for payload in payloads:
            self._accumulate_costed_usage(payload, totals)

        totals["total_tokens"] = (
            totals["input_tokens"]
            + totals["output_tokens"]
            + totals["cache_read_tokens"]
            + totals["cache_write_tokens"]
        )
        if totals["request_count"] > 0 and totals["cost_usd"] == 0.0:
            totals["cost_usd"] = self._estimate_cost(totals)
        totals["cost_usd"] = round(totals["cost_usd"], 6)
        return totals

    def _extract_official_result_usage(
        self,
        payloads: list[Any],
    ) -> dict[str, Any] | None:
        for payload in reversed(payloads):
            if not isinstance(payload, dict) or payload.get("type") != "result":
                continue
            usage = payload.get("usage")
            if not isinstance(usage, dict):
                continue

            input_tokens = int(self._num(usage.get("input_tokens")))
            output_tokens = int(self._num(usage.get("output_tokens")))
            cache_read_tokens = int(
                self._num(usage.get("cache_read_input_tokens"))
            )
            cache_write_tokens = int(
                self._num(usage.get("cache_creation_input_tokens"))
            )
            request_count = int(self._num(payload.get("num_turns")))
            if request_count <= 0:
                request_count = sum(
                    1
                    for row in payloads
                    if isinstance(row, dict) and row.get("type") == "assistant"
                )
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
                "total_tokens": (
                    input_tokens
                    + output_tokens
                    + cache_read_tokens
                    + cache_write_tokens
                ),
                "cost_usd": round(
                    self._num(payload.get("total_cost_usd")),
                    6,
                ),
                "request_count": request_count,
            }
        return None

    def _accumulate_costed_usage(self, payload: Any, totals: dict[str, Any]) -> None:
        if isinstance(payload, list):
            for item in payload:
                self._accumulate_costed_usage(item, totals)
            return
        if not isinstance(payload, dict):
            return

        if (
            "input_tokens" in payload
            and "output_tokens" in payload
            and ("cost_details" in payload or "cost" in payload)
        ):
            input_tokens = int(payload.get("input_tokens") or 0)
            output_tokens = int(payload.get("output_tokens") or 0)
            cache_read_tokens = int(payload.get("cache_read_input_tokens") or 0)
            cache_write_tokens = int(payload.get("cache_creation_input_tokens") or 0)
            cost_details = payload.get("cost_details")
            cost = self._num(
                cost_details.get("upstream_inference_cost") if isinstance(cost_details, dict) else payload.get("cost"),
                default=0.0,
            )

            if (
                input_tokens == 0
                and output_tokens == 0
                and cache_read_tokens == 0
                and cache_write_tokens == 0
                and cost == 0
            ):
                return

            totals["input_tokens"] += input_tokens
            totals["output_tokens"] += output_tokens
            totals["cache_read_tokens"] += cache_read_tokens
            totals["cache_write_tokens"] += cache_write_tokens
            totals["cost_usd"] += cost
            totals["request_count"] += 1
            return

        for value in payload.values():
            self._accumulate_costed_usage(value, totals)

    def _sync_agent_log_from_claude_logs(self, task_id: str, output_dir: Path, log_dest: Path) -> None:
        candidates = (
            log_dest / "agent.log",
            log_dest / "chat.json",
            log_dest / "chat.jsonl",
        )
        for src in candidates:
            if not src.exists() or not src.is_file():
                continue
            try:
                content = src.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                logger.warning("[%s] Failed to read ClaudeCode log source %s: %s", task_id, src, exc)
                continue
            if not content.strip():
                continue
            try:
                (output_dir / "agent.log").write_text(content, encoding="utf-8")
            except Exception as exc:
                logger.warning("[%s] Failed to write agent.log from %s: %s", task_id, src, exc)
                return
            logger.info("[%s] agent.log synced from %s", task_id, src)
            return

    def _copy_file_from_container(self, task_id: str, src: str, dest: Path) -> None:
        r = subprocess.run(
            ["docker", "cp", f"{task_id}:{src}", str(dest)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            logger.warning("[%s] ClaudeCode file copy failed (%s): %s", task_id, src, r.stderr.strip())

    def _copy_dir_from_container(self, task_id: str, src: str, dest: Path) -> None:
        r = subprocess.run(
            ["docker", "cp", f"{task_id}:{src}", str(dest)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            logger.warning("[%s] ClaudeCode log dir copy failed: %s", task_id, r.stderr.strip())

    def _start_container(self, task_id: str, workspace_path: str, model: str = "") -> None:
        proxy_http = os.environ.get("HTTP_PROXY_INNER", "")
        proxy_https = os.environ.get("HTTPS_PROXY_INNER", "")
        env_map = {
            "ANTHROPIC_API_KEY": self.api_key,
            "ANTHROPIC_BASE_URL": self.api_base_url,
            "OPENROUTER_API_KEY": self.api_key,
            "OPENROUTER_BASE_URL": self.openrouter_base_url,
            "DISABLE_PROMPT_CACHING": os.environ.get("DISABLE_PROMPT_CACHING", "1"),
            "DISABLE_INTERLEAVED_THINKING": os.environ.get("DISABLE_INTERLEAVED_THINKING", "1"),
            "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": os.environ.get("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "1"),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": os.environ.get(
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1"
            ),
            "DISABLE_AUTOUPDATER": os.environ.get("DISABLE_AUTOUPDATER", "1"),
            "IS_SANDBOX": os.environ.get("IS_SANDBOX", "1"),
            "CLAUDE_CODE_FULL_LOG_PATH": os.environ.get("CLAUDE_CODE_FULL_LOG_PATH", "./log"),
            "http_proxy": proxy_http,
            "https_proxy": proxy_https,
            "HTTP_PROXY": proxy_http,
            "HTTPS_PROXY": proxy_https,
        }
        maas_max_tokens = resolve_maas_max_tokens(model, self.api_base_url)
        if maas_max_tokens is not None:
            # Claude Code exposes this setting for the Anthropic Messages
            # max_tokens field.  It is injected only for MaaS candidates.
            env_map["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(maas_max_tokens)
        env_args: list[str] = []
        for key, value in env_map.items():
            if value:
                env_args += ["-e", f"{key}={value}"]

        exec_path = os.path.join(workspace_path, "exec")
        os.makedirs(exec_path, exist_ok=True)
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            task_id,
            *container_resource_args(),
            *env_args,
            "-v",
            f"{exec_path}:/workspace:ro",
            self.image,
            "/bin/bash",
            "-c",
            "tail -f /dev/null",
        ]
        logger.info("[%s] Starting ClaudeCode container (%s)", task_id, self.image)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ClaudeCode container startup failed:\n{r.stderr}")
        logger.info("[%s] Container ID: %s", task_id, r.stdout.strip()[:12])
        self._patch_claudecode_runtime(task_id)

    def _patch_claudecode_runtime(self, task_id: str) -> None:
        patch_cmd = r"""python3 - <<'PY'
from pathlib import Path

path = Path("/claude_code/src/tasks/LocalAgentTask/LocalAgentTask.tsx")
if not path.exists():
    raise SystemExit(0)
text = path.read_text(encoding="utf-8")
old = "  const usage = message.message.usage;\n  // Keep latest input (it's cumulative in the API), sum outputs\n"
new = '''  const usage = message.message.usage ?? {
    input_tokens: 0,
    cache_creation_input_tokens: 0,
    cache_read_input_tokens: 0,
    output_tokens: 0,
  };
  // Keep latest input (it's cumulative in the API), sum outputs
'''
if old in text and new not in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
PY"""
        r = subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c", patch_cmd],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            logger.warning("[%s] ClaudeCode runtime patch failed: %s", task_id, r.stderr.strip())

    def _prepare_workspace(self, task_id: str) -> None:
        r = subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-c",
                "mkdir -p /tmp_workspace && cp -r /workspace/. /tmp_workspace && chmod -R u+w /tmp_workspace",
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"ClaudeCode workspace copy failed:\n{r.stderr}")

    def _copy_tmp_files(self, task_id: str, workspace_path: str) -> None:
        tmp_path = Path(workspace_path) / "tmp"
        if not tmp_path.exists():
            return
        r_mkdir = subprocess.run(
            ["docker", "exec", task_id, "mkdir", "-p", "/tmp_workspace/tmp"],
            capture_output=True,
            text=True,
        )
        if r_mkdir.returncode != 0:
            raise RuntimeError(f"ClaudeCode tmp directory setup failed:\n{r_mkdir.stderr}")
        r_cp = subprocess.run(
            ["docker", "cp", f"{tmp_path}/.", f"{task_id}:/tmp_workspace/tmp/"],
            capture_output=True,
            text=True,
        )
        if r_cp.returncode != 0:
            raise RuntimeError(f"ClaudeCode tmp copy failed:\n{r_cp.stderr}")

    @staticmethod
    def _build_prompt_command(
        prompt: str,
        model: str,
        thinking: str | None = None,
    ) -> str:
        normalized_thinking = thinking.strip() if thinking else ""
        effort_arg = (
            f" --effort {shlex.quote(normalized_thinking)}"
            if normalized_thinking
            else ""
        )
        prompt_event = json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                },
            },
            ensure_ascii=False,
        )
        official_command = (
            "mkdir -p /claude_code/log && "
            "cd /tmp_workspace && "
            "set -o pipefail && "
            f"{{ printf '%s\\n' {shlex.quote(prompt_event)}; "
            "IS_SANDBOX=1 claude "
            "--print --verbose --output-format stream-json "
            "--dangerously-skip-permissions "
            "--no-session-persistence --no-chrome "
            "--add-dir /tmp_workspace "
            f"--model {shlex.quote(model)}"
            f"{effort_arg} "
            f"-- {shlex.quote(prompt)}; }} "
            "| tee /claude_code/log/chat.json"
        )
        legacy_command = (
            "cd /claude_code && "
            "IS_SANDBOX=1 ./start.sh "
            "--add-dir /tmp_workspace "
            f"--model {shlex.quote(model)}"
            f"{effort_arg} "
            f"-p {shlex.quote(prompt)}"
        )
        return (
            "if command -v claude >/dev/null 2>&1; then "
            f"{official_command}; "
            "elif [ -x /claude_code/start.sh ]; then "
            f"{legacy_command}; "
            "else echo 'Claude Code CLI is not installed' >&2; exit 127; fi"
        )

    def _run_prompt(
        self,
        task_id: str,
        prompt: str,
        model: str,
        timeout_seconds: int,
        output_dir: Path,
        thinking: str | None = None,
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = self._build_prompt_command(prompt, model, thinking=thinking)
        full_cmd = ["docker", "exec", task_id, "/bin/bash", "-c", cmd]
        log_path = output_dir / "agent.log"
        progress_interval = self._progress_log_interval_seconds()
        start_time = time.perf_counter()
        deadline = start_time + timeout_seconds

        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            proc = subprocess.Popen(
                full_cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            logger.info(
                "[%s] Started ClaudeCode process PID=%s → %s",
                task_id,
                proc.pid,
                log_path,
            )
            logger.info("[%s] Waiting for ClaudeCode to finish...", task_id)
            write_execution_status(
                output_dir,
                status="claudecode_running",
                pid=proc.pid,
                progress_log_interval_seconds=progress_interval,
            )

            while True:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    self._terminate_prompt_process(task_id, proc)
                    raise subprocess.TimeoutExpired(full_cmd, timeout_seconds)

                try:
                    returncode = proc.wait(timeout=min(progress_interval, remaining))
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.perf_counter() - start_time
                    if elapsed >= timeout_seconds:
                        self._terminate_prompt_process(task_id, proc)
                        raise subprocess.TimeoutExpired(full_cmd, timeout_seconds)

                    log_file.flush()
                    try:
                        log_bytes = log_path.stat().st_size
                    except OSError:
                        log_bytes = 0
                    write_execution_status(
                        output_dir,
                        status="claudecode_running",
                        pid=proc.pid,
                        elapsed_time=round(elapsed, 2),
                        agent_log_bytes=log_bytes,
                    )
                    logger.info(
                        "[%s] ClaudeCode still running, elapsed: %.0fs/%ds, agent.log: %d bytes",
                        task_id,
                        elapsed,
                        timeout_seconds,
                        log_bytes,
                    )

        elapsed = time.perf_counter() - start_time
        if returncode == 0:
            logger.info(
                "[%s] ClaudeCode finished successfully, elapsed: %.2f seconds",
                task_id,
                elapsed,
            )
        logger.info("[%s] ClaudeCode exit code: %s", task_id, returncode)
        if returncode != 0:
            raise RuntimeError(
                f"ClaudeCode run failed (rc={returncode}); see {log_path}"
            )

    @staticmethod
    def _progress_log_interval_seconds() -> float:
        raw = os.environ.get("WILDCLAW_PROGRESS_LOG_INTERVAL_SECONDS", "").strip()
        if not raw:
            return DEFAULT_PROGRESS_LOG_INTERVAL_SECONDS
        try:
            interval = float(raw)
        except ValueError:
            logger.warning(
                "Invalid WILDCLAW_PROGRESS_LOG_INTERVAL_SECONDS=%r; using %.0fs",
                raw,
                DEFAULT_PROGRESS_LOG_INTERVAL_SECONDS,
            )
            return DEFAULT_PROGRESS_LOG_INTERVAL_SECONDS
        if interval <= 0:
            logger.warning(
                "WILDCLAW_PROGRESS_LOG_INTERVAL_SECONDS must be > 0, got %r; using %.0fs",
                raw,
                DEFAULT_PROGRESS_LOG_INTERVAL_SECONDS,
            )
            return DEFAULT_PROGRESS_LOG_INTERVAL_SECONDS
        return interval

    @staticmethod
    def _terminate_prompt_process(
        task_id: str,
        proc: subprocess.Popen[str],
    ) -> None:
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    task_id,
                    "/bin/bash",
                    "-lc",
                    (
                        "pkill -TERM -f '[s]tart.sh' 2>/dev/null || true; "
                        "pkill -TERM -f '[c]laude' 2>/dev/null || true"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                "[%s] Failed to stop ClaudeCode processes in container: %s",
                task_id,
                exc,
            )
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning(
                "[%s] ClaudeCode docker exec did not exit after kill",
                task_id,
            )

    def _extract_usage_from_logs(self, log_dir: Path) -> dict[str, Any]:
        totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
        }
        if not log_dir.exists():
            return totals

        for file_path in log_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {".json", ".jsonl", ".log", ".txt"}:
                continue
            self._accumulate_from_file(file_path, totals)

        totals["total_tokens"] = (
            totals["input_tokens"]
            + totals["output_tokens"]
            + totals["cache_read_tokens"]
            + totals["cache_write_tokens"]
        )
        totals["cost_usd"] = round(self._estimate_cost(totals), 6)
        return totals

    def _extract_usage_from_usage_json(self, usage_path: Path) -> dict[str, Any]:
        totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
        }
        if not usage_path.exists():
            return totals

        try:
            payload = json.loads(usage_path.read_text(encoding="utf-8"))
        except Exception:
            return totals

        if not isinstance(payload, dict):
            return totals

        # Support both known schemas:
        # 1) totalInputTokens / totalOutputTokens / totalCostUSD / modelUsage
        # 2) total_cost_usd + nested usage.{input_tokens,output_tokens,...}
        usage_block = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}

        totals["input_tokens"] = int(
            self._num(
                payload.get("totalInputTokens", usage_block.get("input_tokens")),
            )
        )
        totals["output_tokens"] = int(
            self._num(
                payload.get("totalOutputTokens", usage_block.get("output_tokens")),
            )
        )
        totals["cache_read_tokens"] = int(
            self._num(
                payload.get("totalCacheReadInputTokens", usage_block.get("cache_read_input_tokens")),
            )
        )
        totals["cache_write_tokens"] = int(
            self._num(
                payload.get("totalCacheCreationInputTokens", usage_block.get("cache_creation_input_tokens")),
            )
        )
        totals["cost_usd"] = round(
            self._num(
                payload.get("totalCostUSD", payload.get("total_cost_usd")),
                default=0.0,
            ),
            6,
        )

        totals["total_tokens"] = (
            totals["input_tokens"]
            + totals["output_tokens"]
            + totals["cache_read_tokens"]
            + totals["cache_write_tokens"]
        )

        totals["request_count"] = self._request_count_from_model_usage(payload.get("modelUsage"))
        return totals

    def _request_count_from_model_usage(self, model_usage: Any) -> int:
        if isinstance(model_usage, list):
            total = 0
            for item in model_usage:
                if not isinstance(item, dict):
                    continue
                total += int(
                    self._num(
                        item.get("requestCount", item.get("requests", item.get("count"))),
                        default=0,
                    )
                )
            return total

        if isinstance(model_usage, dict):
            total = 0
            for value in model_usage.values():
                if not isinstance(value, dict):
                    continue
                total += int(
                    self._num(
                        value.get("requestCount", value.get("requests", value.get("count"))),
                        default=0,
                    )
                )
            return total

        return 0

    def _extract_request_count_from_chat_json(self, chat_path: Path) -> int:
        if not chat_path.exists():
            return 0
        try:
            content = chat_path.read_text(encoding="utf-8")
        except Exception:
            return 0

        rows: list[Any] = []
        try:
            payload = json.loads(content)
        except Exception:
            payload = None

        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = [payload]
        else:
            for line in content.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(row)

        model_requests = sum(
            1
            for row in rows
            if isinstance(row, dict)
            and str(row.get("event", "")).lower() == "model_request"
        )
        if model_requests > 0:
            return model_requests

        query_starts = sum(
            1
            for row in rows
            if isinstance(row, dict)
            and str(row.get("event", "")).lower() == "query_start"
        )
        if query_starts > 0:
            return query_starts

        for row in reversed(rows):
            if not isinstance(row, dict) or row.get("type") != "result":
                continue
            num_turns = int(self._num(row.get("num_turns")))
            if num_turns > 0:
                return num_turns

        return sum(
            1
            for row in rows
            if isinstance(row, dict)
            and (
                str(row.get("role", "")).lower() == "assistant"
                or str(row.get("type", "")).lower() == "assistant"
                or (
                    isinstance(row.get("message"), dict)
                    and str(row["message"].get("role", "")).lower()
                    == "assistant"
                )
            )
        )

    @staticmethod
    def _probe_harness_version(task_id: str) -> str:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    task_id,
                    "/bin/bash",
                    "-lc",
                    (
                        "if command -v claude >/dev/null 2>&1; then "
                        "claude --version; "
                        "elif [ -f /claude_code/package.json ]; then "
                        "node -p \"require('/claude_code/package.json').version\"; "
                        "else exit 127; fi"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("[%s] ClaudeCode version probe failed: %s", task_id, exc)
            return ""
        if result.returncode != 0:
            logger.warning(
                "[%s] ClaudeCode package version probe returned %s: %s",
                task_id,
                result.returncode,
                (result.stderr or result.stdout).strip(),
            )
            return ""
        first_line = (result.stdout or "").strip().splitlines()
        return first_line[0].split()[0] if first_line else ""

    def _num(self, value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return default
        return default

    def _accumulate_from_file(self, file_path: Path, totals: dict[str, Any]) -> None:
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return

        for line in lines:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = self._find_usage(payload)
            if usage is None:
                continue
            totals["request_count"] += 1
            totals["input_tokens"] += int(usage.get("input_tokens", usage.get("input", 0)) or 0)
            totals["output_tokens"] += int(usage.get("output_tokens", usage.get("output", 0)) or 0)
            totals["cache_read_tokens"] += int(
                usage.get("cache_read_input_tokens", usage.get("cacheRead", 0)) or 0
            )
            totals["cache_write_tokens"] += int(
                usage.get("cache_creation_input_tokens", usage.get("cacheWrite", 0)) or 0
            )

    def _find_usage(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if "usage" in payload and isinstance(payload["usage"], dict):
            return payload["usage"]
        message = payload.get("message")
        if isinstance(message, dict) and isinstance(message.get("usage"), dict):
            return message["usage"]
        return None

    def _estimate_cost(self, totals: dict[str, Any]) -> float:
        input_price = float(os.environ.get("CLAUDECODE_INPUT_PRICE_PER_MTOK", "0"))
        output_price = float(os.environ.get("CLAUDECODE_OUTPUT_PRICE_PER_MTOK", "0"))
        cache_read_price = float(os.environ.get("CLAUDECODE_CACHE_READ_PRICE_PER_MTOK", "0"))
        cache_write_price = float(os.environ.get("CLAUDECODE_CACHE_WRITE_PRICE_PER_MTOK", "0"))
        return (
            totals["input_tokens"] / 1_000_000 * input_price
            + totals["output_tokens"] / 1_000_000 * output_price
            + totals["cache_read_tokens"] / 1_000_000 * cache_read_price
            + totals["cache_write_tokens"] / 1_000_000 * cache_write_price
        )
