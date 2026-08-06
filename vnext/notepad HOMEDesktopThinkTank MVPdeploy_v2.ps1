$Root = "$HOME\Desktop\ThinkTank MVP\vnext"

New-Item -ItemType Directory -Force -Path "$Root\js" | Out-Null
New-Item -ItemType Directory -Force -Path "$Root\css" | Out-Null

# CSS

@'
body{
    background:#030a16;
    color:white;
    font-family:Segoe UI,sans-serif;
    padding:20px;
}

h1{
    color:#34d399;
}

.dashboard{
    display:grid;
    grid-template-columns:1fr 2fr 1fr;
    gap:15px;
}

.panel{
    background:#071626;
    border-radius:12px;
    padding:20px;
}

.full{
    grid-column:1 / -1;
}
'@ | Set-Content "$Root\css\thinktank_os.css"

# APP

@'
window.TTOS = {
    version:"1.0",
    state:"ONLINE"
};

function tick(){
    simulateTelemetry();
    updateAgent();
    updateReservoir();
    updateVICS();
    updateIntelligence();
    renderDashboard();
}

setInterval(tick,2000);
tick();
'@ | Set-Content "$Root\js\app.js"

# SENSOR TWIN

@'
window.SENSOR_TWIN = {
    cpuTemp:84,
    cpuLoad:91,
    ramUsage:67,
    batteryPct:88,
    recoveryScore:78
};

function simulateTelemetry(){

    SENSOR_TWIN.cpuTemp =
        65 + Math.floor(Math.random()*25);

    SENSOR_TWIN.cpuLoad =
        20 + Math.floor(Math.random()*80);

    SENSOR_TWIN.ramUsage =
        30 + Math.floor(Math.random()*60);

    SENSOR_TWIN.recoveryScore =
        Math.floor(
            (
                SENSOR_TWIN.cpuTemp +
                SENSOR_TWIN.cpuLoad +
                SENSOR_TWIN.ramUsage
            ) / 3
        );
}
'@ | Set-Content "$Root\js\sensor_twin.js"

# AGENT

@'
window.AGENT = {
    objective:"Maximize Thermal Recovery",
    confidence:96,
    recommendation:"Standby"
};

function updateAgent(){

    if(SENSOR_TWIN.cpuTemp > 85)
        AGENT.recommendation =
            "Increase Stability Reserve";
    else
        AGENT.recommendation =
            "Maintain Current State";
}
'@ | Set-Content "$Root\js\thinktank_agent.js"

# RESERVOIR

@'
window.RESERVOIR = {
    thermal:75,
    electrical:30,
    kinetic:10
};

function updateReservoir(){
    if(SENSOR_TWIN.cpuTemp > 80)
        RESERVOIR.thermal++;
}
'@ | Set-Content "$Root\js\reservoir.js"

# VICS

@'
window.VICS = {
    acquisition:40,
    stability:60,
    protection:80
};

function updateVICS(){
    if(RESERVOIR.thermal > 80)
        VICS.stability++;
}
'@ | Set-Content "$Root\js\vics.js"

# INTELLIGENCE

@'
window.INTELLIGENCE = {
    summary:""
};

function updateIntelligence(){

    if(SENSOR_TWIN.cpuTemp > 85)
        INTELLIGENCE.summary =
            "Thermal opportunity elevated.";
    else
        INTELLIGENCE.summary =
            "System operating normally.";
}
'@ | Set-Content "$Root\js\intelligence.js"

# RENDER

@'
function renderDashboard(){

    document.getElementById("cpuTemp").innerText =
        "CPU Temp: " + SENSOR_TWIN.cpuTemp + "°C";

    document.getElementById("cpuLoad").innerText =
        "CPU Load: " + SENSOR_TWIN.cpuLoad + "%";

    document.getElementById("ramUsage").innerText =
        "RAM Usage: " + SENSOR_TWIN.ramUsage + "%";

    document.getElementById("recoveryScore").innerText =
        "Recovery Score: " + SENSOR_TWIN.recoveryScore;

    document.getElementById("agentObjective").innerText =
        AGENT.objective;

    document.getElementById("agentRecommendation").innerText =
        AGENT.recommendation;

    document.getElementById("agentConfidence").innerText =
        AGENT.confidence + "%";

    document.getElementById("thermalReservoir").innerText =
        "Thermal: " + RESERVOIR.thermal;

    document.getElementById("electricalReservoir").innerText =
        "Electrical: " + RESERVOIR.electrical;

    document.getElementById("kineticReservoir").innerText =
        "Kinetic: " + RESERVOIR.kinetic;

    document.getElementById("vicsA").innerText =
        "Acquisition: " + VICS.acquisition;

    document.getElementById("vicsB").innerText =
        "Stability: " + VICS.stability;

    document.getElementById("vicsC").innerText =
        "Protection: " + VICS.protection;

    document.getElementById("intelligenceSummary").innerText =
        INTELLIGENCE.summary;
}
'@ | Set-Content "$Root\js\render.js"

# HTML

@'
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>ThinkTank OS</title>

/thinktank_os.css">

</head>
<body>

<h1>ThinkTank OS</h1>
<p>Sensor Twin Engine • Autonomous Recovery Platform</p>

<div class="dashboard">

<section class="panel">
<h2>ThinkTank Agent</h2>
<div id="agentObjective"></div>
<div id="agentRecommendation"></div>
<div id="agentConfidence"></div>
</section>

<section class="panel">
<h2>Sensor Twin Core</h2>
<div id="cpuTemp"></div>
<div id="cpuLoad"></div>
<div id="ramUsage"></div>
<div id="recoveryScore"></div>
</section>

<section class="panel">
<h2>Thermal Recovery Reservoir</h2>
<div id="thermalReservoir"></div>
<div id="electricalReservoir"></div>
<div id="kineticReservoir"></div>
</section>

<section class="panel full">
<h2>VICS Core</h2>
<div id="vicsA"></div>
<div id="vicsB"></div>
<div id="vicsC"></div>
</section>

<section class="panel full">
<h2>Sensor Twin Intelligence</h2>
<div id="intelligenceSummary"></div>
</section>

</div>

ensor_twin.js"></script>
.js"></script>
js/reservoir.js
js/vics.js
elligence.js"></script>
js/render.js
js/app.js

</body>
</html>
'@ | Set-Content "$Root\thinktank_os_v2.html"

Write-Host ""
Write-Host "ThinkTank OS V2 Built"
Write-Host ""