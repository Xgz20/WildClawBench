"""Prepare an explicitly pinned Windows AStudio runtime before candidate dispatch."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import time
from urllib.parse import urlsplit

from .agentcube import PlatformError
from .common import E2EError, atomic_json, digest, utc_now

GUEST = r"C:\ProgramData\WGUI\runtime-bootstrap"
DATA = r"C:\Users\Docker\AppData\Local\Programs\AStudio Data"


def validate_runtime(spec):
    if not isinstance(spec, dict) or set(spec) - {"version", "download_url", "size", "sha512", "session_file", "sync_clock"}:
        raise E2EError("ASTUDIO_RUNTIME_CONFIG_INVALID")
    url = urlsplit(str(spec.get("download_url", "")))
    if (not re.fullmatch(r"\d+\.\d+\.\d+", str(spec.get("version", "")))
            or url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment
            or not re.fullmatch(r"[0-9a-fA-F]{128}", str(spec.get("sha512", "")))
            or type(spec.get("size")) is not int or spec["size"] <= 0
            or type(spec.get("sync_clock", True)) is not bool):
        raise E2EError("ASTUDIO_RUNTIME_CONFIG_INVALID")
    if spec.get("session_file"):
        read_session(Path(spec["session_file"]).expanduser())


def read_session(path):
    if not path.is_file() or (os.name != "nt" and path.stat().st_mode & 0o077):
        raise E2EError("ASTRON_SESSION_FILE_MUST_BE_PRIVATE")
    raw = path.read_bytes()
    try:
        session = json.loads(raw)
        valid = isinstance(session, dict) and all(isinstance(session.get(k), str) and session[k].strip()
                                                 for k in ("uid", "token", "modelBearerToken"))
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise E2EError("ASTRON_SESSION_FILE_INVALID")
    return raw


def installer_script(spec, identity=None, model="auto"):
    # 安装和登录只修改运行环境，脚本与私有备份均位于候选 Workspace 之外。
    values = {"VERSION": spec["version"], "URL": spec["download_url"], "SIZE": str(spec["size"]),
              "SHA": spec["sha512"].lower(), "GUEST": GUEST, "DATA": DATA,
              "IDENTITY": identity or digest(spec), "MODEL": model,
              "RESTORE_SESSION": "$true" if spec.get("session_file") else "$false"}
    script = r'''$ErrorActionPreference='Stop'
$dir='__GUEST__';$data='__DATA__';$exe='C:\Users\Docker\AppData\Local\Programs\AStudio\AStudio.exe';$restoreSession=__RESTORE_SESSION__
function State($stage,$details){@{stage=$stage;details=$details;identity='__IDENTITY__';version='__VERSION__';utc=(Get-Date).ToUniversalTime().ToString('o')}|ConvertTo-Json -Depth 5 -Compress|Set-Content -Encoding UTF8 "$dir\status.json"}
function Version(){
 $f=[IO.File]::OpenRead('C:\Users\Docker\AppData\Local\Programs\AStudio\resources\app.asar');$r=New-Object IO.BinaryReader($f)
 try{$null=$r.ReadUInt32();$h=$r.ReadUInt32();$null=$r.ReadUInt32();$n=$r.ReadUInt32();$tree=([Text.Encoding]::UTF8.GetString($r.ReadBytes($n)))|ConvertFrom-Json;$entry=$tree.files.'package.json';$f.Position=8+$h+[long]$entry.offset;return (([Text.Encoding]::UTF8.GetString($r.ReadBytes($entry.size)))|ConvertFrom-Json).version}finally{$r.Close();$f.Close()}
}
try{
 $before=Version
 if($before -ne '__VERSION__' -or (Test-Path "$dir\session.json") -or (Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -eq $exe})){
  $apps=@(Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -eq $exe})
  State 'quiescing' @{pids=@($apps.ProcessId)}
  if($apps.Count){$p=Start-Process $exe -ArgumentList '--shutdown-for-uninstall' -PassThru -Wait;for($i=0;$i -lt 30;$i++){if(!(Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -eq $exe})){break};Start-Sleep -Seconds 1}}
  if(Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -eq $exe}){throw 'ASTUDIO_RUNTIME_STILL_ACTIVE'}
 }
 if($before -ne '__VERSION__'){
  State 'downloading' @{before=$before}
  $file="$dir\installer.exe";[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
  (New-Object Net.WebClient).DownloadFile('__URL__',"$file.part")
  if((Get-Item "$file.part").Length -ne __SIZE__ -or (Get-FileHash -Algorithm SHA512 "$file.part").Hash.ToLower() -ne '__SHA__'){throw 'ASTUDIO_INSTALLER_DIGEST_MISMATCH'}
  Move-Item "$file.part" $file -Force
  $backup="$dir\backup-before-install";New-Item -ItemType Directory -Force $backup|Out-Null
  Copy-Item "$data\userdata" "$backup\userdata" -Recurse
  $who=[Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls $backup /inheritance:r /grant:r "$($who):(OI)(CI)F" 'SYSTEM:(OI)(CI)F'|Out-Null
  State 'installing' @{before=$before}
  $p=Start-Process $file -ArgumentList '/S','--updated','/KEEP_APP_DATA' -PassThru -Wait
  if($p.ExitCode -ne 0){throw "ASTUDIO_INSTALLER_EXIT_$($p.ExitCode)"}
 }
 $after=Version
 if($after -ne '__VERSION__'){throw 'ASTUDIO_INSTALLED_VERSION_MISMATCH'}
 if($restoreSession){
  if(!(Test-Path "$dir\session.json")){throw 'ASTRON_REQUESTED_SESSION_FILE_MISSING'}
  if(Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -eq $exe}){throw 'ASTUDIO_AUTH_RESTORE_REQUIRES_IDLE_APP'}
  $s=Get-Content -Raw -Encoding UTF8 "$dir\session.json"|ConvertFrom-Json
  if(!$s.uid -or !$s.token -or !$s.modelBearerToken){throw 'ASTRON_SESSION_INVALID'}
  if(Test-Path "$data\userdata\astron-session.json"){Copy-Item "$data\userdata\astron-session.json" "$dir\previous-session.json" -Force}
  Copy-Item "$dir\session.json" "$data\userdata\astron-session.json" -Force
  $who=[Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls "$data\userdata\astron-session.json" /inheritance:r /grant:r "$($who):F" 'SYSTEM:F'|Out-Null
  Remove-Item "$dir\session.json"
 }elseif(Test-Path "$dir\session.json"){
  # 没有显式请求账号覆盖时，旧暂存文件不得改变模板账号。
  Remove-Item "$dir\session.json" -Force
 }
 if(Test-Path "$data\userdata\provider-model-catalog-v1.json"){Move-Item "$data\userdata\provider-model-catalog-v1.json" "$dir\previous-provider-model-catalog.json" -Force}
 State 'warming-model-catalog' @{model='__MODEL__'}
 $started=[DateTimeOffset]::UtcNow
 if(!(Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -eq $exe})){Start-Process $exe|Out-Null}
 $session=Get-Content -Raw -Encoding UTF8 "$data\userdata\astron-session.json"|ConvertFrom-Json
 $sha=[Security.Cryptography.SHA256]::Create()
 $scopes=@();foreach($namespace in @('AStudio','AstronStudio')){$key=$namespace+':provider-model-catalog:v1:account'+[char]0+$session.accountId;$scopes+=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($key)))).Replace('-','').ToLower()}
 $matched=$false;$catalog=$null
 for($i=0;$i -lt 180;$i++){
  try{
   $catalog=Get-Content -Raw -Encoding UTF8 "$data\userdata\provider-model-catalog-v1.json"|ConvertFrom-Json
   $models=@($catalog.models|Where-Object{$_.name -ieq '__MODEL__' -or $_.slug -ieq '__MODEL__'})
   $fresh=[DateTimeOffset]::Parse($catalog.fetchedAt) -ge $started.AddSeconds(-2)
   if($scopes -contains $catalog.accountScopeHash -and $fresh -and $models.Count -gt 0){$matched=$true;break}
  }catch{}
  Start-Sleep -Seconds 1
 }
 if(!$matched){throw 'ASTUDIO_MODEL_CATALOG_NOT_READY'}
 # 目录预热不能替控制器占有实例；持久化目录后退出本准备步骤启动的客户端。
 $p=Start-Process $exe -ArgumentList '--shutdown-for-uninstall' -PassThru -Wait
 for($i=0;$i -lt 30;$i++){if(!(Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -eq $exe})){break};Start-Sleep -Seconds 1}
 if(Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -eq $exe}){throw 'ASTUDIO_WARMUP_STILL_RUNNING'}
 State 'ready' @{before=$before;after=$after;installerSha512='__SHA__';model='__MODEL__';catalogCount=@($catalog.models).Count;catalogAccountMatched=$true;catalogFetchedAt=$catalog.fetchedAt;warmupStopped=$true;sessionRestored=$restoreSession;loginSource=$(if($restoreSession){'explicit_snapshot'}else{'template'})}
}catch{State 'failed' @{error=$_.Exception.Message;errorType=$_.Exception.GetType().FullName;errorId=$_.FullyQualifiedErrorId};exit 1}
'''
    for key, value in values.items():
        script = script.replace("__" + key + "__", value.replace("'", "''"))
    return script


def prepare_runtime(driver, sid, wgui, powershell):
    spec = driver.config.astudio_runtime
    if not spec:
        return
    validate_runtime(spec)
    session = read_session(Path(spec["session_file"]).expanduser()) if spec.get("session_file") else None
    model = getattr(driver, "unit", {}).get("model", "auto")
    identity = digest({**spec, "model": model, "session_sha256": hashlib.sha256(session).hexdigest() if session else None})
    row = driver.store.get(driver.key)
    state = row.get("runtime_prepare", {})
    if state and state.get("identity") != identity:
        raise E2EError("ASTUDIO_RUNTIME_INPUT_DRIFT")
    if state.get("ready"):
        return
    if spec.get("sync_clock", True):
        script = "$ErrorActionPreference='Stop';$before=[DateTimeOffset]::UtcNow;$target=[DateTimeOffset]::Parse('" + utc_now() + "');if([Math]::Abs(($before-$target).TotalSeconds)-gt 120){Set-Date -Date $target.LocalDateTime|Out-Null};@{before=$before.ToString('o');after=[DateTimeOffset]::UtcNow.ToString('o');source='controller-utc'}|ConvertTo-Json -Compress"
        clock = driver.client.windows_execute(sid, powershell(script), timeout=30)
        atomic_json(driver.staging / "metadata/windows-clock.json", json.loads(clock["output"].strip()))
    if not state.get("launch_intent"):
        remote = "/tmp/wcb-runtime-" + row["attempt_id"]
        driver.client.checked(sid, "mkdir -p " + shlex.quote(remote) + " && chmod 700 " + shlex.quote(remote))
        # Windows PowerShell 5.1 对无 BOM 脚本按本地代码页读取，中文注释可能吞掉后续行。
        driver.client.upload(sid, remote + "/prepare.ps1", installer_script(spec, identity, model).encode("utf-8-sig"))
        if session:
            driver.client.upload(sid, remote + "/session.json", session)
        secure = "$d='" + GUEST + "';New-Item -ItemType Directory -Force $d|Out-Null;$who=[Security.Principal.WindowsIdentity]::GetCurrent().Name;icacls $d /inheritance:r /grant:r \"$($who):(OI)(CI)F\" 'SYSTEM:(OI)(CI)F'|Out-Null"
        driver.client.windows_execute(sid, powershell(secure), timeout=30)
        driver._checked_job("runtime-upload", wgui + " workspace upload --source " + shlex.quote(remote) + " --guest " + shlex.quote(GUEST))
        state = {"identity": identity, "launch_intent": utc_now(), "version": spec["version"], "ready": False}
        driver._phase("PREPARING", runtime_prepare=state)
        launch = "$d='" + GUEST + "';Start-Process powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',($d+'\\prepare.ps1') -RedirectStandardOutput ($d+'\\prepare.stdout') -RedirectStandardError ($d+'\\prepare.stderr')|Out-Null"
        try:
            driver.client.windows_execute(sid, powershell(launch), timeout=30)
        except PlatformError:
            # 启动回执不明时只观察同一状态文件，不能再次执行安装/登录恢复。
            pass
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        driver.checkpoint()
        try:
            result = driver.client.windows_execute(sid, powershell("Get-Content -Raw '" + GUEST + "\\status.json'"), timeout=30)
            status = json.loads(result["output"].strip().lstrip("\ufeff"))
            if status.get("version") != spec["version"] or status.get("identity") != identity:
                time.sleep(2)
                continue
            atomic_json(driver.staging / "metadata/astudio-runtime.json", status)
            if status["stage"] == "failed":
                raise E2EError("ASTUDIO_RUNTIME_PREPARATION_FAILED: " + str(status.get("details", {}).get("error", "unknown")))
            if status["stage"] == "ready":
                driver._phase("PREPARING", runtime_prepare={**state, "ready": True, "completed_at": utc_now()})
                return
        except (PlatformError, json.JSONDecodeError, KeyError):
            pass
        time.sleep(2)
    raise PlatformError("ASTUDIO_RUNTIME_PREPARATION_UNRESOLVED", uncertain=True)
