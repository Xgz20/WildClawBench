"""Docker lifecycle helpers for the MaaS request-limit proxy."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path


MAAS_PROXY_PORT = 18080
MAAS_PROXY_BASE_URL = f"http://127.0.0.1:{MAAS_PROXY_PORT}"
MAAS_PROXY_SCRIPT_PATH = "/tmp/wcb_maas_request_proxy.py"
MAAS_PROXY_AUDIT_PATH = "/tmp/wcb_maas_request_limits.jsonl"
MAAS_PROXY_AUDIT_NAME = "maas_request_limits.jsonl"


def start_maas_request_proxy(
    container_name: str,
    *,
    upstream_base_url: str,
    max_tokens: int,
) -> str:
    """Start the per-container MaaS proxy and return its local base URL."""

    script_path = Path(__file__).with_name("maas_request_proxy.py")
    copied = subprocess.run(
        ["docker", "cp", str(script_path), f"{container_name}:{MAAS_PROXY_SCRIPT_PATH}"],
        capture_output=True,
        text=True,
    )
    if copied.returncode != 0:
        raise RuntimeError(f"MaaS request proxy copy failed: {copied.stderr.strip()}")

    started = subprocess.run(
        [
            "docker",
            "exec",
            "-d",
            container_name,
            "python3",
            MAAS_PROXY_SCRIPT_PATH,
            "--port",
            str(MAAS_PROXY_PORT),
            "--upstream-base-url",
            upstream_base_url,
            "--max-tokens",
            str(max_tokens),
            "--audit-log",
            MAAS_PROXY_AUDIT_PATH,
        ],
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        raise RuntimeError(f"MaaS request proxy startup failed: {started.stderr.strip()}")

    probe_code = (
        "import socket; "
        f"s=socket.create_connection(('127.0.0.1',{MAAS_PROXY_PORT}),1); s.close()"
    )
    for _ in range(40):
        probe = subprocess.run(
            ["docker", "exec", container_name, "python3", "-c", probe_code],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return MAAS_PROXY_BASE_URL
        time.sleep(0.1)

    raise RuntimeError("MaaS request proxy readiness check failed")


def collect_maas_request_audit(container_name: str, output_dir: Path) -> bool:
    """Copy the secret-free proxy audit log into the run directory if present."""

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / MAAS_PROXY_AUDIT_NAME
    temporary = output_dir / f".{MAAS_PROXY_AUDIT_NAME}.tmp"
    try:
        copied = subprocess.run(
            ["docker", "cp", f"{container_name}:{MAAS_PROXY_AUDIT_PATH}", str(temporary)],
            capture_output=True,
            text=True,
        )
    except Exception:
        # Audit export is diagnostic only and must never change evaluation
        # usage collection or container cleanup behavior.
        temporary.unlink(missing_ok=True)
        return False
    if copied.returncode != 0:
        temporary.unlink(missing_ok=True)
        return False
    shutil.move(str(temporary), str(destination))
    return True
