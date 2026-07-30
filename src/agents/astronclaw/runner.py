from __future__ import annotations

import logging
import os
import subprocess

from src.agents.openclaw import OpenClawAgent

logger = logging.getLogger(__name__)

DEFAULT_ASTRONCLAW_IMAGE = "wildclawbench-astronclaw-ubuntu:v0.2.9-eval.1"


class AstronClawAgent(OpenClawAgent):
    """AstronClaw backend using its OpenClaw-compatible CLI."""

    harness_name = "astronclaw"
    harness_display_name = "AstronClaw"
    supports_provider_timeout_seconds = True

    def __init__(
        self,
        gateway_port: int,
        openrouter_api_key: str = "",
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        image_model: str | None = None,
        image: str | None = None,
    ) -> None:
        super().__init__(
            gateway_port=gateway_port,
            openrouter_api_key=openrouter_api_key,
            openrouter_base_url=openrouter_base_url,
            image_model=image_model,
            image=(
                image
                or os.environ.get("DOCKER_IMAGE_ASTRONCLAW", "").strip()
                or DEFAULT_ASTRONCLAW_IMAGE
            ),
        )

    def _configure_harness(self, task_id: str) -> None:
        # AstronClaw's default config lacks gateway.mode, so its gateway refuses
        # to start until local mode is explicitly selected.
        result = subprocess.run(
            [
                "docker", "exec", task_id, "/bin/bash", "-c",
                "openclaw config set gateway.mode local",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "[%s] Failed to set gateway.mode=local: %s",
                task_id,
                result.stderr.strip()[:200],
            )
        else:
            logger.info("[%s] gateway.mode set: local", task_id)
