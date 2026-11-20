"""AStudio controller-v2 execution in one owned AgentCube sandbox."""
from __future__ import annotations

import base64
import gzip
import hashlib
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shlex
import time
import uuid
import zipfile

from .agentcube import AgentCubeClient, AgentCubeConfig, PlatformError
from .artifacts import _members, _protect, copy_stream_readonly, inventory, quarantine_local_metadata, remove_temporary_tree
from .common import E2EError, atomic_json, digest, file_sha256, identifier, inside, read_json, utc_now
from .trace import normalize_rollout, windows_equal
from . import preprocessing, windows_preprocess


WGUI = "/opt/wgui-venv/bin/python -m controller.cli.main"
GUEST_WORKSPACE = r"C:\ProgramData\WGUI\workspace\project"
NATIVE_ROOT = r"C:\Users\Docker\AppData\Local\Programs\AStudio Data\acode-home-overlay\sessions"


class ObservationPaused(E2EError):
    pass


def powershell(script: str) -> str:
    compressed = base64.b64encode(gzip.compress(script.encode("utf-8"), mtime=0)).decode()
    bootstrap = ("$m=[IO.MemoryStream]::new([Convert]::FromBase64String('" + compressed + "'));"
                 "$g=[IO.Compression.GZipStream]::new($m,[IO.Compression.CompressionMode]::Decompress);"
                 "$r=[IO.StreamReader]::new($g);&([ScriptBlock]::Create($r.ReadToEnd()))")
    return "powershell -NoProfile -NonInteractive -EncodedCommand " + base64.b64encode(bootstrap.encode("utf-16-le")).decode()


def _decode_output(result: dict):
    return json.loads(base64.b64decode(result["output"].strip(), validate=True).decode("utf-8-sig"))


