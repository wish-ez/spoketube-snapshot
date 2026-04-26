"""
Data ingestion building blocks used by both the web app and the cron jobs.

Provides:
- Connector: a thin MySQL/Sphinx connection wrapper (pymysql under the hood),
  reused for both the application DB and the Sphinx daemon on the MySQL port.
- YouTubeAPI: a wrapper around googleapiclient.discovery.build for the
  YouTube Data API v3, with helpers for channels, videos, playlists, and
  quota cost accounting against the DataApiQuotas table.
- CaptionParser: fetches and parses YouTube subtitle XML through an optional
  HTTP(S) proxy, handling proxy errors and YouTube captcha responses.
- Model-like helpers (Videos / Channels / Proxies / DataParserTasks /
  DataParserStatuses) that speak directly to MySQL / Sphinx and mirror the
  Django ORM models, so the cron worker can run outside the Django process.
"""

from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow
from googleapiclient.discovery import build_from_document
from googleapiclient.discovery import build
from nltk.stem import PorterStemmer
from urllib import parse
from contextlib import closing
from bs4 import BeautifulSoup
from math import ceil
from datetime import datetime, timedelta
import isodate
import pytz
import logging
import requests
import ujson
import os
import httplib2
import pymysql

logger = logging.getLogger(__name__)

SPEECH_ALLOWED_CHARS_EN = [' ', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H',
                          'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'a',
                          'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't',
                          'u', 'v', 'w', 'x', 'y', 'z', '[', ']', '\''
                          ]

def current_string_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def string_to_timestamp(string_datetime):
    """
    Function for sphinx indexes (which accepts only UNIX timestamp INT values in 'timestamp' fields
    :param string string_datetime:
    :return int:
    """
    try:
        # If string in datetime format - return UNIX timestamp
        res = datetime.strptime(string_datetime, "%Y-%m-%d %H:%M:%S").timestamp()
        return int(res)
    except ValueError:
        # Check if string already in UNIX timestamp format, in this way return that string in int type
        unix_ts = int(string_datetime)
        (datetime.fromtimestamp(unix_ts) - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
        return unix_ts



def datetime_to_timestamp(datetime):
    """
    Function for sphinx indexes (which accepts only UNIX timestamp INT values in 'timestamp' fields
    :param datetime datetime:
    :return int:
    """
    res = datetime.timestamp()
    res = int(res)
    return res


def timestamp_to_strftime(date_time):
    """
    Function for converting INT values of UNIX timestamp to string in '%Y-%m-%d %H:%M:%S' format
    :param string date_time:
    :return str:
    """
    # If date_time already in '%Y-%m-%d %H:%M:%S' format then return it as is
    try:
        date_time = str(date_time)
        datetime.strptime(date_time, '%Y-%m-%d %H:%M:%S')
        return date_time
    # Otherwise convert UNIX timestamp to '%Y-%m-%d %H:%M:%S' format
    except ValueError:
        date_time = int(date_time)
        res = datetime.utcfromtimestamp(date_time).strftime('%Y-%m-%d %H:%M:%S')
        return res


class Connector:

    def __init__(self, host='127.0.0.1', port=9306, user='root', password='', charset='utf8mb4', db=''):
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.charset = charset
        self.db = db
        self.connection = None
        self.connect()

    def connect(self):
        self.connection = pymysql.connect(host=self.host,
                                          port=self.port,
                                          user=self.user,
                                          db=self.db,
                                          password=self.password,
                                          charset=self.charset,
                                          cursorclass=pymysql.cursors.DictCursor,
                                          autocommit=True,
                                          use_unicode=True
                                          )

    def query(self, sql):
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql)
        except (pymysql.OperationalError, pymysql.InterfaceError, AttributeError):
            self.connect()
            cursor = self.connection.cursor()
            cursor.execute(sql)
        return cursor

    def query_values(self, sql, values):
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, values)
        except (pymysql.OperationalError, AttributeError):
            self.connect()
            cursor = self.connection.cursor()
            cursor.execute(sql, values)
        return cursor

    def get_last_id(self, table_name):
        sql = "SELECT id FROM " + table_name + " ORDER BY id DESC LIMIT 1"
        cursor = self.query(sql)
        result = cursor.fetchone()
        if result:
            id = result['id']
        else:
            id = 0
        cursor.close()
        return id

    def get_table_columns(self, table_name):
        sql = 'desc ' + table_name
        cursor = self.query(sql)
        result = cursor.fetchall()
        columns = {}
        for i in result:
            columns[i['Field']] = i['Type']
        cursor.close()
        return columns


