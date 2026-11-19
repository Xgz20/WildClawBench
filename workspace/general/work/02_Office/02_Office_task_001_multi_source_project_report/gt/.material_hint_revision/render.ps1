param([string]$Root)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath($Root)
$renderRoot=Join-Path $taskRoot 'rendered'
$qaRoot=Join-Path $taskRoot 'qa_input'
New-Item -ItemType Directory -Force -Path $renderRoot,$qaRoot | Out-Null
$records=@()
$app=$null;$doc=$null
try {
    $app=New-Object -ComObject kwps.Application
    $app.Visible=$false;$app.DisplayAlerts=0
    foreach($source in Get-ChildItem -LiteralPath (Join-Path $taskRoot 'draft') -Filter '*.docx') {
        $copy=Join-Path $qaRoot $source.Name
        Copy-Item -LiteralPath $source.FullName -Destination $copy
        $pdf=Join-Path $renderRoot ($source.BaseName+'.pdf')
        $doc=$app.Documents.Open($copy,$false,$true)
        $pages=$doc.ComputeStatistics(2)
        $doc.ExportAsFixedFormat($pdf,17)
        $records+=@{file=$source.Name;engine='WPS Writer';version=$app.Version;pages=$pages;pdf=$pdf}
        $doc.Close(0);$doc=$null
        Write-Output ($source.Name+' rendered '+$pages+' pages')
    }
} finally {
    if($null -ne $doc){$doc.Close(0)}
    if($null -ne $app){$app.Quit()}
}
$app=$null;$deck=$null
try {
    $app=New-Object -ComObject kwpp.Application
    foreach($variant in @('original','draft')) {
        $source=Get-ChildItem -LiteralPath (Join-Path $taskRoot $variant) -Filter '*.pptx' | Select-Object -First 1
        $copy=Join-Path $qaRoot ($variant+'.pptx')
        Copy-Item -LiteralPath $source.FullName -Destination $copy
        $deck=$app.Presentations.Open($copy,$true,$false,$false)
        $slidesDir=Join-Path $renderRoot ($variant+'_slides')
        New-Item -ItemType Directory -Force -Path $slidesDir | Out-Null
        for($i=1;$i -le $deck.Slides.Count;$i++) {
            $deck.Slides.Item($i).Export((Join-Path $slidesDir ('slide-'+$i+'.png')),'PNG',1440,810)
        }
        $records+=@{file=$source.Name;variant=$variant;engine='WPS Presentation';version=$app.Version;slides=$deck.Slides.Count;directory=$slidesDir}
        $deck.Close();$deck=$null
        Write-Output ($variant+' PPT rendered')
    }
} finally {
    if($null -ne $deck){$deck.Close()}
    if($null -ne $app){$app.Quit()}
}
$app=$null;$book=$null
try {
    $app=New-Object -ComObject ket.Application
    $app.Visible=$false;$app.DisplayAlerts=$false
    $source=Get-ChildItem -LiteralPath (Join-Path $taskRoot 'draft') -Filter '*.xlsx' | Select-Object -First 1
    $copy=Join-Path $qaRoot $source.Name
    Copy-Item -LiteralPath $source.FullName -Destination $copy
    $book=$app.Workbooks.Open($copy,0,$true)
    for($i=1;$i -le $book.Worksheets.Count;$i++) {
        $sheet=$book.Worksheets.Item($i)
        $visible=$sheet.Visible
        $sheet.Visible=-1
        $sheet.PageSetup.Orientation=2
        $sheet.PageSetup.Zoom=$false
        $sheet.PageSetup.FitToPagesWide=1
        $sheet.PageSetup.FitToPagesTall=1
        $pdf=Join-Path $renderRoot ('sheet-'+$i+'.pdf')
        $sheet.Range('A1:I8').ExportAsFixedFormat(0,$pdf)
        $records+=@{sheet=$sheet.Name;engine='WPS Spreadsheets';version=$app.Version;original_visible=$visible;pdf=$pdf}
        $sheet.Visible=$visible
        Write-Output ('Sheet '+$i+' rendered')
    }
    $book.Close($false);$book=$null
} finally {
    if($null -ne $book){$book.Close($false)}
    if($null -ne $app){$app.Quit()}
}
$records | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskRoot 'native_validation.json') -Encoding utf8
