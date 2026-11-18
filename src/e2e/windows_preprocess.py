"""Apply the frozen environment steps before handing a case to WGUI."""
from __future__ import annotations

import base64
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
# WGUI's workspace command limits the total size of each source directory.
CHUNKS_PER_UPLOAD = 4
SIMPLE_ERROR = re.compile(r"[A-Z0-9_]{1,100}\Z")
WINDOWS_ROOT = PureWindowsPath(r"C:\ProgramData\WGUI\environment-preprocessing")
PYTHON = r"Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'"


def diagnostic_code(error, default):
    # Only stable identifiers are safe to project. Provider bodies can contain
    # arbitrary guest text, paths or credentials.
    code = str(error).partition(":")[0]
    return code if SIMPLE_ERROR.fullmatch(code) else default


def public_diagnostics(value):
    if not isinstance(value, dict):
        return {}
    data = {key: value[key] for key in ("line", "winerror", "rpc_code")
            if type(value.get(key)) is int and abs(value[key]) <= 2 ** 31}
    for key in ("category", "exception", "error_id"):
        field = value.get(key)
        if isinstance(field, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", field):
            data[key] = field
    return data


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
        # Windows kernels can be hundreds of MiB uncompressed. Keep the
        # chunked transfer within the step budget without changing file hashes.
        with zipfile.ZipFile(packed, "w") as archive:
            for path in sorted(files):
                # A resumed upload can reuse earlier WGUI jobs. Keep the same
                # archive bytes even when files were extracted at a new time.
                entry = zipfile.ZipInfo(path)
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.file_size = (payload / path).stat().st_size
                with (payload / path).open("rb") as source, archive.open(entry, "w") as target:
                    shutil.copyfileobj(source, target)
        contract = {"invocation": job["invocation"], "files": files, "step": recipe,
                    "package_sha256": file_sha256(packed)}

        def prepare(source):
            quoted = shlex.quote(source)
            driver.client.checked(sid, "mkdir -p " + quoted + " && chmod 700 " + quoted,
                                  timeout=min(30, remaining()))

        def upload_workspace(label, source, destination):
            driver._checked_job(f"preprocess-upload-{job['index']}-{label}",
                                wgui + " workspace upload --source " + shlex.quote(source)
                                + " --guest " + shlex.quote(str(destination)), timeout=remaining())

        control = remote + "/control"
        prepare(control)
        driver.client.upload(sid, control + "/step.json", json.dumps(contract, ensure_ascii=False).encode(),
                             timeout=remaining())
        worker = Path(__file__).with_name("preprocess_windows_guest.py")
        driver.client.upload(sid, control + "/worker.py", worker.read_bytes(), timeout=remaining())
        upload_workspace("control", control, guest)
        with packed.open("rb") as input_file:
            chunk = input_file.read(CHUNK_BYTES)
            index = 0
            while chunk:
                label = f"parts-{index // CHUNKS_PER_UPLOAD:05d}"
                source = remote + "/" + label
                prepare(source)
                for _ in range(CHUNKS_PER_UPLOAD):
                    driver.checkpoint()
                    driver.client.upload(sid, f"{source}/part-{index:05d}", chunk, timeout=remaining())
                    index += 1
                    chunk = input_file.read(CHUNK_BYTES)
                    if not chunk:
                        break
                upload_workspace(label, source, guest / label)
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


def _receipt(driver, sid, guest, job, step, encode):
    # The Windows file route can return a gateway response while the worker is
    # starting. Probe the exact receipt path inside the owned session instead.
    path = str(guest / "receipt.json").replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$p='{path}';"
        "if(!(Test-Path -LiteralPath $p -PathType Leaf)){[Console]::Write('pending');return};"
        "$f=[IO.File]::OpenRead($p);"
        "try{if($f.Length -gt 8192){[Console]::Write('oversize');return};"
        "$r=[IO.BinaryReader]::new($f);$data=$r.ReadBytes(8193);"
        "if($data.Length -gt 8192){[Console]::Write('oversize');return};"
        "[Console]::Write('receipt:'+ [Convert]::ToBase64String($data))}finally{$f.Dispose()}"
    )
    while _elapsed(job["started_at"]) <= step["timeout"] + 40:
        driver.checkpoint()
        try:
            response = driver.client.windows_execute(sid, encode(script), timeout=10)
        except PlatformError:
            driver.stop.wait(1)
            continue
        output = response.get("output")
        if isinstance(output, str) and output.strip() == "pending":
            driver.stop.wait(1)
            continue
        if not isinstance(output, str) or not output.strip().startswith("receipt:") or len(output) > 11000:
            raise E2EError("PREPROCESS_STEP_RECEIPT_INVALID")
        try:
            value = base64.b64decode(output.strip().removeprefix("receipt:"), validate=True)
            row = json.loads(value)
        except ValueError as exc:
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
            details = public_diagnostics(row.get("diagnostics"))
            if details:
                result["diagnostics"] = details
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
        stage = "receipt" if job else "upload"
        try:
            if job is None:
                state["current"] = {**base, "stage": stage}
                driver._phase("PREPARING", preprocess_receipt=state)
                job = {"invocation": invocation, "index": index}
                _upload(driver, sid, step, job, remote, guest, wgui, encode)
                stage = "launch"
                job["started_at"] = utc_now()
                jobs[key] = job
                state["current"] = {**base, "stage": stage}
                driver._phase("PREPARING", preprocess_jobs=jobs, preprocess_receipt=state)
                _launch(driver, sid, guest, encode)
            stage = "receipt"
            state["current"] = {**base, "stage": stage}
            driver._phase("PREPARING", preprocess_receipt=state)
            result = _receipt(driver, sid, guest, job, step, encode)
            stage = "verify"
        except (E2EError, OSError, ValueError, zipfile.BadZipFile) as exc:
            from .backend import ObservationPaused
            if isinstance(exc, ObservationPaused):
                raise
            result = {"status": "failed", "error": diagnostic_code(exc, "PREPROCESS_STEP_TRANSPORT_FAILED")}
        state.pop("current", None)
        state["steps"].append({**base, "stage": stage, **result})
        state["status"] = "failed" if result["status"] != "passed" else "running"
        atomic_json(driver.staging / "metadata/preprocessing.json", state)
        driver._phase("PREPARING", preprocess_jobs=jobs, preprocess_receipt=state)
        if state["status"] == "failed":
            raise E2EError("PREPROCESS_STEP_FAILED: " + result["error"])
    state["status"] = "passed"
    atomic_json(driver.staging / "metadata/preprocessing.json", state)
    driver._phase("PREPARING", preprocess_jobs=jobs, preprocess_receipt=state)


