$word = New-Object -ComObject Word.Application
$word.Visible = $false

$docxDir = "C:\T1-2\contract-ai-sprint1\dataset\docx"
$pdfDir = "C:\T1-2\contract-ai-sprint1\dataset\pdf"

for ($i = 1; $i -le 10; $i++) {
    $num = "{0:D4}" -f $i
    $docPath = "$docxDir\contract_$num.docx"
    $pdfPath = "$pdfDir\contract_$num.pdf"
    
    if (Test-Path $docPath) {
        $doc = $word.Documents.Open($docPath)
        $doc.SaveAs([ref] $pdfPath, [ref] 17)  # 17 = PDF format
        $doc.Close()
        Write-Host "OK: contract_$num.docx -> PDF"
    }
}

$word.Quit()
Write-Host "Конвертация завершена!" -ForegroundColor Green
