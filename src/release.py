"""Identify the executor/Skill release, independently of dataset content."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


def release_revision(repo: Path) -> str:
    configured = os.environ.get("WCB_E2E_REVISION", "").strip()
    marker = repo / ".wildclawbench-revision"
    if not configured and marker.is_file():
        configured = marker.read_text(encoding="utf-8").strip()
    if configured:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", configured):
            raise ValueError("WCB_E2E_REVISION_INVALID")
        return configured.lower()
    # Git is a development-checkout fallback, never a dataset version source.
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("WCB_E2E_REVISION_INVALID")
    return revision
