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

}

/* Init scrollbox for statistic container */
function scrollboxStatisticInit() {
    if (isOverflown(document.querySelector('.main-page-statistic'))) {
        $(".main-page-statistic").scrollBox();
    }
}

/* Set event handler to get rest channels via ajax (loadRestChannels) when container scrolls down to load-button-wrap */
function scrollGetRest() {
    var box = document.querySelector('.sb-content');
    var load_button = document.querySelector('.load-more-button')
    if(load_button) {
            $(box).on('scroll', setCheckScrolled);
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
		loadRestChannels(load_button);
		/* Current event handler will be set on back on AJAX 'complete' event, see loadRestChannels function */
		};
}

/* Lazy loading channels statistic logos */
function lazyLogoLoad() {
    var channel_logos = document.querySelectorAll('.channel-logo')
    for (i = 0; i < channel_logos.length; i++) {
        var logo_img = channel_logos[i].querySelector('img')
        logo_img.src = logo_img.attributes.thumbnailUrl.value;
    }
}

$(document).ready(function() {
    daterangeInit();
    lazyLogoLoad();
    scrollboxStatisticInit();
    scrollGetRest();
    onEnterSubmit();
});