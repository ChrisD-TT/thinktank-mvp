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
