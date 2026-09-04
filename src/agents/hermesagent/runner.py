from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.agents.base import AgentExecution, AgentTaskSpec, BaseAgent
from src.utils.docker_utils import (
    container_resource_args,
    run_warmup,
    setup_skills,
    inject_lobster_workspace,
    TMP_WORKSPACE,
)
from src.utils.grading import extract_usage_from_jsonl
from src.utils.model_limits import maas_max_tokens_enabled, resolve_maas_max_tokens

load_dotenv()

logger = logging.getLogger(__name__)

HERMES_IMAGE = os.environ.get("HERMES_DOCKER_IMAGE", "wildclawbench-hermes-agent:v0.5")
HERMES_HOME = "/root/.hermes"
HERMES_INSTALL_DIR = "/opt/hermes"
HERMES_VENV_PYTHON = "/opt/hermes/.venv/bin/python3"

OPENCLAW_COMPAT_TRANSCRIPT_PATH = "/root/.openclaw/agents/main/sessions/chat.jsonl"
BENCH_RUNNER_HOST_PATH = Path(__file__).with_name("bench_runner.py")
BENCH_CONFIG_CONTAINER_PATH = "/tmp/hermes_bench_config.json"
BENCH_RESULT_CONTAINER_PATH = "/tmp/hermes_bench_result.json"
COMPAT_TRANSCRIPT_HOST_PATH = Path(__file__).with_name("compat_transcript.py")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_execution_status(output_dir: Path, **updates: Any) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "execution_status.json"
    status: dict[str, Any] = {}
    if status_path.exists():
        try:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                status = loaded
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
    serialized = json.dumps(status, indent=2, ensure_ascii=False)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{status_path.name}.", suffix=".tmp", dir=output_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, status_path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return status


def initialize_host_run_artifacts(
    output_dir: Path,
    task_id: str,
    model: str,
    timeout_seconds: int,
    *,
    image: str,
    max_tokens: int | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "agent.log").touch(exist_ok=True)
    write_execution_status(
        output_dir,
        task_id=task_id,
        harness="hermesagent",
        image=image,
        model=model,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        status="created",
        started_at=_now_iso(),
        timed_out=False,
        exit_code=None,
        error=None,
        task_completed=None,
        partial=False,
        termination_reason=None,
        completion_error=None,
        api_calls=0,
    )


def _optional_positive_int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using provider default", name, raw)
        return None
    if value <= 0:
        logger.warning("Ignoring non-positive %s=%r; using provider default", name, raw)
        return None
    return value


