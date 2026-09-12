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
    [int]$TimeoutSeconds = 20,

    [switch]$CheckOnly,

    [switch]$ForceRestart
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$includeCodex = $Application -in @("All", "Codex", "CodexWorkBuddy")
$includeAstronStudio = $Application -in @("All", "AstronStudio")
$includeWorkBuddy = $Application -in @("WorkBuddy", "CodexWorkBuddy")

if ($CheckOnly -and $ForceRestart) {
    throw "CheckOnly and ForceRestart cannot be used together."
}

$selectedPorts = @()
if ($includeCodex) { $selectedPorts += [pscustomobject]@{ Name = "Codex"; Port = $CodexPort } }
if ($includeAstronStudio) { $selectedPorts += [pscustomobject]@{ Name = "AstronStudio"; Port = $AstronStudioPort } }
if ($includeWorkBuddy) { $selectedPorts += [pscustomobject]@{ Name = "WorkBuddy"; Port = $WorkBuddyPort } }
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
        [string[]]$ExpectedProcesses
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
        [int]$Timeout
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)

    do {
        $status = Get-CdpStatus `
            -Name $Name `
            -Port $Port `
            -ExpectedProcesses $ExpectedProcesses
        if ($status) {
            return $status
        }

        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "$Name CDP endpoint did not become ready on port $Port within $Timeout seconds."
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

function Assert-PortRestartable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string[]]$ExpectedProcesses
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

    if (-not $process -or $process.ProcessName -notin $ExpectedProcesses) {
        $processName = if ($process) { $process.ProcessName } else { "unknown" }
        throw "Port $Port is already used by $processName (PID $($listener.OwningProcess)); refusing to stop an unrelated process."
    }
}

if ($includeCodex) {
    $codexReady = $null -ne (Get-CdpStatus `
        -Name "Codex Desktop" `
        -Port $CodexPort `
        -ExpectedProcesses @("ChatGPT", "Codex"))
}
else {
    $codexReady = $true
}

