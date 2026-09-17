param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [Parameter(Mandatory = $true)][string]$Folder,
    [Parameter(Mandatory = $true)][int]$TimeoutSeconds
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class NativeFolderDialogControl {
    public delegate bool EnumWindowCallback(IntPtr window, IntPtr state);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool EnumWindows(EnumWindowCallback callback, IntPtr state);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetClassNameW(IntPtr window, StringBuilder className, int capacity);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsWindowVisible(IntPtr window);

    [DllImport("user32.dll", EntryPoint = "SendMessageW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr SendTextMessage(IntPtr window, uint message, IntPtr parameter, string value);

    [DllImport("user32.dll", EntryPoint = "SendMessageW", SetLastError = true)]
    public static extern IntPtr SendButtonMessage(IntPtr window, uint message, IntPtr parameter, IntPtr value);

    [DllImport("user32.dll", EntryPoint = "SendMessageW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr ReadTextMessage(IntPtr window, uint message, IntPtr capacity, StringBuilder value);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsWindowEnabled(IntPtr window);

    public static long[] FindVisibleTopLevelDialogs(int[] processIds) {
        var expected = new HashSet<int>(processIds ?? new int[0]);
        var matches = new List<long>();
        EnumWindows(delegate(IntPtr window, IntPtr state) {
            uint processId;
            GetWindowThreadProcessId(window, out processId);
            if (!expected.Contains((int)processId) || !IsWindowVisible(window)) return true;
            var className = new StringBuilder(256);
            GetClassNameW(window, className, className.Capacity);
            if (className.ToString() == "#32770") matches.Add(window.ToInt64());
            return true;
        }, IntPtr.Zero);
        return matches.ToArray();
    }
}
"@

$WmSetText = 0x000C
$WmGetText = 0x000D
$BmClick = 0x00F5

function Get-NativeHandle([System.Windows.Automation.AutomationElement]$Element) {
    $handle = [IntPtr]$Element.Current.NativeWindowHandle
    if ($handle -eq [IntPtr]::Zero) {
        throw "The native folder dialog control does not expose a window handle"
    }
    return $handle
}

function Set-NativeText(
    [System.Windows.Automation.AutomationElement]$Element,
    [string]$Value
) {
    $handle = Get-NativeHandle $Element
    [void][NativeFolderDialogControl]::SendTextMessage($handle, $WmSetText, [IntPtr]::Zero, $Value)
    $readback = [System.Text.StringBuilder]::new(32768)
    [void][NativeFolderDialogControl]::ReadTextMessage(
        $handle,
        $WmGetText,
        [IntPtr]$readback.Capacity,
        $readback
    )
    return $readback.ToString()
}

function Invoke-NativeButton([System.Windows.Automation.AutomationElement]$Element) {
    $handle = Get-NativeHandle $Element
    if (-not [NativeFolderDialogControl]::IsWindowEnabled($handle)) {
        throw "The native folder dialog button is disabled"
    }
    [void][NativeFolderDialogControl]::SendButtonMessage(
        $handle,
        $BmClick,
        [IntPtr]::Zero,
        [IntPtr]::Zero
    )
}

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
    $matches = @()
    $dialogHandles = [NativeFolderDialogControl]::FindVisibleTopLevelDialogs($ProcessIds)
    foreach ($handleValue in $dialogHandles) {
        $window = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$handleValue)
        if (-not $window -or $window.Current.IsOffscreen) { continue }
        $elements = $window.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        $folderEdits = @($elements | Where-Object {
            -not $_.Current.IsOffscreen -and
            @("1148", "1152") -contains $_.Current.AutomationId -and
            $_.Current.ClassName -eq "Edit" -and
            $_.Current.NativeWindowHandle -ne 0
        })
        $confirmButtons = @($elements | Where-Object {
            -not $_.Current.IsOffscreen -and
            $_.Current.AutomationId -eq "1" -and
            $_.Current.ClassName -eq "Button" -and
            $_.Current.NativeWindowHandle -ne 0
        })
        $cancelButtons = @($elements | Where-Object {
            -not $_.Current.IsOffscreen -and
            $_.Current.AutomationId -eq "2" -and
            $_.Current.ClassName -eq "Button" -and
            $_.Current.NativeWindowHandle -ne 0
        })
        if ($folderEdits.Count -eq 1 -and $confirmButtons.Count -eq 1 -and $cancelButtons.Count -eq 1) {
            $matches += [pscustomobject]@{
                Window = $window
                FileNameEdit = $folderEdits[0]
                ConfirmButton = $confirmButtons[0]
                CancelButton = $cancelButtons[0]
            }
        }
    }
    return @($matches)
}

$resolvedApp = (Resolve-Path -LiteralPath $AppPath).Path
$resolvedFolder = (Resolve-Path -LiteralPath $Folder).Path
if (-not (Test-Path -LiteralPath $resolvedFolder -PathType Container)) {
    throw "Candidate directory does not exist: $resolvedFolder"
}
$processIds = Get-ExactAppProcessIds $resolvedApp
if ($processIds.Count -eq 0) {
    throw "No QwenWork process exactly matches the executable path: $resolvedApp"
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$dialog = $null
do {
    $dialogs = @(Get-FolderDialog $processIds)
    if ($dialogs.Count -gt 1) {
        throw "Multiple QwenWork folder dialogs were found; refusing an ambiguous selection"
    }
    if ($dialogs.Count -eq 1) {
        $dialog = $dialogs[0]
        break
    }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)
if (-not $dialog) { throw "Timed out waiting for the QwenWork folder dialog" }

try {
    $readback = Set-NativeText $dialog.FileNameEdit $resolvedFolder
    if (-not $readback.Equals($resolvedFolder, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The folder dialog path readback does not match the requested path"
    }
    Invoke-NativeButton $dialog.ConfirmButton

    do {
        Start-Sleep -Milliseconds 100
        $remaining = @(Get-FolderDialog $processIds)
        if ($remaining.Count -eq 0) { break }
    } while ([DateTime]::UtcNow -lt $deadline)
    if (@(Get-FolderDialog $processIds).Count -ne 0) {
        throw "The folder dialog did not close after submitting the target directory"
    }
} catch {
    $selectionError = $_
    try {
        Invoke-NativeButton $dialog.CancelButton
    } catch {
        # Preserve the original selection error if closing the dialog also fails.
    }
    throw $selectionError
}

[pscustomobject]@{
    status = "selected"
    method = "windows-uia-common-item-dialog"
    folder = $resolvedFolder
    app_path = $resolvedApp
} | ConvertTo-Json -Compress
