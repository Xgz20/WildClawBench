"""Install the controller-selected Skill in the Windows scoring client's runtime."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from preprocess_windows_guest import StepError, astudio_paths, quiescent, runtime, _reparse


ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{1,99}\Z")


def general_failure(action, stderr):
    fallback = "DESKTOP_SCORING_GENERAL_" + action.upper().replace("-", "_") + "_FAILED"
    try:
        code = json.loads(stderr)["error"]["code"]
    except (UnicodeError, ValueError, KeyError, TypeError):
        lines = stderr.decode("utf-8", errors="replace").splitlines()
        failure = re.fullmatch(r"([A-Za-z][A-Za-z0-9_.]{0,63}):\s*(.*)", lines[-1]) if lines else None
        if not failure:
            return StepError(fallback)
        exception, message = failure.groups()
        frames = re.findall(r'File "[^"\n]*[\\/]([A-Za-z0-9_]+\.py)", line (\d+)', "\n".join(lines))
        details = {"exception": exception}
        if frames:
            details["category"], line = frames[-1]
            details["line"] = int(line)
        winerror = re.match(r"\[WinError (\d+)\]", message)
        if winerror:
            details["winerror"] = int(winerror[1])
        return StepError(message if ERROR_CODE.fullmatch(message) else fallback, **details)
    return StepError(code if isinstance(code, str) and ERROR_CODE.fullmatch(code) else fallback)


def contents(root):
    rows = {}
    for path in root.rglob("*"):
        if _reparse(path) or (not path.is_dir() and not path.is_file()):
            raise ValueError("DESKTOP_SCORING_UNSAFE_SKILL_PATH")
        if path.is_file():
            rows[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return rows


def prepare_general(work, target, tooling, request):
    entry = target / "scripts/score_general_e2e.py"

    def run(action, *args):
        response = subprocess.run([sys.executable, "-X", "utf8", str(entry), action, *map(str, args)],
                                  cwd=work, capture_output=True, timeout=request["timeout_seconds"])
        if response.returncode:
            raise general_failure(action, response.stderr)

    attempt = work / "attempts" / request["attempt"]
    if not (attempt / "attempt-manifest.json").is_file():
        # The frozen Skill nests its output under the batch, unit and case
        # identifiers. Use extended paths for preparation and expose a short
        # directory for the judge and the workspace collector.
        extended = "\\\\?\\"
        preparation = Path(extended + str(work / "attempts" / ".prepare"))
        prepared = list(preparation.rglob("attempt-manifest.json")) if preparation.exists() else []
        if not prepared:
            run("prepare", "--unit-root", "unit", "--execution-record", request["execution_record"],
                "--scoring-package", request["scoring_package"], "--task-id", request["task_id"],
                "--scoring-attempt-id", request["attempt"], "--output-root", preparation,
                "--judge-protocol", "codex-agent-judge-v1", "--judge-model", request["model"],
                "--judge-reasoning-effort", "none", "--judge-attempt-id", request["attempt"])
            prepared = list(preparation.rglob("attempt-manifest.json"))
        if len(prepared) != 1:
            raise ValueError("DESKTOP_SCORING_GENERAL_ATTEMPT_AMBIGUOUS")
        prepared[0].parent.rename(extended + str(attempt))
        shutil.rmtree(preparation)
    run("verify", "--attempt-root", attempt)
    contract = json.loads((attempt / "private/contract.json").read_text(encoding="utf-8"))
    if contract["grading_type"] != "automated":
        return False
    if not (attempt / "score.json").is_file():
        if not (attempt / "rule-component.json").is_file():
            run("run-rules", "--attempt-root", attempt, "--runtime-python", sys.executable)
        run("finalize", "--attempt-root", attempt)
    run("verify-score", "--attempt-root", attempt)
    shutil.make_archive(str(tooling / "rules-result"), "zip", root_dir=work, base_dir="attempts")
    return True


def install(work):
    tooling = work / "desktop-scoring-tooling"
    request = json.loads((tooling / "skill-lock.json").read_text(encoding="utf-8"))
    name = request["name"]
    if name not in {"score-general-e2e", "score-web-e2e"}:
        raise ValueError("DESKTOP_SCORING_SKILL_UNKNOWN")
    source = tooling / name
    if contents(source) != request["files"]:
        raise ValueError("DESKTOP_SCORING_SKILL_DRIFT")
    binary, data, user, home = astudio_paths()
    registered = home / "skills"
    if _reparse(registered):
        raise ValueError("DESKTOP_SCORING_UNSAFE_SKILL_PATH")
    target = registered / name
    # A new template can already contain the exact pinned release.
    if target.exists():
        if _reparse(target) or not target.is_dir() or contents(target) != request["files"]:
            raise ValueError("DESKTOP_SCORING_PREINSTALLED_SKILL_MISMATCH")
        disposition = "verified"
    else:
        quiescent(work)
        registered.mkdir(exist_ok=True)
        temporary = registered / (".desktop-scoring-" + name)
        if temporary.exists():
            if _reparse(temporary):
                raise ValueError("DESKTOP_SCORING_UNSAFE_SKILL_PATH")
            shutil.rmtree(temporary)
        shutil.copytree(source, temporary)
        temporary.rename(target)
        disposition = "installed"
    with runtime(binary, home, work, 45) as rpc:
        listing = rpc.call("skills/list", {"cwds": [str(work)], "forceReload": True})
    matches = [skill for group in listing.get("data", []) for skill in group.get("skills", [])
               if skill.get("name") == name and skill.get("enabled") is True]
    if not matches or any(Path(skill["path"]).resolve() != target / "SKILL.md" for skill in matches):
        raise ValueError("DESKTOP_SCORING_SKILL_NOT_ACTIVE")
    node = shutil.which("node")
    if request["scene"] == "web" and not node:
        raise ValueError("DESKTOP_SCORING_NODE_UNAVAILABLE")
    rules_only = request["scene"] == "general" and prepare_general(work, target, tooling, request)
    receipt = {"name": name, "version": request["version"], "inventory_sha256": request["inventory_sha256"],
               "skill_root": str(target), "python": sys.executable, "node": node, "status": disposition, "rules_only": rules_only}
    (tooling / "installation.json").write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    try:
        install(Path(sys.argv[1]).resolve(strict=True))
    except (OSError, ValueError, StepError, subprocess.SubprocessError) as error:
        code = str(error)
        print(json.dumps({"status": "failed",
                          "error": code if ERROR_CODE.fullmatch(code) else "DESKTOP_SCORING_SKILL_INSTALLATION_FAILED",
                          "exception": type(error).__name__, "winerror": getattr(error, "winerror", None),
                          **(error.diagnostics if isinstance(error, StepError) else {})}))
