from django.contrib import admin, messages
from django.urls import path
from django.template.response import TemplateResponse, HttpResponse
from django.shortcuts import redirect
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.admin.utils import flatten_fieldsets
from .models import Videos, Channels, DataApiQuotas, DataParserStatuses, DataParserTasks, Proxies
from .forms import VideosForm, SPHINX_FIELDS
from data_parser.data_parser import Videos as ParserVideos, Channels as ParserChannels, VideosModel
from spoketube.settings import MySQL_conn_admin, Sphinx_conn_admin, YT
from datetime import timedelta

parser_videos = ParserVideos(MySQL_conn_admin, Sphinx_conn_admin)
parser_channels = ParserChannels(MySQL_conn_admin, Sphinx_conn_admin)


class MyAdminSite(admin.AdminSite):

    def each_context(self, request):
        each_context = super(MyAdminSite, self).each_context(request)

        parser_status = DataParserStatuses.get_last_status()
        quotas_used = DataApiQuotas.get_quotas_used()
        quotas_percents = int(quotas_used / DataApiQuotas.TOTAL_QUOTAS * 100)
        proxies_count = Proxies.get_count_available()

        each_context['parser'] = parser_status
        each_context['quotas_used'] = quotas_used
        each_context['quotas_percents'] = quotas_percents
        each_context['proxies_count'] = proxies_count
        return each_context

    def get_urls(self):
        default_urls = super().get_urls()
        my_urls = [
            path('add_youtube_data/', self.add_youtube_data),
            path('get_youtube_details/', self.get_youtube_details),
            path('stop_parser/', self.stop_parser)
        ]

        return default_urls + my_urls

    def add_youtube_data(self, request):
        yt_search_results = None
        yt_search_type = None
        search_value = None

        if request.method == 'GET' and request.GET:
            if request.GET['q']:
                search_type = request.GET['type']
                search_value = request.GET['q']
                if search_type == 'channels':
                    yt_search_results = YT.search_channel(search_value)
                    yt_search_type = 'channels'
                    for item in yt_search_results:
                        try:
                            is_in_db = Channels.objects.get(channelId=item.channelId)
                            is_in_db = bool(is_in_db)
                        except ObjectDoesNotExist:
                            is_in_db = False
                        item.is_in_db = is_in_db

                if search_type == 'videos':
                    yt_search_results = YT.search_video(search_value)
                    yt_search_type = 'videos'
                    for item in yt_search_results:
                        try:
                            is_in_db = Videos.objects.get(videoId=item.channelId)
                            is_in_db = bool(is_in_db)
                        except ObjectDoesNotExist:
                            is_in_db = False
                        item.is_in_db = is_in_db

                if not yt_search_results:
                    messages.error(request, 'Can\'t find anything')


        context = dict(
            # Include common variables for rendering the admin template.
            self.each_context(request),
            # Anything else you want in the context...
            yt_search_results=yt_search_results,
            yt_search_type=yt_search_type,
            search_value=search_value,
        )
        return TemplateResponse(request, "admin/add_youtube_data.html", context)

    def get_youtube_details(self, request):
        yt_item = None
        yt_item_type = None

        if request.method == 'GET' and request.GET:
            req = request.GET
            item_id = req.get('id')
            item_type = req.get('type')
            item_title = req.get('title')
            is_add = req.get('add')
            if item_id and item_type:
                if is_add:
                    if item_type == 'channel':
                        try:
                            Channels.objects.get(channelId=item_id)
                            messages.error(request, 'Channel already in DB')
                        except ObjectDoesNotExist:
                            new_task = DataParserTasks()
                            new_task.task_item = item_id
                            new_task.item_title = item_title
                            new_task.task = 'add_channel'
                            new_task.save()
                            messages.success(request, 'Channel added to parser queue')
                    if item_type == 'video':
                        try:
                            Videos.objects.get(videoId=item_id)
                            messages.error(request, 'Video already in DB')
                        except ObjectDoesNotExist:
                            new_task = DataParserTasks()
                            new_task.task_item = item_id
                            new_task.item_title = item_title
                            new_task.task = 'add_video'
                            new_task.save()
                            messages.success(request, 'Video added to parser queue')
                else:
                    if item_type == 'channel':
                        yt_item = YT.get_channel(item_id)
                        yt_item_type = 'channel'
                        try:
                            is_in_db = Channels.objects.get(channelId=yt_item.channelId)
                            is_in_db = bool(is_in_db)
                        except ObjectDoesNotExist:
                            is_in_db = False
                        yt_item.is_in_db = is_in_db
                    elif item_type == 'video':
                        yt_item = YT.get_video(item_id)
                        yt_item_type = 'video'
                        try:
                            is_in_db = Videos.objects.get(videoId=yt_item.channelId)
                            is_in_db = bool(is_in_db)
                        except ObjectDoesNotExist:
                            is_in_db = False
                        yt_item.is_in_db = is_in_db

        context = dict(
            # Include common variables for rendering the admin template.
            self.each_context(request),
            # Anything else you want in the context...
            yt_item=yt_item,
            yt_item_type=yt_item_type,
        )
        return TemplateResponse(request, "admin/get_youtube_details.html", context)

    def stop_parser(self, request):
        last_status = DataParserStatuses.objects.latest('createdAt')
        if last_status.status != 'work':
            messages.error(request, 'Can\'t stop parser which status is not \'work\'')
        else:
            new_status = DataParserStatuses(status='stop')
            new_status.save()
            messages.success(request, 'Parser stopped')
        return redirect(request.META.get('HTTP_REFERER', '/'))


class DurationRangeListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = ('duration range')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'duration'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('0-1', ('Up to 1 minute')),
            ('1-5', ('1 to 5 minutes')),
            ('5-15', ('5 to 15 minutes')),
            ('15-30', ('15 to 30 minutes')),
            ('30-60', ('30 to 60 minutes')),
            ('60-120', ('60 to 120 minutes')),
            ('120', ('Over 2 hours')),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value
        # to decide how to filter the queryset.
        if self.value() == '0-1':
            return queryset.filter(duration__range=[timedelta(), timedelta(minutes=1)])
        if self.value() == '1-5':
            return queryset.filter(duration__range=[timedelta(minutes=1, seconds=1), timedelta(minutes=5)])
        if self.value() == '5-15':
            return queryset.filter(duration__range=[timedelta(minutes=5, seconds=1), timedelta(minutes=15)])
        if self.value() == '15-30':
            return queryset.filter(duration__range=[timedelta(minutes=15, seconds=1), timedelta(minutes=30)])
        if self.value() == '30-60':
            return queryset.filter(duration__range=[timedelta(minutes=30, seconds=1), timedelta(hours=1)])
        if self.value() == '60-120':
            return queryset.filter(duration__range=[timedelta(hours=1, seconds=1), timedelta(hours=2)])
        if self.value() == '120':
            return queryset.filter(duration__gt=timedelta(hours=2, seconds=1))


class ViewRangeListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = ('view count')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'view_count'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('0-1k', ('Up to 1000 views')),
            ('1k-10k', ('1k to 10k views')),
            ('10k-100k', ('10k to 100k views')),
            ('100k-500k', ('100k to 500k views')),
            ('500k-1.5m', ('500k to 1.5m views')),
            ('1.5m-3m', ('1.5m to 3m views')),
            ('3m-10m', ('3m to 10m views')),
            ('10m-50m', ('10m to 50m views')),
            ('50m', ('Over 50m views')),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either '80s' or '90s')
        # to decide how to filter the queryset.
        if self.value() == '0-1k':
            return queryset.filter(viewCount__range=(0, 1000))
        if self.value() == '1k-10k':
            return queryset.filter(viewCount__range=(1001, 10000))
        if self.value() == '10k-100k':
            return queryset.filter(viewCount__range=(10001, 100000))
        if self.value() == '100k-500k':
            return queryset.filter(viewCount__range=(100001, 500000))
        if self.value() == '500k-1.5m':
            return queryset.filter(viewCount__range=(500001, 1500000))
        if self.value() == '1.5m-3m':
            return queryset.filter(viewCount__range=(1500001, 3000000))
        if self.value() == '3m-10m':
            return queryset.filter(viewCount__range=(3000001, 10000000))
        if self.value() == '10m-50m':
            return queryset.filter(viewCount__range=(10000001, 50000000))
        if self.value() == '50m':
            return queryset.filter(viewCount__gt=50000001)


class VideoRangeListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = ('video count')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'video_count'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('0-100', ('Up to 100 videos')),
            ('100-500', ('100 to 500 videos')),
            ('500-1.5k', ('500 to 1.5k videos')),
            ('1.5k-3k', ('1.5k to 3k videos')),
            ('3k-10k', ('3k to 10k videos')),
            ('10k', ('Over 10k videos')),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either '80s' or '90s')
        # to decide how to filter the queryset.
        if self.value() == '0-100':
            return queryset.filter(videoCount__range=(0, 100))
        if self.value() == '100-500':
            return queryset.filter(videoCount__range=(101, 500))
        if self.value() == '500-1.5k':
            return queryset.filter(videoCount__range=(501, 1500))
        if self.value() == '1.5k-3k':
            return queryset.filter(videoCount__range=(1501, 3000))
        if self.value() == '3k-10k':
            return queryset.filter(videoCount__range=(3001, 10000))
        if self.value() == '10k':
            return queryset.filter(videoCount__gt=10001)


class SubscriberRangeListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = ('subscriber count')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'subscriber_count'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('0-10k', ('Up to 10k subscribers')),
            ('10k-100k', ('10k to 100k subscribers')),
            ('100k-500k', ('100k to 500k subscribers')),
            ('500k-1.5m', ('500k to 1.5m subscribers')),
            ('1.5m-3m', ('1.5m to 3m subscribers')),
            ('3m-10m', ('3m to 10m subscribers')),
            ('10m-50m', ('10m to 50m subscribers')),
            ('50m-100m', ('50m to 100m subscribers')),
            ('100m', ('Over 100m subscribers')),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either '80s' or '90s')
        # to decide how to filter the queryset.
        if self.value() == '0-10k':
            return queryset.filter(subscriberCount__range=(0, 10000))
        if self.value() == '10k-100k':
            return queryset.filter(subscriberCount__range=(10001, 100000))
        if self.value() == '100k-500k':
            return queryset.filter(viewCount__range=(100001, 500000))
        if self.value() == '500k-1.5m':
            return queryset.filter(viewCount__range=(500001, 1500000))
        if self.value() == '1.5m-3m':
            return queryset.filter(viewCount__range=(1500001, 3000000))
        if self.value() == '3m-10m':
            return queryset.filter(viewCount__range=(3000001, 10000000))
        if self.value() == '10m-50m':
            return queryset.filter(viewCount__range=(10000001, 50000000))
        if self.value() == '50m-100m':
            return queryset.filter(viewCount__range=(50000001, 100000000))
        if self.value() == '100m':
            return queryset.filter(viewCount__gt=100000001)


class VideosAdmin(admin.ModelAdmin):
    form = VideosForm
    list_per_page = 20
    fieldsets = (
        ('Main properties', {
            'fields': ('title', 'videoId', 'channelTitle', 'channelId', 'defaultLanguage', 'defaultAudioLanguage', 'duration',
                       'publishedAt', 'lastUpdated', 'description', 'tags', 'embeddable', 'isAvailable', 'isCaptions', 'caption',
                       'captionLanguage', 'trackKind', 'captionUrl',),
        }),
        ('Statistic properties', {
            'fields': ('viewCount', 'likeCount', 'dislikeCount', 'favoriteCount', 'commentCount',),
        }),
        ('Rest properties', {
            'classes': ('collapse',),
            'fields': ('categoryId', 'contentRatingMpaaRating', 'contentRatingRussiaRating', 'contentRatingYtRating',
                       'definition', 'dimension', 'failureReason', 'hasCustomThumbnail', 'license',
                       'licensedContent', 'liveBroadcastContent', 'privacyStatus', 'publicStatsViewable',
                       'regionRestrictionAllowed', 'regionRestrictionBlocked', 'rejectionReason',
                       'thumbnailsDefaultUrl', 'thumbnailsHighUrl', 'thumbnailsMaxResUrl', 'thumbnailsMediumUrl',
                       'thumbnailsStandardUrl', 'uploadStatus', 'lxml_subtitle'),
        }),
    )
    list_display = ('title', 'channelTitle', 'videoId', 'duration', 'viewCount', 'isCaptions', 'trackKind',
                    'isAvailable', 'publishedAt', 'lastUpdated',)
    list_filter = (ViewRangeListFilter, DurationRangeListFilter, 'publishedAt', 'lastUpdated', 'isCaptions',
                   'trackKind', 'isAvailable')

    readonly_fields = ('videoId', 'channelId', 'channelTitle', 'lastUpdated',)

    search_fields = ['videoId', 'title', 'channelTitle']

    actions = ['yt_update_videos']

    def get_form(self, request, obj=None, **kwargs):
        # By passing 'fields', we prevent ModelAdmin.get_form from
        # looking up the fields itself by calling self.get_fieldsets()
        # If you do not do this you will get an error from
        # modelform_factory complaining about non-existent fields.

        # use this line only for django 1.9 and later
        kwargs['fields'] = flatten_fieldsets(self.fieldsets)

        form = super(VideosAdmin, self).get_form(request, obj, **kwargs)
        return form

    def get_fieldsets(self, request, obj=None):
        fieldsets = super(VideosAdmin, self).get_fieldsets(request, obj)
        newfieldsets = list(fieldsets)
        fields = []
        for field in SPHINX_FIELDS:
            fields.append('sphinx_' + field)
        newfieldsets.append(['Sphinx fields', {'fields': fields}])

        return newfieldsets

    def yt_update_videos(self, request, queryset):
        for video in queryset:
            new_task = DataParserTasks()
            new_task.task = 'update_video'
            new_task.task_item = video.videoId
            new_task.save()
        self.message_user(request, "Videos added to update queue")
    yt_update_videos.short_description = "Update YouTube data for selected videos"

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            parser_videos.Sphinx.delete(obj)
        super().delete_queryset(request, queryset)

    def save_model(self, request, obj, form, change):
        cleaned_form = form.cleaned_data
        sphinx_values = {}
        for key in cleaned_form:
            if key[:7] == 'sphinx_':
                k = key[7:]
                sphinx_values[k] = cleaned_form[key]

        sphinx_video = parser_videos.Sphinx.load_values_to_object(VideosModel, sphinx_values)
        parser_videos.Sphinx.update(sphinx_video)

        super().save_model(request, obj, form, change)


