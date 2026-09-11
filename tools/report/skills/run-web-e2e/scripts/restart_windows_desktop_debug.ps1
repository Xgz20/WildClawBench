[CmdletBinding()]
param(
    [ValidateSet("All", "Codex", "AstronStudio", "WorkBuddy", "CodexWorkBuddy")]
    [string]$Application = "All",

    [ValidateRange(1024, 65535)]
    [int]$CodexPort = 9230,

    [ValidateRange(1024, 65535)]
    [int]$AstronStudioPort = 9240,

    [ValidateRange(1024, 65535)]
    [int]$WorkBuddyPort = 9229,

    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 60,

    [ValidateRange(1, 30)]
    [int]$DelaySeconds = 5,

    [string]$StatusDirectory,

    [switch]$ScheduledWorker,

    [string]$TaskName
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

function Write-RestartStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Status,

        [string]$ErrorMessage
    )

    $payload = [ordered]@{
        schema_version = "wildclawbench.windows-desktop-debug-restart/v1"
        status = $Status
        application = $Application
        task_name = $TaskName
        codex_port = $CodexPort
        astronstudio_port = $AstronStudioPort
        workbuddy_port = $WorkBuddyPort
        timeout_seconds = $TimeoutSeconds
        delay_seconds = $DelaySeconds
        updated_at = [DateTime]::UtcNow.ToString("o")
        error = $ErrorMessage
    }

    $payload |
        ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath $Path -Encoding UTF8
}

function ConvertTo-SingleQuotedPowerShellLiteral {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return "'" + $Value.Replace("'", "''") + "'"
}

$launcherPath = Join-Path $PSScriptRoot "start_windows_desktop_debug.ps1"
if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
    throw "Desktop debug launcher was not found: $launcherPath"
}

if ($ScheduledWorker) {
    if ([string]::IsNullOrWhiteSpace($TaskName) -or
        $TaskName -notlike "WildClawBench-Desktop-Debug-Restart-*") {
        throw "Scheduled worker requires a managed WildClawBench task name."
    }
    if ([string]::IsNullOrWhiteSpace($StatusDirectory)) {
        throw "Scheduled worker requires StatusDirectory."
    }

    New-Item -ItemType Directory -Path $StatusDirectory -Force | Out-Null
    $statusPath = Join-Path $StatusDirectory "status.json"
    $stdoutPath = Join-Path $StatusDirectory "stdout.log"
    $stderrPath = Join-Path $StatusDirectory "stderr.log"
    $failed = $false

    try {
        Start-Sleep -Seconds $DelaySeconds
        Write-RestartStatus -Path $statusPath -Status "RUNNING"

        $launcherArguments = @{
            Application = $Application
            CodexPort = $CodexPort
            AstronStudioPort = $AstronStudioPort
            WorkBuddyPort = $WorkBuddyPort
            TimeoutSeconds = $TimeoutSeconds
            ForceRestart = $true
        }

        & $launcherPath @launcherArguments *>&1 |
            Out-File -LiteralPath $stdoutPath -Encoding UTF8

        Write-RestartStatus -Path $statusPath -Status "PASSED"
    }
    catch {
        $failed = $true
        $message = $_.Exception.Message
        $_ | Out-String | Out-File -LiteralPath $stderrPath -Encoding UTF8
        Write-RestartStatus `
            -Path $statusPath `
            -Status "FAILED" `
            -ErrorMessage $message
    }
    finally {
        Unregister-ScheduledTask `
            -TaskName $TaskName `
            -Confirm:$false `
            -ErrorAction SilentlyContinue
    }

    if ($failed) {
        exit 1
    }
    exit 0
}

if (-not [string]::IsNullOrWhiteSpace($TaskName)) {
    throw "TaskName is reserved for the scheduled worker."
}

if ([string]::IsNullOrWhiteSpace($StatusDirectory)) {
    $restartId = "{0}-{1}" -f `
        [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ"), `
        ([Guid]::NewGuid().ToString("N").Substring(0, 8))
    $StatusDirectory = Join-Path `
        $env:LOCALAPPDATA `
        "WildClawBench\desktop-debug-restart\$restartId"
}
else {
    $StatusDirectory = [IO.Path]::GetFullPath($StatusDirectory)
}

New-Item -ItemType Directory -Path $StatusDirectory -Force | Out-Null
$TaskName = "WildClawBench-Desktop-Debug-Restart-$([Guid]::NewGuid().ToString('N'))"
$statusPath = Join-Path $StatusDirectory "status.json"
$windowsPowerShell = Join-Path `
    $env:SystemRoot `
    "System32\WindowsPowerShell\v1.0\powershell.exe"

$workerCommand = @(
    "& $(ConvertTo-SingleQuotedPowerShellLiteral -Value $PSCommandPath)",
    "-Application $(ConvertTo-SingleQuotedPowerShellLiteral -Value $Application)",
    "-CodexPort $CodexPort",
    "-AstronStudioPort $AstronStudioPort",
    "-WorkBuddyPort $WorkBuddyPort",
    "-TimeoutSeconds $TimeoutSeconds",
    "-DelaySeconds $DelaySeconds",
    "-StatusDirectory $(ConvertTo-SingleQuotedPowerShellLiteral -Value $StatusDirectory)",
    "-ScheduledWorker",
    "-TaskName $(ConvertTo-SingleQuotedPowerShellLiteral -Value $TaskName)"
) -join " "
$encodedCommand = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($workerCommand)
)

$action = New-ScheduledTaskAction `
    -Execute $windowsPowerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encodedCommand"
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Force |
        Out-Null

    Write-RestartStatus -Path $statusPath -Status "SCHEDULED"
    Start-ScheduledTask -TaskName $TaskName
}
catch {
    Unregister-ScheduledTask `
        -TaskName $TaskName `
        -Confirm:$false `
        -ErrorAction SilentlyContinue
    throw
}

[pscustomobject]@{
    Scheduled = $true
    Application = $Application
    TaskName = $TaskName
    DelaySeconds = $DelaySeconds
    StatusDirectory = $StatusDirectory
    StatusFile = $statusPath
} | Format-List
