[CmdletBinding()]
param(
    [ValidateSet("All", "Codex", "AstronStudio", "WorkBuddy", "CodexWorkBuddy", "QwenWork", "CodexQwenWork")]
    [string]$Application = "All",

    [ValidateRange(1024, 65535)]
    [int]$CodexPort = 9230,

    [ValidateRange(1024, 65535)]
    [int]$AstronStudioPort = 9240,

    [ValidateRange(1024, 65535)]
    [int]$WorkBuddyPort = 9229,

    [ValidateRange(1024, 65535)]
    [int]$QwenWorkPort = 9250,

    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 20,

    [switch]$CheckOnly,

    [switch]$ForceRestart
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$includeCodex = $Application -in @("All", "Codex", "CodexWorkBuddy", "CodexQwenWork")
$includeAstronStudio = $Application -in @("All", "AstronStudio")
$includeWorkBuddy = $Application -in @("WorkBuddy", "CodexWorkBuddy")
$includeQwenWork = $Application -in @("QwenWork", "CodexQwenWork")

if ($CheckOnly -and $ForceRestart) {
    throw "CheckOnly and ForceRestart cannot be used together."
}

$selectedPorts = @()
if ($includeCodex) { $selectedPorts += [pscustomobject]@{ Name = "Codex"; Port = $CodexPort } }
if ($includeAstronStudio) { $selectedPorts += [pscustomobject]@{ Name = "AstronStudio"; Port = $AstronStudioPort } }
if ($includeWorkBuddy) { $selectedPorts += [pscustomobject]@{ Name = "WorkBuddy"; Port = $WorkBuddyPort } }
if ($includeQwenWork) { $selectedPorts += [pscustomobject]@{ Name = "QwenWork"; Port = $QwenWorkPort } }
$duplicatePorts = @($selectedPorts | Group-Object Port | Where-Object Count -gt 1)
if ($duplicatePorts.Count -gt 0) {
    throw "Selected desktop applications must use different CDP ports."
}

# The Appx module used to launch Codex is supported by Windows PowerShell 5.1.
# Relaunch there automatically when this script is invoked from PowerShell 7.
if ($PSVersionTable.PSEdition -ne "Desktop") {
    $windowsPowerShell = Join-Path `
        $env:SystemRoot `
        "System32\WindowsPowerShell\v1.0\powershell.exe"

    $childArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-Application", $Application,
        "-CodexPort", $CodexPort,
        "-AstronStudioPort", $AstronStudioPort,
        "-WorkBuddyPort", $WorkBuddyPort,
        "-QwenWorkPort", $QwenWorkPort,
        "-TimeoutSeconds", $TimeoutSeconds
    )

    if ($CheckOnly) {
        $childArguments += "-CheckOnly"
    }
    if ($ForceRestart) {
        $childArguments += "-ForceRestart"
    }

    & $windowsPowerShell @childArguments
    exit $LASTEXITCODE
}

