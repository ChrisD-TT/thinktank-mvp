$Root = "$HOME\Desktop\ThinkTank MVP\vnext"

Write-Host ""
Write-Host "================================"
Write-Host " THINKTANK OS BOOTSTRAP"
Write-Host "================================"
Write-Host ""

$Folders = @(
    "$Root\css",
    "$Root\js",
    "$Root\telemetry",
    "$Root\modules"
)

foreach($Folder in $Folders){
    New-Item -ItemType Directory -Force -Path $Folder | Out-Null
}

Set-Content "$Root\js\app.js" @'
window.TTOS = {
    version: "0.3",
    state: "ONLINE",
    tick: 0
};

console.log("ThinkTank OS Loaded");
'@

Set-Content "$Root\js\sensor_twin.js" @'
window.SENSOR_TWIN = {
    cpuTemp: 84,
    cpuLoad: 91,
    ramUsage: 67,
    batteryPct: 88
};

console.log("Sensor Twin Loaded");
'@

Write-Host ""
Write-Host "ThinkTank OS files created."
Write-Host ""
Write-Host $Root
