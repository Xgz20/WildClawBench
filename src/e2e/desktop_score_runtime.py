"""Prepare the frozen General scoring runtime inside a disposable Windows VM."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
import zipfile


# Official PyPI Windows x64 wheel, matching the deployment's uv release.
UV_URL = "https://files.pythonhosted.org/packages/b5/9c/1954092ce17c00a8c299d39f8121e4c8d60f22a69c103f34d8b8dc68444d/uv-0.10.12-py3-none-win_amd64.whl"
UV_MIRROR_URL = "https://pypi.tuna.tsinghua.edu.cn/packages/b5/9c/1954092ce17c00a8c299d39f8121e4c8d60f22a69c103f34d8b8dc68444d/uv-0.10.12-py3-none-win_amd64.whl"
UV_WHEEL_SHA256 = "76ebe11572409dfbe20ec25a823f9bc8781400ece5356aa33ec44903af7ec316"
UV_EXE_SHA256 = "f13b441ca13bf0a1d02d367e395c8a72e11733c5c29efa4a2f71af6a3a30d5ac"
UV_MEMBER = "uv-0.10.12.data/scripts/uv.exe"
MAX_WHEEL_BYTES = 30 * 1024 * 1024
UV_CONFIG = '[[index]]\nurl = "https://pypi.tuna.tsinghua.edu.cn/simple"\ndefault = true\n'


def requires_browser(skill, contract):
    """Use the frozen rule core's import audit; uncertainty keeps the full runtime."""
    if contract is None:
        return True
    package = skill / "vendor/e2e-shared/wildclawbench_grading_core"
    name = "_desktop_rule_core_" + hashlib.sha256(str(package).encode()).hexdigest()[:16]
    try:
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, package / "__init__.py",
                                                         submodule_search_locations=[str(package)])
            core = importlib.util.module_from_spec(spec)
            sys.modules[name] = core
            spec.loader.exec_module(core)
        profile = sys.modules[name].inspect_rule_dependencies(contract["automated_checks"])
        return any(asset.get("name") == "chromium" for dependency in profile["external"]
                   for asset in dependency.get("runtime_assets", []))
    except Exception:
        # This selects provisioning scope, never whether a rule or score is
        # valid. The frozen scorer still validates and executes the contract.
        sys.modules.pop(name, None)
        return True


def uv_executable(directory, remaining):
    """Use only the pinned executable; never install into the VM's system Python."""
    directory.mkdir(exist_ok=True)
    executable = directory / "uv.exe"
    if executable.is_file():
        if hashlib.sha256(executable.read_bytes()).hexdigest() != UV_EXE_SHA256:
            raise ValueError("DESKTOP_SCORING_UV_DIGEST_MISMATCH")
        return executable
    archive = directory / "uv.whl.part"
    try:
        digest = hashlib.sha256()
        size = 0
        # Use the same PyPI mirror as the framework deployment. Both sources
        # must match the official wheel's pinned digest before extraction.
        try:
            response = urllib.request.urlopen(UV_MIRROR_URL, timeout=min(30, remaining()))
        except OSError:
            response = urllib.request.urlopen(UV_URL, timeout=min(30, remaining()))
        with response, archive.open("wb") as output:
            read = getattr(response, "read1", response.read)
            while chunk := read(1024 * 1024):
                remaining()
                size += len(chunk)
                if size > MAX_WHEEL_BYTES:
                    raise ValueError("DESKTOP_SCORING_UV_DOWNLOAD_TOO_LARGE")
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != UV_WHEEL_SHA256:
            raise ValueError("DESKTOP_SCORING_UV_DIGEST_MISMATCH")
        with zipfile.ZipFile(archive) as wheel:
            payload = wheel.read(UV_MEMBER)
        if hashlib.sha256(payload).hexdigest() != UV_EXE_SHA256:
            raise ValueError("DESKTOP_SCORING_UV_DIGEST_MISMATCH")
        temporary = directory / "uv.exe.part"
        temporary.write_bytes(payload)
        temporary.replace(executable)
    finally:
        archive.unlink(missing_ok=True)
    return executable


