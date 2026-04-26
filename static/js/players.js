var CURRENT_PLAYER = null;
var CURRENT_MATCH = null;
var CURRENT_TIMEOUT = null;

// Coefficient to add additional playing seconds on mobile devices
var delay_k = 0;
if( /Android|Mobi/i.test(navigator.userAgent) ) {
    delay_k = 2000;
}

function jumpToTime(e, loop, play_all) {
    // If some match object been in use - remove all status icons
    if (CURRENT_MATCH != null ) {
        CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused', 'looped')
    }

    // If here active player and it doesn't equal to player in passed object - pause it
    if (CURRENT_PLAYER) {
        var result_container = e.closest(".result-container");
        if (result_container && CURRENT_PLAYER.a != result_container.getElementsByClassName("player-container")[0]) {
            CURRENT_PLAYER.pauseVideo();
            }
        }

    // Argument can be "match-wrap" element, his child or special blank item to playing video from share-form
    if ( $(e.parentElement).hasClass("match-wrap") ) {
        var match_wrap = e.parentElement;
    }
    else if (e.attributes.id.value == "blank-match-wrap" || $(e).hasClass("match-wrap") ) {
        var match_wrap = e;
    }
    else {
        console.log("Match wrap doesnt valid");
        return;
    }

    var player_container = match_wrap.parentElement.parentElement.parentElement.parentElement.querySelector('.player-container')
    var video_id = match_wrap.attributes.video_id.value;
    var startTime = parseInt(match_wrap.attributes.start_time.value);
    var endTime = parseInt(match_wrap.attributes.end_time.value);
    var player = YT.get(video_id);

    //If player doesn't exist:
    if (player == undefined) {
        player = createPlayer(video_id, startTime, endTime, loop);
        CURRENT_PLAYER = player;
        CURRENT_MATCH = match_wrap;

        // Passing loop and play_all options from args into match-wrap object to handle it in player events;
        CURRENT_MATCH.attributes.loop.value = loop;
        CURRENT_MATCH.attributes.play_all.value = play_all;
        return;
    }

    CURRENT_PLAYER = player;
    CURRENT_MATCH = match_wrap;
    // Passing loop option from args into match-wrap object to handle it in player events;
    CURRENT_MATCH.attributes.loop.value = loop;
    CURRENT_MATCH.attributes.play_all.value = play_all;


    player.addEventListener('onStateChange', checkPlayerStatus);
    player.seekTo(startTime);
    player.playVideo();

    function checkPlayerStatus(event) {
        // If loop option checked - showing loop icon;
        var loop = CURRENT_MATCH.attributes.loop.value;
        var play_all = CURRENT_MATCH.attributes.play_all.value;
        if (loop == "true") {
            addClassToElement(CURRENT_MATCH, 'looped');
            }

        //If player stopped:
        if (event.data == 0) {
            CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused');
            addClassToElement(CURRENT_MATCH, 'stopped');
            CURRENT_PLAYER = null;
        };

        //If player playing:
        if (event.data == 1) {
            // Condition to pause any other playing player
            if (CURRENT_PLAYER && CURRENT_PLAYER != event.target) {
                CURRENT_PLAYER.pauseVideo();
                }
            CURRENT_PLAYER = event.target;

            addClassToElement(CURRENT_MATCH, 'showed');
            CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused');
            addClassToElement(CURRENT_MATCH, 'playing');

            var player = event.target; // target is YT object (video player)
            var startTime = parseInt(CURRENT_MATCH.attributes.start_time.value)
            var endTime = parseInt(CURRENT_MATCH.attributes.end_time.value)
            var currentTime = parseInt(player.getCurrentTime());
            //If currently playing video keeps in text-specific time frames:
            if (startTime <= currentTime && currentTime < endTime){
                p_left_time = endTime - player.getCurrentTime();
                p_left_time = p_left_time*1000;
                p_left_time = parseInt(p_left_time) + delay_k;

                //Have to start hard timer due youtube didn't provides api to change ending time of already buffered video
                //Here we waiting left time (in ms) and doing something based om options:

                if (loop == "true") {
                    var timeout = setTimeout(function (){ player.seekTo(startTime); }, p_left_time);
                    CURRENT_TIMEOUT = timeout;
                    }

                else if (play_all == "true") {
                    var next_match = CURRENT_MATCH.nextElementSibling;
                    if (next_match != null) {
                        // Clause to auto smooth scrolling match-container during playing;
                        // Scrolling up to previous match-wrap element;
                        if (CURRENT_MATCH.previousElementSibling != null) {
                            var match_container = CURRENT_MATCH.parentElement;
                            scrollToElm(match_container, CURRENT_MATCH.previousElementSibling, 600);
                            }
                        var timeout = setTimeout(function (){
                            jumpToTime(next_match, 'false', 'true')
                            }, p_left_time);
                        CURRENT_TIMEOUT = timeout;
                        }
                    // If last element in match-container is null - pause this moment at the end;
                    else {
                        var timeout = setTimeout(function (){ player.pauseVideo(); }, p_left_time);
                        CURRENT_TIMEOUT = timeout;
                        }
                    }
                // If whole options are false - just pause at the end of playing;
                else {
                    var timeout = setTimeout(function (){ player.pauseVideo(); }, p_left_time);
                    CURRENT_TIMEOUT = timeout;
                    }

                //After timeout creation we make function and event that will break out timeout (and video pausing)
                // if user going to move player's time-scroll for some reasons:
                function stopTimeout() { clearTimeout(timeout); };
                player.addEventListener('onStateChange', stopTimeout);
                }
            else {
                CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused');
                CURRENT_MATCH = null;
            }
            }

        // If player paused:
        if (event.data == 2) {
            CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused');
            addClassToElement(CURRENT_MATCH, 'paused');
        };
};
};

