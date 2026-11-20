"""Install the controller-selected Skill in the Windows scoring client's runtime."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from preprocess_windows_guest import astudio_paths, quiescent, runtime, _reparse


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
            raise ValueError("DESKTOP_SCORING_GENERAL_" + action.upper().replace("-", "_") + "_FAILED")

    attempts = list((work / "attempts").rglob("attempt-manifest.json"))
    if not attempts:
        run("prepare", "--unit-root", "unit", "--execution-record", request["execution_record"],
            "--scoring-package", request["scoring_package"], "--task-id", request["task_id"],
            "--scoring-attempt-id", request["attempt"], "--output-root", "attempts",
            "--judge-protocol", "codex-agent-judge-v1", "--judge-model", request["model"],
            "--judge-reasoning-effort", "none", "--judge-attempt-id", request["attempt"])
        attempts = list((work / "attempts").rglob("attempt-manifest.json"))
    if len(attempts) != 1:
        raise ValueError("DESKTOP_SCORING_GENERAL_ATTEMPT_AMBIGUOUS")
    attempt = attempts[0].parent
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
    install(Path(sys.argv[1]).resolve(strict=True))
