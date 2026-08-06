window.VICS = {
    acquisition:40,
    stability:60,
    protection:80
};

function updateVICS(){

    if(RESERVOIR.thermal > 80){

        VICS.stability++;

    }
}
