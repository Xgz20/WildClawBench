"""Read-only platform configuration and health probes; never allocate a session."""

from __future__ import annotations
import socket
from urllib.parse import urlsplit
import requests
from .agentcube import AgentCubeConfig
from .common import E2EError


def runtime_status(config_path=None, *, probe=False):
    result = {
        "credentials": {"state": "not_configured", "authenticated": None},
        "endpoints": {},
        "cloud_capacity": {"state": "not_published", "value": None},
        "template": None,
        "astudio_login": {"state": "not_checked"},
    }
    try:
        config = AgentCubeConfig.load(config_path)
    except (OSError, ValueError, E2EError):
        return result
    result["credentials"] = {"state": "configured", "authenticated": None}
    result["template"] = {
        "name": config.template,
        "namespace": config.namespace,
        "state": "configured",
        "runtime_verified": False,
    }
    if config.astudio_runtime:
        from pathlib import Path

        file = config.astudio_runtime.get("session_file")
        result["astudio_login"] = {
            "state": (
                "configured" if file and Path(file).is_file() else "not_configured"
            ),
            "validity": "not_checked",
        }
    for role, url, path in [
        ("manager", config.workload_manager_url, "/health"),
        ("router", config.router_url, "/health/ready"),
    ]:
        target = urlsplit(url)
        row = {
            "state": "not_checked",
            "host": target.hostname,
            "dns": "not_checked",
            "http_status": None,
        }
        if probe:
            try:
                socket.getaddrinfo(
                    target.hostname,
                    target.port or (443 if target.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
                row["dns"] = "passed"
            except (OSError, ValueError):
                row.update(dns="failed", state="unreachable")
            if row["dns"] == "passed":
                try:
                    with requests.Session() as session:
                        session.trust_env = config.trust_env
                        response = session.get(
                            url.rstrip("/") + path,
                            timeout=(2, 3),
                            allow_redirects=False,
                        )
                    row["http_status"] = response.status_code
                    row["state"] = (
                        "responding"
                        if response.status_code == 200
                        else (
                            "not_published" if response.status_code == 404 else "failed"
                        )
                    )
                except requests.RequestException:
                    row["state"] = "unreachable"
        result["endpoints"][role] = row
    return result
