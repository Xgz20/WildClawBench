"""Read-only transport inventory. Connectivity is never memory admission."""

from __future__ import annotations

import json
import plistlib
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from . import HARNESS_PORTS
from .io import publish, read_json, require, sha, timestamp

APP_NAMES = {"AstronStudio": ("AStudio.app", "AstronStudio.app", "Acode.app"),
             "WorkBuddy": ("WorkBuddy.app", "CodeBuddy.app"),
             "QwenWork": ("QwenWorkCN.app", "QwenWork.app"), "DoubaoWork": ("DoubaoWork.app",)}


def scan():
    clients = []
    for name, port in HARNESS_PORTS.items():
        installs = []
        for base in (Path("/Applications"), Path.home() / "Applications"):
            for app in APP_NAMES[name]:
                info_path = base / app / "Contents/Info.plist"
                if info_path.is_file():
                    with info_path.open("rb") as stream:
                        info = plistlib.load(stream)
                    installs.append({"path": str(base / app), "bundle_id": info.get("CFBundleIdentifier"),
                                     "version": info.get("CFBundleShortVersionString")})
        transport = {"endpoint": f"http://127.0.0.1:{port}", "reachable": False}
        try:
            with urllib.request.urlopen(transport["endpoint"] + "/json/version", timeout=2) as response:
                data = json.load(response)
            transport.update(reachable=True, browser=data.get("Browser"))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            transport["error_type"] = type(exc).__name__
        clients.append({"harness": name, "installs": installs, "transport": transport,
                        "memory_admission": "UNVERIFIED", "account_policy": "current_signed_in_account",
                        "required_evidence": ["native_identity", "actual_model_permissions", "synthetic_scope",
                                              "cross_session_readback", "targeted_cleanup", "background_settled"],
                        "memory_capabilities_inspected": False})
    return {"contract": "wildclawbench.memory-preflight/v1", "created_at": timestamp(),
            "status": "NEEDS_MEMORY_PREFLIGHT", "side_effects": "none", "clients": clients}


def native_preflight(output_dir, harnesses=None):
    """Reuse the existing read-only General probes; never restart or submit."""
    repository = Path(__file__).resolve().parents[1]
    output = Path(output_dir).absolute()
    require(not output.exists() and not output.resolve().is_relative_to(repository),
            "PREFLIGHT_OUTPUT", "Use a new private evidence directory outside the checkout")
    selected = list(HARNESS_PORTS) if harnesses is None else harnesses
    require(selected and len(set(selected)) == len(selected) and set(selected) <= set(HARNESS_PORTS),
            "HARNESS_SCOPE", "Unknown or duplicate Harness")
    base = repository / "tools/report/skills/general-e2e/execute-general-e2e"
    scripts = {"AstronStudio": base / "scripts/probe_astronstudio_macos.mjs",
               "WorkBuddy": base / "drivers/workbuddy/probe.mjs",
               "QwenWork": base / "drivers/qwenwork/probe.mjs", "DoubaoWork": base / "drivers/doubaowork/probe.mjs"}
    output.mkdir(parents=True)
    results = []
    for name in selected:
        folder = output / name
        folder.mkdir()
        app = "/Applications/" + APP_NAMES[name][0]
        command = ["node", str(scripts[name]), "--app-path", app,
                   "--endpoint", f"http://127.0.0.1:{HARNESS_PORTS[name]}"]
        raw = folder / "probe.json"
        command += ["--output-dir", str(folder)] if name == "DoubaoWork" else ["--output", str(raw)]
        entry = {"harness": name, "memory_admission": "UNVERIFIED", "source_script": str(scripts[name]),
                 "source_sha256": sha(scripts[name].read_bytes()), "prompt_send_attempted": False}
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
            publish(folder / "stdout.log", result.stdout)
            publish(folder / "stderr.log", result.stderr)
            entry["returncode"] = result.returncode
            if raw.is_file():
                report = read_json(raw)
                entry.update(raw_probe=str(raw), raw_sha256=sha(raw.read_bytes()),
                             general_probe_status=report.get("status") or ("READ_ONLY_MAPPING" if report.get("ready_for_read_only_mapping") else "UNVERIFIED"),
                             failed_checks=report.get("failed_checks", report.get("execution_blockers", [])))
                if name == "AstronStudio":
                    entry["active_or_pending_sessions"] = report.get("state_database", report.get("state_db", {})).get("active_or_pending_session_count")
            else:
                entry["general_probe_status"] = "PROBE_PROCESS_FAILED"
        except subprocess.TimeoutExpired as exc:
            publish(folder / "stdout.log", exc.stdout or b"")
            publish(folder / "stderr.log", exc.stderr or b"")
            entry["general_probe_status"] = "PROBE_TRANSPORT_TIMEOUT"
        results.append(entry)
    report = {"contract": "wildclawbench.memory-preflight/v1", "created_at": timestamp(),
              "status": "NEEDS_MEMORY_PREFLIGHT", "side_effects": "read_only_general_probes",
              "account_policy": "current_signed_in_account", "clients": results,
              "interpretation": "General probe PASS or a reachable CDP is not memory readiness. No Prompt or account-memory reset was issued."}
    publish(output / "preflight.json", report)
    return report
