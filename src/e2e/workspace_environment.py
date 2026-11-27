"""Verify shared Windows workspace aliases before any desktop client dispatch."""
from __future__ import annotations

import base64
import json

from src.wildclawbench_workspace import PROFILE, WINDOWS_ALIAS, WINDOWS_ROOT
from .common import E2EError, atomic_json


def preparation_script():
    # Get-Item sees broken junctions too; never replace an unrelated path. A
    # write/read probe proves the alias actually reaches the requested target.
    return r'''$ErrorActionPreference='Stop'
$workspace='C:\ProgramData\WGUI\workspace\project';$alias='C:\tmp_workspace'
if(Test-Path -LiteralPath $workspace){if((Get-Item -LiteralPath $workspace -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'WINDOWS_WORKSPACE_ROOT_CONFLICT'}}
New-Item -ItemType Directory -Force -Path $workspace|Out-Null
$item=Get-Item -LiteralPath $alias -Force -ErrorAction SilentlyContinue
if($item){
 if($item.LinkType -ne 'Junction' -or (@($item.Target)[0]).TrimEnd([char]92) -ine $workspace){throw 'WINDOWS_WORKSPACE_ALIAS_CONFLICT'}
}else{New-Item -ItemType Junction -Path $alias -Target $workspace|Out-Null}
$name='.wcb-alias-'+[guid]::NewGuid().ToString('N');$nonce=[guid]::NewGuid().ToString('N')
try{
 [IO.File]::WriteAllText((Join-Path $workspace $name),$nonce)
 if([IO.File]::ReadAllText((Join-Path $alias $name)) -ne $nonce){throw 'WINDOWS_WORKSPACE_ALIAS_UNREACHABLE'}
}finally{Remove-Item -LiteralPath (Join-Path $workspace $name) -Force -ErrorAction SilentlyContinue}
$python=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if(!(Test-Path -LiteralPath $python)){$cmd=Get-Command python.exe -ErrorAction SilentlyContinue;$python=$cmd.Source}
if(!$python){throw 'WINDOWS_WORKSPACE_PYTHON_UNAVAILABLE'}
$raw=& $python -c 'import json,sys;print(json.dumps(dict(executable=sys.executable,version=list(sys.version_info[:3]))))'
if($LASTEXITCODE -ne 0){throw 'WINDOWS_WORKSPACE_PYTHON_UNAVAILABLE'}
$runtime=$raw|ConvertFrom-Json
if($runtime.version[0] -ne 3){throw 'WINDOWS_WORKSPACE_PYTHON_MISMATCH'}
$proof=@{profile='wildclawbench.workspace-paths/v1';platform='windows';workspace=$workspace;alias=$alias;alias_verified=$true;python=$runtime}|ConvertTo-Json -Depth 4 -Compress
[Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($proof)))
'''


def prepare(driver, sid, powershell):
    result = driver.client.windows_execute(sid, powershell(preparation_script()), timeout=60)
    try:
        proof = json.loads(base64.b64decode(result["output"].strip(), validate=True))
        valid = (proof["profile"] == PROFILE and proof["platform"] == "windows"
                 and proof["workspace"] == WINDOWS_ROOT and proof["alias"] == WINDOWS_ALIAS
                 and proof["alias_verified"] is True and proof["python"]["version"][0] == 3
                 and isinstance(proof["python"]["executable"], str))
    except (KeyError, ValueError, TypeError, IndexError):
        valid = False
    if not valid:
        raise E2EError("WINDOWS_WORKSPACE_ENVIRONMENT_UNVERIFIED")
    atomic_json(driver.staging / "metadata/workspace-environment.json", proof)
    return proof