def bind_running_acode(driver, sid, encode, *, required=True):
    row = driver.store.get(driver.key)
    state = row.get("preprocess_receipt")
    if not state:
        return
    steps = [step for step in state["steps"] if step["kind"] == "acode" and step["status"] == "passed"]
    if not steps:
        return
    expected = steps[-1]["after_sha256"]
    dispatch = row.get("dispatch_armed_at")
    existing = state.get("observed_acode", {})
    if existing.get("sha256") == expected and existing.get("session_id") == sid and existing.get("dispatch_armed_at") == dispatch:
        return existing
    # Capture while task-run is active. The controller can close the subprocess
    # before returning its completed report.
    script = r"""
$ErrorActionPreference='Stop'
$app=Join-Path $env:LOCALAPPDATA 'Programs\AStudio\AStudio.exe'
$bin=Join-Path $env:LOCALAPPDATA 'Programs\AStudio\resources\bin\acode-windows-x64.exe'
$all=@(Get-CimInstance Win32_Process)
$byId=@{}
foreach($process in $all){$byId[[int]$process.ProcessId]=$process}
$owned=@(foreach($candidate in $all){
    if($candidate.ExecutablePath -ine $bin -or $candidate.CommandLine -notmatch '\bapp-server\b'){continue}
    $child=$candidate
    for($depth=0;$depth -lt 8;$depth++){
      $parent=$byId[[int]$child.ParentProcessId]
      if(!$parent -or !$parent.CreationDate -or !$child.CreationDate -or $parent.CreationDate -gt $child.CreationDate){break}
      if($parent.ExecutablePath -ieq $app){$candidate;break}
      $child=$parent
    }
})
if($owned.Count -ne 1){
    [Console]::Write('pending')
    return
}
@{pid=[int]$owned[0].ProcessId;sha256=(Get-FileHash -LiteralPath $bin -Algorithm SHA256).Hash.ToLower()} | ConvertTo-Json -Compress
"""
    try:
        output = driver.client.windows_execute(sid, encode(script), timeout=8)["output"].strip()
        proof = json.loads(output) if output != "pending" else None
    except (PlatformError, ValueError, KeyError) as exc:
        if not required:
            return
        raise E2EError("ASTUDIO_LIVE_ACODE_IDENTITY_UNVERIFIED") from exc
    if proof is None:
        if not required:
            return
        raise E2EError("ASTUDIO_LIVE_ACODE_IDENTITY_UNVERIFIED")
    if not isinstance(proof, dict) or proof.get("sha256") != expected or type(proof.get("pid")) is not int:
        raise E2EError("ASTUDIO_LIVE_ACODE_IDENTITY_MISMATCH")
    state["observed_acode"] = {"sha256": expected, "pid": proof["pid"], "version": steps[-1]["version"],
                               "session_id": sid, "dispatch_armed_at": dispatch}
    atomic_json(driver.staging / "metadata/preprocessing.json", state)
    driver._phase(row["phase"], preprocess_receipt=state)
    return state["observed_acode"]
