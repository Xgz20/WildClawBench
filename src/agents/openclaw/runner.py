from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv

from src.agents.base import AgentExecution, AgentTaskSpec, BaseAgent
from src.utils.grading import extract_usage_from_jsonl
from src.utils.docker_utils import (
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


class OpenClawAgent(BaseAgent):
    def __init__(
        self,
        gateway_port: int,
        openrouter_api_key: str = "",
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        image_model: str | None = None,
    ) -> None:
        self.gateway_port = gateway_port
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_base_url = openrouter_base_url
        self.image_model = image_model if image_model is not None else os.environ.get("OPENCLAW_IMAGE_MODEL", "").strip()

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

        try:
            exec_path = os.path.join(spec.workspace_path, "exec")
            tmp_path = os.path.join(spec.workspace_path, "tmp")
            os.makedirs(exec_path, exist_ok=True)

            start_container(
                spec.task_id,
                exec_path,
                extra_env=spec.task.get("env", ""),
                tmp_path=tmp_path,
                lobster_env=spec.lobster.get("env") if spec.lobster else None,
            )
            if spec.lobster:
                inject_lobster_workspace(spec.task_id, spec.lobster["workspace"])

            setup_workspace(spec.task_id, thinking=spec.thinking)
            # OpenClaw 从 ~/.openclaw/skills/<name>/ 发现 skill（不是 codex 用的 /root/skills）。
            setup_skills(
                spec.task_id,
                spec.task.get("skills", ""),
                spec.task.get("skills_path", ""),
                container_skills_root="/root/.openclaw/skills",
            )
            run_warmup(spec.task_id, spec.task.get("warmup", ""))

            # 注册自定义 provider（openai-completions + 讯飞 baseUrl）到 models 段。
            # 若外部显式传入 models_config，则以它为准（信任外部完整配置）。
            if spec.models_config:
                inject_openclaw_models(spec.task_id, spec.models_config)
            else:
                self._register_provider(spec.task_id, spec.model)

            self._set_model(spec.task_id, spec.model)
            self._inject_openrouter_key(spec.task_id)
            image_model = self.image_model or spec.model
            self._set_image_model(spec.task_id, image_model)

            # AstronClaw 镜像默认配置缺 gateway 段，gateway 启动会被 block
            # （"missing gateway.mode"）。显式设置为 local；对原版 OpenClaw 幂等无害。
            self._ensure_gateway_mode(spec.task_id)

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

            logger.info("[%s] Agent exit code: %s", spec.task_id, agent_proc.returncode)
            return AgentExecution(
                elapsed_time=elapsed_time,
                error=None,
                gateway_proc=gateway_proc,
                agent_proc=agent_proc,
            )
        except Exception as exc:
            logger.error("[%s] Execution error: %s", spec.task_id, exc)
            return AgentExecution(
                elapsed_time=float(spec.timeout_seconds),
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
        # Record harness identity/version for traceability. OpenClaw has no
        # execution_status.json flow, so write a minimal one here (container
        # still alive at collect_usage time — see transcript docker cp above).
        self._write_harness_metadata(task_id, output_dir)
        return usage

    def _write_harness_metadata(self, task_id: str, output_dir: Path) -> None:
        version = self._probe_harness_version(task_id)
        status_path = output_dir / "execution_status.json"
        status: dict = {}
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                status = {}
        status.update({
            "harness": "openclaw",
            "harness_version": version,
            "image": os.environ.get("DOCKER_IMAGE", "wildclawbench-ubuntu:v1.3"),
        })
        output_dir.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
        )

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

    # 内部自定义 provider 名。OpenClaw 内建的 openrouter provider 把 baseURL 硬编码为
    # https://openrouter.ai/api/v1（无环境变量覆盖点），无法连讯飞 maas endpoint。
    # 因此注册一个 openai-completions 兼容的自定义 provider，用 self.openrouter_base_url。
    PROVIDER = "wildclaw"

    @staticmethod
    def _bare_model_id(model: str) -> str:
        """把 openrouter/xopglm52 这样的模型 id 去掉 provider 前缀 → xopglm52。"""
        return model.split("/", 1)[-1] if "/" in model else model

    def _register_provider(self, task_id: str, model: str) -> None:
        """
        在 openclaw.json 的 models 段注册自定义 provider（openai-completions +
        讯飞 baseUrl），并把模型注册进去。mode=merge 保留内建 provider。
        """
        model_id = self._bare_model_id(model)
        image_id = self._bare_model_id(self.image_model) if self.image_model else model_id
        model_entries = [{"id": model_id, "name": model_id}]
        if image_id != model_id:
            model_entries.append({"id": image_id, "name": image_id})
        models_config = {
            "mode": "merge",
            "providers": {
                self.PROVIDER: {
                    "api": "openai-completions",
                    "baseUrl": self.openrouter_base_url,
                    "models": model_entries,
                }
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

    def _ensure_gateway_mode(self, task_id: str) -> None:
        """
        AstronClaw 镜像默认 openclaw.json 只有 plugins/meta 段，缺 gateway 段，
        导致 gateway 启动被 block（"existing config is missing gateway.mode"），
        agent 随后 fallback 到 embedded 模式且认证头缺失（401）。
        显式设置 gateway.mode=local。对原版 OpenClaw（已有该值）幂等无害。
        """
        r = subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c", "openclaw config set gateway.mode local"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            logger.warning("[%s] Failed to set gateway.mode=local: %s", task_id, r.stderr.strip()[:200])
        else:
            logger.info("[%s] gateway.mode set: local", task_id)