class Table:
    def __init__(self, connector, table_name, sphinx=False):
        self._connector = connector
        self.__table_name = table_name
        self.sphinx = sphinx
        self.columns = self.__get_table_columns()
        self.last_id = self.get_last_id()

    def get_last_id(self):
        result = 0
        if self.sphinx:
            sql = "SELECT id FROM " + self.__table_name + " ORDER BY id DESC LIMIT 1"
            cursor = self._connector.query(sql)
            id = cursor.fetchone()
            if id:
                result = id['id']
        else:
            sql = "SELECT MAX(id) FROM " + self.__table_name
            cursor = self._connector.query(sql)
            id = cursor.fetchone()
            if id:
                result = id['MAX(id)']
        cursor.close()
        if result:
            return result
        else:
            return 0

    def __is_unique_key(self, item):
        # Check if unique key field is not empty
        uniq_key = item.unique_key
        if uniq_key != 'id':
            if getattr(item, uniq_key):
                return True
            else:
                return False
        else:
            return True

    def __get_table_columns(self):
        sql = 'desc ' + self.__table_name
        cursor = self._connector.query(sql)
        result = cursor.fetchall()
        columns = {}
        for i in result:
            columns[i['Field']] = i['Type']
        cursor.close()
        return columns

    def __check_duplicate_entry(self, item):
        unique_key = item.unique_key
        key_value = getattr(item, unique_key, None)
        if not key_value:
            return None

        if self.sphinx:
            unique_key = unique_key.lower()
        sql = "SELECT * FROM `" + self.__table_name + "` WHERE " + unique_key + "=%s"
        cursor = self._connector.query_values(sql, key_value)
        duplicate = cursor.fetchone()
        cursor.close()
        return duplicate

    def load_values_to_object(self, item, values):
        item_attrs = dir(item)
        if self.sphinx:
            for attr in item_attrs:
                sphinx_attr = attr.lower()
                if sphinx_attr in values:
                    value = values[sphinx_attr]
                    setattr(item, attr, value)
        else:
            for attr in item_attrs:
                if attr in values:
                    value = values[attr]
                    setattr(item, attr, value)
        return item

    def get_values_from_object(self, item):
        result = {}
        item_attrs = dir(item)
        if self.sphinx:
            for attr in item_attrs:
                sphinx_attr = attr.lower()
                if sphinx_attr in self.columns:
                    value = getattr(item, attr, None)
                    if value is None:
                        if self.columns[sphinx_attr] == 'string':
                            result[sphinx_attr] = ''
                        if self.columns[sphinx_attr] == 'uint':
                            result[sphinx_attr] = 0
                        if self.columns[sphinx_attr] == 'timestamp':
                            result[sphinx_attr] = 0
                    else:
                        if self.columns[sphinx_attr] == 'string':
                            result[sphinx_attr] = str(value)
                        elif self.columns[sphinx_attr] == 'uint':
                            if type(value) == timedelta:
                                result[sphinx_attr] = int(value.total_seconds())
                            else:
                                result[sphinx_attr] = int(value)
                        elif self.columns[sphinx_attr] == 'timestamp':
                            if type(value) == datetime:
                                result[sphinx_attr] = datetime_to_timestamp(value)
                            if type(value) == str:
                                result[sphinx_attr] = string_to_timestamp(value)
                            if type(value) == int:
                                result[sphinx_attr] = value
                        else:
                            result[sphinx_attr] = value
        else:
            for attr in item_attrs:
                if attr in self.columns:
                    value = getattr(item, attr, None)
                    if attr in ('publishedAt', 'lastUpdated', 'createdAt') and value and type(value) != datetime:
                        value = timestamp_to_strftime(value)
                    result[attr] = value
        return result

    def select(self, columns='*', where='', values=(), order_by='', limit=1):
        if columns != '*':
            columns = columns.split(',')
            columns_sep = []
            for column in columns:
                column = '`' + column + '`'
                columns_sep.append(column)
            columns = ', '.join(columns_sep)

        sql = "SELECT " + columns + " FROM `" + self.__table_name + "`"
        if where:
            sql += " WHERE "
            sql += where
        if order_by:
            sql += " ORDER BY "
            sql += order_by
        if limit != 0:
            sql += " LIMIT "
            sql += str(limit)

        cursor = self._connector.query_values(sql, values)
        if limit == 1:
            res = cursor.fetchone()
        else:
            res = cursor.fetchall()
        cursor.close()
        return res

    def get(self, item):
        unique_key = item.unique_key
        key_value = getattr(item, unique_key, None)

        if self.sphinx:
            unique_key = unique_key.lower()

        sql = "SELECT * FROM `" + self.__table_name + "` WHERE " + unique_key + "=%s LIMIT 1"
        cursor = self._connector.query_values(sql, key_value)
        res = cursor.fetchone()
        cursor.close()
        return res

    def get_by_key(self, key_name, key_value):
        sql = "SELECT * FROM `" + self.__table_name + "` WHERE " + key_name + "=%s LIMIT 1"
        cursor = self._connector.query_values(sql, key_value)
        res = cursor.fetchone()
        cursor.close()
        return res

    def insert(self, item):
        duplicate = self.__check_duplicate_entry(item)
        uniq_key = self.__is_unique_key(item)
        if not duplicate and uniq_key:
            item.id = self.get_last_id() + 1
            self.last_id = item.id
            item_values = self.get_values_from_object(item)
            item_columns = list(item_values.keys())

            sql_columns = ','.join(item_columns)
            values = list(item_values.values())

            sql_columns = "(" + sql_columns + ") "
            sql_values = '%s,' * len(values)
            sql_values = sql_values.strip(',')
            sql_values = "VALUES (" + sql_values + ") "

            sql = "INSERT INTO " + self.__table_name
            sql = sql + sql_columns + sql_values
            cursor = self._connector.query_values(sql, values)
            cursor.close()

    def insert_or_update(self, item):
        duplicate = self.__check_duplicate_entry(item)
        uniq_key = self.__is_unique_key(item)
        if not duplicate and uniq_key:
            self.insert(item)
        else:
            self.update(item)

    def update(self, item, where=''):
        # Sphinx indexes doesnt change on UPDATE query, you've to delete and insert new item to index it
        if self.sphinx:
            self.delete(item)
            self.insert(item)
        else:
            unique_key = item.unique_key
            primary_key = item.primary_key

            item_values = self.get_values_from_object(item)
            item_values.pop(primary_key)
            columns = list(item_values.keys())
            values = list(item_values.values())
            key_value = getattr(item, unique_key)
            values.append(key_value)

            sql = "UPDATE " + self.__table_name + " SET "
            for column in columns:
                sql = sql + column + "=%s, "
            sql = sql.strip(', ')

            if self.sphinx:
                unique_key = unique_key.lower()

            sql = sql + " WHERE " + unique_key + "=%s"
            if where:
                sql = sql + "AND " + where

            cursor = self._connector.query_values(sql, values)
            cursor.close()

    def delete(self, item):
        unique_key = item.unique_key
        if self.sphinx:
            unique_key = unique_key.lower()
        sql = "DELETE FROM `" + self.__table_name + "` WHERE `" + unique_key + "`=%s"
        key_value = getattr(item, item.unique_key)
        cursor = self._connector.query_values(sql, key_value)
        cursor.close()

    def delete_by_key(self, key_name, key_value):
        sql = "DELETE FROM `" + self.__table_name + "` WHERE `" + key_name + "`=%s"
        cursor = self._connector.query_values(sql, key_value)
        cursor.close()

    def delete_channel(self, channel_id):
        sql = "DELETE FROM `" + self.__table_name + "` WHERE `channelid`=%s"
        cursor = self._connector.query_values(sql, channel_id)
        cursor.close()

    def count(self):
        sql = "SELECT COUNT(*) FROM " + self.__table_name
        cursor = self._connector.query(sql)
        result = cursor.fetchone()
        cursor.close()
        if self.sphinx:
            result = result.get('count(*)', 0)
        else:
            result = result.get('COUNT(*)', 0)
        return result

    def raw_sql(self, sql, *args):
        cursor = self._connector.query_values(sql, args)
        result = cursor.fetchall()
        cursor.close()
        return result


