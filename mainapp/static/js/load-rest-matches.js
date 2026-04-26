// Trying to get rest speech data for match-container via ajax, e - ".load-more-button-wrap" div
function loadRestMatches(e) {
if (!e) {
    return;
    }

var box = e.parentElement.parentElement;
var last_match_wrap = e.parentElement.previousElementSibling;
var match_container = e.parentElement.parentElement.parentElement;
var matches_left = match_container.attributes.matches_left.value;
var end_id = match_container.attributes.end_id.value;
var video_id = last_match_wrap.attributes.video_id.value;

var urlParams = new URLSearchParams(window.location.search);
var request = urlParams.get('speech');
var exact = urlParams.get('exact');
var load_icon = e.querySelector('.load-icon');
var load_more_button_wrap = e.parentElement;

$.ajax({
url: '/api/rest_matches/',
data: {
  'request': request,
  'exact': exact,
  'id': video_id,
  'end_id': end_id
},
dataType: 'json',
beforeSend: function() {
// Show load icon before send request
$(load_icon).fadeIn(200);
},
complete: function(data) {
/* Hide load icon on request complete and process to add new matches into result-container */
$(load_icon).fadeOut(200, function() {
    $(load_more_button_wrap).insertAfter(last_match_wrap);
    var matches_left = data.responseJSON.matches_left;
    var dom_matches_left = match_container.parentElement.querySelector('.count-left-matches');
    var dom_matches_value = dom_matches_left.querySelector('.left-matches-value');
    // If no matches left - remove load button div and hide counter
    if (matches_left == 0) {
        $(load_more_button_wrap).remove()
        if (dom_matches_left) {
            $(dom_matches_left).fadeOut(200)
            }
        }
    // Else - change matches left counter with fade animation
    else {
        $(dom_matches_value).fadeOut(200, function() {
            $(this).text(matches_left).fadeIn(200)
            })
        }
    }
)
/* Set back scroll event function, see comment of setCheckScrolled function in search-page.js */
$(box).on('scroll', setCheckScrolled);
},
success: function (data) {
  // If new matches - copy last match wrap to the end of container and load new values into it in loop
  if (data.matches) {
	match_container.attributes.end_id.value = data.end_id;
	match_container.attributes.matches_left.value = data.matches_left;
	for (i = 0; i < data.matches.length; i++) {
        var new_match_wrap = last_match_wrap.cloneNode(true);
        var new_match_id = parseInt(data.last_match_id) + i + 1;
        new_match_wrap.attributes.id.value = 'match-' + video_id + '-' + new_match_id;
        new_match_wrap.attributes.start_time.value = data.matches[i].startTime;
        new_match_wrap.attributes.end_time.value = data.matches[i].endTime;
        new_match_wrap.attributes.start_id.value = data.matches[i].start_id;
        new_match_wrap.attributes.end_id.value = data.matches[i].end_id;
        new_match_wrap.querySelector('.match-time').innerText = data.matches[i].startTime_formated;
        new_match_wrap.querySelector('.match-text').innerHTML = '...' + data.matches[i].match + '...';
        last_match_wrap.parentElement.appendChild(new_match_wrap);
        last_match_wrap = new_match_wrap;
        }
	$(window).trigger("resize.scrollBox");
  }
  else {
    match_container.attributes.end_id.value = -1;
    }
}
})

}