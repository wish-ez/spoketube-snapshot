from django import forms
from spoketube.settings import ALLOWED_CHARS_EN, SPEECH_ALLOWED_CHARS_EN
from data_parser.data_parser import CaptionParser
from data_parser.data_parser import Videos as ParserVideos
from spoketube.settings import MySQL_conn_admin, Sphinx_conn_admin
from captcha.fields import ReCaptchaField, ReCaptchaV2Checkbox

parser_videos = ParserVideos(MySQL_conn_admin, Sphinx_conn_admin)

ORDER_CHOICES = (('relevance', 'Relevance'),
                 ('publishedAt', 'Published date'),
                 ('duration', 'Duration'),
                 ('viewCount', 'Views'),
                 ('likeCount', 'Likes'),
                 ('dislikeCount', 'Dislikes'))

DIR_CHOICES = (('desc', 'Descending'),
               ('asc', 'Ascending'))

SEARCH_TYPES = (('speech', 'speech'),
                ('title', 'title'),
                ('description', 'description'),
                ('tags', 'tags'))

RESULTS_P_PAGE = (('5', '5'),
                  ('10', '10'),
                  ('20', '20'))

SPHINX_FIELDS = ('videoid', 'subtitle', 'stemmed_subtitle', 'indexes', 'timeframes', 'topiccategories',
                 'channelid', 'title', 'description', 'tags', 'captionlanguage', 'trackkind', 'categoryid',
                 'publishedat', 'lastupdated', 'isavailable', 'iscaptions', 'duration', 'viewcount',
                 'likecount', 'dislikecount', 'commentcount', 'embeddable'
                 )

class SearchForm(forms.Form):
    speech = forms.CharField(label='Speech to search', max_length=100, required=False, widget=forms.TextInput
                     (attrs={'class': 'clearable',
                             'tagify': 'default',
                             'placeholder': 'Words, phrases, emotions (e.g. [laugh] )'}))

    channels = forms.CharField(label='Channels to search', max_length=100, required=False, widget=forms.TextInput
    (attrs={'tagify': 'custom',
            'init_json': '',
            'placeholder': 'Channel names (optionally)'}))

    start_date = forms.DateField(required=False, widget=forms.TextInput(attrs={'class': 'datepicker', 'value': '', 'type': 'text'}))

    end_date = forms.DateField(required=False, widget=forms.TextInput(attrs={'class': 'datepicker', 'value': '', 'type': 'text'}))

    min_duration = forms.TimeField(required=False, widget=forms.TextInput(attrs={'type': 'time',
                                                                                 'onchange': "updateRange(this, 'min_duration_range');",
                                                                                 'oninput': "resetRange(this, 'min_duration_range');"
                                                                                 }))

    max_duration = forms.TimeField(required=False, widget=forms.TextInput(attrs={'type': 'time',
                                                                                 'onchange': "updateRange(this, 'max_duration_range');",
                                                                                 'oninput': "resetRange(this, 'max_duration_range');"
                                                                                 }))

    tags = forms.CharField(label='Tags to search', max_length=100, required=False, widget=forms.TextInput
                                    (attrs={'tagify': 'default',
                                            'placeholder': 'Video tags'}))

    description = forms.CharField(label='', max_length=100, required=False, widget=forms.TextInput
                                           (attrs={'tagify': 'default',
                                                   'placeholder': 'Video description'}))

    title = forms.CharField(label='', max_length=100, required=False, widget=forms.TextInput
                                           (attrs={'tagify': 'default',
                                                   'placeholder': 'Video title'}))

    exact = forms.BooleanField(label='', label_suffix='', required=False)

    advanced_settings = forms.BooleanField(label='', label_suffix='', required=False, widget=forms.CheckboxInput(
                                           attrs={'onclick': 'showAdvSettings()'}))

    order = forms.ChoiceField(label='', label_suffix='', choices=ORDER_CHOICES,
                                 required=False, initial='relevance',
                                 widget=forms.Select(attrs={"onChange": "submitForm();"}))

    direction = forms.ChoiceField(label='', label_suffix='', choices=DIR_CHOICES, required=False, initial='',
                            widget=forms.Select(attrs={"onChange": "submitForm();"}))

    type = forms.ChoiceField(label='', label_suffix='', choices=SEARCH_TYPES, required=False, initial='',
                            widget=forms.Select(attrs={"hidden": True}))

    def get_search_choices(self):
        return self.fields['type'].choices

    def setFieldAttr(self, field, attr, value):
        self.fields[field].widget.attrs[attr] = value

    def clean_speech(self):
        request = self.cleaned_data['speech']
        request = self.clean_speech_request(request)
        return request

    def clean_channels(self):
        request = self.cleaned_data['channels']
        request = self.clean_request(request)
        return request

    def clean_tags(self):
        request = self.cleaned_data['tags']
        request = self.clean_request(request)
        return request

    def clean_title(self):
        request = self.cleaned_data['title']
        request = self.clean_request(request)
        return request

    def clean_description(self):
        request = self.cleaned_data['description']
        request = self.clean_request(request)
        return request

    def clean_request(self, string):
        """
        Strip spaces at the edges, remove double/triple spaces, remove chars which not in ALLOWED_CHARS
        """
        string = string.strip()
        string = string.replace('   ', ' ').replace('  ', ' ')

        for ch in string:
            if ch not in ALLOWED_CHARS_EN:
                string = string.replace(ch, '')
        string = CaptionParser.i_to_I(string)
        return string

    def clean_speech_request(self, string):
        """
        Strip spaces at the edges, remove double/triple spaces, turn "i" to "I" and
        remove chars which not in SPEECH_ALLOWED_CHARS
        """

        string = string.strip()
        string = string.replace('   ', ' ').replace('  ', ' ')

        for ch in string:
            # Comma needs for multiple tags in search request
            if ch not in SPEECH_ALLOWED_CHARS_EN and ch != ',':
                string = string.replace(ch, '')
        string = CaptionParser.i_to_I(string)
        return string

