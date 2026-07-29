from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.agents.base import AgentExecution, AgentTaskSpec, BaseAgent
from src.utils.grading import extract_usage_from_jsonl
from src.utils.docker_utils import (
    DOCKER_IMAGE,
    inject_lobster_workspace,
    inject_openclaw_models,
    run_background,
    run_warmup,
    setup_skills,
    setup_workspace,
    start_container,
)

load_dotenv()

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_execution_status(output_dir: Path, **updates: Any) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "execution_status.json"
    status: dict[str, Any] = {}
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
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
        json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return status


class OpenClawAgent(BaseAgent):
    harness_name = "openclaw"
    harness_display_name = "OpenClaw"
    supports_provider_timeout_seconds = False

    def __init__(
        self,
        gateway_port: int,
        openrouter_api_key: str = "",
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        image_model: str | None = None,
        image: str | None = None,
    ) -> None:
        self.gateway_port = gateway_port
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_base_url = openrouter_base_url
        self.image_model = (
            image_model
            if image_model is not None
            else os.environ.get("OPENCLAW_IMAGE_MODEL", "").strip()
        )
        self.image = image or DOCKER_IMAGE

    @property
    def expects_gateway(self) -> bool:
        return True

    @property
    def transcript_container_path(self) -> str:
        return "/root/.openclaw/agents/main/sessions/chat.jsonl"

    def run_task(self, spec: AgentTaskSpec) -> AgentExecution:
        gateway_proc = None
        agent_proc = None
        elapsed_time = float(spec.timeout_seconds)
        start_time = time.perf_counter()

        write_execution_status(
            spec.output_dir,
            task_id=spec.task_id,
            model=spec.model,
            timeout_seconds=spec.timeout_seconds,
            status="created",
            started_at=_now_iso(),
            timed_out=False,
            exit_code=None,
            error=None,
        )

        try:
            exec_path = os.path.join(spec.workspace_path, "exec")
            tmp_path = os.path.join(spec.workspace_path, "tmp")
            os.makedirs(exec_path, exist_ok=True)

            write_execution_status(spec.output_dir, status="starting_container")
            start_container(
                spec.task_id,
                exec_path,
                extra_env=spec.task.get("env", ""),
                tmp_path=tmp_path,
                lobster_env=spec.lobster.get("env") if spec.lobster else None,
                docker_image=self.image,
            )
            write_execution_status(
                spec.output_dir,
                status="container_started",
                harness=self.harness_name,
                harness_version=self._probe_harness_version(spec.task_id),
                image=self.image,
            )
            if spec.lobster:
                inject_lobster_workspace(spec.task_id, spec.lobster["workspace"])

            write_execution_status(spec.output_dir, status="preparing_workspace")
            setup_workspace(spec.task_id, thinking=spec.thinking)
            # OpenClaw 从 ~/.openclaw/skills/<name>/ 发现 skill（不是 codex 用的 /root/skills）。
            setup_skills(
                spec.task_id,
                spec.task.get("skills", ""),
                spec.task.get("skills_path", ""),
                container_skills_root="/root/.openclaw/skills",
            )
            run_warmup(spec.task_id, spec.task.get("warmup", ""))

            write_execution_status(spec.output_dir, status="preparing_harness_input")
            # 注册自定义 provider（openai-completions + 讯飞 baseUrl）到 models 段。
            # 若外部显式传入 models_config，则以它为准（信任外部完整配置）。
            if spec.models_config:
                inject_openclaw_models(spec.task_id, spec.models_config)
            else:
                self._register_provider(spec.task_id, spec.model, spec.timeout_seconds)

            self._set_model(spec.task_id, spec.model)
            self._inject_openrouter_key(spec.task_id)
            image_model = self.image_model or spec.model
            self._set_image_model(spec.task_id, image_model)

            self._configure_harness(spec.task_id)

            # 设置 agents.defaults.timeoutSeconds，让 LLM idle timeout 动态跟随任务超时。
            # 慢模型的大 context 请求首 token 延迟可能超过默认上限。
            self._set_agent_timeout(spec.task_id, spec.timeout_seconds)

            write_execution_status(spec.output_dir, status="launching_harness")
            gateway_proc = run_background(
                spec.task_id,
                bash_cmd=(
                    f"export OPENROUTER_API_KEY='{self.openrouter_api_key}' && "
                    f"export OPENROUTER_BASE_URL='{self.openrouter_base_url}' && "
                    f"openclaw gateway --port {self.gateway_port}"
                ),
                log_path=spec.output_dir / "gateway.log",
            )
            logger.info("[%s] Waiting for gateway to be ready (2s)...", spec.task_id)
            time.sleep(2)

            safe_prompt = spec.prompt.replace("'", "'\\''")
            start_time = time.perf_counter()
            agent_proc = run_background(
                spec.task_id,
                bash_cmd=f"openclaw agent --session-id chat --timeout {spec.timeout_seconds} --message '{safe_prompt}'",
                log_path=spec.output_dir / "agent.log",
            )
            write_execution_status(
                spec.output_dir,
                status=f"{self.harness_name}_running",
            )

            logger.info("[%s] Waiting for agent to finish...", spec.task_id)
            try:
                agent_proc.wait(timeout=spec.timeout_seconds)
                elapsed_time = time.perf_counter() - start_time
                logger.info(
                    "[%s] Agent finished successfully, elapsed: %.2f seconds",
                    spec.task_id,
                    elapsed_time,
                )
            except subprocess.TimeoutExpired:
                logger.info("[%s] Agent timed out...", spec.task_id)
                elapsed_time = float(spec.timeout_seconds)
                agent_proc.kill()
                agent_proc.wait()
                error = f"{self.harness_display_name} run timed out"
                write_execution_status(
                    spec.output_dir,
                    status="timed_out",
                    timed_out=True,
                    exit_code=agent_proc.returncode,
                    elapsed_time=round(elapsed_time, 2),
                    error=error,
                )
                return AgentExecution(
                    elapsed_time=elapsed_time,
                    error=error,
                    gateway_proc=gateway_proc,
                    agent_proc=agent_proc,
                )

            logger.info("[%s] Agent exit code: %s", spec.task_id, agent_proc.returncode)
            if agent_proc.returncode not in (0, None):
                error = (
                    f"{self.harness_display_name} run failed "
                    f"(rc={agent_proc.returncode})"
                )
                write_execution_status(
                    spec.output_dir,
                    status="error",
                    exit_code=agent_proc.returncode,
                    elapsed_time=round(elapsed_time, 2),
                    error=error,
                )
                return AgentExecution(
                    elapsed_time=elapsed_time,
                    error=error,
                    gateway_proc=gateway_proc,
                    agent_proc=agent_proc,
                )
            write_execution_status(
                spec.output_dir,
                status="finished",
                finished_at=_now_iso(),
                exit_code=agent_proc.returncode,
                elapsed_time=round(elapsed_time, 2),
                error=None,
            )
            return AgentExecution(
                elapsed_time=elapsed_time,
                error=None,
                gateway_proc=gateway_proc,
                agent_proc=agent_proc,
            )
        except Exception as exc:
            logger.error("[%s] Execution error: %s", spec.task_id, exc)
            elapsed_time = time.perf_counter() - start_time
            write_execution_status(
                spec.output_dir,
                status="error",
                exit_code=agent_proc.returncode if agent_proc is not None else None,
                elapsed_time=round(elapsed_time, 2),
                error=str(exc),
            )
            return AgentExecution(
                elapsed_time=elapsed_time,
                error=str(exc),
                gateway_proc=gateway_proc,
                agent_proc=agent_proc,
            )

    def collect_usage(self, task_id: str, output_dir: Path, elapsed_time: float) -> dict:
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
            usage = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "request_count": 0,
            }
        usage["elapsed_time"] = round(elapsed_time, 2)
        # Refresh version metadata while the container is still alive.
        self._write_harness_metadata(task_id, output_dir)
        return usage

    def _write_harness_metadata(self, task_id: str, output_dir: Path) -> None:
        updates = {
            "harness": self.harness_name,
            "image": self.image,
        }
        version = self._probe_harness_version(task_id)
        if version:
            updates["harness_version"] = version
        write_execution_status(output_dir, **updates)

    @staticmethod
    def _probe_harness_version(task_id: str) -> str:
        """Read the OpenClaw CLI version from inside the container (non-fatal)."""
        try:
            r = subprocess.run(
                ["docker", "exec", task_id, "openclaw", "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("[%s] openclaw --version probe failed: %s", task_id, exc)
            return ""
        if r.returncode != 0:
            logger.warning(
                "[%s] openclaw --version returned %s: %s",
                task_id, r.returncode, (r.stderr or r.stdout).strip(),
            )
            return ""
        out = (r.stdout or "").strip()
        return out.splitlines()[0].strip().split()[-1] if out else ""

    def _configure_harness(self, task_id: str) -> None:
        """Keep OpenClaw bootable when the optional Brave key is absent."""
        if os.environ.get("BRAVE_API_KEY", "").strip():
            return

        configure_cmd = """python3 - <<'PY'
import json
import pathlib

p = pathlib.Path("/root/.openclaw/openclaw.json")
d = json.loads(p.read_text()) if p.exists() else {}
search = d.setdefault("tools", {}).setdefault("web", {}).setdefault("search", {})
search["enabled"] = False
search.pop("apiKey", None)
p.write_text(json.dumps(d, indent=2))
PY"""
        result = subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c", configure_cmd],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Failed to disable OpenClaw web search without BRAVE_API_KEY:\n"
                f"{result.stderr}"
            )
        logger.info(
            "[%s] Disabled tools.web.search because BRAVE_API_KEY is not configured",
            task_id,
        )

    # 内部自定义 provider 名。OpenClaw 内建的 openrouter provider 把 baseURL 硬编码为
    # https://openrouter.ai/api/v1（无环境变量覆盖点），无法连讯飞 maas endpoint。
    # 因此注册一个 openai-completions 兼容的自定义 provider，用 self.openrouter_base_url。
    PROVIDER = "wildclaw"

    @staticmethod
    def _bare_model_id(model: str) -> str:
        """把 openrouter/xopglm52 这样的模型 id 去掉 provider 前缀 → xopglm52。"""
        return model.split("/", 1)[-1] if "/" in model else model

    def _register_provider(self, task_id: str, model: str, timeout_seconds: int) -> None:
        """
        在 openclaw.json 的 models 段注册自定义 provider（openai-completions +
        讯飞 baseUrl），并把模型注册进去。mode=merge 保留内建 provider。
        AstronClaw 的 provider schema 支持 timeoutSeconds，可通过子类能力开关
        写入任务超时；OpenClaw 2026.3.11 不接受该 provider 字段。
        """
        model_id = self._bare_model_id(model)
        image_id = self._bare_model_id(self.image_model) if self.image_model else model_id
        model_entries = [{"id": model_id, "name": model_id}]
        if image_id != model_id:
            model_entries.append({"id": image_id, "name": image_id})
        provider_config = {
            "api": "openai-completions",
            "baseUrl": self.openrouter_base_url,
            "models": model_entries,
        }
        if self.supports_provider_timeout_seconds:
            provider_config["timeoutSeconds"] = timeout_seconds
        models_config = {
            "mode": "merge",
            "providers": {
                self.PROVIDER: provider_config,
            },
        }
        inject_cmd = f"""python3 - <<'PY'
import json
import pathlib

p = pathlib.Path("/root/.openclaw/openclaw.json")
d = json.loads(p.read_text()) if p.exists() else {{}}
d["models"] = json.loads({json.dumps(json.dumps(models_config))})
p.write_text(json.dumps(d, indent=2))
PY"""
        r = subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c", inject_cmd],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Provider registration failed:\n{r.stderr}")
        logger.info(
            "[%s] Registered provider '%s' → %s (models: %s)",
            task_id, self.PROVIDER, self.openrouter_base_url,
            ", ".join(m["id"] for m in model_entries),
        )

    def _set_model(self, task_id: str, model: str) -> None:
        target = f"{self.PROVIDER}/{self._bare_model_id(model)}"
        r = subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c", f"openclaw models set '{target}'"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Model setup failed:\n{r.stderr}")
        logger.info("[%s] Model set: %s", task_id, target)

    def _inject_openrouter_key(self, task_id: str) -> None:
        if not self.openrouter_api_key:
            return

        auth_profile_path = "/root/.openclaw/agents/main/agent/auth-profiles.json"
        inject_cmd = f"""python3 - <<'PY'
import json
import pathlib

p = pathlib.Path("{auth_profile_path}")
p.parent.mkdir(parents=True, exist_ok=True)
d = json.loads(p.read_text()) if p.exists() else {{"version": 1, "profiles": {{}}}}
d.setdefault("profiles", {{}})[{json.dumps(self.PROVIDER + ":default")}] = {{
    "type": "api_key",
    "provider": {json.dumps(self.PROVIDER)},
    "key": {json.dumps(self.openrouter_api_key)}
}}
p.write_text(json.dumps(d, indent=2))
PY"""
        subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c", inject_cmd],
            capture_output=True,
            text=True,
        )
        logger.info("[%s] Injected API key into auth-profiles.json (provider=%s)", task_id, self.PROVIDER)

    def _set_image_model(self, task_id: str, model: str) -> None:
        target = f"{self.PROVIDER}/{self._bare_model_id(model)}"
        subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c", f"openclaw config set agents.defaults.imageModel.primary '{target}'"],
            capture_output=True,
            text=True,
        )
        logger.info("[%s] imageModel set: %s", task_id, target)

    def _set_agent_timeout(self, task_id: str, timeout_seconds: int) -> None:
        """
        设置 agents.defaults.timeoutSeconds，让 LLM idle timeout 动态跟随任务超时。
        openclaw 的 resolveLlmIdleTimeoutMs 会从该值推导 idle 阈值。慢模型的单次
        大 context 请求首 token 延迟可能超过默认上限，需要此配置避免中断。
        """
        r = subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c", f"openclaw config set agents.defaults.timeoutSeconds {timeout_seconds}"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            logger.warning("[%s] Failed to set agents.defaults.timeoutSeconds=%d: %s", task_id, timeout_seconds, r.stderr.strip()[:200])
        else:
            logger.info("[%s] agents.defaults.timeoutSeconds set: %d", task_id, timeout_seconds)
