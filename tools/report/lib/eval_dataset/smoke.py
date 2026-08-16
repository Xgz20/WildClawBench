"""Warmup 的一次性容器 smoke 执行器。默认流程不会导入或调用本模块。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .security import redact_text


def run_warmup_smoke(
    commands: Iterable[str],
    *,
    image: str | None,
    workspace: str | Path,
    timeout_seconds: int = 60,
    docker_bin: str = "docker",
) -> list[dict[str, Any]]:
    commands = [command for command in commands if command.strip()]
    if not commands:
        return []
    if not image:
        return [{"status": "smoke_unavailable", "code": "SMOKE_UNAVAILABLE", "message": "未提供 Warmup 容器镜像"}]
    docker = shutil.which(docker_bin)
    if not docker:
        return [{"status": "smoke_unavailable", "code": "SMOKE_UNAVAILABLE", "message": "找不到 Docker 可执行文件"}]
    workspace = Path(workspace).resolve()
    results: list[dict[str, Any]] = []
    for command in commands:
        argv = [docker, "run", "--rm", "-i", "-v", f"{workspace}:/tmp_workspace", "-w", "/tmp_workspace", image, "sh", "-lc", command]
        try:
            completed = subprocess.run(argv, timeout=timeout_seconds, check=False, capture_output=True, text=True)
        except subprocess.TimeoutExpired as exc:
            results.append({"status": "failed", "code": "WARMUP_SMOKE_TIMEOUT", "returncode": None, "stderr": redact_text(str(exc))})
            continue
        except OSError as exc:
            results.append({"status": "smoke_unavailable", "code": "SMOKE_UNAVAILABLE", "message": redact_text(str(exc))})
            continue
        result = {"status": "passed" if completed.returncode == 0 else "failed", "code": "WARMUP_SMOKE_PASSED" if completed.returncode == 0 else "WARMUP_SMOKE_FAILED", "returncode": completed.returncode, "stderr": redact_text(completed.stderr or "")}
        results.append(result)
    return results
