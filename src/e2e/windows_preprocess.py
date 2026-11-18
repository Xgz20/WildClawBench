"""Apply the frozen environment steps before handing a case to WGUI."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
import re
import shlex
import shutil
import tempfile
import time
import zipfile

from .agentcube import PlatformError
from .common import E2EError, atomic_json, digest, file_sha256, utc_now
from .preprocessing import EXE, MANIFEST, SHA, TRANSFER_TIMEOUT, checked_asset, inspect_asset


CHUNK_BYTES = 8 * 1024 * 1024
SIMPLE_ERROR = re.compile(r"[A-Z0-9_]{1,100}\Z")
WINDOWS_ROOT = PureWindowsPath(r"C:\ProgramData\WGUI\environment-preprocessing")
PYTHON = r"Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'"


def _asset(batch, asset):
    path = batch / "preprocess-assets" / asset["sha256"]
    checked_asset(path, asset)
    return path


def build_payload(batch, step, destination):
    asset = step["asset"]
    kind = step["kind"]
    path = _asset(batch, asset)
    metadata = inspect_asset(path, kind, asset["name"])
    recipe = {key: value for key, value in step.items() if key not in {"asset", "attachments"}}
    if kind == "powershell":
        destination.mkdir()
        (destination / "step.ps1").write_text(path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig", newline="")
        attachments = destination / "attachments"
        attachments.mkdir()
        for attachment in step["attachments"]:
            shutil.copyfile(_asset(batch, attachment), attachments / attachment["name"])
        return recipe
    if kind == "skill":
        if step["target"] not in metadata["skills"]:
            raise E2EError("PREPROCESS_SKILL_ASSET_TARGET_MISMATCH")
        prefix = metadata["skills"][step["target"]]
    elif kind == "plugin":
        if metadata["plugin"] != step["target"]:
            raise E2EError("PREPROCESS_PLUGIN_ASSET_TARGET_MISMATCH")
        recipe["version"] = metadata["version"]
        prefix = metadata["root"]
    else:
        prefix = ""
        recipe["version"] = metadata["version"]
    prefix = prefix + "/" if prefix else ""
    destination.mkdir()
    with zipfile.ZipFile(path) as archive:
        for row in archive.infolist():
            if row.is_dir() or not row.filename.startswith(prefix):
                continue
            relative = row.filename[len(prefix):]
            if kind == "acode" and relative not in {EXE, MANIFEST}:
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(row) as stream, target.open("xb") as output:
                shutil.copyfileobj(stream, output)
    return recipe


def _upload(driver, sid, step, job, remote, guest, wgui, encode):
    deadline = time.monotonic() + TRANSFER_TIMEOUT

    def remaining():
        available = deadline - time.monotonic()
        if available <= 0:
            raise E2EError("PREPROCESS_UPLOAD_TIMEOUT")
        return max(1, int(available))

    with tempfile.TemporaryDirectory(prefix="wcb-preprocessing-") as scratch:
        staging = Path(scratch)
        payload = staging / "payload"
        recipe = build_payload(driver.batch, step, payload)
        files = {path.relative_to(payload).as_posix(): file_sha256(path)
                 for path in sorted(payload.rglob("*")) if path.is_file()}
        packed = staging / "payload.zip"
        with zipfile.ZipFile(packed, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in sorted(files):
                archive.write(payload / path, path)
        contract = {"invocation": job["invocation"], "files": files, "step": recipe,
                    "package_sha256": file_sha256(packed)}
        driver.client.checked(sid, "mkdir -p " + shlex.quote(remote) + " && chmod 700 " + shlex.quote(remote),
                              timeout=min(30, remaining()))
        driver.client.upload(sid, remote + "/step.json", json.dumps(contract, ensure_ascii=False).encode(), timeout=remaining())
        worker = Path(__file__).with_name("preprocess_windows_guest.py")
        driver.client.upload(sid, remote + "/worker.py", worker.read_bytes(), timeout=remaining())
        with packed.open("rb") as input_file:
            index = 0
            while chunk := input_file.read(CHUNK_BYTES):
                driver.checkpoint()
                driver.client.upload(sid, f"{remote}/part-{index:05d}", chunk, timeout=remaining())
                index += 1
        driver._checked_job("preprocess-upload-" + str(job["index"]),
                            wgui + " workspace upload --source " + shlex.quote(remote)
                            + " --guest " + shlex.quote(str(guest)), timeout=remaining())
        # Remote upload bookkeeping is controller-owned and separate from user code.
        probe = (f"$d='{guest}';$py={PYTHON};if(!(Test-Path -LiteralPath $py -PathType Leaf))"
                 "{throw 'WINDOWS_PREPROCESS_PYTHON_UNAVAILABLE'};"
                 "if(!(Test-Path -LiteralPath (Join-Path $d 'worker.py') -PathType Leaf))"
                 "{throw 'WINDOWS_PREPROCESS_WORKER_UNAVAILABLE'}")
        driver.client.windows_execute(sid, encode(probe), timeout=min(30, remaining()))


def _elapsed(start):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(start)).total_seconds()


def _launch(driver, sid, guest, encode):
    script = (f"$d='{guest}';$py={PYTHON};$ErrorActionPreference='Stop';"
              "Start-Process -FilePath $py -ArgumentList ('-I ' + [char]34 + (Join-Path $d 'worker.py') + [char]34)"
              " -WorkingDirectory $d -WindowStyle Hidden | Out-Null")
    try:
        driver.client.windows_execute(sid, encode(script), timeout=30)
    except PlatformError as exc:
        if not exc.uncertain:
            raise E2EError("PREPROCESS_STEP_LAUNCH_FAILED") from exc
        # The remote process may already be running. Only observe the same claim.


def _receipt(driver, sid, guest, job, step):
    while _elapsed(job["started_at"]) <= step["timeout"] + 40:
        driver.checkpoint()
        try:
            value = driver.client.windows_download(sid, str(guest / "receipt.json"), timeout=10, max_bytes=8192)
        except (FileNotFoundError, PlatformError):
            driver.stop.wait(1)
            continue
        try:
            row = json.loads(value)
        except (ValueError, UnicodeError) as exc:
            raise E2EError("PREPROCESS_STEP_RECEIPT_INVALID") from exc
        if (len(value) > 8192 or not isinstance(row, dict) or row.get("invocation") != job["invocation"]
                or row.get("status") not in {"passed", "failed"}
                or type(row.get("duration_seconds")) not in {int, float}
                or not 0 <= row["duration_seconds"] <= step["timeout"] + 40):
            raise E2EError("PREPROCESS_STEP_RECEIPT_INVALID")
        result = {key: row[key] for key in ("status", "duration_seconds")}
        for key in ("before_sha256", "after_sha256"):
            if SHA.fullmatch(str(row.get(key))):
                result[key] = row[key]
        if isinstance(row.get("version"), str) and re.fullmatch(r"[A-Za-z0-9._-]{1,120}", row["version"]):
            result["version"] = row["version"]
        if type(row.get("exit_code")) is int:
            result["exit_code"] = row["exit_code"]
        if row["status"] == "failed":
            code = row.get("error")
            result["error"] = code if isinstance(code, str) and SIMPLE_ERROR.fullmatch(code) else "PREPROCESS_STEP_FAILED"
        elif step["kind"] != "powershell" and not {"before_sha256", "after_sha256"} <= result.keys():
            raise E2EError("PREPROCESS_STEP_RECEIPT_INVALID")
        elif step["kind"] == "powershell" and result.get("exit_code") != 0:
            raise E2EError("PREPROCESS_STEP_RECEIPT_INVALID")
        return result
    raise E2EError("PREPROCESS_STEP_RESULT_UNCONFIRMED")


def apply_recipe(driver, sid, recipe, wgui, encode, *, isolation_receipt=None):
    if recipe is None:
        return
    row = driver.store.get(driver.key)
    attempt = row["attempt_id"]
    identity = digest({"recipe": recipe, "session": sid, "attempt": attempt})
    state = row.get("preprocess_receipt") or {"recipe": {key: recipe[key] for key in ("version_id", "version")},
                                               "recipe_sha256": digest(recipe), "status": "running", "steps": []}
    if isolation_receipt:
        if state.get("isolation_receipt", isolation_receipt) != isolation_receipt:
            raise E2EError("PREPROCESS_SANDBOX_ADMISSION_DRIFT")
        state["isolation_receipt"] = isolation_receipt
    jobs = row.get("preprocess_jobs", {})
    if not row.get("preprocess_receipt"):
        driver._phase("PREPARING", preprocess_receipt=state)
    for index, step in enumerate(recipe["steps"]):
        key = str(index)
        invocation = digest({"identity": identity, "step": index})
        job = jobs.get(key)
        if job and job.get("invocation") != invocation:
            raise E2EError("PREPROCESS_STEP_INVOCATION_DRIFT")
        if index < len(state["steps"]):
            if state["steps"][index]["status"] != "passed":
                raise E2EError("PREPROCESS_STEP_PREVIOUSLY_FAILED")
            continue
        base = {"index": index, "kind": step["kind"], "asset_sha256": step["asset"]["sha256"]}
        guest = WINDOWS_ROOT / attempt / key
        remote = "/tmp/wcb-preprocess-" + attempt + "/" + key
        try:
            if job is None:
                job = {"invocation": invocation, "index": index}
                _upload(driver, sid, step, job, remote, guest, wgui, encode)
                job["started_at"] = utc_now()
                jobs[key] = job
                driver._phase("PREPARING", preprocess_jobs=jobs, preprocess_receipt=state)
                _launch(driver, sid, guest, encode)
            result = _receipt(driver, sid, guest, job, step)
        except (E2EError, OSError, ValueError, zipfile.BadZipFile) as exc:
            from .backend import ObservationPaused
            if isinstance(exc, ObservationPaused):
                raise
            code = str(exc)
            result = {"status": "failed", "error": code if SIMPLE_ERROR.fullmatch(code) else "PREPROCESS_STEP_TRANSPORT_FAILED"}
        state["steps"].append({**base, **result})
        state["status"] = "failed" if result["status"] != "passed" else "running"
        atomic_json(driver.staging / "metadata/preprocessing.json", state)
        driver._phase("PREPARING", preprocess_jobs=jobs, preprocess_receipt=state)
        if state["status"] == "failed":
            raise E2EError("PREPROCESS_STEP_FAILED: " + result["error"])
    state["status"] = "passed"
    atomic_json(driver.staging / "metadata/preprocessing.json", state)
    driver._phase("PREPARING", preprocess_jobs=jobs, preprocess_receipt=state)


def bind_running_acode(driver, sid, encode):
    row = driver.store.get(driver.key)
    state = row.get("preprocess_receipt")
    if not state:
        return
    steps = [step for step in state["steps"] if step["kind"] == "acode" and step["status"] == "passed"]
    if not steps:
        return
    expected = steps[-1]["after_sha256"]
    # The model was dispatched only after the compatibility probe. Bind the live
    # app-server process before the normal cleanup terminates this sandbox app.
    script = r"""
