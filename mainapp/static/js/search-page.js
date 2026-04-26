/* Init for custom calendar widget */
function daterangeInit() {
    /* Date-picker widget init */
    $('.datepicker').daterangepicker({
    "singleDatePicker": true,
    "showDropdowns": true,
    "autoUpdateInput": false
    });
    /* Date-picker events to keep input value empty by default */
    $('.datepicker').on('apply.daterangepicker', function(ev, picker) {
      $(this).val(picker.startDate.format('MM/DD/YYYY'));
    });

    $('.datepicker').on('cancel.daterangepicker', function(ev, picker) {
      $(this).val('');
    });

    // Init dialog windows for share buttons
    $( function() {
    $( "#shareFormMatch" ).dialog({
    autoOpen: false,
    width: "25vw",
    close: function () {CURRENT_SHARE_RESULT = null; CURRENT_SHARE_MATCH = null;},
    classes: {
    "ui-dialog-titlebar": "dialog-titlebar",
    "ui-dialog-content": "dialog-ui-widget"
    }
    });

    $( "#shareFormResult" ).dialog({
    autoOpen: false,
    width: "25vw",
    close: function () {CURRENT_SHARE_RESULT = null; CURRENT_SHARE_MATCH = null;},
    classes: {
    "ui-dialog-titlebar": "dialog-titlebar",
    "ui-dialog-content": "dialog-ui-widget"
    }
    });

    });



}


/* Init custom scrollbar for overflown containers */
function matchScrollInit(match_container_id) {
    var result_container = document.getElementById(match_container_id);
    var match_container = result_container.querySelector('.match-container');
    $(match_container).scrollBox();
    var scrollbar = match_container.querySelector('.sb-scrollbar');
    var sb_container = match_container.querySelector('.sb-scrollbar-container');
    /* Remove widget if height of scrollbar-container == height of scrollbar */
    if (parseInt(scrollbar.style.height) == sb_container.offsetHeight) {
        sb_container.remove();
    };
}

/* Set event handler to get rest matches via ajax (loadRestMatches) when container scrolls down to load-button-wrap */
function scrollGetRest() {
    boxes = document.querySelectorAll('.sb-content');
    for(var i = 0; i < boxes.length; i++) {
        var box = boxes[i]
        var load_button = box.querySelector('.load-more-button')
        if(load_button) {
                $(box).on('scroll', setCheckScrolled);
            }
        }
    }

/* Event handler to fire on box scrolled down */
function setCheckScrolled() {
	load_button = this.querySelector('.load-more-button')
	/* If container scrolls down to the end */
	var diff = this.scrollHeight - this.offsetHeight;
	/* Round up scrollTop and adds 5px to avoid small mismatches */
	var scrollTop = Math.round(this.scrollTop) + 5;
	if(scrollTop >= diff) {
	    /* Disable current event handler, otherwise it will be fire few more times and load duplicates
	    due to rounded dimensions of scroll height above */
	    $(this).off('scroll', setCheckScrolled);
		loadRestMatches(load_button);
		/* Current event handler will be set on back on AJAX 'complete' event, see loadRestMatches function */
		};
}

$(document).ready(function() {
    scrollGetRest();
    updateTabs();
    daterangeInit();
    onEnterSubmit();
});