def process_cleanup_script(proof_path: str, workspace: str, *, product="astudio") -> str:
    # A sandbox contains one evaluated GUI product. Every kill is tied to the
    # observed executable path, PID and CreationDate, with a workspace backstop.
    script = r"""
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';
$proofPath=__PROOF__;$workspace=__WORKSPACE__;
function Snap($p){@{pid=[int]$p.ProcessId;parent_pid=[int]$p.ParentProcessId;name=$p.Name;path=$p.ExecutablePath;created=$p.CreationDate.ToUniversalTime().ToString('o');command=$p.CommandLine}}
function Save($value){$text=ConvertTo-Json -InputObject $value -Depth 15 -Compress;[IO.File]::WriteAllText($proofPath,$text,[Text.UTF8Encoding]::new($false))}
if(Test-Path -LiteralPath $proofPath){
 $proof=Get-Content -LiteralPath $proofPath -Raw|ConvertFrom-Json;
 if($proof.schema -ne 'wildclawbench.agentcube-process-cleanup/v1' -or $proof.workspace -ne $workspace){throw 'CLEANUP_PROOF_IDENTITY_MISMATCH'};
 if($proof.phase -eq 'completed' -and $proof.success -and $proof.quiet_observed_milliseconds -ge 5000){
  [Console]::Out.Write([Convert]::ToBase64String([IO.File]::ReadAllBytes($proofPath)));return
 };
 if($proof.phase -notin @('started','completed')){throw 'CLEANUP_PROOF_PHASE_INVALID'};
 $additional=@($proof.additional_targets|Where-Object {$_});
 foreach($late in @($proof.after|Where-Object {$_.command -and $_.command.IndexOf($workspace,[StringComparison]::OrdinalIgnoreCase) -ge 0})){
  if(@($proof.before+$additional|Where-Object {$_.pid -eq $late.pid}).Count -eq 0){$additional+=@($late)}
 };
 $proof|Add-Member -NotePropertyName additional_targets -NotePropertyValue $additional -Force;
 $targets=@($proof.before)+$additional;$ids=[Collections.Generic.HashSet[int]]::new();foreach($p in $targets){[void]$ids.Add([int]$p.pid)};Save $proof;
}else{
$all=@(Get-CimInstance Win32_Process);
$apps=@($all|Where-Object {$_.Name -ieq 'AStudio.exe'});
$appIds=@($apps|ForEach-Object {[int]$_.ProcessId});
$roots=@($apps|Where-Object {$appIds -notcontains [int]$_.ParentProcessId});
if($roots.Count -gt 1){throw 'HARNESS_PROCESS_ROOT_AMBIGUOUS'};
$rootPid=$null;$disposition='already_exited';
$ids=[Collections.Generic.HashSet[int]]::new();
if($roots.Count -eq 1){
 if(-not $roots[0].ExecutablePath -or -not $roots[0].CreationDate){throw 'HARNESS_PROCESS_IDENTITY_UNAVAILABLE'};
 $rootPid=[int]$roots[0].ProcessId;[void]$ids.Add($rootPid);$disposition='stopped_owned_tree';
};
foreach($p in @($all|Where-Object {$_.CommandLine -and $_.CommandLine.IndexOf($workspace,[StringComparison]::OrdinalIgnoreCase) -ge 0})){
 if(-not $p.ExecutablePath -or -not $p.CreationDate){throw 'WORKSPACE_PROCESS_IDENTITY_UNAVAILABLE'};[void]$ids.Add([int]$p.ProcessId)
};
do{$added=$false;foreach($p in $all){if($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)){$added=$true}}}while($added);
$targets=@($all|Where-Object {$ids.Contains([int]$_.ProcessId)}|ForEach-Object {Snap $_});
$proof=[pscustomobject]@{schema='wildclawbench.agentcube-process-cleanup/v1';phase='started';supported=$true;success=$false;platform='win32';workspace=$workspace;root_pid=$rootPid;disposition=$disposition;before=$targets};
Save $proof;
};
foreach($p in ($targets|Sort-Object @{Expression={if($_.pid -eq $proof.root_pid){0}else{1}}})){
 $live=Get-CimInstance Win32_Process -Filter ('ProcessId='+$p.pid);
 for($retry=0;$live -and -not $live.ExecutablePath -and $retry -lt 20;$retry++){Start-Sleep -Milliseconds 100;$live=Get-CimInstance Win32_Process -Filter ('ProcessId='+$p.pid)};
 if($live){$current=Snap $live;if($current.created -ne $p.created -or $current.path -ne $p.path){throw 'PROCESS_IDENTITY_CHANGED'};Stop-Process -Id $p.pid -Force -ErrorAction Stop}
};
$watch=[Diagnostics.Stopwatch]::StartNew();$late=$false;$after=@();
while($watch.ElapsedMilliseconds -lt 5000){
 Start-Sleep -Milliseconds 250;
 $after=@(Get-CimInstance Win32_Process|Where-Object {
   $same=$false;foreach($old in $targets){if([int]$_.ProcessId -eq $old.pid -and $_.CreationDate.ToUniversalTime().ToString('o') -eq $old.created){$same=$true}};
   $same -or $ids.Contains([int]$_.ParentProcessId) -or
   ($_.Name -ieq 'AStudio.exe') -or
   ($_.ExecutablePath -and ($_.ExecutablePath -like '*\Programs\AStudio\*' -or $_.ExecutablePath -like '*\Programs\AStudio Data\*')) -or
   ($_.CommandLine -and $_.CommandLine.IndexOf($workspace,[StringComparison]::OrdinalIgnoreCase) -ge 0)
 }|ForEach-Object {Snap $_});
 if($after.Count -ne 0){$late=$true;break}
};
$proof.phase='completed';foreach($entry in @{after=$after;late_process_detected=$late;quiet_observed_milliseconds=$watch.ElapsedMilliseconds}.GetEnumerator()){$proof|Add-Member -NotePropertyName $entry.Key -NotePropertyValue $entry.Value -Force};$proof.success=(-not $late -and $after.Count -eq 0 -and $watch.ElapsedMilliseconds -ge 5000);Save $proof;
[Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $proof -Depth 15 -Compress))));
""".replace("__PROOF__", "'" + proof_path.replace("'", "''") + "'").replace(
        "__WORKSPACE__", "'" + workspace.replace("'", "''") + "'")
    if product == "workbuddy":
        script=script.replace('AStudio.exe','WorkBuddy.exe').replace('Programs\\AStudio\\','Programs\\WorkBuddy\\').replace('Programs\\AStudio Data\\','Programs\\WorkBuddy Data\\')
    elif product != "astudio": raise E2EError("UNSUPPORTED_PROCESS_CLEANUP_PRODUCT")
    return script



