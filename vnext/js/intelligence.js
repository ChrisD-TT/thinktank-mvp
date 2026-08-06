window.INTELLIGENCE = {
    summary:""
};

function updateIntelligence(){

    if(SENSOR_TWIN.cpuTemp > 85){

        INTELLIGENCE.summary =
            "Thermal opportunity elevated.";

    }else{

        INTELLIGENCE.summary =
            "System operating normally.";
    }
}
