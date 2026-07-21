from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agents.base import AgentExecution, AgentTaskSpec, BaseAgent
from src.agents.opencode.backend import (
    OPENCODE_PROMPT_PATH,
    load_skill_documents,
    prepare_opencode_prompt,
)
from src.utils.docker_utils import container_resource_args, run_warmup, setup_skills, snapshot_workspace_state
from src.utils.endpoint_utils import normalize_openrouter_base_url_for_openclaw

logger = logging.getLogger(__name__)

# OpenCode config dir (XDG_CONFIG_HOME/opencode); config injected via OPENCODE_CONFIG_CONTENT env.
OPENCODE_CONFIG_HOME = "/root/.config/opencode"
# OpenCode native data dir (XDG_DATA_HOME/opencode): opencode.db + storage/ + log/.
# Pinned via XDG_DATA_HOME=/root/.local/share so the path is deterministic.
OPENCODE_DATA_DIR = "/root/.local/share/opencode"
OPENCODE_SKILLS_DIR = f"{OPENCODE_CONFIG_HOME}/skills"
# OpenClaw-shape transcript that safety-alignment graders hard-code.
OPENCLAW_TRANSCRIPT_DIR = "/root/.openclaw/agents/main/sessions"
OPENCLAW_TRANSCRIPT_PATH = f"{OPENCLAW_TRANSCRIPT_DIR}/chat.jsonl"
# Provider id under which the OpenRouter-compatible endpoint is registered in config.
OPENCODE_PROVIDER_ID = "openrouter"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_agent_log_event(output_dir: Path, event: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    enriched = {"timestamp": _now_iso(), **event}
    with (output_dir / "runner.log").open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(enriched, ensure_ascii=False) + "\n")


