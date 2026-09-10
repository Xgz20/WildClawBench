param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [Parameter(Mandatory = $true)][string]$Folder,
    [Parameter(Mandatory = $true)][int]$TimeoutSeconds
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-ExactAppProcessIds([string]$ExpectedPath) {
    $normalized = [System.IO.Path]::GetFullPath($ExpectedPath)
    $matches = Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and
        [System.IO.Path]::GetFullPath($_.ExecutablePath).Equals(
            $normalized,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    }
    return @($matches | ForEach-Object { [int]$_.ProcessId })
}

function Get-FolderDialog([int[]]$ProcessIds) {
    $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition
    )
    $matches = @()
    foreach ($window in $windows) {
        if ($ProcessIds -notcontains $window.Current.ProcessId -or $window.Current.IsOffscreen) { continue }
        $fileNameEdit = $window.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
                "1148"
            )
        )
        $confirmButton = $window.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
                "1"
            )
        )
        if ($fileNameEdit -and $confirmButton) {
            $matches += [pscustomobject]@{
                Window = $window
                FileNameEdit = $fileNameEdit
                ConfirmButton = $confirmButton
            }
        }
    }
    return @($matches)
}

$resolvedApp = (Resolve-Path -LiteralPath $AppPath).Path
$resolvedFolder = (Resolve-Path -LiteralPath $Folder).Path
if (-not (Test-Path -LiteralPath $resolvedFolder -PathType Container)) {
    throw "目标评分目录不存在：$resolvedFolder"
}
$processIds = Get-ExactAppProcessIds $resolvedApp
if ($processIds.Count -eq 0) {
    throw "找不到与主程序路径精确匹配的 Codex Desktop 进程：$resolvedApp"
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$dialog = $null
do {
    $dialogs = @(Get-FolderDialog $processIds)
    if ($dialogs.Count -gt 1) {
        throw "检测到多个 Codex Desktop 原生文件夹选择器，拒绝选择不唯一窗口"
    }
    if ($dialogs.Count -eq 1) {
        $dialog = $dialogs[0]
        break
    }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)
if (-not $dialog) { throw "等待 Codex Desktop 原生文件夹选择器超时" }

try {
    $valuePattern = $dialog.FileNameEdit.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern
    )
    $valuePattern.SetValue($resolvedFolder)
    if (-not $valuePattern.Current.Value.Equals($resolvedFolder, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "原生文件夹选择器路径回读不一致"
    }
    if (-not $dialog.ConfirmButton.Current.IsEnabled) {
        throw "选择目标目录后确认按钮仍不可用"
    }
    $invokePattern = $dialog.ConfirmButton.GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    )
    $invokePattern.Invoke()

    do {
        Start-Sleep -Milliseconds 100
        $remaining = @(Get-FolderDialog $processIds)
        if ($remaining.Count -eq 0) { break }
    } while ([DateTime]::UtcNow -lt $deadline)
    if (@(Get-FolderDialog $processIds).Count -ne 0) {
        throw "提交目录后原生文件夹选择器未关闭"
    }
} catch {
    $selectionError = $_
    try {
        $windowPattern = $dialog.Window.GetCurrentPattern(
            [System.Windows.Automation.WindowPattern]::Pattern
        )
        $windowPattern.Close()
    } catch {
        # 保留原始错误；关闭失败不能掩盖文件夹选择失败。
    }
    throw $selectionError
}

[pscustomobject]@{
    status = "selected"
    method = "windows-uia-common-item-dialog"
    folder = $resolvedFolder
    app_path = $resolvedApp
} | ConvertTo-Json -Compress