def prepare_runtime(skill, tooling, timeout, *, contract=None):
    """Bootstrap and probe with the Skill's own lock, without changing that lock."""
    deadline = time.monotonic() + timeout
    diagnostic = tooling / "general-runtime-steps.jsonl"

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise ValueError("DESKTOP_SCORING_RUNTIME_TIMEOUT")
        return seconds

    def run(action, *args):
        try:
            response = subprocess.run(
                [sys.executable, "-X", "utf8", str(skill / "scripts/score_general_e2e.py"), action, *map(str, args)],
                cwd=cache, capture_output=True, timeout=remaining(),
            )
        except subprocess.TimeoutExpired:
            code = "DESKTOP_SCORING_RUNTIME_TIMEOUT"
            with diagnostic.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"action": action, "error": code}) + "\n")
            raise ValueError(code) from None
        code = None
        if response.returncode:
            code = "DESKTOP_SCORING_RUNTIME_PREPARATION_FAILED"
            try:
                value = json.loads(response.stderr)["error"]["code"]
                if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,99}", value):
                    code = value
            except (UnicodeError, ValueError, KeyError, TypeError):
                pass
        with diagnostic.open("a", encoding="utf-8") as stream:
            # CLI stderr may contain proxy credentials or arbitrary guest paths.
            stream.write(json.dumps({"action": action, "returncode": response.returncode, "error": code}) + "\n")
        if code:
            # Keep the detailed CLI output in the private guest workspace. Only
            # the bounded structured step receipt is projected by the controller.
            (tooling / ("general-runtime-" + action + ".stderr.log")).write_bytes(response.stderr)
            raise ValueError(code)
        return json.loads(response.stdout)

    lock_path = skill / "references/scoring-runtime-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    browser = requires_browser(skill, contract)
    # Keep Python, dependencies and Chromium outside the collected project.
    # Only their verification receipt belongs in the scoring evidence package.
    cache = tooling.parent.parent / ".desktop-scoring-runtime" / hashlib.sha256(lock_path.read_bytes()).hexdigest()[:16]
    cache.mkdir(parents=True, exist_ok=True)
    config = cache / "uv.toml"
    if config.exists() and config.read_text(encoding="utf-8") != UV_CONFIG:
        raise ValueError("DESKTOP_SCORING_RUNTIME_CONFIG_DRIFT")
    config.write_text(UV_CONFIG, encoding="utf-8")
    runtime = cache / ("runtime" if browser else "runtime-no-browser")
    python = runtime / "Scripts/python.exe"
    if not runtime.exists():
        try:
            uv = uv_executable(cache / "bootstrap", remaining)
        except (OSError, ValueError) as error:
            code = str(error) if re.fullmatch(r"[A-Z][A-Z0-9_]{1,99}", str(error)) else "DESKTOP_SCORING_UV_DOWNLOAD_FAILED"
            with diagnostic.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"action": "download-uv", "error": code}) + "\n")
            raise ValueError(code) from None
        run("bootstrap-runtime", "--venv-root", runtime, "--uv-command", uv, *([] if browser else ["--skip-browser"]))
    # An interrupted/unknown environment must be verified, never silently reused.
    imports = [arg for dependency in lock["dependencies"] if browser or not dependency.get("runtime_assets")
               for name in dependency["import_roots"]
               for arg in ("--import-root", name)]
    probe = run("probe-runtime", "--runtime-python", python, "--runtime-lock", lock_path,
                *(["--playwright-browsers-path", runtime / "playwright-browsers"] if browser else []), *imports)
    result = {"status": probe["status"], "python": str(python),
              "runtime_lock_sha256": probe["runtime_lock_sha256"], "browser_required": browser, "probe": probe["probe"]}
    (tooling / "general-runtime.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result