class ChannelsAdmin(admin.ModelAdmin):
    """
    Custom class for Channels models (allows to handle YouTube and Sphinx data)
    """
    fieldsets = (
        ('Main properties', {
            'fields': ('title', 'channelId', 'customUrl', 'country', 'defaultLanguage', 'textDefaultLanguage',
                       'description', 'keywords', 'publishedAt', 'lastUpdated',),
        }),
        ('Statistic properties', {
            'fields': ('videoCount', 'subscriberCount', 'hiddenSubscriberCount', 'viewCount', 'commentCount',),
        }),
        ('Rest properties', {
            'classes': ('collapse',),
            'fields': ('featuredChannelsTitle', 'featuredChannelsUrls', 'hints', 'isLinked', 'longUploadsStatus',
                       'moderateComments', 'privacyStatus', 'relatedPlaylistsFavorites', 'relatedPlaylistsLikes',
                       'relatedPlaylistsUploads', 'showBrowseView', 'showRelatedChannels',
                       'thumbnailsDefaultUrl', 'thumbnailsHighUrl', 'thumbnailsMediumUrl',
                       'trackingAnalyticsAccountId', 'watchIconImageUrl', ),
        }),
    )

    list_display = ('title', 'channelId', 'customUrl', 'country',
                    'videoCount', 'subscriberCount', 'viewCount', 'commentCount', 'publishedAt', 'lastUpdated')

    readonly_fields = ('channelId', 'title', 'lastUpdated',)

    list_filter = (VideoRangeListFilter, SubscriberRangeListFilter, ViewRangeListFilter, 'publishedAt',
                   'lastUpdated', 'country', 'defaultLanguage',)

    search_fields = ['channelId', 'title']

    actions = ['yt_update_channels', 'yt_refresh_channels', 'yt_get_missed_videos', 'yt_get_new_videos',
               'yt_sync_videos', 'yt_build_sphinx_data', 'yt_reindex_sphinx_data']

    def yt_update_channels(self, request, queryset):
        for channel in queryset:
            new_task = DataParserTasks()
            new_task.task = 'update_channel'
            new_task.task_item = channel.channelId
            new_task.item_title = channel.title
            new_task.save()
        self.message_user(request, "Channels added to update queue")
    yt_update_channels.short_description = "Update channel (update YouTube meta data for selected channels)"

    def yt_refresh_channels(self, request, queryset):
        for channel in queryset:
            new_task = DataParserTasks()
            new_task.task = 'refresh_channel'
            new_task.task_item = channel.channelId
            new_task.item_title = channel.title
            new_task.save()
        self.message_user(request, "Channels added to refresh queue")
    yt_refresh_channels.short_description = "Refresh channel (get new videos, " \
                                            "update unavailable and no-caption videos, " \
                                            "update YouTube meta data for selected channels)"

    def yt_get_missed_videos(self, request, queryset):
        for channel in queryset:
            new_task = DataParserTasks()
            new_task.task = 'get_missed_videos'
            new_task.task_item = channel.channelId
            new_task.item_title = channel.title
            new_task.save()
        self.message_user(request, "Channels added to get missed videos queue")
    yt_get_missed_videos.short_description = "Get missed videos for selected channels (checks whole channel videos)"

    def yt_get_new_videos(self, request, queryset):
        for channel in queryset:
            new_task = DataParserTasks()
            new_task.task = 'get_new_videos'
            new_task.task_item = channel.channelId
            new_task.item_title = channel.title
            new_task.save()
        self.message_user(request, "Channels added to get new videos queue")
    yt_get_new_videos.short_description = "Get new videos for selected channels (check only after last added channel's video)"

    def yt_sync_videos(self, request, queryset):
        for channel in queryset:
            new_task = DataParserTasks()
            new_task.task = 'sync_videos'
            new_task.task_item = channel.channelId
            new_task.item_title = channel.title
            new_task.save()
        self.message_user(request, "Channels added to sync videos queue")
    yt_sync_videos.short_description = "Sync (remove) videos which does not exists in BOTH mysql and sphinx indexes"

    def yt_build_sphinx_data(self, request, queryset):
        for channel in queryset:
            new_task = DataParserTasks()
            new_task.task = 'build_sphinx_data'
            new_task.task_item = channel.channelId
            new_task.item_title = channel.title
            new_task.save()
        self.message_user(request, "Channels added to build sphinx videos queue")
    yt_build_sphinx_data.short_description = "Build sphinx data and get subtitles for selected channels"

    def yt_reindex_sphinx_data(self, request, queryset):
        for channel in queryset:
            new_task = DataParserTasks()
            new_task.task = 'reindex_channel'
            new_task.task_item = channel.channelId
            new_task.item_title = channel.title
            new_task.save()
        self.message_user(request, "Channels added to reindex sphinx data queue")
    yt_reindex_sphinx_data.short_description = "Reindex sphinx data for selected channels"

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            parser_videos.Sphinx.delete_channel(obj.channelId)
        super().delete_queryset(request, queryset)