def write_execution_status(output_dir: Path, **updates: Any) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "execution_status.json"
    status: dict[str, Any] = {}
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
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
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "agent.log").touch(exist_ok=True)
    write_execution_status(
        output_dir,
        task_id=task_id,
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


class OpenCodeAgent(BaseAgent):
    def __init__(
        self,
        image: str | None = None,
        openrouter_api_key: str = "",
        openrouter_base_url: str = "",
    ) -> None:
        resolved_image = (
            image
            or os.environ.get("DOCKER_IMAGE_OPENCODE")
            or "wildclawbench-opencode-ubuntu:v0.0"
        )
        self.image: str = resolved_image
        self.openrouter_api_key = (
            openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
        ).strip()
        self.openrouter_base_url = normalize_openrouter_base_url_for_openclaw(
            openrouter_base_url or os.environ.get("OPENROUTER_BASE_URL", "")
        )

    @property
    def expects_gateway(self) -> bool:
        return False

    @property
    def transcript_container_path(self) -> str:
        # Graders read the OpenClaw-shape transcript; prepare_grading_transcript
        # writes it there from the raw NDJSON event stream.
        return OPENCLAW_TRANSCRIPT_PATH

    def run_task(self, spec: AgentTaskSpec) -> AgentExecution:
        elapsed_time = float(spec.timeout_seconds)
        start_time = time.perf_counter()
        task_id = spec.task_id
        initialize_host_run_artifacts(
            output_dir=spec.output_dir,
            task_id=task_id,
            model=spec.model,
            timeout_seconds=spec.timeout_seconds,
        )

        try:
            try:
                write_execution_status(spec.output_dir, status="starting_container")
                self._start_container(task_id, spec.workspace_path, spec.task, spec.lobster)
                write_execution_status(spec.output_dir, status="container_started")
                write_execution_status(spec.output_dir, status="preparing_workspace")
                self._prepare_workspace(task_id, spec.workspace_path)
                skills_text = spec.task.get("skills", "") if spec.task else ""
                skills_path = spec.task.get("skills_path", "") if spec.task else ""
                setup_skills(
                    task_id,
                    skills_text,
                    skills_path,
                    container_skills_root=OPENCODE_SKILLS_DIR,
                )
                skill_docs = load_skill_documents(
                    skills_text,
                    skills_path,
                    container_skill_root=OPENCODE_SKILLS_DIR,
                )
                run_warmup(
                    task_id,
                    spec.task.get("warmup", "") if spec.task else "",
                    detach_background=True,
                )
                image_helper_enabled = self._should_enable_image_helper(
                    spec.prompt, spec.workspace_path
                )
                if image_helper_enabled:
                    self._install_image_helper(task_id, spec.model)
                snapshot_workspace_state(task_id)
                write_execution_status(spec.output_dir, status="opencode_running")
                self._run_prompt(
                    task_id=task_id,
                    model=spec.model,
                    prompt=self._build_task_prompt(
                        spec.prompt,
                        image_helper_enabled=image_helper_enabled,
                        skill_docs=skill_docs,
                    ),
                    timeout_seconds=spec.timeout_seconds,
                    output_dir=spec.output_dir,
                )
                elapsed_time = time.perf_counter() - start_time
                write_execution_status(
                    spec.output_dir,
                    status="finished",
                    timed_out=False,
                    elapsed_time=round(elapsed_time, 2),
                    exit_code=0,
                )
                return AgentExecution(
                    elapsed_time=elapsed_time, error=None, gateway_proc=None, agent_proc=None
                )
            except subprocess.TimeoutExpired:
                logger.info("[%s] OpenCode timed out...", task_id)
                elapsed_time = float(spec.timeout_seconds)
                append_agent_log_event(
                    spec.output_dir,
                    {
                        "type": "runner.timeout",
                        "message": f"OpenCode timed out after {spec.timeout_seconds} seconds.",
                        "timeout_seconds": spec.timeout_seconds,
                        "elapsed_time": elapsed_time,
                    },
                )
                write_execution_status(
                    spec.output_dir,
                    status="timed_out",
                    timed_out=True,
                    elapsed_time=round(elapsed_time, 2),
                    error="OpenCode run timed out",
                )
                return AgentExecution(
                    elapsed_time=elapsed_time,
                    error="OpenCode run timed out",
                    gateway_proc=None,
                    agent_proc=None,
                )
            except Exception as exc:
                elapsed_time = time.perf_counter() - start_time
                logger.error("[%s] OpenCode execution error: %s", task_id, exc)
                append_agent_log_event(
                    spec.output_dir,
                    {
                        "type": "runner.error",
                        "stage": "opencode_execution",
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
        finally:
            try:
                self._install_openclaw_transcript_shim(task_id, spec.output_dir)
            except Exception as exc:
                logger.warning("[%s] OpenClaw transcript shim failed: %s", task_id, exc)

    def prepare_grading_transcript(self, task_id: str) -> str:
        # The OpenClaw-shape transcript is written into the container during the
        # run_task finally block (shim). Graders read OPENCLAW_TRANSCRIPT_PATH.
        return OPENCLAW_TRANSCRIPT_PATH

    def collect_usage(
        self, task_id: str, output_dir: Path, elapsed_time: float
    ) -> dict[str, Any]:
        usage = self._empty_totals()
        usage["elapsed_time"] = round(elapsed_time, 2)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1) Preserve OpenCode's native trajectory: copy the whole data dir
        #    (opencode.db SQLite + storage/ + log/) out to output/opencode_data/.
        native_dest = output_dir / "opencode_data"
        native_dest.mkdir(parents=True, exist_ok=True)
        self._copy_dir_from_container(task_id, f"{OPENCODE_DATA_DIR}/.", native_dest)

        # 2) Parse token usage from the raw NDJSON event stream (agent.log).
        parsed = self._extract_usage_from_agent_log(output_dir / "agent.log")
        if parsed["cost_usd"] == 0.0:
            parsed["cost_usd"] = round(self._estimate_cost(parsed), 6)
        usage.update(parsed)
        usage["elapsed_time"] = round(elapsed_time, 2)
        return usage

    def _start_container(
        self,
        task_id: str,
        workspace_path: str,
        task: dict[str, Any],
        lobster: dict[str, Any] | None,
    ) -> None:
        workspace = Path(workspace_path).expanduser()
        exec_path = workspace / "exec"
        if not exec_path.is_dir():
            logger.warning(
                "[%s] Workspace exec dir missing, auto-creating empty dir "
                "(assuming task has no input files; verify dataset if unexpected): %s",
                task_id,
                exec_path,
            )
            exec_path.mkdir(parents=True, exist_ok=True)

        if not self.openrouter_api_key:
            raise RuntimeError(
                "OpenCode external models require OPENROUTER_API_KEY."
            )

        proxy_http = os.environ.get("HTTP_PROXY_INNER", "").strip()
        proxy_https = os.environ.get("HTTPS_PROXY_INNER", "").strip()
        no_proxy = "" if not proxy_http else os.environ.get("NO_PROXY_INNER", "").strip()
        env_map: dict[str, str] = {
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "OPENROUTER_BASE_URL": self.openrouter_base_url,
            "OPENROUTER_IMAGE_MODEL": os.environ.get("OPENROUTER_IMAGE_MODEL", "").strip(),
            "WILDCLAW_IMAGE_MODEL": os.environ.get("WILDCLAW_IMAGE_MODEL", "").strip(),
            "BRAVE_API_KEY": os.environ.get("BRAVE_API_KEY", ""),
            # Pin OpenCode's data dir so opencode.db lands at a deterministic path.
            "XDG_DATA_HOME": "/root/.local/share",
            "XDG_CONFIG_HOME": "/root/.config",
            "http_proxy": proxy_http,
            "https_proxy": proxy_https,
            "HTTP_PROXY": proxy_http,
            "HTTPS_PROXY": proxy_https,
            "no_proxy": no_proxy,
        }

        env_args: list[str] = []
        for key, value in env_map.items():
            if value:
                env_args += ["-e", f"{key}={value}"]

        extra_env = task.get("env", "") if task else ""
        for line in extra_env.splitlines():
            key = line.strip()
            if not key or key.startswith("#"):
                continue
            value = os.environ.get(key, "").strip()
            env_args += ["-e", f"{key}={value}"]
            masked = (value[:4] + "***") if value else "(empty)"
            logger.info("[%s] Injecting env var: %s=%s", task_id, key, masked)

        for key in (lobster or {}).get("env", []) or []:
            value = os.environ.get(key, "").strip()
            if not value:
                logger.warning(
                    "[%s] Lobster env key %s not found, skipping", task_id, key
                )
                continue
            env_args += ["-e", f"{key}={value}"]
            logger.info("[%s] Injecting lobster env: %s=%s***", task_id, key, value[:4])

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
        logger.info("[%s] Starting OpenCode container (%s)", task_id, self.image)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"OpenCode container startup failed:\n{r.stderr}")
        logger.info("[%s] Container ID: %s", task_id, r.stdout.strip()[:12])

    def _prepare_workspace(self, task_id: str, workspace_path: str) -> None:
        r = subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-c",
                (
                    "mkdir -p /tmp_workspace "
                    f"&& mkdir -p {OPENCODE_CONFIG_HOME} {OPENCODE_DATA_DIR} "
                    "&& cp -r /workspace/. /tmp_workspace "
                    "&& chmod -R u+w /tmp_workspace"
                ),
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"OpenCode workspace copy failed:\n{r.stderr}")

        tmp_path = Path(workspace_path) / "tmp"
        if tmp_path.exists():
            mkdir_tmp = subprocess.run(
                ["docker", "exec", task_id, "mkdir", "-p", "/tmp_workspace/tmp"],
                capture_output=True,
                text=True,
            )
            if mkdir_tmp.returncode != 0:
                raise RuntimeError(f"OpenCode tmp mkdir failed:\n{mkdir_tmp.stderr}")

            copied = subprocess.run(
                ["docker", "cp", f"{tmp_path}/.", f"{task_id}:/tmp_workspace/tmp/"],
                capture_output=True,
                text=True,
            )
            if copied.returncode != 0:
                raise RuntimeError(f"OpenCode tmp copy failed:\n{copied.stderr}")

    @staticmethod
    def _bare_model(model: str) -> str:
        """Strip a leading ``openrouter/`` scheme; keep provider/model remainder.

        ``openrouter/anthropic/claude-sonnet-4.6`` -> ``anthropic/claude-sonnet-4.6``
        ``anthropic/claude-sonnet-4.6``            -> ``anthropic/claude-sonnet-4.6``
        """
        if model.startswith("openrouter/"):
            return model[len("openrouter/") :]
        return model

    def _model_arg(self, model: str) -> str:
        """OpenCode --model expects ``<providerID>/<modelID>``.

        We register the endpoint under provider id ``openrouter`` and use the
        bare model (which may itself contain slashes) as the model id.
        """
        return f"{OPENCODE_PROVIDER_ID}/{self._bare_model(model)}"

    def _render_opencode_config(self, model: str, redact_secrets: bool) -> str:
        """Inline JSON config for OPENCODE_CONFIG_CONTENT.

        - permission: allow everything (headless, non-interactive autonomy)
        - provider.openrouter: an @ai-sdk/openai-compatible provider pointed at
          the benchmark's OpenRouter-compatible endpoint.
        """
        bare_model = self._bare_model(model)
        api_key = "***" if redact_secrets else self.openrouter_api_key
        config = {
            "$schema": "https://opencode.ai/config.json",
            "permission": {
                "bash": "allow",
                "edit": "allow",
                "webfetch": "allow",
                "write": "allow",
                "read": "allow",
            },
            "provider": {
                OPENCODE_PROVIDER_ID: {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "OpenRouter",
                    "options": {
                        "baseURL": self.openrouter_base_url,
                        "apiKey": api_key,
                    },
                    "models": {
                        bare_model: {"name": bare_model},
                    },
                }
            },
        }
        return json.dumps(config, ensure_ascii=False)

    def _run_prompt(
        self,
        task_id: str,
        model: str,
        prompt: str,
        timeout_seconds: int,
        output_dir: Path,
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Mirror a redacted config host-side for debugging.
        (output_dir / "config.json").write_text(
            self._render_opencode_config(model, redact_secrets=True),
            encoding="utf-8",
        )
        config_content = self._render_opencode_config(model, redact_secrets=False)

        prompt_path = prepare_opencode_prompt(task_id, prompt, OPENCODE_PROMPT_PATH)
        log_path = output_dir / "agent.log"
        r = self._run_opencode_exec(
            task_id, model, prompt_path, config_content, timeout_seconds, log_path
        )
        if r.returncode == 0:
            return
        raise RuntimeError(
            f"OpenCode run failed (rc={r.returncode}):\n{r.stderr or r.stdout}"
        )

    def _build_exec_command(self, model: str, prompt_path: str, config_content: str) -> str:
        model_arg = self._model_arg(model)
        # OPENCODE_CONFIG_CONTENT carries the inline JSON config (provider + perms).
        # `opencode run` reads the message from argv; we pass the prompt file body.
        return (
            f"export OPENCODE_CONFIG_CONTENT={shlex.quote(config_content)} && "
            "cd /tmp_workspace && "
            f"opencode run \"$(cat {shlex.quote(prompt_path)})\" "
            f"--model {shlex.quote(model_arg)} "
            "--format json --yolo --print-logs"
        )

    def _run_opencode_exec(
        self,
        task_id: str,
        model: str,
        prompt_path: str,
        config_content: str,
        timeout_seconds: int,
        log_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        cmd = self._build_exec_command(model, prompt_path, config_content)
        full_cmd = ["docker", "exec", task_id, "/bin/bash", "-c", cmd]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.Popen(
                full_cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                returncode = proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                log.write("\n" + json.dumps({
                    "timestamp": _now_iso(),
                    "type": "runner.timeout",
                    "message": f"OpenCode timed out after {timeout_seconds} seconds and was killed.",
                    "timeout_seconds": timeout_seconds,
                    "pid": proc.pid,
                }, ensure_ascii=False) + "\n")
                log.flush()
                try:
                    os.fsync(log.fileno())
                except OSError:
                    pass
                self._terminate_opencode_processes(task_id)
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    log.write("[OpenCode runner] docker exec did not exit after kill\n")
                    log.flush()
                raise

        return subprocess.CompletedProcess(
            full_cmd,
            returncode,
            stdout=self._read_text_tail(log_path),
            stderr="",
        )

    @staticmethod
    def _terminate_opencode_processes(task_id: str) -> None:
        subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-lc",
                (
                    "pkill -TERM -f 'opencode' 2>/dev/null || true; "
                    "sleep 2; "
                    "pkill -KILL -f 'opencode' 2>/dev/null || true"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )

    @staticmethod
    def _read_text_tail(path: Path, max_chars: int = 20000) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    @staticmethod
    def _build_task_prompt(
        prompt: str,
        image_helper_enabled: bool,
        skill_docs: list[dict[str, str]] | None = None,
    ) -> str:
        sections: list[str] = []
        if image_helper_enabled:
            sections.append(
                "## Image Helper\n\n"
                "When image understanding is needed, use the recoverable helper "
                "for image analysis:\n\n"
                '```bash\npython3 /tmp_workspace/.wildclaw_image.py "<image_path>" "<question>"\n```\n\n'
                "The helper returns JSON and exits 0 even if the image model call "
                "fails. It defaults to the task model. Call it at most twice per task. "
                "If the helper returns ok=false because the model or endpoint cannot "
                "handle the request, you may make a direct OpenRouter /chat/completions "
                "request using OPENROUTER_API_KEY, OPENROUTER_BASE_URL, and an "
                "image-capable model. Otherwise, continue with other available methods "
                "and still write the required output files. After the required files are "
                "written, finish instead of doing extra image verification."
            )
        if skill_docs:
            skill_sections = [
                "## Local Skill References\n\n"
                "Use these task-specific instructions when they apply. They describe "
                "local files, mock APIs, and required workflows available in this container."
            ]
            for skill in skill_docs:
                skill_sections.append(
                    f"### Skill: {skill['name']}\n\n{skill['content'].strip()}"
                )
            sections.append("\n\n".join(skill_sections))
        sections.append("## Task\n\n" + prompt.strip())
        return "\n\n".join(sections).strip() + "\n"

    @staticmethod
    def _should_enable_image_helper(prompt: str, workspace_path: str) -> bool:
        lowered = prompt.lower()
        image_markers = (
            ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff",
            "image", "photo", "picture", "screenshot", "diagram",
        )
        if any(marker in lowered for marker in image_markers):
            return True
        exec_path = Path(workspace_path) / "exec"
        image_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
        try:
            return any(
                path.is_file() and path.suffix.lower() in image_suffixes
                for path in exec_path.rglob("*")
            )
        except OSError:
            return False

    def _install_image_helper(self, task_id: str, model: str) -> None:
        """Install a recoverable OpenRouter chat-completions image helper.

        The helper uses the benchmark's OpenRouter chat-completions path and
        reports failures as JSON so the agent can continue with other methods.
        """
        bare_model = self._bare_model(model)
        helper = self._render_image_helper(default_model=bare_model)
        helper_tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(helper)
                helper_tmp = f.name
            copied = subprocess.run(
                ["docker", "cp", helper_tmp, f"{task_id}:/tmp_workspace/.wildclaw_image.py"],
                capture_output=True,
                text=True,
            )
            if copied.returncode != 0:
                raise RuntimeError(f"OpenCode image helper copy failed:\n{copied.stderr}")
            chmod = subprocess.run(
                ["docker", "exec", task_id, "chmod", "+x", "/tmp_workspace/.wildclaw_image.py"],
                capture_output=True,
                text=True,
            )
            if chmod.returncode != 0:
                raise RuntimeError(f"OpenCode image helper chmod failed:\n{chmod.stderr}")
        finally:
            if helper_tmp:
                Path(helper_tmp).unlink(missing_ok=True)

    @staticmethod
    def _render_image_helper(default_model: str) -> str:
        return f'''#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = {json.dumps(default_model)}
CALL_LIMIT = int(os.environ.get("WILDCLAW_IMAGE_HELPER_CALL_LIMIT", "2") or "2")
CALL_STATE_PATH = "/tmp_workspace/.wildclaw_image_calls.json"


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def resolve_image_path(path: str) -> tuple[str | None, str | None]:
    if os.path.exists(path):
        return path, None

    basename = os.path.basename(path)
    if not basename:
        return None, f"image not found: {{path}}"

    matches: list[str] = []
    for root, _dirs, files in os.walk("/tmp_workspace"):
        if basename in files:
            matches.append(os.path.join(root, basename))
            if len(matches) >= 5:
                break

    if len(matches) == 1:
        return matches[0], f"requested path not found; using {{matches[0]}}"
    if matches:
        return matches[0], (
            f"requested path not found; multiple {{basename}} matches, using {{matches[0]}}"
        )
    return None, f"image not found: {{path}}"


def record_helper_call() -> tuple[bool, int]:
    try:
        with open(CALL_STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {{"count": 0}}

    count = int(state.get("count") or 0) + 1
    try:
        with open(CALL_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({{"count": count}}, f)
    except Exception:
        pass
    return count <= CALL_LIMIT, count


def main() -> int:
    if len(sys.argv) < 2:
        return emit({{"ok": False, "error": "usage: .wildclaw_image.py <image_path> [question]"}})

    requested_path = sys.argv[1]
    question = " ".join(sys.argv[2:]).strip() or "Describe the image and extract task-relevant facts."
    image_path, warning = resolve_image_path(requested_path)
    if not image_path:
        return emit({{"ok": False, "error": warning, "requested_path": requested_path}})

    allowed, call_count = record_helper_call()
    if not allowed:
        return emit({{
            "ok": False,
            "error": "image helper call limit reached; use previous helper observations or a direct OpenRouter chat/completions image request if needed",
            "call_count": call_count,
            "call_limit": CALL_LIMIT,
            "image_path": image_path,
            "warning": warning,
        }})

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return emit({{"ok": False, "error": "OPENROUTER_API_KEY is not set"}})

    base_url = (os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    model = (
        os.environ.get("WILDCLAW_IMAGE_MODEL")
        or os.environ.get("OPENROUTER_IMAGE_MODEL")
        or DEFAULT_MODEL
    )
    if model.startswith("openrouter/"):
        model = model.split("/", 1)[1]

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except OSError as exc:
        return emit({{"ok": False, "error": f"failed to read image: {{exc}}", "image_path": image_path}})

    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    data_url = "data:" + mime + ";base64," + base64.b64encode(image_bytes).decode("ascii")
    payload = {{
        "model": model,
        "messages": [
            {{
                "role": "user",
                "content": [
                    {{"type": "text", "text": question}},
                    {{"type": "image_url", "image_url": {{"url": data_url}}}},
                ],
            }}
        ],
        "max_tokens": 800,
        "temperature": 0,
    }}
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={{
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        }},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        content = data.get("choices", [{{}}])[0].get("message", {{}}).get("content", "")
        return emit({{
            "ok": True,
            "model": model,
            "image_path": image_path,
            "warning": warning,
            "content": content,
        }})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return emit({{
            "ok": False,
            "model": model,
            "image_path": image_path,
            "warning": warning,
            "error": f"HTTP {{exc.code}} {{exc.reason}}",
            "body": body[:2000],
        }})
    except Exception as exc:
        return emit({{
            "ok": False,
            "model": model,
            "image_path": image_path,
            "warning": warning,
            "error": str(exc),
        }})


if __name__ == "__main__":
    raise SystemExit(main())
'''

    def _install_openclaw_transcript_shim(
        self, task_id: str, output_dir: Path
    ) -> None:
        """Translate OpenCode NDJSON events -> OpenClaw schema for graders.

        Safety-alignment graders hard-code
        ``/root/.openclaw/agents/main/sessions/chat.jsonl`` with the OpenClaw
        shape ``{"type":"message","message":{"role":...,"content":[...]}}``.
        We emit that shape from agent.log's event stream (text / tool_use /
        reasoning), including mapped tool_use / tool_result blocks.
        """
        agent_log = output_dir / "agent.log"
        if not agent_log.exists() or agent_log.stat().st_size == 0:
            logger.info("[%s] No agent.log yet; skipping openclaw shim", task_id)
            return

        records = self._opencode_events_to_openclaw(agent_log)
        if not records:
            logger.info("[%s] No mappable OpenCode events; shim skipped", task_id)
            return

        dest = output_dir / "chat_openclaw.jsonl"
        dest.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )

        mk = subprocess.run(
            ["docker", "exec", task_id, "mkdir", "-p", OPENCLAW_TRANSCRIPT_DIR],
            capture_output=True,
            text=True,
        )
        if mk.returncode != 0:
            logger.warning(
                "[%s] mkdir for openclaw transcript failed: %s", task_id, mk.stderr.strip()
            )
            return
        cp = subprocess.run(
            ["docker", "cp", str(dest), f"{task_id}:{OPENCLAW_TRANSCRIPT_PATH}"],
            capture_output=True,
            text=True,
        )
        if cp.returncode != 0:
            logger.warning(
                "[%s] Copy openclaw transcript failed: %s", task_id, cp.stderr.strip()
            )
            return
        logger.info(
            "[%s] OpenClaw transcript shim installed (%d events)", task_id, len(records)
        )

    def _opencode_events_to_openclaw(self, agent_log: Path) -> list[dict[str, Any]]:
        """Map the OpenCode NDJSON event stream to OpenClaw message records.

        Event shapes (from `opencode run --format json`, run.ts:679-786):
          {"type":"text","part":{"type":"text","text":...}}
          {"type":"reasoning","part":{"type":"reasoning","text":...}}
          {"type":"tool_use","part":{"type":"tool","callID","tool","state":{
              "status":"completed","input":{...},"output":"..."}}}
          {"type":"error","error":{...}}
        """
        out: list[dict[str, Any]] = []
        for raw in agent_log.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            etype = str(event.get("type") or "").lower()
            part = event.get("part") if isinstance(event.get("part"), dict) else {}

            if etype in ("text", "reasoning"):
                text = str(part.get("text") or "").strip()
                if text:
                    out.append(self._openclaw_message("assistant", [{"type": "text", "text": text}]))
                continue

            if etype == "tool_use" and isinstance(part, dict):
                call_id = str(part.get("callID") or part.get("id") or "")
                name = str(part.get("tool") or "unknown")
                state = part.get("state") if isinstance(part.get("state"), dict) else {}
                tool_input = state.get("input")
                if not isinstance(tool_input, dict):
                    tool_input = {"_value": tool_input} if tool_input is not None else {}
                out.append(
                    self._openclaw_message(
                        "assistant",
                        [{"type": "tool_use", "id": call_id, "name": name, "input": tool_input}],
                    )
                )
                status = str(state.get("status") or "")
                if status == "completed":
                    output_text = state.get("output")
                elif status == "error":
                    output_text = state.get("error") or state.get("output")
                else:
                    output_text = None
                if output_text is not None:
                    if isinstance(output_text, (dict, list)):
                        try:
                            output_text = json.dumps(output_text, ensure_ascii=False)
                        except Exception:
                            output_text = str(output_text)
                    out.append(
                        self._openclaw_message(
                            "user",
                            [{"type": "tool_result", "tool_use_id": call_id, "content": str(output_text)}],
                        )
                    )
                continue

            if etype == "error":
                err = event.get("error")
                if isinstance(err, dict):
                    data = err.get("data") if isinstance(err.get("data"), dict) else {}
                    msg = str(data.get("message") or err.get("name") or "OpenCode error")
                else:
                    msg = str(err or "OpenCode error")
                out.append(self._openclaw_message("assistant", [{"type": "text", "text": msg}]))
        return out

    def _openclaw_message(self, role: str, content: list[dict[str, Any]]) -> dict[str, Any]:
        return {"type": "message", "message": {"role": role, "content": content}}

    def _copy_dir_from_container(self, task_id: str, src: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            ["docker", "cp", f"{task_id}:{src}", str(dest)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            logger.warning(
                "[%s] OpenCode dir copy failed (%s): %s", task_id, src, r.stderr.strip()
            )

    def _extract_usage_from_agent_log(self, agent_log: Path) -> dict[str, Any]:
        """Sum token usage from the NDJSON stream.

        Both ``step_finish`` and the final assistant carry
        ``tokens:{input,output,reasoning,cache:{read,write}}`` + ``cost``
        (schema/src/v1/session.ts:242-257,471-481). step_finish events are
        per-turn deltas, so we sum them; each is one request.
        """
        totals = self._empty_totals()
        if not agent_log.exists():
            return totals

        request_count = 0
        cost_sum = 0.0
        for raw in agent_log.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if str(event.get("type") or "").lower() != "step_finish":
                continue
            part = event.get("part") if isinstance(event.get("part"), dict) else {}
            tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
            if not tokens:
                continue
            cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
            totals["input_tokens"] += int(self._num(tokens.get("input")))
            totals["output_tokens"] += int(self._num(tokens.get("output")))
            totals["output_tokens"] += int(self._num(tokens.get("reasoning")))
            totals["cache_read_tokens"] += int(self._num(cache.get("read")))
            totals["cache_write_tokens"] += int(self._num(cache.get("write")))
            cost_sum += self._num(part.get("cost"))
            request_count += 1

        totals["request_count"] = request_count
        totals["total_tokens"] = (
            totals["input_tokens"]
            + totals["output_tokens"]
            + totals["cache_read_tokens"]
            + totals["cache_write_tokens"]
        )
        totals["cost_usd"] = round(cost_sum, 6)
        return totals

    def _empty_totals(self) -> dict[str, Any]:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
        }

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

    def _estimate_cost(self, totals: dict[str, Any]) -> float:
        input_price = float(os.environ.get("OPENCODE_INPUT_PRICE_PER_MTOK", "0"))
        output_price = float(os.environ.get("OPENCODE_OUTPUT_PRICE_PER_MTOK", "0"))
        cache_read_price = float(os.environ.get("OPENCODE_CACHE_READ_PRICE_PER_MTOK", "0"))
        cache_write_price = float(os.environ.get("OPENCODE_CACHE_WRITE_PRICE_PER_MTOK", "0"))
        uncached_input = max(
            totals["input_tokens"] - totals["cache_read_tokens"] - totals["cache_write_tokens"],
            0,
        )
        return (
            uncached_input / 1_000_000 * input_price
            + totals["output_tokens"] / 1_000_000 * output_price
            + totals["cache_read_tokens"] / 1_000_000 * cache_read_price
            + totals["cache_write_tokens"] / 1_000_000 * cache_write_price
        )