def validate_collect(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2 or not isinstance(manifest.get("files"), list):
        raise E2EError("COLLECT_MANIFEST_INVALID")
    expected = set()
    for row in manifest["files"]:
        path = inside(root, row["path"])
        if row["path"] in expected or path.is_symlink() or not path.is_file():
            raise E2EError("COLLECT_MEMBER_INVALID")
        expected.add(row["path"])
        if path.stat().st_size != row["size"] or file_sha256(path) != row["sha256"]:
            raise E2EError("COLLECT_MEMBER_DRIFT")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != expected | {"manifest.json"}:
        raise E2EError("COLLECT_MEMBER_SET_MISMATCH")
    return manifest


class AStudioSandboxDriver:
    product = "astudio"
    native_root = NATIVE_ROOT
    native_pattern = "rollout-*.jsonl"
    def __init__(self, *, batch_root: Path, store, item: dict, task: dict, unit: dict,
                 config: AgentCubeConfig, stop_event, client_factory=AgentCubeClient):
        self.batch = batch_root
        self.store, self.key, self.task, self.unit = store, item["key"], task, unit
        self.config = replace(
            config,
            template=unit["template"],
            namespace=unit.get("template_binding", {}).get("namespace", config.namespace),
            astudio_runtime=config.astudio_runtime if self.product == "astudio" else None,
        )
        self.client = client_factory(self.config)
        self.stop = stop_event
        self.root = inside(batch_root, item["execution_root"])
        self.staging = self.root / "staging"
        self.staging.mkdir(parents=True, exist_ok=True)
        self.preprocess_recipe = None

    def checkpoint(self):
        if self.stop.is_set():
            raise ObservationPaused("EXECUTION_OBSERVER_STOPPED")

    def preflight(self):
        if self.unit["model"].casefold().startswith(("custom/","third-party/")) or "://" in self.unit["model"]:
            raise E2EError("CUSTOM_TESTED_MODELS_NOT_SUPPORTED")
        if self.config.required_expire_ttl(self.unit["timeout_override"]) > self.config.expire_ttl:
            raise E2EError("PLATFORM_TTL_TOO_SHORT_FOR_TIMEOUT: increase expire_ttl in AgentCube configuration")
        if (self.batch / "batch.json").is_file():
            self.preprocess_recipe = preprocessing.frozen_recipe(self.batch, self.unit["unit_id"], self.task["task_id"])
        bound = {**self.unit, "preprocessing": {"default": self.preprocess_recipe, "overrides": {}}}
        if self.preprocess_recipe is not None and self.config.required_expire_ttl(
                self.unit["timeout_override"], preprocessing.budget(bound)) > self.config.expire_ttl:
            raise E2EError("PLATFORM_TTL_TOO_SHORT_FOR_TIMEOUT: increase expire_ttl in AgentCube configuration")
        for name, value in self.task.get("requirements", {}).items():
            if str(value).strip().casefold() not in {"", "none", "null", "n/a", "无", "{}", "[]"}:
                raise E2EError("TASK_RUNTIME_REQUIREMENT_NEEDS_ADAPTER: " + name)
        definition = inside(self.batch, self.task["input_root"])
        observed = inventory(definition)
        expected = self.task["definition_inventory"]
        observed = [row for row in observed if row["path"] != "task-definition.json"]
        if observed != expected:
            raise E2EError("FROZEN_TASK_INPUT_DRIFT")

    def _phase(self, phase: str, **fields):
        return self.store.update(self.key, phase, **fields)

    def _job(self, name: str, command: str, *, timeout=None) -> dict:
        self.checkpoint()
        row = self.store.get(self.key)
        jobs = row.get("jobs", {})
        job = jobs.get(name)
        if job:
            if job["command_sha256"] != digest(command):
                raise E2EError("REMOTE_JOB_COMMAND_DRIFT")
            if job.get("result") is not None:
                return job["result"]
            if job.get("submission") == "intent":
                try:
                    self.client.download(row["session_id"], job["remote_directory"] + "/pid")
                except FileNotFoundError as error:
                    raise PlatformError("REMOTE_JOB_SUBMISSION_UNCONFIRMED", uncertain=True) from error
        else:
            job_id = name + "-" + uuid.uuid4().hex
            job = {"job_id": job_id, "remote_directory": "/tmp/wcb-e2e-jobs/" + job_id,
                   "command_sha256": digest(command), "submission": "intent", "created_at": utc_now()}
            jobs[name] = job
            self._phase(row["phase"], jobs=jobs)
            if name == "task-run":
                self._phase("RUNNING", dispatch_armed_at=utc_now())
            self.client.submit_job(row["session_id"], job_id, command)
            job["submission"] = "confirmed"
            self._phase("RUNNING" if name == "task-run" else row["phase"], jobs=jobs)
        began = job.get("created_at") or (self.store.get(self.key).get("dispatch_armed_at") if name == "task-run" else None)
        remaining = timeout
        if timeout is not None and began:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(began)).total_seconds()
            remaining = max(0, timeout - max(0, elapsed))
        heartbeat = self.checkpoint
        if name == "task-run" and any(
                step["kind"] == "acode" and step["status"] == "passed"
                for step in row.get("preprocess_receipt", {}).get("steps", [])):
            def heartbeat():
                self.checkpoint()
                windows_preprocess.bind_running_acode(self, row["session_id"], powershell, required=False)
        result = self.client.await_job(row["session_id"], job, control_timeout=remaining, heartbeat=heartbeat)
        job["result"] = result
        self._phase(self.store.get(self.key)["phase"], jobs=jobs)
        if result["exit_code"] != 0:
            atomic_json(self.staging / "metadata" / (name + "-failure.json"), result)
        return result

    def _checked_job(self, name, command, timeout=300):
        result = self._job(name, command, timeout=timeout)
        if result["exit_code"] != 0:
            raise E2EError(f"CONTROLLER_{name.upper().replace('-', '_')}_FAILED: {result['stderr'][-1500:]}")
        return result

    def _health(self, sid):
        deadline = time.monotonic() + 1800
        last = None
        while time.monotonic() < deadline:
            self.checkpoint()
            try:
                output = self.client.checked(sid, WGUI + " vm health --timeout 10", timeout=25)
                health = json.loads(output)
                if health.get("status") == "healthy" and health.get("protocol_version") == "wgui.v2":
                    atomic_json(self.staging / "metadata/health.json", health)
                    return
                last = health
            except (PlatformError, ValueError) as error:
                last = str(error)
            self.stop.wait(5)
        raise E2EError("VM_HEALTH_INCOMPLETE: " + str(last))

    def _inventory_native(self, sid):
        script = ("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$rows=@();"
                  "if(Test-Path -LiteralPath '" + self.native_root + "'){$rows=@(Get-ChildItem -LiteralPath '"
                  + self.native_root + "' -Recurse -Filter '" + self.native_pattern + "' -File|Select-Object FullName,Length,"
                  "@{Name='Sha256';Expression={(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()}})};"
                  "$out=ConvertTo-Json -InputObject $rows -Compress;"
                  "[Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($out)))")
        rows = _decode_output(self.client.windows_execute(sid, powershell(script), timeout=120))
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise E2EError("NATIVE_INVENTORY_INVALID")
        return {row["FullName"]: row for row in rows}

    def _upload(self, sid):
        if self.unit.get("workbuddy_full_access") is False:
            raise E2EError("GENERAL_E2E_FULL_ACCESS_REQUIRED: sandbox unit requests default permissions")
        if self.product == "workbuddy" and "permission" not in getattr(self, "ui_fields", {"permission"}):
            raise E2EError("GENERAL_E2E_FULL_ACCESS_UNVERIFIABLE: controller permission field missing")
        self.client.checked(sid, "mkdir -p /run/wgui /workspace/input /logs/agent /logs/artifacts")
        self.client.windows_execute(sid, powershell("$ErrorActionPreference='Stop';New-Item -ItemType Directory -Force -Path '"
                                                    + GUEST_WORKSPACE + "'|Out-Null"))
        public = inside(self.batch, self.task["input_root"]) / "execution"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for path in sorted((public / "workspace").rglob("*")):
                target.write(path, path.relative_to(public / "workspace").as_posix())
        self.client.upload(sid, "/tmp/wcb-input.zip", archive.getvalue())
        unpack = "import zipfile,pathlib;pathlib.Path('/workspace/input').mkdir(parents=True,exist_ok=True);zipfile.ZipFile('/tmp/wcb-input.zip').extractall('/workspace/input')"
        self.client.checked(sid, "python3 -c " + shlex.quote(unpack), 120)
        self.client.upload(sid, "/run/wgui/instruction.txt", (public / "PROMPT.md").read_bytes())
        ui = {"permission": "full access"}
        if self.product=="astudio" and self.unit.get("reasoning_effort") is not None:
            ui["reasoning"] = {"none": "None", "high": "High", "max": "Max"}[self.unit["reasoning_effort"].casefold()]
        if self.product=="workbuddy":
            proposed={"mode":"代码开发","max_mode":self.unit.get("max_mode",False),"plan_mode":False,"ask_mode":False,
                      "permission":"full access"}
            ui={key:value for key,value in proposed.items() if key in getattr(self,"ui_fields",set(proposed))}
        request = {"schema_version": 2, "product": self.product, "instruction_file": "/run/wgui/instruction.txt",
                   "workspace": {"guest": GUEST_WORKSPACE}, "timeout_sec": self.unit["timeout_override"],
                   "product_config": {"model": self.unit["model"], "ui": ui}}
        collect = {"schema_version": 2, "workspace": {"guest": GUEST_WORKSPACE}}
        self.client.upload(sid, "/run/wgui/run-request.json", json.dumps(request).encode())
        self.client.upload(sid, "/run/wgui/collect-request.json", json.dumps(collect).encode())
        atomic_json(self.staging / "metadata/run-request.json", request)
        atomic_json(self.staging / "metadata/collect-request.json", collect)
        self._checked_job("workspace-upload", WGUI + " workspace upload --source /workspace/input --guest " + shlex.quote(GUEST_WORKSPACE))

    def _download_tree(self, sid, remote: str, name: str):
        target = self.staging / name
        transport = self.staging / "metadata" / (name + "-transport.json")
        if target.is_dir() and transport.exists():
            expected_files = set(read_json(transport)["files"])
            _protect(target)
            quarantine_local_metadata(target, expected_files,
                                      self.staging / "metadata/local-metadata" / (name + "-" + uuid.uuid4().hex))
            return target
        remote_zip = "/tmp/wcb-" + name + ".zip"
        script = ("import pathlib,zipfile;root=pathlib.Path(" + repr(remote) + ");"
                  "paths=list(root.rglob('*'));assert root.is_dir();assert not any(p.is_symlink() for p in paths);"
                  "z=zipfile.ZipFile(" + repr(remote_zip) + ",'w',zipfile.ZIP_DEFLATED,strict_timestamps=False);"
                  "[z.write(p,p.relative_to(root).as_posix()) for p in paths];z.close()")
        self._checked_job("archive-" + name + "-" + digest(script)[:10], "python3 -c " + shlex.quote(script), timeout=600)
        archive_path = self.staging / ("." + name + ".download.zip")
        self.client.download_to(sid, remote_zip, archive_path)
        temporary = target.with_name("." + name + ".extract-" + uuid.uuid4().hex)
        temporary.mkdir(parents=True)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                members = _members(archive)
                expected_files = {relative for relative, info in members.items() if not info.is_dir()}
                atomic_json(transport, {"schema": "wildclawbench.download-transport/v1", "source": remote,
                                        "archive_sha256": file_sha256(archive_path), "files": sorted(expected_files)})
                if target.is_dir():
                    _protect(target)
                    quarantine_local_metadata(target, expected_files,
                                              self.staging / "metadata/local-metadata" / (name + "-" + uuid.uuid4().hex))
                    return target
                for relative, info in members.items():
                    output = inside(temporary, relative)
                    if info.is_dir():
                        output.mkdir(parents=True, exist_ok=True)
                    else:
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info) as source:
                            copy_stream_readonly(source, output)
            _protect(temporary)
            quarantine_local_metadata(temporary, expected_files,
                                      self.staging / "metadata/local-metadata" / (name + "-" + uuid.uuid4().hex))
            temporary.rename(target)
        finally:
            archive_path.unlink(missing_ok=True)
            if temporary.exists():
                remove_temporary_tree(temporary)
        return target

    def _cleanup_processes(self, sid):
        path = self.staging / "metadata/process-cleanup.json"
        proof = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if not proof or proof.get("phase") != "completed" or proof.get("quiet_observed_milliseconds", 0) < 5000:
            row = self.store.get(self.key)
            proof_path = r"C:\Windows\Temp\wcb-cleanup-" + row["attempt_id"] + ".json"
            if not row.get("process_cleanup_intent"):
                self._phase("COLLECTING", process_cleanup_intent={"path": proof_path, "at": utc_now()})
            # The guest resumes the original target identities from its durable
            # proof and returns base64, preserving JSON bytes across the gateway.
            proof = _decode_output(self.client.windows_execute(sid, powershell(process_cleanup_script(proof_path, GUEST_WORKSPACE, product=self.product)), timeout=120))
            if proof.get("phase") == "completed":
                atomic_json(path, proof)
        if (proof.get("schema") != "wildclawbench.agentcube-process-cleanup/v1" or proof.get("phase") != "completed"
                or proof.get("success") is not True or proof.get("supported") is not True
                or proof.get("after") or proof.get("quiet_observed_milliseconds", 0) < 5000
                or not windows_equal(proof.get("workspace", ""), GUEST_WORKSPACE)):
            raise E2EError("REMOTE_PROCESS_CLEANUP_UNVERIFIED")
        return proof

    def _native_model(self):
        return self.unit["model"]

    def _bound_native(self, sid, before, report, identity, prompt, stage):
        after = self._inventory_native(sid)
        atomic_json(self.staging / "metadata" / ("native-" + stage + ".json"), after)
        changed = [path for path in after if before.get(path) != after[path]]
        native_dir = self.staging / "native" / stage
        native_dir.mkdir(parents=True, exist_ok=True)
        bound = []
        for path in changed:
            if not path.casefold().startswith(self.native_root.casefold() + "\\"):
                raise E2EError("NATIVE_PATH_OUTSIDE_ROOT")
            name = path.replace("\\", "/").rsplit("/", 1)[-1]
            identifier(name, "native_filename")
            data = self.client.windows_download(sid, path)
            if len(data) != after[path]["Length"] or hashlib.sha256(data).hexdigest() != after[path]["Sha256"]:
                raise E2EError("NATIVE_TRANSFER_MISMATCH")
            local = native_dir / name
            local.write_bytes(data)
            try:
                binding = normalize_rollout(local, identity=identity, prompt=prompt, guest_cwd=GUEST_WORKSPACE,
                                            requested_model=self._native_model(), requested_effort=self.unit.get("reasoning_effort"), report=report)
                bound.append((local, binding))
            except E2EError as error:
                atomic_json(self.staging / "metadata" / (stage + "-" + name + ".binding-error.json"), {"error": str(error)})
        if len(bound) != 1:
            raise E2EError("TASK_NATIVE_BINDING_AMBIGUOUS")
        if len(changed) != 1:
            raise E2EError("ADDITIONAL_NATIVE_ROLLOUTS_NEED_BINDING")
        return bound[0]

    def _prepare_runtime(self, sid):
        from .windows_runtime import prepare_runtime
        prepare_runtime(self,sid,WGUI,powershell)

    def execute(self) -> dict:
        self.preflight()
        row = self.store.get(self.key)
        runtime = self.config.public()
        if row.get("runtime") and row["runtime"] != runtime:
            raise E2EError("EXECUTION_RUNTIME_CONFIGURATION_DRIFT")
        sid = row.get("session_id")
        if sid is None:
            if row["phase"] not in {"PENDING", "RESERVED"}:
                raise PlatformError("SESSION_CREATION_UNRESOLVED", uncertain=True)
            self._phase("CREATING", resource_held=True, runtime=runtime, creation_intent_at=utc_now())
            sid = self.client.create_session()
            self._phase("PREPARING", session_id=sid, created_at=utc_now())
        if not self.store.get(self.key).get("dispatch_armed_at"):
            self._health(sid)
            self._prepare_runtime(sid)
            windows_preprocess.apply_recipe(self, sid, self.preprocess_recipe, WGUI, powershell)
            self._upload(sid)
            windows_preprocess.verify_remote_plugins(self, sid, self.preprocess_recipe, powershell)
            before = self._inventory_native(sid)
            atomic_json(self.staging / "metadata/native-before.json", before)
            self._phase("PREPARING", native_before=before)
        self._phase("RUNNING")
        result = self._job("task-run", WGUI + " task run --request /run/wgui/run-request.json --output /logs/artifacts/run",
                           timeout=self.unit["timeout_override"] + 1800)
        atomic_json(self.staging / "metadata/task-run-process.json", result)
        report_bytes = self.client.download(sid, "/logs/artifacts/run/report.json")
        (self.staging / "metadata/report.json").write_bytes(report_bytes)
        report = json.loads(report_bytes)
        if report.get("schema_version") != 2:
            raise E2EError("RUN_REPORT_SCHEMA_UNSUPPORTED")
        self._phase("COLLECTING", report=report, observed_terminal_at=utc_now())
        if result["exit_code"] != 0 or report.get("status") != "completed":
            raise E2EError("CONTROLLER_EXECUTION_INCOMPLETE: " + str(report.get("status")))
        windows_preprocess.verify_remote_plugins(self, sid, self.preprocess_recipe, powershell)
        self._download_tree(sid, "/logs/artifacts/run", "run")
        identity = {"batch_id": self.batch.name + f"-r{row['run_index']:04d}", "unit_id": row["unit_id"], "task_id": row["task_id"],
                    "attempt_id": row["attempt_id"]}
        prompt = (inside(self.batch, self.task["input_root"]) / "execution/PROMPT.md").read_text(encoding="utf-8")
        before = self.store.get(self.key).get("native_before", {})
        before_close, before_binding = self._bound_native(sid, before, report, identity, prompt, "before-cleanup")
        if self.preprocess_recipe:
            windows_preprocess.bind_running_acode(self, sid, powershell)
        cleanup = self._cleanup_processes(sid)
        self._checked_job("task-collect", WGUI + " task collect --request /run/wgui/collect-request.json --output /logs/artifacts/collect", timeout=600)
        collected = self._download_tree(sid, "/logs/artifacts/collect", "collect")
        validate_collect(collected)
        native_path, binding = self._bound_native(sid, before, report, identity, prompt, "after-cleanup")
        if (before_binding["session"] != binding["session"]
                or not native_path.read_bytes().startswith(before_close.read_bytes())):
            raise E2EError("NATIVE_CHANGED_DURING_CLEANUP")
        atomic_json(self.staging / "metadata/native-binding.json", {key: value for key, value in binding.items() if key != "events"})
        atomic_json(self.staging / "metadata/controller-runtime.json", {"config": runtime, "guest_workspace": GUEST_WORKSPACE,
                                                                      "session_id": sid, "process_cleanup": cleanup})
        if binding["missing"]:
            raise E2EError("NATIVE_TRACE_INCOMPLETE: " + ",".join(binding["missing"]))
        return {"identity": identity, "report": report, "binding": binding, "native_path": str(native_path.relative_to(self.staging)),
                "workspace": "collect/workspace", "cleanup": cleanup}

    def salvage(self):
        row = self.store.get(self.key)
        sid = row.get("session_id")
        if not sid:
            return {"complete": True, "coverage": "no_session_created"}
        results = {}
        quiesced = bool(row.get("dispatch_armed_at"))
        if quiesced:
            # A controller timeout can leave the GUI agent writing its rollout
            # and workspace. Stop the owned tree before taking failure evidence.
            # Use a distinct collection job/directory so an earlier live snapshot
            # remains available and is never mistaken for this terminal snapshot.
            try:
                self._cleanup_processes(sid)
                results["process_cleanup"] = True
            except Exception as error:
                atomic_json(self.staging / "metadata/failure-cleanup-error.json", {"error": str(error)})
                return {"complete": False, "components": {"process_cleanup": False}, "captured_at": utc_now()}
        try:
            observed = self._inventory_native(sid)
            before = row.get("native_before", {})
            raw = self.staging / ("native/failure-quiesced" if quiesced else "native/failure")
            raw.mkdir(parents=True, exist_ok=True)
            for path, info in observed.items():
                if before.get(path) == info:
                    continue
                if not path.casefold().startswith(self.native_root.casefold() + "\\"):
                    raise E2EError("NATIVE_PATH_OUTSIDE_ROOT")
                name = identifier(path.replace("\\", "/").rsplit("/", 1)[-1], "native_filename")
                data = self.client.windows_download(sid, path)
                if len(data) != info["Length"] or hashlib.sha256(data).hexdigest() != info["Sha256"]:
                    raise E2EError("NATIVE_TRANSFER_MISMATCH")
                (raw / name).write_bytes(data)
            observation = "failure-quiesced-native-observation.json" if quiesced else "failure-native-observation.json"
            atomic_json(self.staging / "metadata" / observation, {
                "coverage": "partial_unverified_terminal", "session_id": sid, "files": observed, "captured_at": utc_now()})
            results["native"] = True
        except Exception as error:
            results["native"] = False
            atomic_json(self.staging / "metadata/native-salvage-error.json", {"error": str(error)})
        try:
            collect_name = "failure-quiesced-collect" if quiesced else "collect"
            job_name = "failure-quiesced-task-collect" if quiesced else "failure-task-collect"
            self._checked_job(job_name, WGUI + " task collect --request /run/wgui/collect-request.json --output /logs/artifacts/" + collect_name, timeout=600)
            results["collect_command"] = True
        except Exception as error:
            results["collect_command"] = False
            atomic_json(self.staging / "metadata/collect-salvage-error.json", {"error": str(error)})
        for remote, name in (("/logs/artifacts/run", "run"), ("/logs/artifacts/" + collect_name, collect_name)):
            component = "collect" if name == collect_name else name
            try:
                self._download_tree(sid, remote, name)
                if component == "collect":
                    validate_collect(self.staging / name)
                results[component] = True
            except Exception as error:
                results[component] = False
                atomic_json(self.staging / "metadata" / (name + "-salvage-error.json"), {"error": str(error)})
        result = {"complete": all(results.values()), "components": results, "captured_at": utc_now()}
        atomic_json(self.staging / "metadata/failure-salvage.json", result)
        return result


