/* Few functions to handle range-inputs actions (such as setting time or date) */


/* Update input's value on range thumb moving */
function updateTime(e, input_id, seconds=false) {
    if (seconds == true) {
        var time_input = document.getElementById(input_id);
        time_input.value = getStringTime(e.value);
        return;
    }
    var hours = parseInt(e.value / 60);
    var minutes = e.value - hours * 60;
    if (hours < 10 || hours == 0) {
    hours = "0" + hours.toString();
    };
    if (minutes < 10 || minutes == 0) {
    minutes = "0" + minutes.toString();
    };
    var time_input = document.getElementById(input_id);
    time_input.value = hours + ":" + minutes;
};

/* Return time in "HH:mm:ss" format from seconds string */
function getStringTime(total_seconds) {
    var hours = parseInt(total_seconds / 3600);
    var minutes = parseInt((total_seconds - hours * 3600) / 60);
    var seconds = total_seconds - hours * 3600 - minutes * 60;
    if (hours < 10 || hours == 0) {
    hours = "0" + hours.toString();
    };
    if (minutes < 10 || minutes == 0) {
    minutes = "0" + minutes.toString();
    };

    if (seconds < 10 || seconds == 0) {
    seconds = "0" + seconds.toString();
    };
    var res = hours + ":" + minutes + ":" + seconds;
    return res;
};

/* Return int seconds from string time "HH:mm:ss" format */
function stringTimeToSecs(string_time) {
var arr_string_time = string_time.split(":");
var hours = parseInt(arr_string_time[0]);
var minutes = parseInt(arr_string_time[1]);
var seconds = parseInt(arr_string_time[2]);

var result = hours*3600 + minutes*60 + seconds;
return result;
}

/* Moving range thumb to nearest value when time input filled by user manually */
function updateRange(e, range_id, seconds=false) {
    var time_input = e.value.split(':');
    var range_input = document.getElementById(range_id);

    /* If input is empty or cleared by browser X widget - pass work to resetRange function below */
    if (time_input == "") {
        return;
    }
    if (seconds == true) {
        var seconds = parseInt(time_input[0] * 3600) + parseInt(time_input[1] * 60) + parseInt(time_input[2]);
        range_input.value = seconds;
    }
    else {
        var seconds = parseInt(time_input[0] * 60) + parseInt(time_input[1]);
        range_input.value = seconds;
    }
};


function resetRange(e, range_id) {
    var range_input = document.getElementById(range_id);
    range_input.value = 0;
};