function thumbPlay(e) {
    var match = e.nextElementSibling.getElementsByClassName('match')[0];
    match.click();
}

function createPlayer(video_id, startTime, endTime, loop, play_all) {
          var player_container = document.getElementById(video_id)
          var height = player_container.clientHeight.value + 'px'
          var width = player_container.clientHeight.value + 'px'

          var player = new YT.Player(video_id, {
             height: height,
             width: width,
             videoId: video_id,
             host: 'https://www.youtube.com',
             playerVars: {
             enablejsapi: 1
             },
             events: {
             'onReady': onReady,
             'onStateChange': checkPlayerStatus
             }
             })
          return player;


    function onReady(event) {
        var player = event.target;
        player.seekTo(startTime);
        // Hiding thumb on click
        var video_id = player.playerInfo.videoData.video_id;
        var player_container = document.getElementById(video_id);
        var thumb = player_container.nextElementSibling;
        thumb.style.visibility = 'hidden';
    };

    function checkPlayerStatus(event) {
        // If loop option checked - showing loop icon;
        var loop = CURRENT_MATCH.attributes.loop.value;
        var play_all = CURRENT_MATCH.attributes.play_all.value;
        if (loop == "true") {
            addClassToElement(CURRENT_MATCH, 'looped');
            }

        //If player stopped:
        if (event.data == 0) {
            CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused');
            addClassToElement(CURRENT_MATCH, 'stopped');
            CURRENT_PLAYER = null;
        };

        //If player playing:
        if (event.data == 1) {
            // Condition to pause any other playing player
            if (CURRENT_PLAYER && CURRENT_PLAYER != event.target) {
                CURRENT_PLAYER.pauseVideo();
                }
            CURRENT_PLAYER = event.target;

            addClassToElement(CURRENT_MATCH, 'showed');
            CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused');
            addClassToElement(CURRENT_MATCH, 'playing');

            var player = event.target; // target is YT object (video player)
            var startTime = parseInt(CURRENT_MATCH.attributes.start_time.value)
            var endTime = parseInt(CURRENT_MATCH.attributes.end_time.value)
            var currentTime = parseInt(player.getCurrentTime());
            //If currently playing video keeps in text-specific time frames:
            if (startTime <= currentTime && currentTime < endTime){
                p_left_time = endTime - player.getCurrentTime();
                p_left_time = p_left_time*1000;
                p_left_time = parseInt(p_left_time) + delay_k;

                //Have to start hard timer due youtube didn't provides api to change ending time of already buffered video
                //Here we waiting left time (in ms) and doing something based om options:

                if (loop == "true") {
                    var timeout = setTimeout(function (){ player.seekTo(startTime); }, p_left_time);
                    CURRENT_TIMEOUT = timeout;
                    }

                else if (play_all == "true") {
                    var next_match = CURRENT_MATCH.nextElementSibling;
                    if (next_match != null) {
                        // Clause to auto smooth scrolling match-container during playing;
                        // Scrolling up to previous match-wrap element;
                        if (CURRENT_MATCH.previousElementSibling != null) {
                            var match_container = CURRENT_MATCH.parentElement;
                            scrollToElm(match_container, CURRENT_MATCH.previousElementSibling, 600);
                            }
                        var timeout = setTimeout(function (){
                            jumpToTime(next_match, 'false', 'true')
                            }, p_left_time);
                        CURRENT_TIMEOUT = timeout;
                        }
                    // If last element in match-container is null - pause this moment at the end;
                    else {
                        var timeout = setTimeout(function (){ player.pauseVideo(); }, p_left_time);
                        CURRENT_TIMEOUT = timeout;
                        }
                    }
                // If whole options are false - just pause at the end of playing;
                else {
                    var timeout = setTimeout(function (){ player.pauseVideo(); }, p_left_time);
                    CURRENT_TIMEOUT = timeout;
                    }

                //After timeout creation we make function and event that will break out timeout (and video pausing)
                // if user going to move player's time-scroll for some reasons:
                function stopTimeout() { clearTimeout(timeout); };
                player.addEventListener('onStateChange', stopTimeout);
                }
            else {
                CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused');
                CURRENT_MATCH = null;
            }
            }

        // If player paused:
        if (event.data == 2) {
            CURRENT_MATCH.classList.remove('stopped', 'playing', 'paused');
            addClassToElement(CURRENT_MATCH, 'paused');
        };
};
};