if ($includeAstronStudio) {
    $astronStudioReady = $null -ne (Get-CdpStatus `
        -Name "AstronStudio" `
        -Port $AstronStudioPort `
        -ExpectedProcesses @("AStudio", "AstronStudio", "Acode"))
}
else {
    $astronStudioReady = $true
}

if ($includeWorkBuddy) {
    $workBuddyReady = $null -ne (Get-CdpStatus `
        -Name "WorkBuddy" `
        -Port $WorkBuddyPort `
        -ExpectedProcesses @("WorkBuddy", "CodeBuddy"))
}
else {
    $workBuddyReady = $true
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
}
else {
    if ($includeCodex -and -not $codexReady) {
        Assert-PortRestartable `
            -Port $CodexPort `
            -ExpectedProcesses @("ChatGPT", "Codex")
    }
    if ($includeAstronStudio -and -not $astronStudioReady) {
        Assert-PortRestartable `
            -Port $AstronStudioPort `
            -ExpectedProcesses @("AStudio", "AstronStudio", "Acode")
    }
    if ($includeWorkBuddy -and -not $workBuddyReady) {
        Assert-PortRestartable `
            -Port $WorkBuddyPort `
            -ExpectedProcesses @("WorkBuddy", "CodeBuddy")
    }

    $workBuddyExecutable = $null
    $workBuddyProcesses = @()
    if ($includeWorkBuddy -and -not $workBuddyReady) {
        $workBuddyExecutable = Resolve-WorkBuddyExecutable
        $expectedWorkBuddyPath = [IO.Path]::GetFullPath($workBuddyExecutable)
        $workBuddyProcesses = @(
            Get-Process -Name "WorkBuddy", "CodeBuddy" -ErrorAction SilentlyContinue |
                Where-Object {
                    $actualPath = $null
                    try { $actualPath = $_.Path } catch { }
                    $actualPath -and ([IO.Path]::GetFullPath($actualPath) -ieq $expectedWorkBuddyPath)
                }
        )
        if ($workBuddyProcesses.Count -gt 0) {
            Assert-WorkBuddyRestartSafe
        }
    }

    $processNames = @()
    if ($includeCodex -and -not $codexReady) {
        $processNames += "ChatGPT"
        $processNames += "Codex"
    }
    if ($includeAstronStudio -and -not $astronStudioReady) {
        $processNames += "AStudio"
        $processNames += "AstronStudio"
        $processNames += "Acode"
    }
    if ($processNames.Count -gt 0) {
        Write-Host "Stopping desktop processes that are missing valid CDP endpoints..."
        $existingProcesses = Get-Process `
            -Name $processNames `
            -ErrorAction SilentlyContinue

        if ($existingProcesses) {
            $existingProcesses | Stop-Process -Force
            $existingProcesses | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
        }
    }

    if ($workBuddyProcesses.Count -gt 0) {
        Write-Host "Stopping WorkBuddy processes whose executable path matches the discovered installation..."
        $workBuddyProcesses | Stop-Process -Force
        $workBuddyProcesses | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
    }

    if ($includeCodex -and -not $codexReady) {
        Assert-PortAvailable -Port $CodexPort

        Import-Module Appx
        $codexPackage = Get-AppxPackage -Name "OpenAI.Codex" |
            Sort-Object Version -Descending |
            Select-Object -First 1

        if (-not $codexPackage) {
            throw "The OpenAI.Codex package is not installed."
        }

        $manifest = Get-AppxPackageManifest -Package $codexPackage
        $applicationEntry = @($manifest.Package.Applications.Application) |
            Select-Object -First 1

        if (-not $applicationEntry) {
            throw "No application entry was found in the OpenAI.Codex package manifest."
        }

        $codexExecutable = Join-Path `
            $codexPackage.InstallLocation `
            ([string]$applicationEntry.Executable)

        if (-not (Test-Path -LiteralPath $codexExecutable)) {
            throw "Codex executable was not found: $codexExecutable"
        }

        Write-Host "Starting Codex with CDP on port $CodexPort..."
        Invoke-CommandInDesktopPackage `
            -PackageFamilyName $codexPackage.PackageFamilyName `
            -AppId ([string]$applicationEntry.Id) `
            -Command $codexExecutable `
            -Args "--remote-debugging-address=127.0.0.1 --remote-debugging-port=$CodexPort"
    }

    if ($includeAstronStudio -and -not $astronStudioReady) {
        Assert-PortAvailable -Port $AstronStudioPort

        $astronStudioExecutable = Resolve-AstronStudioExecutable

        Write-Host "Starting AstronStudio with CDP on port $AstronStudioPort..."
        Start-Process `
            -FilePath $astronStudioExecutable `
            -ArgumentList @(
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=$AstronStudioPort"
            )
    }

    if ($includeWorkBuddy -and -not $workBuddyReady) {
        Assert-PortAvailable -Port $WorkBuddyPort

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
}

Write-Host "Waiting for $Application CDP endpoints..."
$statuses = @()
if ($includeCodex) {
    $statuses += Wait-CdpStatus `
        -Name "Codex Desktop" `
        -Port $CodexPort `
        -ExpectedProcesses @("ChatGPT", "Codex") `
        -Timeout $TimeoutSeconds
}
if ($includeAstronStudio) {
    $statuses += Wait-CdpStatus `
        -Name "AstronStudio" `
        -Port $AstronStudioPort `
        -ExpectedProcesses @("AStudio", "AstronStudio", "Acode") `
        -Timeout $TimeoutSeconds
}
if ($includeWorkBuddy) {
    $statuses += Wait-CdpStatus `
        -Name "WorkBuddy" `
        -Port $WorkBuddyPort `
        -ExpectedProcesses @("WorkBuddy", "CodeBuddy") `
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
