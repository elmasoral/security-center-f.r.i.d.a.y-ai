$ErrorActionPreference = "Stop"

$Root = (Get-Location).Path
$UiPath = Join-Path $Root "ui.py"
$PatchRoot = Join-Path $Root "medpov_friday_ui_v3_file_badge_fix"
$BlockPath = Join-Path $PatchRoot "PATCH_FILES\ui_v3_refinement_block.py"
$AssetSrc = Join-Path $PatchRoot "PATCH_FILES\assets\medpov_security_badge.png"
$AssetDir = Join-Path $Root "assets"
$AssetDst = Join-Path $AssetDir "medpov_security_badge.png"

if (!(Test-Path $UiPath)) { throw "ui.py bulunamadı. Patch'i repo ana klasöründe çalıştır: C:\wamp64\www\med\medpov-friday-git" }
if (!(Test-Path $BlockPath)) { throw "Patch bloğu bulunamadı: $BlockPath" }
if (!(Test-Path $AssetSrc)) { throw "Security badge asset bulunamadı: $AssetSrc" }

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $Root "_backup_ui_v3_file_badge_$Stamp"
New-Item -ItemType Directory -Path $BackupDir | Out-Null
Copy-Item $UiPath (Join-Path $BackupDir "ui.py") -Force

if (!(Test-Path $AssetDir)) { New-Item -ItemType Directory -Path $AssetDir | Out-Null }
Copy-Item $AssetSrc $AssetDst -Force

# QGridLayout import güvenliği
$content = Get-Content $UiPath -Raw -Encoding UTF8
if ($content -notmatch "QGridLayout") {
    $content = $content -replace "QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,", "QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,"
}

$begin = "# === MEDPOV FRIDAY UI V3 FILE INPUT + SECURITY BADGE FIX ==="
$end = "# === /MEDPOV FRIDAY UI V3 FILE INPUT + SECURITY BADGE FIX ==="
$pattern = "(?s)\r?\n?$([regex]::Escape($begin)).*?$([regex]::Escape($end))\r?\n?"
$content = [regex]::Replace($content, $pattern, "`r`n")
$block = Get-Content $BlockPath -Raw -Encoding UTF8
$content = $content.TrimEnd() + "`r`n`r`n" + $block.Trim() + "`r`n"
Set-Content $UiPath $content -Encoding UTF8

Write-Host "[OK] ui.py patch uygulandı." -ForegroundColor Cyan
Write-Host "[OK] Badge asset kopyalandı: assets\medpov_security_badge.png" -ForegroundColor Cyan
Write-Host "[OK] Backup: $BackupDir" -ForegroundColor DarkCyan

try {
    python -m py_compile ui.py
    Write-Host "[OK] Python syntax kontrolü geçti." -ForegroundColor Green
} catch {
    Write-Host "[UYARI] py_compile hata verdi. Backup klasöründen geri dönebilirsin: $BackupDir" -ForegroundColor Yellow
    throw
}