function thumbPlayNoSpeech(e) {
    if (CURRENT_PLAYER) {
        CURRENT_PLAYER.pauseVideo();
        }
    var result_container = e.closest('.result-container');
    var video_id = result_container.attributes.id.value.replace('result-', '')
    var player = createPlayerNoSpeech(video_id);
    CURRENT_PLAYER = player;
}

function createPlayerNoSpeech(video_id) {
          var player_container = document.getElementById(video_id)
          var height = player_container.clientHeight.value + 'px'
          var width = player_container.clientHeight.value + 'px'

          var player = new YT.Player(video_id, {
             height: height,
             width: width,
             videoId: video_id,
             host: 'https://www.youtube.com',
             playerVars: {
             enablejsapi: 1
             },
             events: {
             'onReady': onReadyPlay,
             'onStateChange': pauseOtherPlayers
             }
             })
          return player;

    function onReadyPlay(event) {
        var player = event.target;
        player.playVideo();
        // Hiding thumb on click
        var video_id = player.playerInfo.videoData.video_id;
        var player_container = document.getElementById(video_id);
        var thumb = player_container.nextElementSibling;
        thumb.style.visibility = 'hidden';
    };

    function pauseOtherPlayers(event) {
        if (event.data == 1) {
            if (CURRENT_PLAYER && CURRENT_PLAYER != event.target) {
                CURRENT_PLAYER.pauseVideo();
                }
            CURRENT_PLAYER = event.target;
            }
        }
}


function addClassToElement(e, class_name) {
    if ( e != null && !e.classList.contains(class_name) ) {
        e.className = e.className + ' ' + class_name;
    }
};



// Function to play all matches in result list
function playAllMatches(e) {
    var match_container_wrap = $(e).closest(".match-container-wrap")[0];
    var match = match_container_wrap.getElementsByClassName("match")[0];
    jumpToTime(match, "false", "true");
    }

function showVolumeInfo(e) {
    $(e).prev().slideToggle('fast');
    var logo = $(e).children('.volume-slide-logo');
    $(logo).fadeOut(300, function () {
        if ($(logo).hasClass("logo-rotate")) {$(logo).removeClass("logo-rotate")}
        else {
            $(logo).addClass("logo-rotate");
        };
        $(logo).fadeIn(300);
    });
};