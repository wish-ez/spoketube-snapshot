var TAGIFY_WITH_VALUES = []
function tagifySetup() {
    /* Init for regular text inputs by attribute 'tagify' */
    var inputs = document.querySelectorAll('[tagify=default]');
    inputs.forEach(function (e) {
        tagify = new Tagify(e, {
            whitelist:[],
            dropdown : {
                enabled: 0,
                classname : 'extra-properties'
                }
            })
        if (e.attributes.value) {
            TAGIFY_WITH_VALUES.push(tagify);
            }
        });




    /* Initialise where_input value from it's init_json attribute to keep tag's icons showing on page refreshing */
    var where_input = document.querySelector('[tagify=custom]');
    where_input.value = where_input.attributes.init_json.value;

    /* Init for where_input with ajax autocomplete and additional widgets (channel icon and videos count */
    var input = document.querySelector('[tagify=custom]'),
    tagify = new Tagify(input, {
            whitelist : [],
            dropdown : {
                classname : 'extra-properties',
                /* Template for dropdown list to show channel's icons and videos count */
                itemTemplate : function(tagData){
                    return `<div class='tagify__dropdown__item ${tagData.class ? tagData.class : ""}'>
                                    <img onerror="this.style.display = 'none'"
                                         src='${tagData.icon_url}'>
                                    <span>${tagData.value}</span>
                                    <span>(${tagData.video_count} videos)</span>
                                </div>`
                    }
            },
            mapValueToProp : "icon_url",
            /* Template for tags to show channel's icons */
            tagTemplate : function(v, tagData){
                return `<tag title='${v}'>
                                <x title=''></x>
                                <div>
                                    <img onerror="this.style.display = 'none'" src='${tagData.icon_url}'>
                                    <span class='tagify__tag-text'>${v}</span>
                                </div>
                            </tag>`;
                }
            }), controller;

    tagify.on('input', onInput)

    /* Ajax function to set channel's icons and videos count from autocomplete_where view */
    function onInput( e ){
      var value = e.detail;
      if (value.length < 2) {return};
      tagify.settings.whitelist.length = 0; // reset the whitelist

      $.ajax({
        url: '/api/autocomplete_channels/',
        data: {
          'term': value,
        },
        dataType: 'json',
        success: function (whitelist) {
        whitelist = JSON.parse(whitelist);
        tagify.settings.whitelist = whitelist;
        tagify.dropdown.show.call(tagify, value);
        }
        })
    }
};


