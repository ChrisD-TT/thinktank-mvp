window.AGENT = {
    objective:"Maximize Thermal Recovery",
    confidence:96,
    recommendation:"Standby"
};

function updateAgent(){

    if(SENSOR_TWIN.cpuTemp > 85){

        AGENT.recommendation =
            "Increase Stability Reserve";

    }else{

        AGENT.recommendation =
            "Maintain Current State";
    }
}
