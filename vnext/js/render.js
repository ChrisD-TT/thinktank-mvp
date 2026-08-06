function renderDashboard(){

    document.getElementById("cpuTemp").textContent =
        "CPU Temp: " + SENSOR_TWIN.cpuTemp + "°C";

    document.getElementById("cpuLoad").textContent =
        "CPU Load: " + SENSOR_TWIN.cpuLoad + "%";

    document.getElementById("ramUsage").textContent =
        "RAM Usage: " + SENSOR_TWIN.ramUsage + "%";

    document.getElementById("recoveryScore").textContent =
        "Recovery Score: " + SENSOR_TWIN.recoveryScore;

    document.getElementById("agentObjective").textContent =
        AGENT.objective;

    document.getElementById("agentRecommendation").textContent =
        AGENT.recommendation;

    document.getElementById("agentConfidence").textContent =
        AGENT.confidence + "%";

    document.getElementById("thermalReservoir").textContent =
        "Thermal: " + RESERVOIR.thermal;

    document.getElementById("electricalReservoir").textContent =
        "Electrical: " + RESERVOIR.electrical;

    document.getElementById("kineticReservoir").textContent =
        "Kinetic: " + RESERVOIR.kinetic;

    document.getElementById("vicsA").textContent =
        "Layer A • Acquisition: " + VICS.acquisition;

    document.getElementById("vicsB").textContent =
        "Layer B • Stability: " + VICS.stability;

    document.getElementById("vicsC").textContent =
        "Layer C • Protection: " + VICS.protection;

    document.getElementById("intelligenceSummary").textContent =
        INTELLIGENCE.summary;
}
