var CURRENT_SHARE_MATCH = null;
var CURRENT_SHARE_RESULT = null;

// Function to handle shared result or shared moment on page's open
function showShared() {
    $('#shared-result').on($.modal.BEFORE_OPEN, function(event, modal) {
        var shared_container = event.target.querySelector('.player-container');
        var player_id = shared_container.attributes.id.value;
        var player_container = document.getElementById(player_id);
        if (shared_container != player_container) {
            player_container.attributes.id.value = 'shared-blank'
            };
        });

    $('#shared-result').on($.modal.BEFORE_CLOSE, function(event, modal) {
        var shared_container = event.target.querySelector('.player-container');
        var player_id = shared_container.attributes.id.value;
        player = YT.get(player_id);
        if (player) {
            player.destroy();
            CURRENT_PLAYER = null;
            CURRENT_MATCH = null;
            };

        var player_container = document.getElementById('shared-blank');
        if (player_container) {
            var shared_result = document.getElementById('result-'+player_id);
            player_container.attributes.id.value = player_id;
            delete shared_container;
            };
        });

    $('#shared-result').modal();
    shared_result = document.getElementById('shared-result').querySelector('.result-container')
    match_container = shared_result.querySelector('.match-container');
    $(match_container).scrollBox();
    sb_content = shared_result.querySelector('.sb-content');
    $(sb_content).on('scroll', function() {
        load_button = this.querySelector('.load-more-button')
        /* If container scrolls down to the end */
        var diff = this.scrollHeight - this.offsetHeight
        /* Round up scrollTop and adds 5px to avoid small mismatches */
        var scrollTop = Math.round(this.scrollTop) + 5;
        if(scrollTop >= diff) {
            loadRestMatches(load_button);
        };
    });
};

// Function for "Reset to default" share-form button
function resetShareMoment() {
    var video_id = CURRENT_SHARE_MATCH.attributes.video_id.value;
    var result = document.getElementById("result-"+video_id);
    var channel_title = result.getElementsByClassName("channel-title")[0].innerText;
    var match_text = CURRENT_SHARE_MATCH.getElementsByClassName("match-text")[0].innerText;

    document.getElementById("id_share_start_time").value = getStringTime(CURRENT_SHARE_MATCH.attributes.start_time.value);
    document.getElementById("id_share_start_time").dispatchEvent(new Event('change'));
    document.getElementById("id_share_end_time").value = getStringTime(CURRENT_SHARE_MATCH.attributes.end_time.value);
    document.getElementById("id_share_end_time").dispatchEvent(new Event('change'));
    document.getElementById("id_share_title").value = channel_title + ": " + match_text;
    document.getElementById("id_loop_checkbox").checked = document.getElementById("id_loop_checkbox").defaultChecked;
}

// Function for "Watch this moment" share-form button
function previewShareMoment() {
    var video_id = CURRENT_SHARE_MATCH.attributes.video_id.value;
    var sh_start_time = stringTimeToSecs(document.getElementById("id_share_start_time").value);
    var sh_end_time = stringTimeToSecs(document.getElementById("id_share_end_time").value);
    var match_start_time = parseInt(CURRENT_SHARE_MATCH.attributes.start_time.value);
    var match_end_time = parseInt(CURRENT_SHARE_MATCH.attributes.end_time.value);
    var loop = document.getElementById("id_loop_checkbox").checked.toString();
    if (sh_start_time < sh_end_time) {
        if (sh_start_time == match_start_time && sh_end_time == match_end_time) {
            var match = CURRENT_SHARE_MATCH.getElementsByClassName("match")[0]
            jumpToTime(match, loop);
            }
        else {
            var blank_match = document.getElementById("blank-match-wrap");
            blank_match.attributes.video_id.value = video_id;
            blank_match.attributes.start_time.value = sh_start_time;
            blank_match.attributes.end_time.value = sh_end_time;
            blank_match.attributes.loop.value = loop;
            jumpToTime(blank_match, loop);
            }
        }
    else {
        alert("Oops! Seems like playback start time more or equal end time, that's not OK \nCheck this fields or press 'Reset to default' button")
        }
    }