function Get-CdpStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string[]]$ExpectedProcesses,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedExecutablePath
    )

    try {
        $version = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/json/version" `
            -TimeoutSec 2
        $targets = @(
            Invoke-RestMethod `
                -Uri "http://127.0.0.1:$Port/json/list" `
                -TimeoutSec 2
        )
        $listener = Get-NetTCPConnection `
            -LocalPort $Port `
            -State Listen `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1

        if (-not $listener -or $targets.Count -eq 0) {
            return $null
        }

        $process = Get-Process `
            -Id $listener.OwningProcess `
            -ErrorAction SilentlyContinue

        if (-not $process -or $process.ProcessName -notin $ExpectedProcesses) {
            return $null
        }

        $actualExecutablePath = $null
        try { $actualExecutablePath = $process.Path } catch { }
        if (-not $actualExecutablePath -or
            [IO.Path]::GetFullPath($actualExecutablePath) -ine [IO.Path]::GetFullPath($ExpectedExecutablePath)) {
            return $null
        }

        return [pscustomobject]@{
            Application = $Name
            Address = "127.0.0.1"
            Port = $Port
            Process = if ($process) { $process.ProcessName } else { "unknown" }
            PID = $listener.OwningProcess
            Browser = $version.Browser
            Protocol = $version.'Protocol-Version'
            Targets = $targets.Count
            Endpoint = "http://127.0.0.1:$Port/json/list"
        }
    }
    catch {
        return $null
    }
}

function Wait-CdpStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string[]]$ExpectedProcesses,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedExecutablePath,

        [Parameter(Mandatory = $true)]
        [int]$Timeout
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)

    do {
        $status = Get-CdpStatus `
            -Name $Name `
            -Port $Port `
            -ExpectedProcesses $ExpectedProcesses `
            -ExpectedExecutablePath $ExpectedExecutablePath
        if ($status) {
            return $status
        }

        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "$Name CDP endpoint did not become ready on port $Port within $Timeout seconds."
}

function Resolve-CodexApplication {
    Import-Module Appx
    $package = Get-AppxPackage -Name "OpenAI.Codex" |
        Sort-Object Version -Descending |
        Select-Object -First 1

    if (-not $package) {
        throw "The OpenAI.Codex package is not installed."
    }

    $manifest = Get-AppxPackageManifest -Package $package
    $applicationEntry = @($manifest.Package.Applications.Application) |
        Select-Object -First 1
    if (-not $applicationEntry) {
        throw "No application entry was found in the OpenAI.Codex package manifest."
    }

    $executable = Join-Path `
        $package.InstallLocation `
        ([string]$applicationEntry.Executable)
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "Codex executable was not found: $executable"
    }

    return [pscustomobject]@{
        Package = $package
        ApplicationEntry = $applicationEntry
        Executable = (Get-Item -LiteralPath $executable).FullName
    }
}

function Resolve-AstronStudioExecutable {
    $executableNames = @("AStudio.exe", "AstronStudio.exe", "Acode.exe")
    $candidates = @()

    foreach ($registryPath in @(
        "HKCU:\Software\AStudio",
        "HKCU:\Software\AstronStudio",
        "HKCU:\Software\Acode"
    )) {
        $registryValue = Get-ItemProperty `
            -LiteralPath $registryPath `
            -Name "InstallLocation" `
            -ErrorAction SilentlyContinue

        $installLocation = if ($registryValue) {
            $registryValue.InstallLocation
        }
        else {
            $null
        }

        if ($installLocation) {
            $candidates += [string]$installLocation
        }
    }

    foreach ($directoryName in @("AStudio", "AstronStudio", "Acode")) {
        $candidates += Join-Path `
            $env:LOCALAPPDATA `
            "Programs\$directoryName"
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            if ((Split-Path -Leaf $candidate) -in $executableNames) {
                return (Get-Item -LiteralPath $candidate).FullName
            }
            continue
        }

        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
            continue
        }

        foreach ($executableName in $executableNames) {
            $executable = Join-Path $candidate $executableName
            if (Test-Path -LiteralPath $executable -PathType Leaf) {
                return (Get-Item -LiteralPath $executable).FullName
            }
        }
    }

    throw "AstronStudio was not found in its registry keys or LOCALAPPDATA Programs directories."
}

