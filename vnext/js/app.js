window.TTOS = {
    version: "1.0",
    state: "ONLINE",
    tick: 0
};

function systemTick(){
    TTOS.tick++;

    if(window.simulateTelemetry)
        simulateTelemetry();

    if(window.updateAgent)
        updateAgent();

    if(window.updateReservoir)
        updateReservoir();

    if(window.updateVICS)
        updateVICS();

    if(window.updateIntelligence)
        updateIntelligence();

    if(window.renderDashboard)
        renderDashboard();
}

setInterval(systemTick,2000);

systemTick();