class VideosModel:
    unique_key = 'videoId'
    primary_key = 'id'
    id = None
    videoId = None
    caption = None
    categoryId = None
    channelId = None
    channelTitle = None
    commentCount = None
    captionLanguage = None
    captionUrl = None
    contentRatingMpaaRating = None
    contentRatingRussiaRating = None
    contentRatingYtRating = None
    defaultAudioLanguage = None
    defaultLanguage = None
    definition = None
    description = None
    dimension = None
    dislikeCount = None
    duration = None
    embeddable = None
    failureReason = None
    favoriteCount = None
    hasCustomThumbnail = None
    isAvailable = None
    isCaptions = None
    lastUpdated = None
    license = None
    licensedContent = None
    likeCount = None
    liveBroadcastContent = None
    privacyStatus = None
    publicStatsViewable = None
    publishedAt = None
    regionRestrictionAllowed = None
    regionRestrictionBlocked = None
    rejectionReason = None
    tags = None
    thumbnailsDefaultUrl = None
    thumbnailsHighUrl = None
    thumbnailsMaxresUrl = None
    thumbnailsMediumUrl = None
    thumbnailsStandardUrl = None
    title = None
    topicCategories = None
    trackKind = None
    uploadStatus = None
    viewCount = None

    lxml_subtitle = None

    subtitle = None
    stemmed_subtitle = None
    indexes = None
    timeframes = None
    speech_data = []

    def __init__(self):
        self.unique_key = VideosModel.unique_key
        self.primary_key = VideosModel.primary_key

    def _load_yt_list_items(self, json_object):
        self.videoId = json_object.get('id', None)
        self.channelId = json_object['snippet'].get('channelId', None)
        self.title = json_object['snippet'].get('title', None)
        self.channelTitle = json_object['snippet'].get('channelTitle', None)
        self.description = json_object['snippet'].get('description', None)
        self.publishedAt = json_object['snippet'].get('publishedAt', "0000-00-00 00:00:00")
        self.publishedAt = datetime.strptime(self.publishedAt[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        self.lastUpdated = current_string_time()

        self.tags = json_object['snippet'].get('tags', [])
        if self.tags:
            self.tags = ujson.dumps(self.tags)
        else:
            self.tags = None

        self.categoryId = json_object['snippet'].get('categoryId', None)
        self.liveBroadcastContent = json_object['snippet'].get('liveBroadcastContent', None)
        self.defaultAudioLanguage = json_object['snippet'].get('defaultAudioLanguage', None)
        self.thumbnailsDefaultUrl = json_object['snippet']['thumbnails']['default'].get('url', None)
        self.thumbnailsMediumUrl = json_object['snippet']['thumbnails']['medium'].get('url', None)
        self.thumbnailsHighUrl = json_object['snippet']['thumbnails']['high'].get('url', None)
        self.thumbnailsStandardUrl = json_object['snippet']['thumbnails'].get('standard', {}).get('url', None)
        self.thumbnailsMaxresUrl = json_object['snippet']['thumbnails'].get('maxres', {}).get('url', None)
        self.defaultLanguage = json_object['snippet'].get('defaultLanguage', None)
        self.duration = json_object['contentDetails'].get('duration', None)

        if self.duration:
            self.duration = isodate.parse_duration(self.duration)
            self.duration = int(self.duration.total_seconds())
            # Django stores duration in microseconds, convert seconds to microseconds
            self.duration = self.duration * 1000000

        self.dimension = json_object['contentDetails'].get('dimension', None)
        self.definition = json_object['contentDetails'].get('definition', None)

        self.caption = json_object['contentDetails'].get('caption', None)
        if self.caption == 'true':
            self.caption = True
        elif self.caption == 'false':
            self.caption = False

        self.hasCustomThumbnail = json_object['contentDetails'].get('hasCustomThumbnail', None)
        self.licensedContent = json_object['contentDetails'].get('licensedContent', None)

        self.regionRestrictionAllowed = json_object['contentDetails'].get('regionRestriction', {}).get('allowed', [])
        if self.regionRestrictionAllowed:
            self.regionRestrictionAllowed = ujson.dumps(self.regionRestrictionAllowed)
        else:
            self.regionRestrictionAllowed = None

        self.regionRestrictionBlocked = json_object['contentDetails'].get('regionRestriction', {}).get('blocked', [])
        if self.regionRestrictionBlocked:
            self.regionRestrictionBlocked = ujson.dumps(self.regionRestrictionBlocked)
        else:
            self.regionRestrictionBlocked = None

        self.contentRatingMpaaRating = json_object['contentDetails'].get('contentRating', {}).get('mpaaRating', None)
        self.contentRatingRussiaRating = json_object['contentDetails'].get('contentRating', {}).get('russiaRating',
                                                                                                    None)
        self.contentRatingYtRating = json_object['contentDetails'].get('contentRating', {}).get('ytRating', None)
        self.privacyStatus = json_object['status'].get('privacyStatus', None)
        self.uploadStatus = json_object['status'].get('uploadStatus', None)
        self.failureReason = json_object['status'].get('failureReason', None)
        self.rejectionReason = json_object['status'].get('rejectionReason', None)
        self.license = json_object['status'].get('license', None)
        self.embeddable = json_object['status'].get('embeddable', None)
        self.publicStatsViewable = json_object['status'].get('publicStatsViewable', None)
        self.viewCount = json_object['statistics'].get('viewCount', None)
        self.commentCount = json_object['statistics'].get('commentCount', None)
        self.likeCount = json_object['statistics'].get('likeCount', None)
        self.dislikeCount = json_object['statistics'].get('dislikeCount', None)
        self.favoriteCount = json_object['statistics'].get('favoriteCount', None)

    def _load_yt_search_items(self, json_object):
        self.videoId = json_object['id'].get('videoId', None)
        self.channelId = json_object['snippet'].get('channelId', None)
        self.title = json_object['snippet'].get('title', None)
        self.channelTitle = json_object['snippet'].get('channelTitle', None)
        self.description = json_object['snippet'].get('description', None)
        self.publishedAt = json_object['snippet'].get('publishedAt', "0000-00-00 00:00:00")
        self.publishedAt = datetime.strptime(self.publishedAt[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        self.lastUpdated = current_string_time()
        self.liveBroadcastContent = json_object['snippet'].get('liveBroadcastContent', None)
        self.thumbnailsDefaultUrl = json_object['snippet']['thumbnails']['default'].get('url', None)
        self.thumbnailsMediumUrl = json_object['snippet']['thumbnails']['medium'].get('url', None)
        self.thumbnailsHighUrl = json_object['snippet']['thumbnails']['high'].get('url', None)

    def load_yt_item(self, yt_response):
        if yt_response:
            if yt_response['kind'] == 'youtube#searchResult':
                self._load_yt_search_items(yt_response)
            elif yt_response['kind'] == 'youtube#video':
                self._load_yt_list_items(yt_response)
            else:
                return
        else:
            return


class ChannelsModel:
    unique_key = 'channelId'
    primary_key = 'id'
    id = None
    channelId = None
    title = None
    textDefaultLanguage = None
    commentCount = None
    country = None
    customUrl = None
    defaultLanguage = None
    description = None
    featuredChannelsTitle = None
    featuredChannelsUrls = None
    hiddenSubscriberCount = None
    hints = None
    isLinked = None
    keywords = None
    lastUpdated = None
    longUploadsStatus = None
    moderateComments = None
    privacyStatus = None
    publishedAt = None
    relatedPlaylistsFavorites = None
    relatedPlaylistsLikes = None
    relatedPlaylistsUploads = None
    showBrowseView = None
    showRelatedChannels = None
    subscriberCount = None
    thumbnailsDefaultUrl = None
    thumbnailsHighUrl = None
    thumbnailsMediumUrl = None
    topicCategories = None
    trackingAnalyticsAccountId = None
    videoCount = None
    viewCount = None
    watchIconImageUrl = None

    def __init__(self):
        self.unique_key = ChannelsModel.unique_key
        self.primary_key = ChannelsModel.primary_key

    def _load_yt_list_items(self, json_object):
        self.channelId = json_object.get('id', None)
        self.title = json_object['snippet'].get('title', None)
        self.description = json_object['snippet'].get('description', None)
        self.customUrl = json_object['snippet'].get('customUrl', None)
        self.publishedAt = json_object['snippet'].get('publishedAt', "0000-00-00 00:00:00")
        self.publishedAt = datetime.strptime(self.publishedAt[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        self.lastUpdated = current_string_time()
        self.thumbnailsDefaultUrl = json_object['snippet']['thumbnails']['default'].get('url', None)
        self.thumbnailsMediumUrl = json_object['snippet']['thumbnails']['medium'].get('url', None)
        self.thumbnailsHighUrl = json_object['snippet']['thumbnails']['high'].get('url', None)
        self.defaultLanguage = json_object['snippet'].get('defaultLanguage', None)
        self.country = json_object['snippet'].get('country', None)
        self.relatedPlaylistsLikes = json_object['contentDetails']['relatedPlaylists'].get('likes', None)
        self.relatedPlaylistsFavorites = json_object['contentDetails']['relatedPlaylists'].get('favorites', None)
        self.relatedPlaylistsUploads = json_object['contentDetails']['relatedPlaylists'].get('uploads', None)
        self.viewCount = json_object['statistics'].get('viewCount', None)
        self.commentCount = json_object['statistics'].get('commentCount', None)
        self.subscriberCount = json_object['statistics'].get('subscriberCount', None)
        self.videoCount = json_object['statistics'].get('videoCount', None)
        self.hiddenSubscriberCount = json_object['statistics'].get('hiddenSubscriberCount', None)

        self.topicCategories = json_object.get('topicDetails', {}).get('topicCategories', [])
        if self.topicCategories:
            self.topicCategories = ujson.dumps(self.topicCategories)
        else:
            self.topicCategories = None

        self.longUploadsStatus = json_object['status'].get('longUploadsStatus', None)
        self.privacyStatus = json_object['status'].get('privacyStatus', None)
        self.isLinked = json_object['status'].get('isLinked', None)
        self.keywords = json_object['brandingSettings']['channel'].get('keywords', None)
        self.trackingAnalyticsAccountId = json_object['brandingSettings']['channel'].get('trackingAnalyticsAccountId',
                                                                                         None)
        self.moderateComments = json_object['brandingSettings']['channel'].get('moderateComments', None)
        self.featuredChannelsTitle = json_object['brandingSettings']['channel'].get('featuredChannelsTitle', None)

        self.featuredChannelsUrls = json_object['brandingSettings']['channel'].get('featuredChannelsUrls', [])
        if self.featuredChannelsUrls:
            self.featuredChannelsUrls = ujson.dumps(self.featuredChannelsUrls)
        else:
            self.featuredChannelsUrls = None

        self.textDefaultLanguage = json_object['brandingSettings']['channel'].get('defaultLanguage', None)
        self.watchIconImageUrl = json_object['brandingSettings']['image'].get('watchIconImageUrl', None)

        self.hints = json_object['brandingSettings'].get('hints', [])
        if self.hints:
            self.hints = ujson.dumps(self.hints)
        else:
            self.hints = None

        self.showBrowseView = json_object['brandingSettings']['channel'].get('showBrowseView', None)
        self.showRelatedChannels = json_object['brandingSettings']['channel'].get('showRelatedChannels', None)

    def _load_yt_search_items(self, json_object):
        self.channelId = json_object['id'].get('channelId', None)
        self.title = json_object['snippet'].get('title', None)
        self.description = json_object['snippet'].get('description', None)
        self.publishedAt = json_object['snippet'].get('publishedAt', "0000-00-00 00:00:00")
        self.publishedAt = datetime.strptime(self.publishedAt[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        self.lastUpdated = current_string_time()
        self.thumbnailsDefaultUrl = json_object['snippet']['thumbnails']['default'].get('url', None)
        self.thumbnailsMediumUrl = json_object['snippet']['thumbnails']['medium'].get('url', None)
        self.thumbnailsHighUrl = json_object['snippet']['thumbnails']['high'].get('url', None)

    def load_yt_item(self, yt_response):
        if yt_response:
            if yt_response['kind'] == 'youtube#searchResult':
                self._load_yt_search_items(yt_response)
            elif yt_response['kind'] == 'youtube#channel':
                self._load_yt_list_items(yt_response)
            else:
                return
        else:
            return


class DataParserStatusesModel:
    def __init__(self):
        self.unique_key = 'id'
        self.primary_key = 'id'
        self.id = None
        self.taskId = None
        self.status = None
        self.status_description = None
        self.count_items_total = 0
        self.count_items_done = 0
        self.count_unavailable_videos = 0
        self.count_nocaption_videos = 0
        self.count_error_videos = 0
        self.estimated_quotas = 0
        self.createdAt = None
        self.lastUpdated = None
        self.fatal_error_details = None


class DataParserTasksModel:
    def __init__(self):
        self.unique_key = 'id'
        self.primary_key = 'id'
        self.id = None
        self.task = None
        self.task_item = None
        self.item_title = None
        self.createdAt = None
        self.finishedAt = None
        self.isFatalError = None


class ProxiesModel:
    def __init__(self):
        self.unique_key = 'id'
        self.primary_key = 'id'
        self.id = None
        self.type = None
        self.port = None
        self.ip = None
        self.login = None
        self.password = None
        self.isAvailable = None
        self.isCaptcha = None
        self.createdAt = None
        self.lastUpdated = None


class YouTubeAPI(VideosModel, ChannelsModel):
    __CLIENT_SECRETS_FILE = "client_secrets.json"
    # This OAuth 2.0 access scope allows for full read/write access to the
    # authenticated user's account and requires requests to use an SSL connection.
    __YOUTUBE_READ_WRITE_SSL_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
    __YOUTUBE_API_SERVICE_NAME = "youtube"
    __YOUTUBE_API_VERSION = "v3"
    # This variable defines a message to display if the CLIENT_SECRETS_FILE is
    # missing.
    __MISSING_CLIENT_SECRETS_MESSAGE = """
    WARNING: Please configure OAuth 2.0

    To make this sample run you will need to populate the client_secrets.json file
    found at:
       %s
    with information from the APIs Console
    https://console.developers.google.com

    For more information about the client_secrets.json file format, please visit:
    https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
    """ % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                       __CLIENT_SECRETS_FILE))

    def __init__(self, mysql_connector, yt_dev_key):
        self._connector = mysql_connector

        self.__DEVELOPER_KEY = yt_dev_key

        self.__YOUTUBE_KEY = build(self.__YOUTUBE_API_SERVICE_NAME, self.__YOUTUBE_API_VERSION,
                              developerKey=self.__DEVELOPER_KEY)

        # Default per day quotas limit 160000
        self.total_quotas = os.environ.get('YT_DAY_QUOTAS', 160000)
        self.total_quotas = int(self.total_quotas)

        self.quotas_table = "data_api_quotas"

        self.quotas_last_reset_time = self._init_quotas_last_reset_time()
        self.quotas_used = self._init_quotas_used()

    def _init_quotas_last_reset_time(self):
        tz_quotas = pytz.timezone('US/Pacific')
        tz_locale = pytz.timezone('Europe/Moscow')
        locale_datetime = datetime.now()
        quotas_reset_datetime = locale_datetime.astimezone(tz_quotas).replace(hour=0, minute=0, second=0, microsecond=0)
        locale_quotas_reset_datetime = quotas_reset_datetime.astimezone(tz_locale)
        return locale_quotas_reset_datetime

    def _init_quotas_used(self):
        sql = "SELECT quotas FROM " + self.quotas_table + " WHERE datetime > %s"
        cursor = self._connector.query_values(sql, self.quotas_last_reset_time)
        result = cursor.fetchall()
        cursor.close()
        quotas = 0
        if result:
            for item in result:
                quotas += int(item['quotas'])
        return quotas

    def _calc_quotas(self, part):
        quotas_pricing = {'auditdetails': 4,
                          'brandingsettings': 2,
                          'contentdetails': 2,
                          'contentownerdetails': 2,
                          'filedetails': 1,
                          'id': 0,
                          'livestreamingdetails': 2,
                          'localizations': 2,
                          'player': 0,
                          'processingdetails': 1,
                          'recordingdetails': 2,
                          'snippet': 2,
                          'statistics': 2,
                          'status': 2,
                          'suggestions': 1,
                          'topicdetails': 2
                          }

        part = part.lower()
        part = part.replace(' ', '')
        parts = part.split(',')

        quotas = 0
        for part in quotas_pricing:
            if part in parts:
                quotas += quotas_pricing[part]
        return quotas

    def calc_quotas_to_use(self, count_items, action):
        actions_parts = {'get_video': 'contentDetails,liveStreamingDetails,snippet,statistics,status,id',
                         'get_channel': 'id,contentOwnerDetails,status,snippet,statistics,topicDetails,brandingSettings,contentDetails',
                         'get_playlist_ids': 'snippet',
                         'get_playlist_ids_up_to': 'snippet'}
        cost = 1
        if action in actions_parts:
            cost += self._calc_quotas(actions_parts[action]) * count_items
        return cost

    def update_quotas(self, method_price, method_parts):
        self.quotas_used += method_price
        self.quotas_used += self._calc_quotas(method_parts)

        sql = "SELECT id FROM `" + self.quotas_table + "` WHERE datetime > %s"
        cursor = self._connector.query_values(sql, self.quotas_last_reset_time)
        res = cursor.fetchone()
        cursor.close()
        if res:
            id = res['id']
            sql = "UPDATE `" + self.quotas_table + "` SET quotas=%s WHERE id=%s"
            cursor = self._connector.query_values(sql, (self.quotas_used, id))
        else:
            sql = "INSERT INTO `" + self.quotas_table + "`(`datetime`, `quotas`) VALUES (%s, %s)"
            cursor = self._connector.query_values(sql, (datetime.now(), self.quotas_used))
        cursor.close()

    def get_left_quotas(self):
        quotas_left = self.total_quotas - self.quotas_used
        return quotas_left

    def search_video(self, query, part='snippet', order=None, max_results=50):
        result = self.__YOUTUBE_KEY.search().list(q=query, part=part, maxResults=max_results, type='video',
                                                  order=order).execute()
        result = result.get('items', [])
        results = []
        for item in result:
            video = VideosModel()
            video.load_yt_item(item)
            results.append(video)
        self.update_quotas(100, part)
        return results

    def search_channel(self, query, part='snippet', order=None, max_results=50):
        result = self.__YOUTUBE_KEY.search().list(q=query, part=part, maxResults=max_results, type='channel',
                                                  order=order).execute()
        result = result.get('items', [])
        results = []
        for item in result:
            channel = ChannelsModel()
            channel.load_yt_item(item)
            results.append(channel)
        self.update_quotas(100, part)
        return results

    def get_channel(self, channel_id, part='id,'
                                           'contentOwnerDetails,'
                                           'status,'
                                           'snippet,'
                                           'statistics,'
                                           'topicDetails,'
                                           'brandingSettings,'
                                           'contentDetails'):
        result = self.__YOUTUBE_KEY.channels().list(id=channel_id, part=part).execute()
        result = result.get('items', None)
        if result:
            result = result[0]
        channel = ChannelsModel()
        channel.load_yt_item(result)
        self.update_quotas(1, part)
        return channel

    def get_video(self, video_id, part='contentDetails,'
                                       'liveStreamingDetails,'
                                       'snippet,'
                                       'statistics,'
                                       'status,'
                                       'id'):
        result = self.__YOUTUBE_KEY.videos().list(id=video_id, part=part).execute()
        result = result.get('items', None)
        if result:
            result = result[0]
        video = VideosModel()
        video.load_yt_item(result)
        self.update_quotas(1, part)
        return video

    def get_many_videos(self, list_video_id, max_results=0, part='contentDetails,'
                                                                 'liveStreamingDetails,'
                                                                 'snippet,'
                                                                 'statistics,'
                                                                 'status,'
                                                                 'topicDetails,'
                                                                 'id'):
        if max_results == 0 or max_results > 50:
            nested_list_video_id = self.chunk_list(list_video_id, 50)
        else:
            nested_list_video_id = self.chunk_list(list_video_id, max_results)

        videos = []
        for list_video_id in nested_list_video_id:
            list_video_id = ','.join(list_video_id)
            result = self.__YOUTUBE_KEY.videos().list(id=list_video_id, part=part).execute()
            results = result.get('items', [])
            for item in results:
                video = VideosModel()
                video.load_yt_item(item)
                videos.append(video)
            self.update_quotas(1, part)
        return videos

    def get_playlist_ids(self, playlist_id, part='snippet', max_results=0):
        results = []
        if max_results == 0 or max_results > 50:
            search = self.__YOUTUBE_KEY.playlistItems().list(part=part, playlistId=playlist_id,
                                                             maxResults=50).execute()

            try:
                nextPageToken = search['nextPageToken']
            except KeyError:
                nextPageToken = None

            ids = []
            for item in search['items']:
                ids.append(item['snippet']['resourceId']['videoId'])
            results.extend(ids)
            self.update_quotas(1, part)

            while nextPageToken:
                search = self.__YOUTUBE_KEY.playlistItems().list(pageToken=nextPageToken, part=part,
                                                                 playlistId=playlist_id,
                                                                 maxResults=50).execute()

                ids = []
                for item in search['items']:
                    ids.append(item['snippet']['resourceId']['videoId'])
                results.extend(ids)
                self.update_quotas(1, part)

                try:
                    nextPageToken = search['nextPageToken']
                except KeyError:
                    break

        else:
            search = self.__YOUTUBE_KEY.playlistItems().list(playlistId=playlist_id, part=part,
                                                             maxResults=max_results).execute()
            ids = []
            for item in search['items']:
                ids.append(item['snippet']['resourceId']['videoId'])
            results.extend(ids)
            self.update_quotas(1, part)

        return results

    def get_playlist_ids_up_to(self, playlist_id, id_to_stop, part='snippet'):
        results = []
        search = self.__YOUTUBE_KEY.playlistItems().list(part=part, playlistId=playlist_id,
                                                         maxResults=50).execute()
        self.update_quotas(1, part)

        try:
            nextPageToken = search['nextPageToken']
        except KeyError:
            nextPageToken = None

        ids = []
        for item in search['items']:
            id = item['snippet']['resourceId']['videoId']
            if id == id_to_stop:
                self.update_quotas(1, part)
                return ids
            else:
                ids.append(id)

        results.extend(ids)

        while nextPageToken:
            search = self.__YOUTUBE_KEY.playlistItems().list(pageToken=nextPageToken, part=part,
                                                             playlistId=playlist_id,
                                                             maxResults=50).execute()
            self.update_quotas(1, part)

            ids = []
            for item in search['items']:
                id = item['snippet']['resourceId']['videoId']
                if id == id_to_stop:
                    self.update_quotas(1, part)
                    return ids
                else:
                    ids.append(id)

            results.extend(ids)

            try:
                nextPageToken = search['nextPageToken']
            except KeyError:
                break

        return results

    def get_oauth(self):
        flow = flow_from_clientsecrets(self.__CLIENT_SECRETS_FILE, scope=self.__YOUTUBE_READ_WRITE_SSL_SCOPE,
                                       message=self.__MISSING_CLIENT_SECRETS_MESSAGE)
        # Uncomment print(flow) when the OAuth token is revoked: a browser window will open
        # asking for access to the Google account, producing fresh credentials.

        storage = Storage("credentials.json")
        credentials = storage.get()

        if credentials is None or credentials.invalid:
            credentials = run_flow(flow, storage)

        with open("youtube-v3-api-captions.json", encoding="utf_8_sig") as f:
            doc = f.read()
            return build_from_document(doc, http=credentials.authorize(httplib2.Http()))

    @staticmethod
    def chunk_list(l, n):
        res = []
        for i in range(0, len(l), n):
            res.append(l[i:i + n])
        return res

    @staticmethod
    def _get_dict_values(obj, key):
        """Recursively pull values of specified key from nested JSON."""
        arr = []

        def extract(obj, arr, key):
            """Return all matching values in an object."""
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, (dict, list)):
                        extract(v, arr, key)
                    elif k == key:
                        arr.append(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract(item, arr, key)
            return arr

        results = extract(obj, arr, key)
        return results


class CaptionParser:
    def __init__(self):
        self.count_videos_parsed = 0
        self.count_unavailable = 0
        self.count_nocaptions = 0
        self.count_errors = 0
        self.allowed_chars = SPEECH_ALLOWED_CHARS_EN

    def show_statistic(self):
        logger.info(
            'Captions run statistic: parsed=%s, unavailable=%s, no_captions=%s, http_errors=%s',
            self.count_videos_parsed, self.count_unavailable, self.count_nocaptions, self.count_errors,
        )

    def load_captions(self, video, language, kind_priority, proxy=None):
        self.count_videos_parsed += 1
        return self._parse_captions(video, language, kind_priority, proxy=proxy)

    def load_many_captions(self, videos, language, kind_priority):
        result = []
        for video in videos:
            res = self._parse_captions(video, language, kind_priority)
            result.append(res)
            self.count_videos_parsed += 1
        return result

    @staticmethod
    def i_to_I(string):
        string = string.lower()
        string = string.strip()

        if string[0:2] == "i ":
            string = string[2:]
            string = "I " + string

        if string[0:3] == "im ":
            string = string[3:]
            string = "I\'m " + string

        if string[0:4] == "i\'d ":
            string = string[4:]
            string = "I\'d " + string

        if string[0:2] == "i\'":
            string = string[2:]
            string = "I\'" + string

        if string[-2:] == " i":
            string = string[:-2]
            string = string + " I"

        if string[-3:] == " im":
            string = string[:-3]
            string = string + " I\'m"

        if string[-4:] == " i\'d":
            string = string[:-4]
            string = string + " I\'d"

        while " i " in string or " i\'" in string or " im " in string:
            string = string.replace(" i ", " I ")
            string = string.replace(" i\'", " I\'")
            string = string.replace(" im ", " I\'m ")
        return string

    def clean_captions_en(self, text):
        text = text.lower()
        text = text.replace('\"', '\'')
        text = text.replace('+', ' plus ')
        text = text.replace('   ', ' ')
        text = text.replace('  ', ' ')
        text = self.remove_unsupported_chars(text)
        text = self.i_to_I(text)
        return text

    def _parse_captions(self, video, language, kind_priority, proxy=None):
        """
            Error status:
            0 = No subtitles available
            -1 = Video unavailable
            -2 = Some HTTP error
        """
        try:
            # Stream captions data in chunks to avoid downloading the full page
            CHUNKSIZE = 1024
            r = ""
            video_url = "https://www.youtube.com/watch?v=" + video.videoId
            with closing(requests.get(video_url, stream=True, proxies=proxy, timeout=10)) as res:
                for chunk in res.iter_content(chunk_size=CHUNKSIZE, decode_unicode=True):
                    r = "".join([r, chunk])
                    if 'captionTrackIndices' in r:
                        break
            r = parse.unquote(r)

        except (requests.exceptions.RequestException, requests.exceptions.TooManyRedirects,
                requests.exceptions.ProxyError):
            self.count_errors += 1
            if proxy:
                raise self.ProxyUnavailable("Unknown proxy error on video ID:" + video.videoId + " with proxy: "
                                            + str(proxy))
            else:
                return video

        except Exception:
            self.count_errors += 1
            return video

        if 'captionTracks' in r:
            video.isAvailable = 1
            captionTracksIndex = r.find('\"captionTracks')
            url_begin = captionTracksIndex + 17
            url_end = r.index("\"audioTracks", url_begin) - 2
            url = r[url_begin:url_end]
            url = url.replace('\\', '').replace('\\', '').replace('\\', '').replace('\\', '')
            url = url.replace('u0026', '&')
            url = url.replace('%2C', ',')
            if '[' not in url and ']' not in url:
                url = '[' + url + ']'

            res = ujson.loads(url)

            # Pick the caption track by language, preferring the requested kind (ASR vs. standard)
            if kind_priority == 'ASR':
                high_priority_url_index = None
                medium_priority_url_index = None
                low_priority_url_index = None

                for i, data in enumerate(res):
                    if language in data['languageCode'] and 'a.' + language in data['vssId']:
                        high_priority_url_index = i
                        break
                    elif language == data['languageCode']:
                        medium_priority_url_index = i
                    elif language in data['languageCode']:
                        low_priority_url_index = i

                if high_priority_url_index is not None:
                    video.captionUrl = res[high_priority_url_index]['baseUrl']
                    video.captionLanguage = language
                    video.trackKind = 'ASR'

                elif medium_priority_url_index is not None:
                    video.captionUrl = res[medium_priority_url_index]['baseUrl']
                    video.captionLanguage = language
                    video.trackKind = 'standard'

                elif low_priority_url_index is not None:
                    video.captionUrl = res[low_priority_url_index]['baseUrl']
                    video.captionLanguage = language
                    video.trackKind = 'standard'


            elif kind_priority == 'standard':
                high_priority_url_index = None
                medium_priority_url_index = None
                low_priority_url_index = None
                for i, data in enumerate(res):
                    if language == data['languageCode'] and 'a.' + language not in data['vssId']:
                        high_priority_url_index = i
                        break
                    elif language in data['languageCode'] and language in data['vssId'] and 'a.' + language not in data['vssId']:
                        medium_priority_url_index = i
                    elif language in data['languageCode']:
                        low_priority_url_index = i

                if high_priority_url_index is not None:
                    video.captionUrl = res[high_priority_url_index]['baseUrl']
                    video.captionLanguage = language
                    video.trackKind = 'standard'

                elif medium_priority_url_index is not None:
                    video.captionUrl = res[medium_priority_url_index]['baseUrl']
                    video.captionLanguage = language
                    video.trackKind = 'standard'

                elif low_priority_url_index is not None:
                    video.captionUrl = res[low_priority_url_index]['baseUrl']
                    video.captionLanguage = language
                    video.trackKind = 'ASR'

            else:
                raise ValueError(
                    "Wrong kind_priority value: '%s', allowed values: ASR, standard" % kind_priority
                )

            if video.captionUrl:
                caption = self.download_captions(video.captionUrl, proxies=proxy)
                video.subtitle = caption['subtitle']
                video.isCaptions = 1
                video.stemmed_subtitle = caption['stemmed_subtitle']
                video.indexes = caption['indexes']
                video.timeframes = caption['timeframes']
                video.lxml_subtitle = caption['lxml_subtitle']

            else:
                video.isCaptions = 0
                self.count_nocaptions += 1

        elif 'captionTracks' not in r and 'like-button-renderer-like-button' in r:
            video.isAvailable = 1
            video.isCaptions = 0
            self.count_nocaptions += 1

        elif 'captionTracks' not in r and 'g-recaptcha' in r:
            raise self.YtCaptcha("YouTube captcha has occurred on video ID:" + video.videoId + ", proxy: " + str(proxy))

        elif 'captionTracks' not in r and 'g-recaptcha' not in r and res.status_code != 200:
            raise self.YtNoResponse("Can\'t get server response (response code:" + res.status_code +
                                        ") on video ID:" + video.videoId + ", proxy: " + str(proxy))

        else:
            self.count_unavailable += 1
            video.isAvailable = 0

        return video

    def download_captions(self, caption_url, proxies=None):
        try:
            timedtext = requests.get(caption_url, proxies=proxies)
        except requests.exceptions.ProxyError:
            raise self.ProxyError("Can\'t download captions, proxy unavailable:" + str(proxies))

        timedtext = timedtext.text
        soup = BeautifulSoup(timedtext, 'lxml')
        startTime_list = []
        results = []

        for item in soup.findAll('text'):
            try:
                start = int(float(item['start']))
            except KeyError:
                start = 0

            if len(startTime_list) > 0 and item['start'] in startTime_list:
                continue

            try:
                dur = ceil(float(item['dur']))
                if dur == 0:
                    continue
                else:
                    end = start + dur
            except KeyError:
                continue

            text = item.get_text()
            text = BeautifulSoup(text, "lxml").text
            if len(text) == 0:
                continue

            # Replacing quotes, fixing spaces, upper 'I' phrases
            # and removing chars which not described in charset_table in sphinx.conf
            text = self.clean_captions_en(text)
            temp = {'text': text, 'startTime': start, 'endTime': end}
            results.append(temp)

        stemmer = PorterStemmer()
        indexes = ''
        timeframes = ''
        subtitle = ''
        stemmed_subtitle = ''

        last_index = 0
        for sub in results:
            splited_sub = sub['text'].split(' ')
            last_index += len(splited_sub)
            indexes = indexes + ',' + str(last_index)
            subtitle = subtitle + '  ' + '  '.join(splited_sub)
            for word in splited_sub:
                word = word.lower()
                if len(word) >= 2:
                    if word[0] == '[' and word[-1] == ']':
                        stemmed_subtitle = stemmed_subtitle + '  ' + '[' + stemmer.stem(word[1:-1]) + ']'
                    else:
                        stemmed_subtitle = stemmed_subtitle + '  ' + stemmer.stem(word)
                else:
                    stemmed_subtitle = stemmed_subtitle + '  ' + stemmer.stem(word)

            timeframes = timeframes + ',' + str(sub['startTime']) + '-' + str(sub['endTime'])

        subtitle = subtitle.strip(',').strip()
        # Search module wont work correctly without spaces at the end of subtitle
        subtitle = ' ' + subtitle + ' '
        stemmed_subtitle = stemmed_subtitle.strip(',').strip()
        # Same for stemmed sub
        stemmed_subtitle = ' ' + stemmed_subtitle + ' '
        indexes = indexes.strip(',').strip()
        timeframes = timeframes.strip(',').strip()

        result = {'subtitle': subtitle, 'stemmed_subtitle': stemmed_subtitle, 'indexes': indexes,
                  'timeframes': timeframes, 'lxml_subtitle': timedtext}
        return result

    def remove_unsupported_chars(self, string):
        for ch in string:
            if ch not in self.allowed_chars:
                string = string.replace(ch, '', 1)
        return string

    class YtCaptcha(Exception):
        def __init__(self, text):
            self.txt = text

    class YtNoResponse(Exception):
        def __init__(self, text):
            self.txt = text

    class ProxyUnavailable(Exception):
        def __init__(self, text):
            self.txt = text

    class ProxyError(Exception):
        def __init__(self, text):
            self.txt = text

class Videos(VideosModel):
    def __init__(self, MySQL_connector, Sphinx_connector):
        self.MySQL = Table(MySQL_connector, 'videos')
        self.Sphinx = Table(Sphinx_connector, 'videos', sphinx=True)

    def _merge_objects(self, mysql_object, sphinx_object):
        self_attrs = dir(VideosModel)
        result = VideosModel()
        for attr in self_attrs:
            if '_' in attr[0:1] or '__' in attr[0:2]:
                continue
            mysql_value = getattr(mysql_object, attr, None)
            sphinx_value = getattr(sphinx_object, attr.lower(), None)
            if mysql_value:
                setattr(result, attr, mysql_value)
                continue
            elif sphinx_value:
                setattr(result, attr, sphinx_value)
                continue
            else:
                setattr(result, attr, None)
        return result

    def save(self, item):
        self.MySQL.insert(item)
        self.Sphinx.insert(item)

    def save_or_update(self, item):
        self.MySQL.insert_or_update(item)
        self.Sphinx.insert_or_update(item)

    def get(self, video_object):
        mysql_res = self.MySQL.get(video_object)
        result = None
        if mysql_res:
            video = VideosModel()
            mysql_res = self.MySQL.load_values_to_object(video, mysql_res)
            sphinx_res = self.Sphinx.get(video_object)
            sphinx_res = self.Sphinx.load_values_to_object(video, sphinx_res)
            result = self._merge_objects(mysql_res, sphinx_res)
        return result

    def get_by_id(self, video_id):
        video = VideosModel()
        mysql_res = self.MySQL.get_by_key(self.unique_key, video_id)
        if mysql_res:
            mysql_res = self.MySQL.load_values_to_object(video, mysql_res)

        sphinx_res = self.Sphinx.get_by_key(self.unique_key, video_id)
        if sphinx_res:
            sphinx_res = self.Sphinx.load_values_to_object(video, sphinx_res)

        if mysql_res and sphinx_res:
            result = self._merge_objects(mysql_res, sphinx_res)
            return result
        elif mysql_res:
            return mysql_res
        elif sphinx_res:
            return sphinx_res
        else:
            return None

    def get_channel_mysql_video_ids(self, channel_id):
        videos_ids = self.MySQL.select(columns='videoId', where='channelId=%s', limit=0, values=channel_id)
        result = []
        if videos_ids:
            for video_id in videos_ids:
                result.append(video_id['videoId'])
        return result

    def get_channel_sphinx_video_ids(self, channel_id):
        videos_ids = self.Sphinx.raw_sql("SELECT videoid FROM videos WHERE channelid=%s LIMIT 100000000 "
                                         "OPTION max_matches=100000000", channel_id)
        result = []
        if videos_ids:
            for video_id in videos_ids:
                result.append(video_id['videoid'])
        return result

    def get_channel_nocaption_videos_ids(self, channel_id):
        videos_ids = self.MySQL.select(columns='videoId', where='channelId=%s AND isCaptions=%s',
                                       limit=0, values=(channel_id, 0))
        result = []
        if videos_ids:
            for video_id in videos_ids:
                result.append(video_id['videoId'])
        return result

    def get_channel_unavailable_videos_ids(self, channel_id):
        videos_ids = self.MySQL.select(columns='videoId', where='channelId=%s AND isAvailable=%s',
                                       limit=0, values=(channel_id, 0))
        result = []
        if videos_ids:
            for video_id in videos_ids:
                result.append(video_id['videoId'])
        return result

    def update(self, item, mysql=True, sphinx=True):
        if mysql:
            self.MySQL.update(item)
        if sphinx:
            self.Sphinx.update(item)

    def update_many(self, list_objects, mysql=True, sphinx=True):
        for item in list_objects:
            self.update(item, mysql=mysql, sphinx=sphinx)

    def delete(self, video_object):
        self.MySQL.delete(video_object)
        self.Sphinx.delete(video_object)

    def delete_by_id(self, video_id):
        self.MySQL.delete_by_key(self.unique_key, video_id)
        self.Sphinx.delete_by_key(self.unique_key, video_id)

    def delete_channel(self, channel_id):
        self.MySQL.delete_channel(channel_id)
        self.Sphinx.delete_channel(channel_id)
        self.MySQL.raw_sql("DELETE FROM `channels` WHERE channelId=%s", channel_id)


class Channels(ChannelsModel):
    def __init__(self, MySQL_connector, Sphinx_connector):
        self.MySQL = Table(MySQL_connector, 'channels')
        self.SphinxVideos = Table(Sphinx_connector, 'videos', sphinx=True)

    def save(self, item):
        self.MySQL.insert(item)

    def save_or_update(self, item):
        self.MySQL.insert_or_update(item)

    def get(self, channel_object):
        mysql_res = self.MySQL.get(channel_object)
        if mysql_res:
            channel = ChannelsModel()
            mysql_res = self.MySQL.load_values_to_object(channel, mysql_res)
        return mysql_res

    def get_by_id(self, channel_id):
        mysql_res = self.MySQL.get_by_key(self.unique_key, channel_id)
        if mysql_res:
            channel = ChannelsModel()
            mysql_res = self.MySQL.load_values_to_object(channel, mysql_res)
        return mysql_res

    def get_channel_video_ids(self, channel_id):
        videos_ids = self.MySQL.select(columns='videoId', where='channelId=%s', limit=0, values=channel_id)
        result = []
        if videos_ids:
            for video_id in videos_ids:
                result.append(video_id['videoId'])
        return result

    def get_all_channels_ids(self):
        channel_ids = self.MySQL.select(columns='channelId', limit=0)
        result = []
        if channel_ids:
            for channel_id in channel_ids:
                result.append(channel_id['channelId'])
        return result

    def update(self, item):
        self.MySQL.update(item)

    def update_many(self, list_objects):
        for item in list_objects:
            self.MySQL.update(item)

    def delete(self, channel_object):
        self.MySQL.delete_channel(channel_object.channelId)
        self.SphinxVideos.delete_channel(channel_object.channelId)
        self.MySQL.raw_sql("DELETE FROM `channels` WHERE channelId=%s", channel_object.channelId)

    def delete_by_id(self, channel_id):
        self.MySQL.delete_channel(channel_id)
        self.SphinxVideos.delete_channel(channel_id)
        self.MySQL.raw_sql("DELETE FROM `channels` WHERE channelId=%s", channel_id)

    def mysql_count(self, channel_id):
        res = self.MySQL.raw_sql("SELECT COUNT(*) FROM videos WHERE channelid=%s", channel_id)
        res = res[0]['COUNT(*)']
        return res

    def sphinx_count(self, channel_id):
        res = self.SphinxVideos.raw_sql("SELECT count(*) FROM videos WHERE channelid IN(%s)", channel_id)
        res = res[0]['count(*)']
        return res

    def mysql_last_video_id(self, channel_id):
        res = self.MySQL.raw_sql("SELECT videoid FROM videos WHERE channelid=%s ORDER BY id DESC", channel_id)
        if res:
            res = res[0]['videoid']
        else:
            res = None
        return res

    def sphinx_last_video_id(self, channel_id):
        res = self.MySQL.raw_sql("SELECT videoid FROM videos WHERE channelid IN (%s) ORDER BY id DESC", channel_id)
        if res:
            res = res[0]['videoid']
        else:
            res = None
        return res


class DataParserStatuses(DataParserStatusesModel):
    def __init__(self, MySQL_connector):
        self.MySQL = Table(MySQL_connector, 'data_parser_statuses')

    def save(self, parser_status):
        parser_status.lastUpdated = current_string_time()
        self.MySQL.insert(parser_status)
        parser_status.id = self.MySQL.get_last_id()

    def delete(self, parser_status):
        self.MySQL.delete(parser_status)

    def update(self, parser_status):
        parser_status.lastUpdated = current_string_time()
        self.MySQL.update(parser_status)

    def load_captions_statistic(self, parser_status_obj, caption_parser_object):
        parser_status_obj.count_unavailable_videos = caption_parser_object.count_unavailable
        parser_status_obj.count_nocaption_videos = caption_parser_object.count_nocaptions
        parser_status_obj.count_error_videos = caption_parser_object.count_errors
        return parser_status_obj

    def create_new_status(self):
        new_status = DataParserStatusesModel()
        new_status.createdAt = current_string_time()
        new_status.lastUpdated = current_string_time()
        return new_status

    def add_new_status(self, status, status_description=None):
        new_status = self.create_new_status()
        new_status.status = status
        new_status.status_description = status_description
        new_status.lastUpdated = current_string_time()
        self.MySQL.insert(new_status)

    def get_last_status(self):
        last_status = None
        res = self.MySQL.select(order_by="id DESC", limit=1)
        if res:
            last_status = DataParserStatusesModel()
            last_status = self.MySQL.load_values_to_object(last_status, res)
        return last_status


class DataParserTasks(DataParserTasksModel):
    def __init__(self, MySQL_connector):
        self.MySQL = Table(MySQL_connector, 'data_parser_tasks')

    def get_fresh_task(self):
        res = None
        mysql_res = self.MySQL.select(where="finishedAt IS NULL AND isFatalError IS NULL", order_by='id DESC', limit=1)
        if mysql_res:
            res = DataParserTasksModel()
            res = self.MySQL.load_values_to_object(res, mysql_res)
        return res

    def set_finished(self, task):
        task.finishedAt = current_string_time()
        self.MySQL.update(task)

    def set_fatal_error(self, task):
        task.finishedAt = current_string_time()
        task.isFatalError = 1
        self.MySQL.update(task)


class Proxies(ProxiesModel):
    def __init__(self, MySQL_connector):
        self.MySQL = Table(MySQL_connector, 'proxies')

    def save(self, proxy):
        proxy.lastUpdated = current_string_time()
        self.MySQL.insert(proxy)
        proxy.id = self.MySQL.get_last_id()

    def delete(self, proxy):
        self.MySQL.delete(proxy)

    def update(self, proxy):
        proxy.lastUpdated = current_string_time()
        self.MySQL.update(proxy)

    def create_new_proxy(self, type, ip, port, isAvailable=1, isCaptcha=0, login=None, password=None):
        proxy = ProxiesModel()
        proxy.createdAt = current_string_time()
        proxy.lastUpdated = proxy.createdAt
        proxy.type = type
        proxy.ip = ip
        proxy.port = port
        proxy.login = login
        proxy.password = password
        proxy.isAvailable = isAvailable
        proxy.isCaptcha = isCaptcha
        return proxy

    def get_last_proxy(self):
        last_proxy = None
        res = self.MySQL.select(order_by="id DESC", limit=1)
        if res:
            last_proxy = ProxiesModel()
            last_proxy = self.MySQL.load_values_to_object(last_proxy, res)
        return last_proxy

    def get_available_proxy(self):
        results = self.MySQL.select(where="isAvailable=1 AND isCaptcha=0", limit=10000)
        proxies = []
        for res in results:
            proxy = ProxiesModel()
            proxy = self.MySQL.load_values_to_object(proxy, res)
            proxies.append(proxy)
        return proxies

    def get_all_proxy(self):
        results = self.MySQL.select(limit=10000)
        proxies = []
        for res in results:
            proxy = ProxiesModel()
            proxy = self.MySQL.load_values_to_object(proxy, res)
            proxies.append(proxy)
        return proxies

    def dict_format_proxy(self, proxy):
        proxy_type = str(proxy.type)
        if proxy.login and proxy.password:
            proxy_str = "https://" + str(proxy.login) + ":" + str(proxy.password) + "@" + str(proxy.ip) + ":" + str(proxy.port)
        else:
            proxy_str = str(proxy.ip) + ":" + str(proxy.port)

        proxy_dict = {proxy_type: proxy_str}
        return proxy_dict