function Resolve-WorkBuddyExecutable {
    $executableNames = @("WorkBuddy.exe", "CodeBuddy.exe")
    $candidates = @()

    $uninstallEntries = Get-ItemProperty `
        -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.PSObject.Properties["DisplayName"] -and
            [string]$_.DisplayName -match "^WorkBuddy(?:\s|$)"
        }

    foreach ($entry in $uninstallEntries) {
        if ($entry.PSObject.Properties["InstallLocation"] -and $entry.InstallLocation) {
            $candidates += [string]$entry.InstallLocation
        }
        if ($entry.PSObject.Properties["DisplayIcon"] -and $entry.DisplayIcon) {
            $displayIcon = (([string]$entry.DisplayIcon).Trim() -replace ",\d+$", "").Trim('"')
            $candidates += $displayIcon
        }
    }

    $candidates += Join-Path $env:LOCALAPPDATA "Programs\WorkBuddy"

    foreach ($candidate in $candidates | Where-Object { $_ } | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            if ((Split-Path -Leaf $candidate) -in $executableNames) {
                return (Get-Item -LiteralPath $candidate).FullName
            }
            continue
        }

        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
            continue
        }

        foreach ($executableName in $executableNames) {
            $executable = Join-Path $candidate $executableName
            if (Test-Path -LiteralPath $executable -PathType Leaf) {
                return (Get-Item -LiteralPath $executable).FullName
            }
        }
    }

    throw "WorkBuddy was not found in the current-user uninstall registry or LOCALAPPDATA Programs directory."
}

function Resolve-QwenWorkExecutable {
    $executableNames = @("QwenWorkCN.exe", "QwenWork.exe")
    $candidates = @()

    $uninstallEntries = Get-ItemProperty `
        -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.PSObject.Properties["DisplayName"] -and
            [string]$_.DisplayName -match "^(?:千问办公|QwenWorkCN|QwenWork)(?:\s|$)"
        }

    foreach ($entry in $uninstallEntries) {
        if ($entry.PSObject.Properties["InstallLocation"] -and $entry.InstallLocation) {
            $candidates += [string]$entry.InstallLocation
        }
        if ($entry.PSObject.Properties["DisplayIcon"] -and $entry.DisplayIcon) {
            $displayIcon = (([string]$entry.DisplayIcon).Trim() -replace ",\d+$", "").Trim('"')
            $candidates += $displayIcon
        }
        if ($entry.PSObject.Properties["UninstallString"] -and $entry.UninstallString) {
            $uninstall = ([string]$entry.UninstallString).Trim().Trim('"')
            $candidates += Split-Path -Parent $uninstall
        }
    }

    $candidates += Join-Path $env:LOCALAPPDATA "Programs\QwenWorkCN"
    $candidates += Join-Path $env:LOCALAPPDATA "Programs\QwenWork"

    foreach ($candidate in $candidates | Where-Object { $_ } | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            if ((Split-Path -Leaf $candidate) -in $executableNames) {
                return (Get-Item -LiteralPath $candidate).FullName
            }
            $candidate = Split-Path -Parent $candidate
        }

        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
            continue
        }

        $directories = @((Get-Item -LiteralPath $candidate)) + @(
            Get-ChildItem -LiteralPath $candidate -Directory -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending
        )
        foreach ($directory in $directories) {
            foreach ($executableName in $executableNames) {
                $executable = Join-Path $directory.FullName $executableName
                if (Test-Path -LiteralPath $executable -PathType Leaf) {
                    return (Get-Item -LiteralPath $executable).FullName
                }
            }
        }
    }

    throw "QwenWork was not found in the current-user uninstall registry or LOCALAPPDATA Programs directories."
}

function Resolve-WorkBuddyBundledNodeDirectory {
    $versionsRoot = Join-Path `
        $env:USERPROFILE `
        ".workbuddy\binaries\node\versions"
    if (-not (Test-Path -LiteralPath $versionsRoot -PathType Container)) {
        return $null
    }

    $candidates = @(
        Get-ChildItem -LiteralPath $versionsRoot -Directory -ErrorAction SilentlyContinue |
            ForEach-Object {
                $parsedVersion = [version]"0.0.0.0"
                [void][version]::TryParse(
                    ($_.Name -replace "-.*$", ""),
                    [ref]$parsedVersion
                )
                [pscustomobject]@{
                    Directory = $_.FullName
                    Name = $_.Name
                    Version = $parsedVersion
                }
            } |
            Sort-Object `
                @{ Expression = "Version"; Descending = $true }, `
                @{ Expression = "Name"; Descending = $true }
    )

    foreach ($candidate in $candidates) {
        if (
            (Test-Path -LiteralPath (Join-Path $candidate.Directory "node.exe") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $candidate.Directory "npm.cmd") -PathType Leaf)
        ) {
            return $candidate.Directory
        }
    }
    return $null
}