DRIVERS = {("agentcube", "astronstudio"): AStudioSandboxDriver}


class WorkBuddySandboxDriver(AStudioSandboxDriver):
    product='workbuddy'
    native_root=r'C:\Users\Docker\.workbuddy\projects'
    native_pattern='*.jsonl'

    def _prepare_runtime(self,sid):
        # Inspect the installed controller contract before dispatch, without sending a prompt.
        script = """import ast, importlib.util, json, pathlib, typing
from controller.contracts.models import ProductUIConfig, RunRequestV2

def loads_permission(node):
    return any(
        (isinstance(part, ast.Attribute) and part.attr in {'permission', '_permission'})
        or (isinstance(part, ast.Constant) and part.value == 'permission')
        for part in ast.walk(node)
    )

permission_forwarded = False
spec = importlib.util.find_spec('guest.products.workbuddy.ui_driver')
if spec is not None and spec.origin:
    tree = ast.parse(pathlib.Path(spec.origin).read_text(encoding='utf-8'))
    for klass in tree.body:
        if not isinstance(klass, ast.ClassDef) or klass.name != 'WorkBuddyUiDriver':
            continue
        methods = {node.name: node for node in klass.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        configure = methods.get('configure')
        run = methods.get('_do_automation')
        if configure and run and loads_permission(configure):
            permission_forwarded = any(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'run'
                and any(keyword.arg == 'permission' and loads_permission(keyword.value) for keyword in node.keywords)
                for node in ast.walk(run)
            )
print(json.dumps({
    'ui_fields': list(ProductUIConfig.model_fields),
    'products': list(typing.get_args(RunRequestV2.model_fields['product'].annotation)),
    'workbuddy_permission_forwarded': permission_forwarded,
}))"""
        value=json.loads(self.client.checked(sid,"/opt/wgui-venv/bin/python -c "+shlex.quote(script),timeout=30))
        atomic_json(self.staging/"metadata/controller-capabilities.json",value)
        if 'workbuddy' not in value.get('products',[]):raise E2EError('DEPLOYED_CONTROLLER_WORKBUDDY_UNSUPPORTED')
        self.ui_fields=set(value.get('ui_fields',[]))
        if self.unit.get('max_mode') and 'max_mode' not in self.ui_fields:raise E2EError('DEPLOYED_CONTROLLER_MAX_MODE_UNSUPPORTED')
        if self.unit.get("workbuddy_full_access") is False:
            raise E2EError("GENERAL_E2E_FULL_ACCESS_REQUIRED: sandbox unit requests default permissions")
        if "permission" not in self.ui_fields or not value.get("workbuddy_permission_forwarded"):
            raise E2EError("WORKBUDDY_PERMISSION_NOT_SUPPORTED: 正式评测要求控制器显式传递并核验完全访问")

    def _bound_native(self,sid,before,report,identity,prompt,stage):
        from .workbuddy_trace import normalize_workbuddy
        after=self._inventory_native(sid)
        atomic_json(self.staging/'metadata'/('native-'+stage+'.json'),after)
        changed=[path for path in after if before.get(path)!=after[path]]
        native_dir=self.staging/'native'/stage;native_dir.mkdir(parents=True,exist_ok=True)
        product_path='/logs/agent/native-trajectory/workbuddy-trajectory/report.json'
        product=json.loads(self.client.download(sid,product_path))
        # The WGUI guest retains model/Max/workspace observations under its artifact root.
        diagnostics=self._read_workbuddy_diagnostics(sid)
        atomic_json(self.staging/'metadata/workbuddy-product-report.json',product)
        atomic_json(self.staging/'metadata/workbuddy-diagnostics.json',diagnostics)
        bound=[]
        for path in changed:
            if not path.casefold().startswith(self.native_root.casefold()+'\\'):raise E2EError('NATIVE_PATH_OUTSIDE_ROOT')
            data=self.client.windows_download(sid,path)
            if len(data)!=after[path]['Length'] or hashlib.sha256(data).hexdigest()!=after[path]['Sha256']:raise E2EError('NATIVE_TRANSFER_MISMATCH')
            name=path.replace('\\','/').rsplit('/',1)[-1];identifier(name,'native_filename');local=native_dir/name;local.write_bytes(data)
            try:
                binding=normalize_workbuddy(local,identity=identity,prompt=prompt,guest_cwd=GUEST_WORKSPACE,requested_model=self.unit['model'],requested_max_mode=self.unit.get('max_mode',False),report=report,product_report=product,diagnostics=diagnostics)
                bound.append((local,binding))
            except E2EError as error:atomic_json(self.staging/'metadata'/(stage+'-'+name+'.binding-error.json'),{'error':str(error)})
        if len(bound)!=1:raise E2EError('TASK_NATIVE_BINDING_AMBIGUOUS')
        if len(changed)!=1:raise E2EError('WORKBUDDY_ADDITIONAL_NATIVE_SESSIONS_NEED_BINDING')
        return bound[0]

    def _read_workbuddy_diagnostics(self,sid):
        output=self.client.windows_download(sid,r'C:\ProgramData\WGUI\staging\diagnostics.json')
        diagnostics = json.loads(output.decode("utf-8-sig"))
        # The Windows file proxy wraps JSON files in its API response on some deployments.
        if isinstance(diagnostics, dict) and {"code", "msg", "data"} <= diagnostics.keys():
            if type(diagnostics["code"]) is not int or diagnostics["code"] != 0:
                raise E2EError("WORKBUDDY_DIAGNOSTICS_DOWNLOAD_REJECTED")
            diagnostics = diagnostics["data"]
        if not isinstance(diagnostics, dict):
            raise E2EError("WORKBUDDY_DIAGNOSTICS_INVALID")
        return diagnostics


DRIVERS[('agentcube','workbuddy')]=WorkBuddySandboxDriver