class DataApiQuotasAdmin(admin.ModelAdmin):
    list_display = ('id', 'quotas', 'datetime')

    list_filter = ('datetime',)

    readonly_fields = ('id',)

    search_fields = ['datetime']


class DataParserStatusesAdmin(admin.ModelAdmin):
    list_display = ('id', 'taskId', 'status', 'status_description', 'fatal_error_details',
                    'count_items_total', 'count_items_done', 'estimated_quotas',
                    'count_unavailable_videos', 'count_nocaption_videos', 'count_error_videos', 'createdAt')

    list_filter = ('status', 'createdAt',)

    readonly_fields = ('id',)

    search_fields = ['status_description']


class DataParserTasksAdmin(admin.ModelAdmin):
    list_display = ('id', 'task', 'item_title', 'task_item', 'isFatalError', 'createdAt', 'finishedAt',)

    list_filter = ('task', 'isFatalError', 'createdAt', 'finishedAt',)

    readonly_fields = ('id',)

    search_fields = ['task_item']

    actions = ['reset_tasks']

    def reset_tasks(self, request, queryset):
        for task in queryset:
            task.isFatalError = None
            task.finishedAt = None
            task.save()
        self.message_user(request, "Tasks have been reset")
    reset_tasks.short_description = "Reset tasks (remove error and finished date)"


class ProxiesAdmin(admin.ModelAdmin):
    list_display = ('id', 'ip', 'port', 'isAvailable', 'isCaptcha', 'type', 'createdAt', 'lastUpdated')

    list_filter = ('isAvailable', 'isCaptcha')

    readonly_fields = ('id',)


admin_site = MyAdminSite()

admin_site.register(Videos, VideosAdmin)
admin_site.register(Channels, ChannelsAdmin)
admin_site.register(DataApiQuotas, DataApiQuotasAdmin)
admin_site.register(DataParserStatuses, DataParserStatusesAdmin)
admin_site.register(DataParserTasks, DataParserTasksAdmin)
admin_site.register(Proxies, ProxiesAdmin)
