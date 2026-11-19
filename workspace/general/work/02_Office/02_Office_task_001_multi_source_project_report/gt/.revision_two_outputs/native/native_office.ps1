param([Parameter(Mandatory=$true)][string]$InputPath,[Parameter(Mandatory=$true)][string]$OutputDir,[switch]$EditProbe,[Parameter(Mandatory=$true)][string]$ControlPath)
$ErrorActionPreference='Stop'
$candidatePath=[IO.Path]::GetFullPath($InputPath)
$privateDir=[IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $privateDir | Out-Null
$ext=[IO.Path]::GetExtension($candidatePath).ToLower()
$receipt=@{input=$candidatePath;input_sha256=(Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLower();status='evaluator_error';engine='WPS';phase='launch';edited=$false}
$app=$null;$doc=$null
try {
    if($ext -eq '.docx') {
        $app=New-Object -ComObject kwps.Application
        $app.Visible=$false
        $app.DisplayAlerts=0
        $receipt.version=$app.Version
        $control=$ControlPath
        $doc=$app.Documents.Open([IO.Path]::GetFullPath($control),$false,$true)
        $receipt.control_opened=$true
        $doc.Close(0);$doc=$null
        $receipt.phase='open'
        $doc=$app.Documents.Open($candidatePath,$false,$true)
        $receipt.opened=$true
        $receipt.pages=$doc.ComputeStatistics(2)
        $receipt.phase='export'
        $pdf=Join-Path $privateDir (([IO.Path]::GetFileNameWithoutExtension($candidatePath))+'.pdf')
        $doc.ExportAsFixedFormat($pdf,17)
        $receipt.pdf=$pdf
        $doc.Close(0);$doc=$null
        if($EditProbe) {
            $receipt.phase='edit_copy'
            $copy=Join-Path $privateDir 'edit_probe.docx'
            Copy-Item -LiteralPath $candidatePath -Destination $copy -Force
            $doc=$app.Documents.Open($copy,$false,$false)
            $receipt.tables=$doc.Tables.Count
            if($doc.Tables.Count -lt 2 -or $doc.Paragraphs.Count -lt 4){throw 'candidate lacks editable body or two required tables'}
            $token='EVAL_EDIT_BODY_20260922'
            $bodyIndex=0
            for($ix=1;$ix -le $doc.Paragraphs.Count;$ix++){
                $para=$doc.Paragraphs.Item($ix)
                if($ix -gt 1 -and $para.Range.Text.Trim().Length -gt 0 -and -not $para.Range.Information(12)){$bodyIndex=$ix;break}
            }
            if($bodyIndex -eq 0){throw 'candidate lacks editable body or two required tables'}
            $doc.Paragraphs.Item($bodyIndex).Range.InsertBefore($token)
            $tableToken='EVAL_EDIT_CELL_20260922'
            $editedTables=@()
            for($ix=1;$ix -le $doc.Tables.Count;$ix++){
                if($doc.Tables.Item($ix).Range.Text -match 'XQ-\d{3}'){
                    $doc.Tables.Item($ix).Cell(2,1).Range.InsertBefore($tableToken)
                    $editedTables+=,$ix
                }
            }
            if($editedTables.Count -lt 2){throw 'candidate lacks editable body or two required tables'}
            $doc.Save();$doc.Close(0);$doc=$null
            $receipt.phase='reopen'
            $doc=$app.Documents.Open($copy,$false,$true)
            $receipt.body_persisted=$doc.Content.Text.Contains($token)
            $receipt.table_checks=@()
            foreach($ix in $editedTables){$receipt.table_checks+=,@{table=$ix;persisted=$doc.Tables.Item($ix).Cell(2,1).Range.Text.Contains($tableToken)}}
            $receipt.edited=$receipt.body_persisted -and @($receipt.table_checks | Where-Object {-not $_.persisted}).Count -eq 0
            $receipt.copy=$copy
        }
    } else {throw "unsupported extension $ext"}
    $receipt.status='pass';$receipt.phase='complete'
} catch {$receipt.error=$_.Exception.Message} finally {
    if($null -ne $doc){try{$doc.Close(0)}catch{try{$doc.Close()}catch{}}}
    if($null -ne $app){try{$app.Quit()}catch{}}
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $privateDir 'native_receipt.json') -Encoding UTF8
}
$receipt | ConvertTo-Json -Depth 8
if($receipt.status -ne 'pass'){exit 2}
