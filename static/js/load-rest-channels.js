// Trying to get rest channels data for main-page-statistic via ajax, e - ".load-more-button-wrap" div
function loadRestChannels(e) {
    if (!e) {
        return;
        }

    var scrollbox = e.parentElement.parentElement;
    var statistic_box = scrollbox.parentElement;
    var channels = statistic_box.querySelectorAll('.statistic-channel');
    var last_channel = e.parentElement.previousElementSibling;
    var count = channels.length;
    var load_icon = e.querySelector('.load-icon');
    var load_more_button_wrap = e.parentElement;

    $.ajax({
        url: '/api/rest_channels/',
        data: {'count': count},
        dataType: 'json',
        beforeSend: function() {
            // Show load icon before send request
            $(load_icon).fadeIn(200);
        },
        complete: function(data) {
            /* Hide load icon on request complete and process to add new matches into result-container */
            $(load_icon).fadeOut(200, function() {
                $(load_more_button_wrap).insertAfter(last_channel);
                var is_channels_left = data.responseJSON.is_channels_left;
                var is_channels_left = parseInt(is_channels_left);
                // If no channels left - remove load button div and disable event handler;
                if (is_channels_left == 0) {
                    $(load_more_button_wrap).remove();
                    $(scrollbox).off('scroll', setCheckScrolled);
                    }
            });
            /* Set back scroll event function, see comment of setCheckScrolled function in search-page.js */
            $(scrollbox).on('scroll', setCheckScrolled);
        },
        success: function (data) {
          // If new matches - copy last match wrap to the end of container and load new values into it in loop
          if (data.channels) {
            statistic_box.attributes.isChannelsLeft.value = data.is_channels_left;
            for (i = 0; i < data.channels.length; i++) {
                var channel = data.channels[i];
                var new_channel = last_channel.cloneNode(true);
                var channel_logo = new_channel.querySelector('.channel-logo');
                var channel_title = new_channel.querySelector('.channel-title');
                var channel_subscribers_count = new_channel.querySelector('.channel-subscribers-count');
                var channel_videos_count = new_channel.querySelector('.channel-videos-count');

                channel_logo.querySelector('a').href = 'https://youtube.com/channel/' + channel.channelId;
                channel_logo.querySelector('img').src = channel.thumbnailsDefaultUrl;

                channel_title.querySelector('a').href = 'https://youtube.com/channel/' + channel.channelId;
                channel_title.querySelector('a').innerText = channel.title;

                channel_subscribers_count.querySelector('.channel-value').innerText = channel.subscriberCount;

                channel_videos_count.querySelector('.channel-value').innerText = channel.videoCount;

                last_channel.parentElement.appendChild(new_channel);
                last_channel = new_channel;
                }
            $(window).trigger("resize.scrollBox");
          }
          else {
                statistic_box.attributes.isChannelsLeft.value = 0;
            }
        }
    })
}