class ShareForm(forms.Form):
    share_title = forms.CharField(max_length=100, required=True,
                                  widget=forms.TextInput(attrs={'placeholder': 'Title of shared moment'}))

    result_share_title = forms.CharField(max_length=100, required=True,
                                  widget=forms.TextInput(attrs={'placeholder': 'Title of shared matches'}))

    autoplay_checkbox = forms.BooleanField(label='', label_suffix='', required=False, initial=True)

    loop_checkbox = forms.BooleanField(label='', label_suffix='', required=False, initial=False)

    share_start_time = forms.TimeField(widget=forms.TextInput(attrs={'type': 'time',
                                                                     'step': '1',
                                                                     'onchange': "updateRange(this, 'start_time_range', seconds=true);",
                                                                     'oninput': "resetRange(this, 'start_time_range');"
                                                                     }))

    share_end_time = forms.TimeField(widget=forms.TextInput(attrs={'type': 'time',
                                                                   'step': '1',
                                                                   'onchange': "updateRange(this, 'end_time_range', seconds=true);",
                                                                   'oninput': "resetRange(this, 'end_time_range');"
                                                                   }))

class ContactForm(forms.Form):
    name = forms.CharField(required=True, widget=forms.TextInput(attrs={'placeholder': 'Your name'}))
    from_email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'placeholder': 'Your email'}))
    subject = forms.CharField(required=True, widget=forms.TextInput(attrs={'placeholder': 'Subject'}))
    message = forms.CharField(widget=forms.Textarea(attrs={'placeholder': 'Message'}), required=True)
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox)

class VideosForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(VideosForm, self).__init__(*args, **kwargs)

        for fieldname in SPHINX_FIELDS:
            sphinx_fieldname = 'sphinx_' + fieldname
            if fieldname in ('subtitle', 'stemmed_subtitle', 'indexes', 'timeframes', 'description', 'tags', 'title'):
                self.fields[sphinx_fieldname] = forms.CharField(widget=forms.Textarea(), required=False)
            else:
                self.fields[sphinx_fieldname] = forms.CharField(required=False)

            if kwargs['instance']:
                sphinx_video = parser_videos.Sphinx.get_by_key('videoid', kwargs['instance'].videoId)
                if sphinx_video:
                    self.fields[sphinx_fieldname].initial = sphinx_video[fieldname]

    def clean(self):
        for field in self.fields:
            if field[:7] == 'sphinx_' or field in ('lxml_subtitle'):
                self.cleaned_data[field] = self.data[field]
