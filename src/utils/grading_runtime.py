"""Provision native-text dependencies inside the disposable scoring runtime.

This module is copied into the scoring container; it must use only stdlib
imports until the required package is available. It never runs a candidate CLI.
"""
from __future__ import annotations

import importlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys


PDF_REQUIREMENT = "pypdf>=5,<7"  # Keep aligned with requirements.txt.
INSTALL_TIMEOUT_SECONDS = 120


def _has_pdf(workspace: Path) -> bool:
    for path in workspace.rglob("*"):
        if (path.suffix.lower() == ".pdf" and path.is_file() and not path.is_symlink()
                and not {"gt", ".grading"}.intersection(path.relative_to(workspace).parts)):
            return True
    return False


def _pdf_version() -> str | None:
    try:
        version = metadata.version("pypdf")
        if version.split(".", 1)[0] not in {"5", "6"}:
            return None
        importlib.import_module("pypdf")
        return version
    except (ImportError, metadata.PackageNotFoundError):
        return None


def prepare_pdf_runtime(workspace_path: str) -> dict:
    """Install only when PDF evidence needs it; fail closed before Judge I/O.

    The interpreter is the same one running the judge, not the host Python.
    Keep a dependency audit even when installation fails. Pip output is not
    included because an index/proxy configuration may contain credentials.
    """
    workspace = Path(workspace_path)
    audit = workspace / ".grading/judge/runtime_dependencies.json"
    record = {"schema_version": 1, "requirement": PDF_REQUIREMENT,
              "python": sys.executable, "installed": False, "status": "not_required"}
    try:
        if not _has_pdf(workspace):
            return record
        version = _pdf_version()
        if version is None:
            record["status"] = "installing"
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                 "--no-input", "--retries", "1", "--timeout", "20",
                 "--break-system-packages", PDF_REQUIREMENT],
                capture_output=True, text=True, timeout=INSTALL_TIMEOUT_SECONDS,
            )
            if result.returncode:
                raise RuntimeError(
                    "SCORING_RUNTIME_DEPENDENCY_INSTALL_FAILED: "
                    f"pypdf (exit={result.returncode})"
                )
            record["installed"] = True
            importlib.invalidate_caches()
            version = _pdf_version()
            if version is None:
                raise RuntimeError("SCORING_RUNTIME_DEPENDENCY_VERIFY_FAILED: pypdf")
        record.update(status="available", version=version)
        return record
    except subprocess.TimeoutExpired as exc:
        record.update(status="failed", error="installation_timeout")
        raise RuntimeError("SCORING_RUNTIME_DEPENDENCY_INSTALL_TIMEOUT: pypdf") from exc
    except Exception as exc:
        record.update(status="failed", error=type(exc).__name__)
        raise
    finally:
        audit.parent.mkdir(parents=True, exist_ok=True)
        history = []
        if audit.is_file():
            history = json.loads(audit.read_text(encoding="utf-8")).get("checks", [])
        audit.write_text(json.dumps({"checks": [*history, record]}, indent=2) + "\n",
                         encoding="utf-8")
