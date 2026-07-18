$root = Split-Path -Parent $PSScriptRoot
$docxDir = Join-Path $root "dataset\docx"
$pdfDir  = Join-Path $root "dataset\pdf"

if (-not (Test-Path $pdfDir)) {
    New-Item -ItemType Directory -Path $pdfDir | Out-Null
}

$word = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false

    for ($i = 1; $i -le 10; $i++) {
        $num = "{0:D4}" -f $i
        $docPath = Join-Path $docxDir "contract_$num.docx"
        $pdfPath = Join-Path $pdfDir "contract_$num.pdf"
        
        if (Test-Path $docPath) {
            try {
                $doc = $word.Documents.Open($docPath)
                # Исправленный синтаксис SaveAs
                [ref]$saveFormat = "microsoft.office.interop.word.WdSaveFormat" -as [type]
                $doc.SaveAs($pdfPath, [ref]$saveFormat::wdFormatPDF)
                $doc.Close()
                Write-Host "OK: contract_$num.docx -> PDF" -ForegroundColor Green
            }
            catch {
                Write-Host "ERROR: contract_$num.docx — $_" -ForegroundColor Red
            }
        }
        else {
            Write-Host "SKIP: contract_$num.docx не найден" -ForegroundColor Yellow
        }
    }
    Write-Host "`nКонвертация завершена!" -ForegroundColor Green
}
finally {
    if ($word) {
        $word.Quit()
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
        Write-Host "Word закрыт."
    }
}