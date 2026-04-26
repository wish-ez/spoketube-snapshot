// Function to set search-form inputs order on page's load
function updateTabs() {

    var type = getUrlParameter('type');
    if (type) {
        // If search by speech - nothing to change;
        if (type == 'speech') {
            return;
            }
        var tab = document.getElementById('tab-'+type);
        changeTab(tab, '100%', '100%', 'false');
        }
    else {
        // If no search type - set to default (speech)
        var tab = document.getElementById('tab-speech');
        $(tab).addClass('current-tab');
        }
}

// Function to swap elements in DOM
function swap(a, b) {
    a = $(a); b = $(b);
    var tmp = $('<span>').hide();
    a.before(tmp);
    b.before(a);
    tmp.replaceWith(b);
};

// Function for tabs in search form
// Main/optional input widths are passed in as percentages because they
// are not readily available from computed CSS here.
function changeTab(e, main_input_width, optional_inputs_width, clear_option) {
/* If this tab is current - do nothing */
if ($(e).hasClass('current-tab')) {
    return;
    }
else if (e.attributes.id.value == 'tab-speech' && $(e).hasClass('active-tab')) {
    return;
    }
else {
    /* current-tab class for JS styling, active-tab for django template rendering
    (so that the active tab is displayed immediately before the page is fully loaded)
    both classes do the same styling job */
    var active_tab = document.querySelector('.active-tab');
    $(active_tab).removeClass('active-tab');

    var tab_curr = document.querySelector('.current-tab');
    $(tab_curr).removeClass('current-tab');
    $(e).addClass('current-tab');

    var type = document.getElementById('id_type');
    type.value = e.attributes.id.value.replace('tab-', '');

    var blank_input = document.querySelector('.blank.input');
    var curr_input = document.querySelector('.container-main-inputs').children[0];
    var curr_margin = $(curr_input).css('margin-bottom');

    if (clear_option == 'true') {
        /* Clear tagify tags */
        TAGIFY_WITH_VALUES.forEach(function (e) {
            e.removeAllTags();
            })

        /*Clear form inputs values */
        var inputs = document.querySelector('form').querySelectorAll('input')
        inputs.forEach(function (e) {
            /* Clearing range input, needs to manually fire event for moving slider to start */
            if (e.attributes.type.value == 'range') {
                e.value = 0;
                e.dispatchEvent(new Event('change'));
                }
            else {
                e.value = null;
                }
            })
        }


    if (e.attributes.id.value == 'tab-title') {
        var next_input = document.getElementsByClassName('title input')[0];
        }
    if (e.attributes.id.value == 'tab-description') {
        var next_input = document.getElementsByClassName('description input')[0];
        }
    if (e.attributes.id.value == 'tab-tags') {
        var next_input = document.getElementsByClassName('tags input')[0];
        }
    if (e.attributes.id.value == 'tab-speech') {
        var next_input = document.getElementById('speech-input');
        }

    var next_parent = $(next_input).closest('.options');
    var next_margin = $(next_input).css('margin-left');

    swap(blank_input, curr_input);
    swap(blank_input, next_input);

    $(curr_input).closest('.options').removeClass('blank');
    $(next_parent).addClass('blank');

    next_input.style.width = main_input_width;
    next_input.style.margin_bottom = curr_margin;
    curr_input.style.width = optional_inputs_width;
    curr_input.style.margin_bottom = next_margin;
    }
}

function showAdvSettings() {
    $(".search-options-wrap").slideToggle(300);
};

function submitForm() {
    /* Removing empty values from request */
    var form = document.querySelector('form');
    $(form).submit(function(e){
        var emptyinputs = $(this).find('input').filter(function(){
            return !$.trim(this.value).length;
        }).prop('disabled',true);
    });

    /* Parsing values from tagify objects into native form inputs */
    form.querySelectorAll('input[type=text]').forEach(function(e) {
        if (e.value) {
        var res = []
            try {
            v = JSON.parse(e.value)
            v.forEach(function(t) {
                res.push(t.value)
                })
            }
            catch (e) {
                return false;
                }
            e.value = res.join(',');
            }
        })
    /* Submit GET request */
    $('form').submit();

};

/* Return specific parameter from current URL */
function getUrlParameter(sParam) {
    var sPageURL = window.location.search.substring(1),
        sURLVariables = sPageURL.split('&'),
        sParameterName,
        i;

    for (i = 0; i < sURLVariables.length; i++) {
        sParameterName = sURLVariables[i].split('=');

        if (sParameterName[0] === sParam) {
            return sParameterName[1] === undefined ? true : decodeURIComponent(sParameterName[1]);
        }
    }
};

// Submit search form on Enter pressed inside tagify field
function onEnterSubmit() {
    $('tags.tagify').each(function() {
        if ($(this).parent().attr('id') != "where-input") {
            $(this).keyup(function(event) {
                if (event.keyCode === 13) {
                    submitForm();
                };
            });
        };
    });
};