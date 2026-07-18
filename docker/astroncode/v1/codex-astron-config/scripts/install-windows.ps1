$ErrorActionPreference = "Stop"

$SourceDir = Split-Path -Parent $PSScriptRoot
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".zcode" }
$TomlCatalogPath = (Join-Path $CodexHome "astron-spark.json") -replace "\\", "/"
$CatalogPath = Join-Path $CodexHome "astron-spark.json"
$ProfilePath = Join-Path $CodexHome "astron-spark.config.toml"
$ConfigPath = Join-Path $CodexHome "config.toml"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null
Copy-Item -Force (Join-Path $SourceDir "config/astron-spark.json") $CatalogPath

$Profile = Get-Content -Raw (Join-Path $SourceDir "config/astron-spark.config.toml.template")
$Profile = $Profile.Replace("__MODEL_CATALOG_PATH__", $TomlCatalogPath)
[System.IO.File]::WriteAllText($ProfilePath, $Profile, $Utf8NoBom)

$ProviderHeader = "[model_providers.astron-spark]"
if (-not (Select-String -Path $ConfigPath -Pattern "^\[model_providers\.astron-spark\]$" -Quiet -ErrorAction SilentlyContinue)) {
  $Provider = Get-Content -Raw (Join-Path $SourceDir "config/provider.toml")
  if (Test-Path $ConfigPath) {
    [System.IO.File]::AppendAllText($ConfigPath, "`r`n$Provider", $Utf8NoBom)
  } else {
    [System.IO.File]::WriteAllText($ConfigPath, $Provider, $Utf8NoBom)
  }
}

Write-Output "已安装 Astron Spark 配置：$CodexHome"
