param([string]$BackupDir = "./backups")
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = Join-Path $BackupDir "knowtale_$timestamp"
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
if (Test-Path "data/knowtale.db") {
    Copy-Item "data/knowtale.db" (Join-Path $backupPath "knowtale.db")
    Write-Host "✓ 数据库已备份"
}
if (Test-Path "uploads") {
    Copy-Item -Recurse "uploads" (Join-Path $backupPath "uploads\")
    Write-Host "✓ 上传文件已备份"
}
Compress-Archive -Path "$backupPath\*" -DestinationPath "$BackupDir\knowtale_$timestamp.zip"
Remove-Item -Recurse $backupPath
Write-Host "✓ 备份完成: $BackupDir\knowtale_$timestamp.zip"
