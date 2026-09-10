[CmdletBinding()]
param(
    [ValidateSet("All", "Codex", "AstronStudio")]
    [string]$Application = "All",

    [ValidateRange(1024, 65535)]
    [int]$CodexPort = 9230,

    [ValidateRange(1024, 65535)]
    [int]$AstronStudioPort = 9240,

    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 20,

    [switch]$CheckOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$includeCodex = $Application -in @("All", "Codex")
$includeAstronStudio = $Application -in @("All", "AstronStudio")

if ($includeCodex -and $includeAstronStudio -and $CodexPort -eq $AstronStudioPort) {
    throw "CodexPort and AstronStudioPort must be different."
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
        "-TimeoutSeconds", $TimeoutSeconds
    )

    if ($CheckOnly) {
        $childArguments += "-CheckOnly"
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

if ($CheckOnly) {
    if (-not $codexReady) {
        throw "Codex Desktop is not exposing a valid CDP target on port $CodexPort."
    }
    if (-not $astronStudioReady) {
        throw "AstronStudio is not exposing a valid CDP target on port $AstronStudioPort."
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

    $processNames = @()
    if ($includeCodex -and -not $codexReady) {
        $processNames += "ChatGPT"
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