function Get-WorkBuddyActiveSessionCount {
    $sessionDatabase = Join-Path $env:USERPROFILE ".workbuddy\workbuddy.db"
    if (-not (Test-Path -LiteralPath $sessionDatabase -PathType Leaf)) {
        throw "WorkBuddy session database was not found; refusing to restart a running client: $sessionDatabase"
    }

    $pythonScript = @'
import pathlib, sqlite3, sys
path = pathlib.Path(sys.argv[1]).resolve()
database = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
columns = {row[1] for row in database.execute('PRAGMA table_info(sessions)')}
if 'status' not in columns:
    raise RuntimeError('sessions.status is unavailable')
where = 'lower(status) in (?,?,?,?)'
if 'deleted_at' in columns:
    where += ' and deleted_at is null'
active = ('running', 'needs_attention', 'pending', 'starting')
count = database.execute('select count(*) from sessions where ' + where, active).fetchone()[0]
database.close()
print(count)
'@

    $pythonCommands = @(
        [pscustomobject]@{ Command = "py.exe"; Prefix = @("-3") },
        [pscustomobject]@{ Command = "python.exe"; Prefix = @() }
    )
    $errors = @()
    foreach ($python in $pythonCommands) {
        if (-not (Get-Command $python.Command -ErrorAction SilentlyContinue)) {
            continue
        }
        $arguments = @($python.Prefix) + @("-c", $pythonScript, $sessionDatabase)
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $output = & $python.Command @arguments 2>&1
            $pythonExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($pythonExitCode -eq 0 -and "$output" -match "^\d+$") {
            return [int]$output
        }
        $errors += "$($python.Command): $output"
    }
    throw "No usable read-only SQLite backend could verify WorkBuddy sessions: $($errors -join '; ')"
}

function Assert-WorkBuddyRestartSafe {
    $activeCount = Get-WorkBuddyActiveSessionCount
    if ($activeCount -gt 0) {
        throw "WorkBuddy has $activeCount active or pending session(s); refusing to restart the client."
    }
}

function Get-QwenWorkActiveSessionCount {
    $sessionDatabase = Join-Path $env:APPDATA "QwenWorkCN\data\agents.db"
    if (-not (Test-Path -LiteralPath $sessionDatabase -PathType Leaf)) {
        throw "QwenWork session database was not found; refusing to restart a running client: $sessionDatabase"
    }

    $pythonScript = @'
import pathlib, sqlite3, sys
path = pathlib.Path(sys.argv[1]).resolve()
database = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
tables = {row[0] for row in database.execute('select name from sqlite_master where type=char(116,97,98,108,101)')}
if not {'sub_chats', 'chats'}.issubset(tables):
    raise RuntimeError('sub_chats or chats table is unavailable')
active = database.execute('''
select count(*)
from sub_chats
join chats on chats.id = sub_chats.chat_id
where chats.deleted_at is null
  and (
    sub_chats.stream_id is not null
    or lower(coalesce(json_extract(chats.ext, '$.taskStatus'), '')) in
      ('running', 'needs_attention', 'pending', 'starting')
  )
''').fetchone()[0]
database.close()
print(active)
'@

    $pythonCommands = @(
        [pscustomobject]@{ Command = "py.exe"; Prefix = @("-3") },
        [pscustomobject]@{ Command = "python.exe"; Prefix = @() }
    )
    $errors = @()
    foreach ($python in $pythonCommands) {
        if (-not (Get-Command $python.Command -ErrorAction SilentlyContinue)) {
            continue
        }
        $arguments = @($python.Prefix) + @("-c", $pythonScript, $sessionDatabase)
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $output = & $python.Command @arguments 2>&1
            $pythonExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($pythonExitCode -eq 0 -and "$output" -match "^\d+$") {
            return [int]$output
        }
        $errors += "$($python.Command): $output"
    }
    throw "No usable read-only SQLite backend could verify QwenWork sessions: $($errors -join '; ')"
}

function Assert-QwenWorkRestartSafe {
    $activeCount = Get-QwenWorkActiveSessionCount
    if ($activeCount -gt 0) {
        throw "QwenWork has $activeCount active or pending session(s); refusing to restart the client."
    }
}

function Assert-PortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $listener = Get-NetTCPConnection `
        -LocalPort $Port `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($listener) {
        $process = Get-Process `
            -Id $listener.OwningProcess `
            -ErrorAction SilentlyContinue
        $processName = if ($process) { $process.ProcessName } else { "unknown" }
        throw "Port $Port is already used by $processName (PID $($listener.OwningProcess))."
    }
}

