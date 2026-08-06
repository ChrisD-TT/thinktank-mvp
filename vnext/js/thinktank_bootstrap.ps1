$Root = "C:\Users\ChrisDovico\Desktop\ThinkTank MVP\vnext"

Write-Host ""
Write-Host "================================="
Write-Host "THINKTANK OS BOOTSTRAP"
Write-Host "================================="
Write-Host ""

# -----------------------------
# FOLDERS
# -----------------------------

$Folders = @(
    "$Root",
    "$Root\css",
    "$Root\js",
    "$Root\telemetry",
    "$Root\modules",
    "$Root\modules\agent",
    "$Root\modules\vics",
    "$Root\modules\reservoir",
    "$Root\modules\intelligence",
    "$Root\modules\log"
)

foreach($Folder in $Folders){

    New-Item `
        -ItemType Directory `
        -Force `
        -Path $Folder | Out-Null

}

# -----------------------------
# CORE FILES
# -----------------------------

$Files = @(

    "$Root\thinktank_os.html",

    "$Root\css\thinktank_os.css",

    "$Root\js\app.js",

    "$Root\js\sensor_twin.js",

    "$Root\js\thinktank_agent.js",

    "$Root\js\reservoir.js",

    "$Root\js\vics.js",

    "$Root\js\intelligence.js",

    "$Root\js\mission_log.js",

    "$Root\telemetry\telemetry_server.py"

)

foreach($File in $Files){

    if(!(Test-Path $File)){

        New-Item `
            -ItemType File `
            -Force `
            -Path $File | Out-Null

    }

}

# -----------------------------
# APP.JS
# -----------------------------

@'
window.TTOS = {

    version:"0.2",

    state:"ONLINE",

    tick:0

};

function systemTick(){

    TTOS.tick++;

    if(window.updateSensorTwin)
        updateSensorTwin();

    if(window.updateAgent)
        updateAgent();

    if(window.updateReservoir)
        updateReservoir();

    if(window.updateVICS)
        updateVICS();

    if(window.updateIntelligence)
        updateIntelligence();

}

setInterval(systemTick,2000);
'@ | Set-Content "$Root\js\app.js"

# -----------------------------
# TELEMETRY SERVER
# -----------------------------

@'
from flask import Flask, jsonify
import psutil

app = Flask(__name__)

@app.route("/telemetry")
def telemetry():

    try:
        battery = psutil.sensors_battery()

        battery_pct = (
            battery.percent
            if battery
            else 100
        )

    except:
        battery_pct = 100

    return jsonify({

        "cpuLoad":
            psutil.cpu_percent(),

        "ramUsage":
            psutil.virtual_memory().percent,

        "batteryPct":
            battery_pct

    })

app.run(
    host="0.0.0.0",
    port=5000,
    debug=False
)
'@ | Set-Content "$Root\telemetry\telemetry_server.py"

# -----------------------------
# LAUNCHER
# -----------------------------

@'
@echo off

echo.
echo THINKTANK OS STARTING...
echo.

cd /d "%~dp0"

start "" "vnext\thinktank_os.html"

echo Dashboard Launched.
pause
'@ | Set-Content "C:\Users\ChrisDovico\Desktop\ThinkTank MVP\start_thinktank.bat"

Write-Host ""
Write-Host "ThinkTank OS Structure Ready"
Write-Host ""
Write-Host $Root
Write-Host ""