// Function to show and play shared moment on page's ready
function playSharedMoment(shareMoment_values) {
    // If arg contains match ID:
    if (shareMoment_values.search("match-") != -1) {
        var shareMoment_list = shareMoment_values.split(",");
        var match_wrap_id = shareMoment_list[0];
        var loop = shareMoment_list[1];
        var match_wrap = document.getElementById(match_wrap_id);
        var match = match_wrap.getElementsByClassName("match")[0];
        jumpToTime(match, loop);
        match_wrap.closest(".result-container").scrollIntoView();
        }
    // Else arg contains custom moment with video id, start time and end time (in seconds)
    else {
        var list_shared_values = shareMoment_values.split(",");
        var video_id = list_shared_values[0];
        var start_time = list_shared_values[1];
        var end_time = list_shared_values[2];
        var loop = list_shared_values[3];

        document.getElementById("result-"+video_id).scrollIntoView();
        player = createPlayer(video_id, start_time, end_time, loop);
        CURRENT_PLAYER = player;
        CURRENT_MATCH = document.getElementById("blank-match-wrap");
        CURRENT_MATCH.attributes.video_id.value = video_id;
        CURRENT_MATCH.attributes.start_time.value = start_time;
        CURRENT_MATCH.attributes.end_time.value = end_time;
        CURRENT_MATCH.attributes.loop.value = loop;
        }
    }

// Function to show and play shared result item
function playSharedResult(shareResult_values) {
    var shareResult_list = shareResult_values.split(",");
    var result_id = shareResult_list[0];
    var autoplay = shareResult_list[1];
    var result = document.getElementById(result_id);
    result.closest(".result-container").scrollIntoView();

    if (autoplay == "true") {
            result.getElementsByClassName("playlist-button")[0].click();
        }
    };


// Function to show and play shared result item without speech data
function playSharedResultNoSpeech(shareResult_values) {
    var shareResult_list = shareResult_values.split(",");
    var result_id = shareResult_list[0];
    var autoplay = shareResult_list[1];
    var result = document.getElementById(result_id);
    result.closest(".result-container").scrollIntoView();

    if (autoplay == "true") {
            result.getElementsByClassName("thumbnail")[0].click();
        }
    };

// Function to check shareFormMatch values and pass them into a2a share plugin;
function updateShare(data, nospeech) {
    if (CURRENT_SHARE_MATCH != null) {
        var curr_url = document.location.href;

        // Check if url already contains shareMoment value, in this way remove it
        if (curr_url.indexOf("shareMoment") != -1) {
            var share_moment_index = curr_url.indexOf("shareMoment")
            curr_url = curr_url.slice(0, share_moment_index-1);
        }

        // The same for shareResult values
        if (curr_url.indexOf("shareResult") != -1) {
            var share_moment_index = curr_url.indexOf("shareResult")
            curr_url = curr_url.slice(0, share_moment_index-1);
        }

        var video_id = CURRENT_SHARE_MATCH.attributes.video_id.value
        var sh_start_time = stringTimeToSecs(document.getElementById("id_share_start_time").value);
        var sh_end_time = stringTimeToSecs(document.getElementById("id_share_end_time").value);
        var sh_start_id = CURRENT_SHARE_MATCH.attributes.start_id.value
        var sh_end_id = CURRENT_SHARE_MATCH.attributes.end_id.value
        var loop = document.getElementById("id_loop_checkbox").checked.toString();
        data.title = document.getElementById("id_share_title").value;

        var match_start_time = parseInt(CURRENT_SHARE_MATCH.attributes.start_time.value);
        var match_end_time = parseInt(CURRENT_SHARE_MATCH.attributes.end_time.value);

        // Setting shared icon to clicked element
        var current_share_icon = $(CURRENT_SHARE_MATCH).find(".share-icon")[0];
        if ( !$(current_share_icon).hasClass("shared") ) {
            $(current_share_icon).addClass("shared")
        }

        // If title is not empty and start time less than end time:
        if (data.title && sh_start_time < sh_end_time) {
            // If input time values same for match-wrap values - sharing by match-wrap id
//            if (sh_start_time == match_start_time && sh_end_time == match_end_time) {
//                data.url = curr_url + "&shareMoment=" + CURRENT_SHARE_MATCH.attributes.id.value + "," + loop;
//                return(data);
//                }
            data.url = curr_url + "&shareMoment=" + video_id + "," + sh_start_time;
            data.url = data.url + "," + sh_end_time + "," + sh_start_id + "," + sh_end_id + "," + loop;
            return(data);
        }
        // Otherwise set default values from match-wrap
        else {
            var result = document.getElementById("result-"+video_id);
            var channel_title = result.getElementsByClassName("channel-title")[0].innerText;
            var match_text = CURRENT_SHARE_MATCH.getElementsByClassName("match-text")[0].innerText;

            alert("Oops! Seems like title field is empty or playback time range has wrong values \nWe've set them to default")

            // Reset values to default by clicking "Reset to default" button
            document.getElementById("btn-share-reset").click();

            data.url = curr_url + "&shareMoment=" + video_id + "," + match_start_time + "," + match_end_time
            data.url = data.url + "," + sh_start_id + "," + sh_end_id + "," + loop;
            return(data);
        }
    }
    else if (CURRENT_SHARE_RESULT != null) {
        var curr_url = document.location.href;

        // Check if url already contains shareMoment value, in this way remove it
        if (curr_url.indexOf("shareMoment") != -1) {
            var share_moment_index = curr_url.indexOf("shareMoment")
            curr_url = curr_url.slice(0, share_moment_index-1);
        }

        // The same for shareResult values
        if (curr_url.indexOf("shareResult") != -1) {
            var share_result_index = curr_url.indexOf("shareResult")
            curr_url = curr_url.slice(0, share_result_index-1);
        }

        var autoplay = document.getElementById("id_autoplay_checkbox").checked.toString();

        data.title = document.getElementById("id_result_share_title").value;
        data.url = curr_url + "&shareResult=" + CURRENT_SHARE_RESULT.attributes.id.value + "," + autoplay;

        if (!data.title) {
            alert("Oops! Seems like title field is empty \nWe've filled this value to default")
            var video_id = CURRENT_SHARE_RESULT.attributes.id.value.replace("result-", "");
            var result = document.getElementById("result-"+video_id);
            var channel_title = result.getElementsByClassName("channel-title")[0].innerText;
            var video_title = result.getElementsByClassName("video-title")[0].innerText;
            var search_request = getUrlParameter("speech");

            // If sharing result without speech data - set video title in title field
            if (nospeech == 'true') {
                document.getElementById("id_result_share_title").value = channel_title + ": \"" + video_title + "\"";
                data.title = channel_title + ": \"" + video_title + "\"";
                }
            else {
                // Else - set request data in title field
                document.getElementById("id_result_share_title").value = channel_title + ": \"" + search_request + "\"";
                data.title = channel_title + ": \"" + search_request + "\"";
                }
            }
        return data;
        }
    else {
        console.log("Nothing to share");
        return;
        }
}

