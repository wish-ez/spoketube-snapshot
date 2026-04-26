"""
Domain models for Spoketube.

- Channels / Videos mirror YouTube channel and video metadata; Videos is also
  mirrored into a Sphinx real-time index for full-text search.
- DataApiQuotas tracks YouTube Data API quota consumption against the daily
  Pacific-time reset window.
- DataParserTasks / DataParserStatuses form the ingestion job queue and its
  per-task status trail.
- Proxies is the rotating proxy pool used when scraping captions.
"""

from django.db import models
from django.db.models import Sum, ObjectDoesNotExist
from spoketube.settings import TIME_ZONE
from django.utils.timezone import now
from spoketube.settings import YT_DAY_QUOTAS
import pytz


class Channels(models.Model):
    unique_key = 'channelId'
    id = models.AutoField(primary_key=True)
    channelId = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=1000)
    commentCount = models.PositiveIntegerField(null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    customUrl = models.CharField(max_length=1000, null=True, blank=True)
    defaultLanguage = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    featuredChannelsTitle = models.CharField(max_length=100, null=True, blank=True)
    featuredChannelsUrls = models.CharField(max_length=1000, null=True, blank=True)
    hiddenSubscriberCount = models.BooleanField(null=True, blank=True)
    hints = models.TextField(null=True, blank=True)
    isLinked = models.BooleanField(null=True, blank=True)
    keywords = models.TextField(null=True, blank=True)
    lastUpdated = models.DateTimeField(blank=True, auto_now=True)
    longUploadsStatus = models.CharField(max_length=50, null=True, blank=True)
    moderateComments = models.BooleanField(null=True, blank=True)
    privacyStatus = models.CharField(max_length=50, null=True, blank=True)
    publishedAt = models.DateTimeField(null=True, blank=True)
    relatedPlaylistsFavorites = models.CharField(max_length=100, null=True, blank=True)
    relatedPlaylistsLikes = models.CharField(max_length=100, null=True, blank=True)
    relatedPlaylistsUploads = models.CharField(max_length=100, null=True, blank=True)
    showBrowseView = models.BooleanField(null=True, blank=True)
    showRelatedChannels = models.BooleanField(null=True, blank=True)
    subscriberCount = models.PositiveIntegerField(null=True, blank=True)
    textDefaultLanguage = models.CharField(max_length=100, null=True, blank=True)
    thumbnailsDefaultUrl = models.URLField(null=True, blank=True)
    thumbnailsHighUrl = models.URLField(null=True, blank=True)
    thumbnailsMediumUrl = models.URLField(null=True, blank=True)
    trackingAnalyticsAccountId = models.CharField(max_length=100, null=True, blank=True)
    videoCount = models.PositiveIntegerField(null=True, blank=True)
    viewCount = models.BigIntegerField(null=True, blank=True)
    watchIconImageUrl = models.URLField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'channels'
        verbose_name_plural = 'Channels'

    def __str__(self):
        return self.channelId


class Videos(models.Model):
    unique_key = 'videoId'
    sphinx = True

    id = models.AutoField(primary_key=True)
    videoId = models.CharField(max_length=100, null=False, blank=False, unique=True)
    title = models.CharField(max_length=100, null=False, blank=False)
    caption = models.BooleanField(null=True, blank=True)
    channelId = models.ForeignKey(Channels, on_delete=models.CASCADE, db_column='channelId', to_field='channelId',
                                  null=True, blank=True)
    channelTitle = models.CharField(max_length=100, null=False, blank=False)
    captionLanguage = models.CharField(max_length=10, null=True, blank=True)
    captionUrl = models.TextField(null=True, blank=True)
    categoryId = models.TextField(null=True, blank=True)
    commentCount = models.PositiveIntegerField(null=True, blank=True)
    contentRatingMpaaRating = models.CharField(max_length=50, null=True, blank=True)
    contentRatingRussiaRating = models.CharField(max_length=50, null=True, blank=True)
    contentRatingYtRating = models.CharField(max_length=50, null=True, blank=True)
    defaultAudioLanguage = models.CharField(max_length=100, null=True, blank=True)
    defaultLanguage = models.CharField(max_length=100, null=True, blank=True)
    definition = models.CharField(max_length=10, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    dimension = models.CharField(max_length=100, null=True, blank=True)
    dislikeCount = models.PositiveIntegerField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    embeddable = models.BooleanField(null=True, blank=True)
    failureReason = models.CharField(max_length=100, null=True, blank=True)
    favoriteCount = models.PositiveIntegerField(null=True, blank=True)
    hasCustomThumbnail = models.BooleanField(null=True, blank=True)
    isAvailable = models.BooleanField(null=True, blank=True)
    isCaptions = models.BooleanField(null=True, blank=True)
    lastUpdated = models.DateTimeField(auto_now=True, null=True, blank=True)
    license = models.CharField(max_length=100, null=True, blank=True)
    licensedContent = models.BooleanField(null=True, blank=True)
    likeCount = models.PositiveIntegerField(null=True, blank=True)
    liveBroadcastContent = models.CharField(max_length=50, null=True, blank=True)
    privacyStatus = models.CharField(max_length=50, null=True, blank=True)
    publicStatsViewable = models.BooleanField(null=True, blank=True)
    publishedAt = models.DateTimeField(null=True, blank=True)
    regionRestrictionAllowed = models.TextField(null=True, blank=True)
    regionRestrictionBlocked = models.TextField(null=True, blank=True)
    rejectionReason = models.CharField(max_length=100, null=True, blank=True)
    tags = models.TextField(null=True, blank=True)
    thumbnailsDefaultUrl = models.URLField(null=True, blank=True)
    thumbnailsHighUrl = models.URLField(null=True, blank=True)
    thumbnailsMaxResUrl = models.URLField(null=True, blank=True)
    thumbnailsMediumUrl = models.URLField(null=True, blank=True)
    thumbnailsStandardUrl = models.URLField(null=True, blank=True)
    trackKind = models.CharField(max_length=10, null=True, blank=True)
    uploadStatus = models.CharField(max_length=50, null=True, blank=True)
    viewCount = models.BigIntegerField(null=True, blank=True)

    lxml_subtitle = models.TextField(null=True, blank=True)

    speech_data = []
    end_id = None
    count_rest_speech_data = 0
    count_total_data = 0

    def set_speech_data(self, speech_data):
        self.speech_data = speech_data

    def clear_sphinx_fields(self):
        self.subtitle = None
        self.stemmed_subtitle = None
        self.indexes = None
        self.timeframes = None

    class Meta:
        managed = True
        db_table = 'videos'
        verbose_name_plural = 'Videos'

    def __str__(self):
        return self.videoId


class DataApiQuotas(models.Model):
    unique_key = 'id'
    id = models.AutoField(primary_key=True)
    datetime = models.DateTimeField(auto_now=True, null=True, blank=True)
    quotas = models.PositiveIntegerField(default=0, null=True, blank=True)
    TOTAL_QUOTAS = YT_DAY_QUOTAS

    class Meta:
        managed = True
        db_table = 'data_api_quotas'
        verbose_name_plural = 'Data api quotas'

    @staticmethod
    def get_quotas_left():
        tz_quotas = pytz.timezone('US/Pacific')
        tz_locale = pytz.timezone(TIME_ZONE)
        locale_datetime = now()
        quotas_reset_datetime = locale_datetime.astimezone(tz_quotas).replace(hour=0, minute=0, second=0, microsecond=0)
        locale_quotas_reset_datetime = quotas_reset_datetime.astimezone(tz_locale)
        quotas = DataApiQuotas.objects.filter(datetime__gte=locale_quotas_reset_datetime)
        summ_quotas = quotas.aggregate(Sum('quotas'))['quotas__sum']
        result = DataApiQuotas.TOTAL_QUOTAS - summ_quotas
        return result

    @staticmethod
    def get_quotas_used():
        tz_quotas = pytz.timezone('US/Pacific')
        tz_locale = pytz.timezone(TIME_ZONE)
        locale_datetime = now()
        quotas_reset_datetime = locale_datetime.astimezone(tz_quotas).replace(hour=0, minute=0, second=0, microsecond=0)
        locale_quotas_reset_datetime = quotas_reset_datetime.astimezone(tz_locale)
        quotas = DataApiQuotas.objects.filter(datetime__gte=locale_quotas_reset_datetime)
        summ_quotas = quotas.aggregate(Sum('quotas'))['quotas__sum']
        if not summ_quotas:
            summ_quotas = 0
        return summ_quotas

    def __str__(self):
        return str(self.id)


class DataParserTasks(models.Model):
    TASK_VALUES = ('add_channel', 'update_channel', 'refresh_channel', 'add_video', 'update_video', 'get_missed_videos')
    unique_key = 'id'
    id = models.AutoField(primary_key=True)
    task = models.CharField(max_length=100, null=True, blank=True)
    task_item = models.TextField(null=True, blank=True)
    item_title = models.TextField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    finishedAt = models.DateTimeField(null=True, blank=True)
    isFatalError = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'data_parser_tasks'
        verbose_name_plural = 'Data parser tasks'

    def __str__(self):
        return str(self.id)


class DataParserStatuses(models.Model):
    unique_key = 'id'
    id = models.AutoField(primary_key=True)
    taskId = models.ForeignKey(DataParserTasks, on_delete=models.CASCADE, null=True, blank=True, db_column='taskId')
    status = models.CharField(max_length=100, null=True, blank=True, default='idle')
    status_description = models.TextField(null=True, blank=True, default=None)
    count_items_total = models.PositiveIntegerField(null=True, blank=True, default=None)
    count_items_done = models.PositiveIntegerField(null=True, blank=True, default=None)
    count_unavailable_videos = models.PositiveIntegerField(null=True, blank=True, default=None)
    count_nocaption_videos = models.PositiveIntegerField(null=True, blank=True, default=None)
    count_error_videos = models.PositiveIntegerField(null=True, blank=True, default=None)
    estimated_quotas = models.PositiveIntegerField(null=True, blank=True, default=None)
    createdAt = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    lastUpdated = models.DateTimeField(auto_now=True, null=True, blank=True)
    fatal_error_details = models.TextField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'data_parser_statuses'
        verbose_name_plural = 'Data parser statuses'

    @classmethod
    def get_last_status(cls):
        last_status = None
        try:
            last_status = cls.objects.last()
        except ObjectDoesNotExist:
            pass
        return last_status

    def __str__(self):
        return str(self.id)


class Proxies(models.Model):
    unique_key = 'id'
    id = models.AutoField(primary_key=True)
    type = models.CharField(max_length=10, default="https")
    port = models.PositiveIntegerField()
    ip = models.CharField(max_length=50)
    login = models.CharField(max_length=100, null=True, default=None)
    password = models.CharField(max_length=100, null=True, default=None)
    isAvailable = models.BooleanField(default=True)
    isCaptcha = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)
    lastUpdated = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'proxies'
        verbose_name_plural = 'Proxies'

    def __str__(self):
        return str(self.ip) + ":" + str(self.port)

    @classmethod
    def get_count_available(cls):
        return Proxies.objects.filter(isAvailable=True, isCaptcha=False).count()
