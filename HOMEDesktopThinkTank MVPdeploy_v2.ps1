Write-Host ""
Write-Host "================================="
Write-Host " THINKTANK OS V2 DEPLOY"
Write-Host "================================="
Write-Host ""

Write-Host "Deploy Script Running..."

$Root = "$HOME\Desktop\ThinkTank MVP\vnext"

New-Item -ItemType Directory -Force -Path "$Root\js" | Out-Null

Write-Host ""
Write-Host "SUCCESS"
Write-Host ""