// Function to open dialog window with share-form for whole video matches
function shareResult(e, nospeech) {
    if ( $("#shareFormMatch").dialog("isOpen") ) {
        $("#shareFormMatch").dialog("close")
    };


    var result_container = $(e).closest(".result-container")[0];
    var channel_title = result_container.getElementsByClassName("channel-title")[0].innerText;
    var video_title = result_container.querySelector('.video-title').innerText;
    var type = getUrlParameter("type")
    // Will work when field names change (what_to_search -> speech etc.)
    var search_request = getUrlParameter(type);
    search_request = search_request.replace("+", " ")

    if (nospeech == 'true') {
        document.getElementById("id_result_share_title").value = channel_title + ": \"" + video_title + "\"";
        }

    else {
        document.getElementById("id_result_share_title").value = channel_title + ": \"" + search_request + "\"";
        }

    CURRENT_SHARE_RESULT = result_container;

    $( "#shareFormResult" ).dialog( "option", "position", { my: "center bottom-10%", at: "center top", of: e } );
    $( "#shareFormResult" ).dialog( "open" )
}

// Function to open dialog window with share-form for specific video match
function shareMoment(e) {
    // If another dialog window opened - close it
    if ( $("#shareFormResult").dialog("isOpen") ) {
        $("#shareFormResult").dialog("close")
    };

    var match_wrap = e.parentElement;
    CURRENT_SHARE_MATCH = match_wrap;

    var match_text = match_wrap.getElementsByClassName("match-text")[0].innerText;
    var video_id = match_wrap.attributes.video_id.value
    var start_time = match_wrap.attributes.start_time.value
    var end_time = match_wrap.attributes.end_time.value
    var duration = match_wrap.attributes.duration.value
    duration = stringTimeToSecs(duration)

    var result = document.getElementById("result-"+video_id);
    var channel_title = result.getElementsByClassName("channel-title")[0].innerText;

    document.getElementById("id_share_title").value = channel_title + ": " + match_text;

    document.getElementById("id_share_start_time").value = getStringTime(start_time);
    document.getElementById("id_share_end_time").value = getStringTime(end_time);

    document.getElementById("start_time_range").attributes.max.value = duration;
    document.getElementById("end_time_range").attributes.max.value = duration;

    document.getElementById("start_time_range").value = start_time;
    document.getElementById("end_time_range").value = end_time;

    document.getElementById("id_loop_checkbox").checked = document.getElementById("id_loop_checkbox").defaultChecked;


    $( "#shareFormMatch" ).dialog( "option", "position", { my: "left+5% center", at: "right center", of: e } );
    $( "#shareFormMatch" ).dialog( "open" )

    };