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

$ErrorActionPreference = "Stop"

$skillScript = Join-Path `
    $PSScriptRoot `
    "..\tools\report\skills\run-web-e2e\scripts\start_windows_desktop_debug.ps1"

if (-not (Test-Path -LiteralPath $skillScript)) {
    throw "run-web-e2e desktop debug helper was not found: $skillScript"
}

try {
    & $skillScript @PSBoundParameters
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