$ErrorActionPreference='Stop'
$bin=Join-Path $env:LOCALAPPDATA 'Programs\AStudio\resources\bin\acode-windows-x64.exe'
$rows=@(Get-CimInstance Win32_Process -Filter "Name='acode-windows-x64.exe'" |
  Where-Object {$_.ExecutablePath -ieq $bin -and $_.CommandLine -match '\bapp-server\b'})
if($rows.Count -ne 1){throw 'ASTUDIO_LIVE_ACODE_PROCESS_UNVERIFIED'}
$parent=Get-CimInstance Win32_Process -Filter ('ProcessId='+$rows[0].ParentProcessId)
if(!$parent -or !$parent.ExecutablePath -or
    !$parent.ExecutablePath.StartsWith((Join-Path $env:LOCALAPPDATA 'Programs\AStudio\'), [StringComparison]::OrdinalIgnoreCase)){
  throw 'ASTUDIO_LIVE_ACODE_PARENT_UNVERIFIED'
}
@{pid=[int]$rows[0].ProcessId;sha256=(Get-FileHash -LiteralPath $bin -Algorithm SHA256).Hash.ToLower()} | ConvertTo-Json -Compress
"""
    try:
        proof = json.loads(driver.client.windows_execute(sid, encode(script), timeout=45)["output"].strip())
    except (PlatformError, ValueError, KeyError) as exc:
        raise E2EError("ASTUDIO_LIVE_ACODE_IDENTITY_UNVERIFIED") from exc
    if not isinstance(proof, dict) or proof.get("sha256") != expected or type(proof.get("pid")) is not int:
        raise E2EError("ASTUDIO_LIVE_ACODE_IDENTITY_MISMATCH")
    state["observed_acode"] = {"sha256": expected, "pid": proof["pid"], "version": steps[-1]["version"]}
    atomic_json(driver.staging / "metadata/preprocessing.json", state)
    driver._phase("COLLECTING", preprocess_receipt=state)