function Get-InstalledProcessesByExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ProcessNames,

        [Parameter(Mandatory = $true)]
        [string]$ExecutablePath
    )

    $expectedPath = [IO.Path]::GetFullPath($ExecutablePath)
    return @(
        Get-Process -Name $ProcessNames -ErrorAction SilentlyContinue |
            Where-Object {
                $actualPath = $null
                try { $actualPath = $_.Path } catch { }
                $actualPath -and ([IO.Path]::GetFullPath($actualPath) -ieq $expectedPath)
            }
    )
}

function Test-InstalledProcessIdentity {
    param(
        [Parameter(Mandatory = $true)]
        $Process,

        [Parameter(Mandatory = $true)]
        [string]$ExecutablePath
    )

    $actualPath = $null
    try { $actualPath = $Process.Path } catch { }
    return $actualPath -and (
        [IO.Path]::GetFullPath($actualPath) -ieq [IO.Path]::GetFullPath($ExecutablePath)
    )
}

function Wait-PortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string[]]$ExpectedProcesses,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedExecutablePath,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $listener = Get-NetTCPConnection `
            -LocalPort $Port `
            -State Listen `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1

        if (-not $listener) {
            return
        }

        $process = Get-Process `
            -Id $listener.OwningProcess `
            -ErrorAction SilentlyContinue
        if (-not $process -or
            $process.ProcessName -notin $ExpectedProcesses -or
            -not (Test-InstalledProcessIdentity -Process $process -ExecutablePath $ExpectedExecutablePath)) {
            $processName = if ($process) { $process.ProcessName } else { "unknown" }
            throw "Port $Port was claimed by unrelated process $processName (PID $($listener.OwningProcess)) while waiting for the desktop client to exit."
        }

        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    $processName = if ($process) { $process.ProcessName } else { "unknown" }
    throw "Timed out waiting for port $Port to be released by $processName (PID $($listener.OwningProcess))."
}

function Assert-PortRestartable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string[]]$ExpectedProcesses,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedExecutablePath
    )

    $listener = Get-NetTCPConnection `
        -LocalPort $Port `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if (-not $listener) {
        return
    }

    $process = Get-Process `
        -Id $listener.OwningProcess `
        -ErrorAction SilentlyContinue

    if (-not $process -or
        $process.ProcessName -notin $ExpectedProcesses -or
        -not (Test-InstalledProcessIdentity -Process $process -ExecutablePath $ExpectedExecutablePath)) {
        $processName = if ($process) { $process.ProcessName } else { "unknown" }
        throw "Port $Port is already used by $processName (PID $($listener.OwningProcess)); refusing to stop an unrelated process."
    }
}

$codexApplication = if ($includeCodex) { Resolve-CodexApplication } else { $null }
$codexExecutable = if ($codexApplication) { $codexApplication.Executable } else { $null }
$astronStudioExecutable = if ($includeAstronStudio) { Resolve-AstronStudioExecutable } else { $null }
$workBuddyExecutable = if ($includeWorkBuddy) { Resolve-WorkBuddyExecutable } else { $null }
$qwenWorkExecutable = if ($includeQwenWork) { Resolve-QwenWorkExecutable } else { $null }

if ($includeCodex) {
    $codexReady = $null -ne (Get-CdpStatus `
        -Name "Codex Desktop" `
        -Port $CodexPort `
        -ExpectedProcesses @("ChatGPT", "Codex") `
        -ExpectedExecutablePath $codexExecutable)
}
else {
    $codexReady = $true
}

if ($includeAstronStudio) {
    $astronStudioReady = $null -ne (Get-CdpStatus `
        -Name "AstronStudio" `
        -Port $AstronStudioPort `
        -ExpectedProcesses @("AStudio", "AstronStudio", "Acode") `
        -ExpectedExecutablePath $astronStudioExecutable)
}
else {
    $astronStudioReady = $true
}

if ($includeWorkBuddy) {
    $workBuddyReady = $null -ne (Get-CdpStatus `
        -Name "WorkBuddy" `
        -Port $WorkBuddyPort `
        -ExpectedProcesses @("WorkBuddy", "CodeBuddy") `
        -ExpectedExecutablePath $workBuddyExecutable)
}
else {
    $workBuddyReady = $true
}

if ($includeQwenWork) {
    $qwenWorkReady = $null -ne (Get-CdpStatus `
        -Name "QwenWork" `
        -Port $QwenWorkPort `
        -ExpectedProcesses @("QwenWorkCN", "QwenWork") `
        -ExpectedExecutablePath $qwenWorkExecutable)
}
else {
    $qwenWorkReady = $true
}

if ($ForceRestart) {
    if ($includeCodex) {
        $codexReady = $false
    }
    if ($includeAstronStudio) {
        $astronStudioReady = $false
    }
    if ($includeWorkBuddy) {
        $workBuddyReady = $false
    }
    if ($includeQwenWork) {
        $qwenWorkReady = $false
    }
}

if ($CheckOnly) {
    if (-not $codexReady) {
        throw "Codex Desktop is not exposing a valid CDP target on port $CodexPort."
    }
    if (-not $astronStudioReady) {
        throw "AstronStudio is not exposing a valid CDP target on port $AstronStudioPort."
    }
    if (-not $workBuddyReady) {
        throw "WorkBuddy is not exposing a valid CDP target on port $WorkBuddyPort."
    }
    if (-not $qwenWorkReady) {
        throw "QwenWork is not exposing a valid CDP target on port $QwenWorkPort."
    }
}
else {
    if ($includeCodex -and -not $codexReady) {
        Assert-PortRestartable `
            -Port $CodexPort `
            -ExpectedProcesses @("ChatGPT", "Codex") `
            -ExpectedExecutablePath $codexExecutable
    }
    if ($includeAstronStudio -and -not $astronStudioReady) {
        Assert-PortRestartable `
            -Port $AstronStudioPort `
            -ExpectedProcesses @("AStudio", "AstronStudio", "Acode") `
            -ExpectedExecutablePath $astronStudioExecutable
    }
    if ($includeWorkBuddy -and -not $workBuddyReady) {
        Assert-PortRestartable `
            -Port $WorkBuddyPort `
            -ExpectedProcesses @("WorkBuddy", "CodeBuddy") `
            -ExpectedExecutablePath $workBuddyExecutable
    }
    if ($includeQwenWork -and -not $qwenWorkReady) {
        Assert-PortRestartable `
            -Port $QwenWorkPort `
            -ExpectedProcesses @("QwenWorkCN", "QwenWork") `
            -ExpectedExecutablePath $qwenWorkExecutable
    }

    $codexProcesses = @(
        if ($includeCodex -and -not $codexReady) {
            Get-InstalledProcessesByExecutable `
                -ProcessNames @("ChatGPT", "Codex") `
                -ExecutablePath $codexExecutable
        }
    )
    $astronStudioProcesses = @(
        if ($includeAstronStudio -and -not $astronStudioReady) {
            Get-InstalledProcessesByExecutable `
                -ProcessNames @("AStudio", "AstronStudio", "Acode") `
                -ExecutablePath $astronStudioExecutable
        }
    )
    $workBuddyProcesses = @(
        if ($includeWorkBuddy -and -not $workBuddyReady) {
            Get-InstalledProcessesByExecutable `
                -ProcessNames @("WorkBuddy", "CodeBuddy") `
                -ExecutablePath $workBuddyExecutable
        }
    )
    if ($includeWorkBuddy -and -not $workBuddyReady) {
        if ($workBuddyProcesses.Count -gt 0) {
            Assert-WorkBuddyRestartSafe
        }
    }

    $qwenWorkProcesses = @(
        if ($includeQwenWork -and -not $qwenWorkReady) {
            Get-InstalledProcessesByExecutable `
                -ProcessNames @("QwenWorkCN", "QwenWork") `
                -ExecutablePath $qwenWorkExecutable
        }
    )
    if ($includeQwenWork -and -not $qwenWorkReady) {
        if ($qwenWorkProcesses.Count -gt 0) {
            Assert-QwenWorkRestartSafe
        }
    }

    if ($codexProcesses.Count -gt 0) {
        Write-Host "Stopping Codex processes whose executable path matches the discovered MSIX installation..."
        $codexProcesses | Stop-Process -Force
        $codexProcesses | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
    }

    if ($astronStudioProcesses.Count -gt 0) {
        Write-Host "Stopping AstronStudio processes whose executable path matches the discovered installation..."
        $astronStudioProcesses | Stop-Process -Force
        $astronStudioProcesses | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
    }

    if ($workBuddyProcesses.Count -gt 0) {
        Write-Host "Stopping WorkBuddy processes whose executable path matches the discovered installation..."
        $workBuddyProcesses | Stop-Process -Force
        $workBuddyProcesses | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
    }

    if ($qwenWorkProcesses.Count -gt 0) {
        Write-Host "Stopping QwenWork processes whose executable path matches the discovered installation..."
        $qwenWorkProcesses | Stop-Process -Force
        $qwenWorkProcesses | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
    }

    if ($includeCodex -and -not $codexReady) {
        Wait-PortAvailable `
            -Port $CodexPort `
            -ExpectedProcesses @("ChatGPT", "Codex") `
            -ExpectedExecutablePath $codexExecutable `
            -TimeoutSeconds $TimeoutSeconds

        Write-Host "Starting Codex with CDP on port $CodexPort..."
        Invoke-CommandInDesktopPackage `
            -PackageFamilyName $codexApplication.Package.PackageFamilyName `
            -AppId ([string]$codexApplication.ApplicationEntry.Id) `
            -Command $codexExecutable `
            -Args "--remote-debugging-address=127.0.0.1 --remote-debugging-port=$CodexPort"
    }

    if ($includeAstronStudio -and -not $astronStudioReady) {
        Wait-PortAvailable `
            -Port $AstronStudioPort `
            -ExpectedProcesses @("AStudio", "AstronStudio", "Acode") `
            -ExpectedExecutablePath $astronStudioExecutable `
            -TimeoutSeconds $TimeoutSeconds

        Write-Host "Starting AstronStudio with CDP on port $AstronStudioPort..."
        Start-Process `
            -FilePath $astronStudioExecutable `
            -ArgumentList @(
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=$AstronStudioPort"
            )
    }

    if ($includeWorkBuddy -and -not $workBuddyReady) {
        Wait-PortAvailable `
            -Port $WorkBuddyPort `
            -ExpectedProcesses @("WorkBuddy", "CodeBuddy") `
            -ExpectedExecutablePath $workBuddyExecutable `
            -TimeoutSeconds $TimeoutSeconds

        Write-Host "Starting WorkBuddy with CDP on port $WorkBuddyPort..."
        $workBuddyNodeDirectory = Resolve-WorkBuddyBundledNodeDirectory
        $previousProcessPath = $env:Path
        $previousNpmAudit = [Environment]::GetEnvironmentVariable("npm_config_audit", "Process")
        $previousNpmFund = [Environment]::GetEnvironmentVariable("npm_config_fund", "Process")
        $previousNpmUpdateNotifier = [Environment]::GetEnvironmentVariable("npm_config_update_notifier", "Process")
        $previousNpmPreferOffline = [Environment]::GetEnvironmentVariable("npm_config_prefer_offline", "Process")
        $previousBashDefaultTimeout = [Environment]::GetEnvironmentVariable("BASH_DEFAULT_TIMEOUT_MS", "Process")
        $previousBashMaxTimeout = [Environment]::GetEnvironmentVariable("BASH_MAX_TIMEOUT_MS", "Process")
        try {
            if ($workBuddyNodeDirectory) {
                $pathEntries = @($env:Path -split ";" | Where-Object { $_ })
                if ($workBuddyNodeDirectory -notin $pathEntries) {
                    $env:Path = (@($workBuddyNodeDirectory) + $pathEntries) -join ";"
                }
            }
            if ($null -eq $previousNpmAudit) {
                $env:npm_config_audit = "false"
            }
            if ($null -eq $previousNpmFund) {
                $env:npm_config_fund = "false"
            }
            if ($null -eq $previousNpmUpdateNotifier) {
                $env:npm_config_update_notifier = "false"
            }
            if ($null -eq $previousNpmPreferOffline) {
                $env:npm_config_prefer_offline = "true"
            }
            if ($null -eq $previousBashDefaultTimeout) {
                $env:BASH_DEFAULT_TIMEOUT_MS = "600000"
            }
            if ($null -eq $previousBashMaxTimeout) {
                $env:BASH_MAX_TIMEOUT_MS = "600000"
            }
            Start-Process `
                -FilePath $workBuddyExecutable `
                -ArgumentList @(
                    "--remote-debugging-address=127.0.0.1",
                    "--remote-debugging-port=$WorkBuddyPort"
                )
        }
        finally {
            $env:Path = $previousProcessPath
            foreach ($savedValue in @(
                [pscustomobject]@{ Name = "npm_config_audit"; Value = $previousNpmAudit },
                [pscustomobject]@{ Name = "npm_config_fund"; Value = $previousNpmFund },
                [pscustomobject]@{ Name = "npm_config_update_notifier"; Value = $previousNpmUpdateNotifier },
                [pscustomobject]@{ Name = "npm_config_prefer_offline"; Value = $previousNpmPreferOffline },
                [pscustomobject]@{ Name = "BASH_DEFAULT_TIMEOUT_MS"; Value = $previousBashDefaultTimeout },
                [pscustomobject]@{ Name = "BASH_MAX_TIMEOUT_MS"; Value = $previousBashMaxTimeout }
            )) {
                if ($null -eq $savedValue.Value) {
                    Remove-Item -LiteralPath "Env:$($savedValue.Name)" -ErrorAction SilentlyContinue
                }
                else {
                    [Environment]::SetEnvironmentVariable($savedValue.Name, $savedValue.Value, "Process")
                }
            }
        }
    }

    if ($includeQwenWork -and -not $qwenWorkReady) {
        Wait-PortAvailable `
            -Port $QwenWorkPort `
            -ExpectedProcesses @("QwenWorkCN", "QwenWork") `
            -ExpectedExecutablePath $qwenWorkExecutable `
            -TimeoutSeconds $TimeoutSeconds

        Write-Host "Starting QwenWork with CDP on port $QwenWorkPort..."
        Start-Process `
            -FilePath $qwenWorkExecutable `
            -ArgumentList @(
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=$QwenWorkPort"
            )
    }
}

Write-Host "Waiting for $Application CDP endpoints..."
$statuses = @()
if ($includeCodex) {
    $statuses += Wait-CdpStatus `
        -Name "Codex Desktop" `
        -Port $CodexPort `
        -ExpectedProcesses @("ChatGPT", "Codex") `
        -ExpectedExecutablePath $codexExecutable `
        -Timeout $TimeoutSeconds
}
if ($includeAstronStudio) {
    $statuses += Wait-CdpStatus `
        -Name "AstronStudio" `
        -Port $AstronStudioPort `
        -ExpectedProcesses @("AStudio", "AstronStudio", "Acode") `
        -ExpectedExecutablePath $astronStudioExecutable `
        -Timeout $TimeoutSeconds
}
if ($includeWorkBuddy) {
    $statuses += Wait-CdpStatus `
        -Name "WorkBuddy" `
        -Port $WorkBuddyPort `
        -ExpectedProcesses @("WorkBuddy", "CodeBuddy") `
        -ExpectedExecutablePath $workBuddyExecutable `
        -Timeout $TimeoutSeconds
}
if ($includeQwenWork) {
    $statuses += Wait-CdpStatus `
        -Name "QwenWork" `
        -Port $QwenWorkPort `
        -ExpectedProcesses @("QwenWorkCN", "QwenWork") `
        -ExpectedExecutablePath $qwenWorkExecutable `
        -Timeout $TimeoutSeconds
}

Write-Host ""
$statuses |
    Format-Table `
        Application, Address, Port, Process, PID, Browser, Protocol, Targets `
        -AutoSize

Write-Host ""
Write-Host "CDP endpoints:"
foreach ($status in $statuses) {
    Write-Host "  $($status.Endpoint)"
}
