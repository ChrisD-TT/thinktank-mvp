window.RESERVOIR = {
    thermal:75,
    electrical:30,
    kinetic:10
};

function updateReservoir(){

    if(SENSOR_TWIN.cpuTemp > 80){

        RESERVOIR.thermal++;

    }
}