class HermesAgentAgent(BaseAgent):
    def __init__(
        self,
        image: str | None = None,
        openrouter_api_key: str = "",
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        brave_api_key: str = "",
    ) -> None:
        self.image = image or HERMES_IMAGE
        self.openrouter_api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.openrouter_base_url = openrouter_base_url
        self.brave_api_key = brave_api_key or os.environ.get("BRAVE_API_KEY", "")
        self.max_tokens = _optional_positive_int_env("HERMES_MAX_TOKENS")

    def _resolve_max_tokens(self, model: str, base_url: str) -> int | None:
        """Keep the legacy override while honoring the shared injection switch."""
        if not maas_max_tokens_enabled():
            return None
        if self.max_tokens is not None:
            return self.max_tokens
        return resolve_maas_max_tokens(model, base_url)

    @property
    def expects_gateway(self) -> bool:
        return False

    @property
    def transcript_container_path(self) -> str:
        return OPENCLAW_COMPAT_TRANSCRIPT_PATH

    def prepare_grading_transcript(self, task_id: str) -> str:
        self._write_compat_transcript(task_id)
        return self.transcript_container_path

    def run_task(self, spec: AgentTaskSpec) -> AgentExecution:
        elapsed_time = float(spec.timeout_seconds)
        start_time = time.perf_counter()
        agent_proc: subprocess.Popen[str] | None = None
        initialize_host_run_artifacts(
            spec.output_dir,
            spec.task_id,
            spec.model,
            spec.timeout_seconds,
            image=self.image,
            max_tokens=self.max_tokens,
        )

        try:
            api_key, base_url = self._resolve_runtime_provider(spec.model, spec.models_config)
            max_tokens = self._resolve_max_tokens(spec.model, base_url)
            write_execution_status(spec.output_dir, max_tokens=max_tokens)

            exec_path = os.path.join(spec.workspace_path, "exec")
            tmp_path = os.path.join(spec.workspace_path, "tmp")
            os.makedirs(exec_path, exist_ok=True)

            write_execution_status(spec.output_dir, status="starting_container")
            self._start_container(
                spec.task_id,
                exec_path,
                api_key=api_key,
                base_url=base_url,
                extra_env=spec.task.get("env", ""),
                tmp_path=tmp_path,
                lobster_env=spec.lobster.get("env") if spec.lobster else None,
            )
            write_execution_status(
                spec.output_dir,
                status="container_started",
                harness_version=self._probe_harness_version(spec.task_id),
            )
            if spec.lobster:
                inject_lobster_workspace(spec.task_id, spec.lobster["workspace"])

            write_execution_status(spec.output_dir, status="preparing_workspace")
            self._prepare_workspace(spec.task_id)
            write_execution_status(spec.output_dir, status="preparing_skills")
            setup_skills(
                spec.task_id,
                spec.task.get("skills", ""),
                spec.task.get("skills_path", ""),
                container_skills_root=f"{HERMES_HOME}/skills",
            )
            write_execution_status(spec.output_dir, status="preparing_warmup")
            run_warmup(spec.task_id, spec.task.get("warmup", ""))

            write_execution_status(spec.output_dir, status="preparing_harness_input")
            self._configure_hermes(spec.task_id, api_key, base_url)

            reasoning_config = self._map_thinking(spec.thinking)
            self._write_bench_runner(
                spec.task_id, spec.prompt, spec.model,
                api_key, base_url, reasoning_config, max_tokens,
            )

            write_execution_status(spec.output_dir, status="hermesagent_running")
            agent_proc = self._run_bench_runner_background(
                task_id=spec.task_id,
                log_path=spec.output_dir / "agent.log",
            )

            logger.info("[%s] Waiting for hermes-agent to finish...", spec.task_id)
            try:
                agent_proc.wait(timeout=spec.timeout_seconds)
                elapsed_time = time.perf_counter() - start_time
                logger.info(
                    "[%s] hermes-agent finished, elapsed: %.2f seconds",
                    spec.task_id,
                    elapsed_time,
                )
            except subprocess.TimeoutExpired:
                logger.info("[%s] hermes-agent timed out...", spec.task_id)
                elapsed_time = float(spec.timeout_seconds)
                agent_proc.kill()
                agent_proc.wait()
                error = "HermesAgent run timed out"
                write_execution_status(
                    spec.output_dir,
                    status="timed_out",
                    timed_out=True,
                    elapsed_time=round(elapsed_time, 2),
                    exit_code=agent_proc.returncode,
                    error=error,
                    termination_reason="timeout",
                )
                return AgentExecution(
                    elapsed_time=elapsed_time,
                    error=error,
                    gateway_proc=None,
                    agent_proc=agent_proc,
                )

            logger.info("[%s] hermes-agent exit code: %s", spec.task_id, agent_proc.returncode)
            if agent_proc.returncode != 0:
                error = self._process_error(
                    agent_proc.returncode,
                    spec.output_dir / "agent.log",
                )
                write_execution_status(
                    spec.output_dir,
                    status="error",
                    timed_out=False,
                    elapsed_time=round(elapsed_time, 2),
                    exit_code=agent_proc.returncode,
                    error=error,
                    termination_reason="process_exit",
                )
                return AgentExecution(
                    elapsed_time=elapsed_time,
                    error=error,
                    gateway_proc=None,
                    agent_proc=agent_proc,
                )

            write_execution_status(spec.output_dir, status="collecting_artifacts")
            bench_result = self._read_bench_result(spec.task_id)
            completed = bool(bench_result.get("completed"))
            partial = bool(bench_result.get("partial"))
            completion_error = bench_result.get("error")
            if completion_error is not None:
                completion_error = str(completion_error)
            # Hermes excludes some continuation/retry calls from this loop count.
            # Report request_count remains derived from response logs in collect_usage().
            api_calls = int(bench_result.get("api_calls") or 0)
            termination_reason = self._termination_reason(
                completed=completed,
                partial=partial,
                completion_error=completion_error,
            )
            write_execution_status(
                spec.output_dir,
                status="finished",
                timed_out=False,
                elapsed_time=round(elapsed_time, 2),
                exit_code=0,
                error=None,
                task_completed=completed,
                partial=partial,
                termination_reason=termination_reason,
                completion_error=completion_error,
                api_calls=api_calls,
                finished_at=_now_iso(),
            )

            return AgentExecution(
                elapsed_time=elapsed_time,
                error=None,
                gateway_proc=None,
                agent_proc=agent_proc,
            )
        except Exception as exc:
            elapsed_time = time.perf_counter() - start_time
            logger.error("[%s] hermes-agent execution error: %s", spec.task_id, exc)
            write_execution_status(
                spec.output_dir,
                status="error",
                timed_out=False,
                elapsed_time=round(elapsed_time, 2),
                exit_code=getattr(agent_proc, "returncode", None),
                error=str(exc),
            )
            return AgentExecution(
                elapsed_time=elapsed_time,
                error=str(exc),
                gateway_proc=None,
                agent_proc=agent_proc,
            )
        finally:
            self._close_runner_streams(agent_proc)
            self._cleanup_bench_config(spec.task_id)

    def collect_usage(self, task_id: str, output_dir: Path, elapsed_time: float) -> dict[str, Any]:
        transcript_host = output_dir / "chat.jsonl"
        output_dir.mkdir(parents=True, exist_ok=True)
        r_cp = subprocess.run(
            ["docker", "cp", f"{task_id}:{self.transcript_container_path}", str(transcript_host)],
            capture_output=True,
            text=True,
        )
        if r_cp.returncode == 0 and transcript_host.exists():
            usage = extract_usage_from_jsonl(transcript_host)
        else:
            logger.warning("[%s] Transcript copy failed: %s", task_id, r_cp.stderr.strip())
            usage = self._extract_usage_from_session_logs(task_id)

        if self._usage_has_no_tokens(usage):
            log_usage = self._extract_usage_from_agent_log(output_dir / "agent.log")
            if not self._usage_has_no_tokens(log_usage):
                usage = log_usage

        self._copy_session_log(task_id, output_dir)

        usage.setdefault(
            "cost_status",
            "reported" if float(usage.get("cost_usd") or 0.0) > 0 else "unavailable",
        )
        usage["elapsed_time"] = round(elapsed_time, 2)
        self._write_harness_metadata(task_id, output_dir)
        return usage

    def _write_harness_metadata(self, task_id: str, output_dir: Path) -> None:
        status = self._load_execution_status(output_dir)
        version = str(status.get("harness_version") or "")
        if not version:
            version = self._probe_harness_version(task_id)
        write_execution_status(
            output_dir,
            harness="hermesagent",
            harness_version=version,
            image=self.image,
        )

    @staticmethod
    def _load_execution_status(output_dir: Path) -> dict[str, Any]:
        status_path = output_dir / "execution_status.json"
        if not status_path.exists():
            return {}
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _probe_harness_version(task_id: str) -> str:
        """Read HermesAgent version from the container (non-fatal).

        No standalone CLI; try installed package metadata, then git rev of the
        source checkout at /opt/hermes. Returns "" if none succeed.
        """
        # Try installed package metadata (a few candidate names); if none
        # found, print nothing so the shell falls back to the git short rev.
        py = (
            "import importlib.metadata as m\n"
            "v=''\n"
            "for n in ('hermes-agent','hermes_agent','hermes'):\n"
            "    try:\n"
            "        v=m.version(n); break\n"
            "    except Exception:\n"
            "        pass\n"
            "print(v)\n"
        )
        probe = (
            f"v=$({HERMES_VENV_PYTHON} -c {shlex.quote(py)} 2>/dev/null); "
            f'if [ -n "$v" ]; then echo "$v"; '
            f"else git -C {HERMES_INSTALL_DIR} rev-parse --short HEAD 2>/dev/null; fi"
        )
        try:
            r = subprocess.run(
                ["docker", "exec", task_id, "/bin/bash", "-lc", probe],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("[%s] hermes version probe failed: %s", task_id, exc)
            return ""
        out = (r.stdout or "").strip()
        return out.splitlines()[0].strip() if out else ""

    # ------------------------------------------------------------------
    # Provider / thinking helpers
    # ------------------------------------------------------------------

    def _resolve_runtime_provider(self, model: str, models_config: dict | None) -> tuple[str, str]:
        api_key = self.openrouter_api_key
        base_url = self.openrouter_base_url
        config_key, config_base_url = self._resolve_provider_config(model, models_config)
        if config_key:
            api_key = config_key
        if config_base_url:
            base_url = config_base_url
        return api_key, base_url

    @staticmethod
    def _resolve_provider_config(model: str, models_config: dict | None) -> tuple[str, str]:
        """Extract api_key and base_url from *models_config* for *model*.

        Returns (api_key, base_url) — either or both may be empty strings
        if the config does not contain a matching provider.
        """
        if not models_config:
            return "", ""
        providers = models_config.get("providers", {})
        # Try exact model-id match first.
        for _prov_name, prov in providers.items():
            if not isinstance(prov, dict):
                continue
            for m in prov.get("models", []):
                if isinstance(m, dict) and m.get("id") == model:
                    return prov.get("apiKey", ""), prov.get("baseUrl", "")
        # No exact match — fall back to the first (usually only) provider.
        if providers:
            first = next(iter(providers.values()))
            if isinstance(first, dict):
                return first.get("apiKey", ""), first.get("baseUrl", "")
        return "", ""

    @staticmethod
    def _map_thinking(thinking: str | None) -> dict | None:
        """Map the benchmark ``thinking`` value to a Hermes *reasoning_config* dict."""
        if thinking is None:
            return None
        t = thinking.strip().lower()
        if t in ("off", "none", "disabled", "false"):
            return {"enabled": False}
        if t in ("on", "enabled", "medium", "true"):
            return {"enabled": True, "effort": "medium"}
        if t == "high":
            return {"enabled": True, "effort": "high"}
        if t in ("low", "minimal"):
            return {"enabled": True, "effort": "low"}
        return {"enabled": True, "effort": t}

    # ------------------------------------------------------------------
    # Container setup helpers
    # ------------------------------------------------------------------

    def _start_container(
        self,
        task_id: str,
        workspace_path: str,
        api_key: str,
        base_url: str,
        extra_env: str = "",
        tmp_path: str = "",
        lobster_env: list[str] | None = None,
    ) -> None:
        proxy_http = os.environ.get("HTTP_PROXY_INNER", "")
        proxy_https = os.environ.get("HTTPS_PROXY_INNER", "")
        env_args = [
            "-e", f"http_proxy={proxy_http}",
            "-e", f"https_proxy={proxy_https}",
            "-e", f"HTTP_PROXY={proxy_http}",
            "-e", f"HTTPS_PROXY={proxy_https}",
            "-e", f"BRAVE_API_KEY={self.brave_api_key}",
            "-e", f"OPENROUTER_API_KEY={api_key}",
            "-e", f"OPENROUTER_BASE_URL={base_url}",
            "-e", f"no_proxy={'' if not proxy_http else os.environ.get('NO_PROXY_INNER', '')}",
        ]
        for line in extra_env.splitlines():
            key = line.strip()
            if not key or key.startswith("#"):
                continue
            value = os.environ.get(key, "")
            env_args += ["-e", f"{key}={value}"]

        for key in (lobster_env or []):
            value = os.environ.get(key, "")
            if not value:
                continue
            env_args += ["-e", f"{key}={value}"]

        cmd = [
            "docker", "run", "-d",
            "--name", task_id,
            *container_resource_args(),
            *env_args,
            "-v", f"{workspace_path}:/app:ro",
            self.image,
            "/bin/bash", "-c", "tail -f /dev/null",
        ]
        logger.info("[%s] Starting hermes-agent container (image=%s)", task_id, self.image)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"hermes-agent container startup failed:\n{r.stderr}")
        logger.info("[%s] Container ID: %s", task_id, r.stdout.strip()[:12])

        if tmp_path and os.path.exists(tmp_path):
            subprocess.run(
                ["docker", "exec", task_id, "mkdir", "-p", "/tmp_workspace/tmp"],
                capture_output=True,
            )
            cp_r = subprocess.run(
                ["docker", "cp", f"{tmp_path}/.", f"{task_id}:/tmp_workspace/tmp/"],
                capture_output=True, text=True,
            )
            if cp_r.returncode != 0:
                logger.error("[%s] Temp file copy failed: %s", task_id, cp_r.stderr)

    def _prepare_workspace(self, task_id: str) -> None:
        r = subprocess.run(
            [
                "docker", "exec", task_id, "/bin/bash", "-c",
                f"mkdir -p {TMP_WORKSPACE} && cp -r /app/. {TMP_WORKSPACE} && chmod -R u+w {TMP_WORKSPACE}",
            ],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"hermes-agent workspace copy failed:\n{r.stderr}")

    def _configure_hermes(self, task_id: str, api_key: str = "", base_url: str = "") -> None:
        """Configure hermes-agent inside the container with one consistent provider config."""
        hermes_yaml = (
            "tools:\n"
            "  profile: coding\n"
            "  web:\n"
            "    search:\n"
            "      enabled: true\n"
            "      provider: brave\n"
        )
        hermes_env = (
            f"OPENROUTER_API_KEY={api_key}\n"
            f"OPENROUTER_BASE_URL={base_url}\n"
            f"BRAVE_API_KEY={self.brave_api_key}\n"
        )

        with tempfile.TemporaryDirectory(prefix="hermes_config_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            yaml_host = tmp_root / "hermes.yaml"
            env_host = tmp_root / ".env"
            yaml_host.write_text(hermes_yaml, encoding="utf-8")
            env_host.write_text(hermes_env, encoding="utf-8")

            r_mkdir = subprocess.run(
                [
                    "docker",
                    "exec",
                    task_id,
                    "/bin/bash",
                    "-c",
                    f"mkdir -p {HERMES_HOME} && mkdir -p $(dirname {OPENCLAW_COMPAT_TRANSCRIPT_PATH})",
                ],
                capture_output=True,
                text=True,
            )
            if r_mkdir.returncode != 0:
                raise RuntimeError(f"hermes-agent config mkdir failed:\n{r_mkdir.stderr}")

            for src, dst in (
                (yaml_host, f"{HERMES_HOME}/hermes.yaml"),
                (env_host, f"{HERMES_HOME}/.env"),
            ):
                copied = subprocess.run(
                    ["docker", "cp", str(src), f"{task_id}:{dst}"],
                    capture_output=True,
                    text=True,
                )
                if copied.returncode != 0:
                    raise RuntimeError(f"hermes-agent config copy failed ({dst}):\n{copied.stderr}")

            r_link = subprocess.run(
                ["docker", "exec", task_id, "ln", "-sfn", TMP_WORKSPACE, f"{HERMES_HOME}/workspace"],
                capture_output=True,
                text=True,
            )
            if r_link.returncode != 0:
                raise RuntimeError(f"hermes-agent workspace link failed:\n{r_link.stderr}")

        logger.info("[%s] hermes-agent configured", task_id)

    def _write_bench_runner(
        self,
        task_id: str,
        prompt: str,
        model: str,
        api_key: str,
        base_url: str,
        reasoning_config: dict | None,
        max_tokens: int | None,
    ) -> None:
        """Write the bench runner config into the container."""
        config_payload = {
            "config": {
                "model": model,
                "api_key": api_key,
                "base_url": base_url,
                "max_iterations": 90,
                "max_tokens": max_tokens,
                "reasoning_config": reasoning_config,
            },
            "prompt": prompt,
        }

        config_tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False, encoding="utf-8",
            ) as f:
                json.dump(config_payload, f, ensure_ascii=False)
                config_tmp = f.name

            r = subprocess.run(
                ["docker", "cp", config_tmp, f"{task_id}:{BENCH_CONFIG_CONTAINER_PATH}"],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                raise RuntimeError(f"Failed to copy {BENCH_CONFIG_CONTAINER_PATH} into container:\n{r.stderr}")
        finally:
            for p in (config_tmp,):
                if p:
                    Path(p).unlink(missing_ok=True)

    def _run_bench_runner_background(self, task_id: str, log_path: Path) -> subprocess.Popen[str]:
        if not BENCH_RUNNER_HOST_PATH.exists():
            raise RuntimeError(f"Hermes bench runner script not found: {BENCH_RUNNER_HOST_PATH}")

        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("w", encoding="utf-8")
        script_file = BENCH_RUNNER_HOST_PATH.open("r", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                [
                    "docker",
                    "exec",
                    "-i",
                    task_id,
                    "/bin/bash",
                    "-c",
                    f"cd {HERMES_INSTALL_DIR} && {HERMES_VENV_PYTHON} -",
                ],
                stdin=script_file,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
        except Exception:
            script_file.close()
            log_file.close()
            raise
        proc._log_file = log_file  # type: ignore[attr-defined]
        proc._script_file = script_file  # type: ignore[attr-defined]
        logger.info("[%s] Started Hermes bench runner PID=%s -> %s", task_id, proc.pid, log_path)
        return proc

    @staticmethod
    def _close_runner_streams(proc: subprocess.Popen[str] | None) -> None:
        if proc is None:
            return
        for attribute in ("_script_file", "_log_file"):
            stream = getattr(proc, attribute, None)
            if stream is None:
                continue
            try:
                stream.close()
            except Exception:
                pass

    @staticmethod
    def _cleanup_bench_config(task_id: str) -> None:
        subprocess.run(
            [
                "docker", "exec", task_id, "rm", "-f",
                BENCH_CONFIG_CONTAINER_PATH, BENCH_RESULT_CONTAINER_PATH,
            ],
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _read_bench_result(task_id: str) -> dict[str, Any]:
        result = subprocess.run(
            ["docker", "exec", task_id, "cat", BENCH_RESULT_CONTAINER_PATH],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or "").strip()
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"HermesAgent bench result not found{suffix}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"HermesAgent bench result is invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("HermesAgent bench result must be a JSON object")
        return payload

    @staticmethod
    def _termination_reason(
        *,
        completed: bool,
        partial: bool,
        completion_error: str | None,
    ) -> str:
        if completed:
            return "completed"
        error_text = (completion_error or "").lower()
        if any(marker in error_text for marker in ("truncated", "output length", "max_tokens")):
            return "output_length_limit"
        if partial:
            return "partial"
        return "incomplete"

    @staticmethod
    def _process_error(returncode: int, log_path: Path, max_chars: int = 4000) -> str:
        detail = ""
        try:
            with log_path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - max_chars), os.SEEK_SET)
                detail = stream.read().decode("utf-8", errors="replace").strip()
        except OSError:
            pass
        suffix = f":\n{detail}" if detail else ""
        return f"HermesAgent run failed (rc={returncode}){suffix}"

    # ------------------------------------------------------------------
    # Transcript conversion (all sessions merged)
    # ------------------------------------------------------------------

    def _write_compat_transcript(self, task_id: str) -> None:
        """Convert Hermes session logs to OpenClaw-compatible JSONL for grading."""
        if not COMPAT_TRANSCRIPT_HOST_PATH.exists():
            logger.warning(
                "[%s] Compat transcript script not found: %s",
                task_id,
                COMPAT_TRANSCRIPT_HOST_PATH,
            )
            return

        with COMPAT_TRANSCRIPT_HOST_PATH.open("r", encoding="utf-8") as script_file:
            r = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    task_id,
                    HERMES_VENV_PYTHON,
                    "-",
                ],
                stdin=script_file,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        if r.returncode != 0:
            logger.warning("[%s] Compat transcript write failed: %s", task_id, r.stderr)
        else:
            logger.info("[%s] Compat transcript written to %s", task_id, OPENCLAW_COMPAT_TRANSCRIPT_PATH)

    # ------------------------------------------------------------------
    # Usage extraction (all sessions merged)
    # ------------------------------------------------------------------

    def _extract_usage_from_session_logs(self, task_id: str) -> dict[str, Any]:
        """Fallback: extract usage from copied Hermes session JSON files."""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
        }

        with tempfile.TemporaryDirectory(prefix="hermes_usage_") as tmp_dir:
            sessions_host = Path(tmp_dir) / "sessions"
            sessions_host.mkdir(parents=True, exist_ok=True)
            copied = subprocess.run(
                ["docker", "cp", f"{task_id}:{HERMES_HOME}/sessions/.", str(sessions_host)],
                capture_output=True,
                text=True,
            )
            if copied.returncode != 0:
                return usage

            total_requests = 0
            for session_file in sorted(sessions_host.glob("session_*.json"), key=lambda p: p.stat().st_mtime):
                try:
                    payload = json.loads(session_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                messages = payload.get("messages", [])
                if not isinstance(messages, list):
                    continue
                total_requests += sum(
                    1 for item in messages if isinstance(item, dict) and item.get("role") == "assistant"
                )
            usage["request_count"] = total_requests

        return usage

    def _usage_has_no_tokens(self, usage: dict[str, Any]) -> bool:
        return (
            usage.get("input_tokens", 0) == 0
            and usage.get("output_tokens", 0) == 0
            and usage.get("total_tokens", 0) == 0
        )

    def _extract_usage_from_agent_log(self, log_path: Path) -> dict[str, Any]:
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
        }
        if not log_path.exists():
            return usage

        for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "API Response received" not in line or (
                "CompletionUsage(" not in line and "ResponseUsage(" not in line
            ):
                continue
            usage["request_count"] += 1
            usage["input_tokens"] += (
                self._extract_int_from_log(line, "prompt_tokens")
                or self._extract_int_from_log(line, "input_tokens")
            )
            usage["output_tokens"] += (
                self._extract_int_from_log(line, "completion_tokens")
                or self._extract_int_from_log(line, "output_tokens")
            )
            usage["total_tokens"] += self._extract_int_from_log(line, "total_tokens")
            usage["cache_read_tokens"] += self._extract_int_from_log(line, "cached_tokens")
            usage["cache_write_tokens"] += self._extract_int_from_log(line, "cache_write_tokens")
            usage["cost_usd"] += self._extract_float_from_log(line, "cost")

        usage["cost_usd"] = round(usage["cost_usd"], 6)
        return usage

    def _extract_int_from_log(self, line: str, field: str) -> int:
        match = re.search(rf"\b{re.escape(field)}=(\d+)", line)
        return int(match.group(1)) if match else 0

    def _extract_float_from_log(self, line: str, field: str) -> float:
        match = re.search(rf"\b{re.escape(field)}=([0-9.eE+-]+)", line)
        return float(match.group(1)) if match else 0.0

    def _copy_session_log(self, task_id: str, output_dir: Path) -> None:
        """Copy *all* hermes session logs from the container to the output directory."""
        hermes_log_dest = output_dir / "hermes_session"
        hermes_log_dest.mkdir(parents=True, exist_ok=True)

        r = subprocess.run(
            ["docker", "cp", f"{task_id}:{HERMES_HOME}/sessions/.", str(hermes_log_dest)],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            logger.info("[%s] Hermes session logs copied to %s", task_id, hermes_log_dest)
        else:
            logger.warning("[%s] Hermes session log copy failed: %s", task_id, r.stderr.strip())
