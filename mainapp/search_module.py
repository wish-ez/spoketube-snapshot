"""
Sphinx search layer.

SphinxSearchValues wraps a cleaned search form into the parameters the Sphinx
query needs (stemmed speech terms, escaped quotes, channel id filters, date
and duration ranges, ordering). SphinxSearchModule composes the Sphinx QL
query, returns a page of matching video ids, hydrates them with the ORM
Videos rows, and attaches per-video speech matches via speech_parser.
"""

import datetime
import time
import ujson
from .models import Videos
from .speech_parser import parse_speech_data, parse_match_speech_data, stem_request
from django.db.models import Case, When
from spoketube.settings import ALLOWED_CHARS_EN


class SphinxSearchResult:
    """
    Dummy class to keep Sphinx search result
    """

    def __init__(self):
        self.videos_ids = []
        self.videos = []
        self.shared_video = None
        self.sphinx_ids_execution_time = None
        self.execution_time = None
        self.total_videos = None
        self.total_matches = None
        self.sql = None


class SphinxSearchValues:
    """
    Class to keep and handle Sphinx search values during searching
    """

    def __init__(self, search_request, shared_result=None, shared_moment=None):
        """
        :param dict search_request: Cleaned GET request from views file, contains users search parameters
        :param string shared_result: Value of shared_result parameter in GET request
        :param string shared_moment: Value of shared_result parameter in GET request
        """
        self.exact_match = search_request.get('exact')
        self.speech = search_request.get('speech')

        # Preparing speech request by stemming (if exact match not set) and dividing it into words
        if self.speech:
            if not self.exact_match:
                self.speech = stem_request(self.speech)
            self.speech = self.speech.split(',')

        # Ordering speech tags by desc length
        self.speech = sorted(self.speech, key=len, reverse=True)
        # Replacing quotes (') with escaped quotes (\') for Sphinx QL
        self.escaped_speech = self.escape_string_list(self.speech)

        self.title = search_request.get('title')
        self.description = search_request.get('description')
        self.tags = search_request.get('tags')

        self.option_channels_id = search_request.get('channels_id')
        self.option_start_date = search_request.get('start_date')
        self.option_end_date = search_request.get('end_date')
        self.option_min_duration = search_request.get('min_duration')
        self.option_max_duration = search_request.get('max_duration')
        self.order = search_request.get('order')
        self.direction = search_request.get('direction')

        # Clean escape symbols from shared_result values
        if shared_result:
            shared_result = self._clean_shared(shared_result)
            self.shared_result = shared_result.replace('result-', '')[0:11]
        else:
            self.shared_result = None

        # Clean escape symbols from shared_moment values
        if shared_moment:
            self.shared_moment = {}
            shared_moment = self._clean_shared(shared_moment)
            shared_moment = shared_moment.split(',')
            if len(shared_moment) == 6:
                self.shared_moment['id'] = shared_moment[0]
                self.shared_moment['start'] = int(shared_moment[1])
                self.shared_moment['end'] = int(shared_moment[2])
                self.shared_moment['start_id'] = int(shared_moment[3])
                self.shared_moment['end_id'] = int(shared_moment[4])
                self.shared_moment['loop'] = shared_moment[5]
            else:
                self.shared_moment = None
        else:
            self.shared_moment = None

        self.prepared_subtitle = None
        self.prepared_title = None
        self.prepared_description = None
        self.prepared_tags = None

    def escape_string_list(self, string_list):
        res = []
        for str in string_list:
            str = self.escape_string(str)
            res.append(str)
        return res

    def escape_string(self, string):
        string = string.replace('\'', '\\\'')
        return string

    def _prepare_match(self, request_list, match_option, match_operator):
        """
        Convert request values into Sphinx-acceptable part of query
        :param list request_list: List of request string values
        :param string match_option: Option to add '=' symbol in SQL if exact matches on
        :param string match_operator: Logic operator for several tags to search (e.g. | )
        :return: string
        """
        if request_list:
            match_operator = " " + match_operator + " "
            res = []
            for req in request_list:
                temp = []
                splited_req = req.split(' ')
                for s_req in splited_req:
                    temp.append(match_option + s_req)
                temp = '  '.join(temp)
                temp = '\"' + temp + '\"'
                res.append(temp)
            result = match_operator.join(res)
            return result
        else:
            return ''

    def _clean_shared(self, string):
        """
        Remove symbols which nor presents in ALLOWED_CHARS from share value of GET parameter
        :param string string: String with share value
        :return: string
        """
        string = string.replace(' ', '')

        for ch in string:
            if ch not in ALLOWED_CHARS_EN:
                string = string.replace(ch, '', 1)
        return string

    def prepare_subtitle(self, match_operator):
        """
        Prepare values to search in 'subtitle' field of Sphinx index
        :param string match_operator: Logic operator for several tags to search (e.g. | )
        :return: string
        """
        self.prepared_subtitle = self._prepare_match(self.escaped_speech, "=", match_operator)
        return self.prepared_subtitle

    def prepare_title(self, match_option, match_operator):
        """
        Prepare values to search in 'title' field of Sphinx index
        :param string match_option: Option to add '=' symbol in SQL if exact matches on
        :param string match_operator: Logic operator for several tags to search (e.g. | )
        :return: string
        """
        splited_title = self.title.split(',')
        splited_title = self.escape_string_list(splited_title)
        self.prepared_title = self._prepare_match(splited_title, match_option, match_operator)
        return self.prepared_title

    def prepare_description(self, match_option, match_operator):
        """
        Prepare values to search in 'description' field of Sphinx index
        :param string match_option: Option to add '=' symbol in SQL if exact matches on
        :param string match_operator: Logic operator for several tags to search (e.g. | )
        :return: string
        """
        splited_description = self.description.split(',')
        splited_description = self.escape_string_list(splited_description)
        self.prepared_description = self._prepare_match(splited_description, match_option, match_operator)
        return self.prepared_description

    def prepare_tags(self, match_option, match_operator):
        """
        Prepare values to search in 'tags' field of Sphinx index
        :param string match_option: Option to add '=' symbol in SQL if exact matches on
        :param string match_operator: Logic operator for several tags to search (e.g. | )
        :return: string
        """
        splited_tags = self.tags.split(',')
        splited_tags = self.escape_string_list(splited_tags)
        self.prepared_tags = self._prepare_match(splited_tags, match_option, match_operator)
        return self.prepared_tags


class SphinxSearchModule:
    def __init__(self, sphinx_conn, table_name):
        self._connector = sphinx_conn
        self._table_name = table_name
        self.total_found = None

        self._speech_tag_open = '<span class=\"speech-match-value\">'
        self._speech_tag_close = '</span>'

        self._title_tag_open = '<span class=\"title-match-value\">'
        self._title_tag_close = '</span>'

        self._description_tag_open = '<span class=\"description-match-value\">'
        self._description_tag_close = '</span>'

        self._tags_tag_open = '<span class=\"tags-match-value\">'
        self._tags_tag_open_replace = '<span class=\'tags-match-value\'>'
        self._tags_tag_close = '</span>'

        self.results_max = "1000"

    def prepare_search_values(self, search_request):
        return SphinxSearchValues(search_request)

    def get_videos_ids(self, search_values, meta_info=True):
        self_time = time.time()

        select = "SELECT videoid "
        from_ = " FROM " + self._table_name + " "
        where = "WHERE "
        option = ""
        limit = "LIMIT " + self.results_max + " "

        match_open = "MATCH ('"
        match_body = ""
        match_close = "') "
        match_option = ""
        match_operator = "|"

        reverse_result = False

        if search_values.exact_match:
            match_option = "="

        if search_values.speech:
            if search_values.exact_match:
                match_body += "@subtitle " + search_values.prepare_subtitle(match_operator)
            else:
                match_body += "@stemmed_subtitle " + search_values.prepare_subtitle(match_operator)

        if search_values.title:
            match_body += "@title " + search_values.prepare_title(match_option, match_operator)

        if search_values.description:
            match_body += "@description " + search_values.prepare_description(match_option, match_operator)

        if search_values.tags:
            match_body += "@tags " + search_values.prepare_tags(match_option, match_operator)

        select = select.strip(', ')

        match = match_open + match_body + match_close
        where = where + match + " "

        if search_values.option_channels_id:
            where += "AND channelid IN (" + search_values.option_channels_id + ")"

        if search_values.option_start_date:
            try:
                start_date = int(time.mktime(time.strptime(str(search_values.option_start_date), '%Y-%m-%d')))
                where += "AND publishedAt >= " + str(start_date) + " "
            except (ValueError, TypeError):
                pass

        if search_values.option_end_date:
            try:
                end_date = int(time.mktime(time.strptime(str(search_values.option_end_date), '%Y-%m-%d')))
                where += "AND publishedAt <= " + str(end_date) + " "
            except (ValueError, TypeError):
                pass

        if search_values.option_min_duration:
            try:
                min_duration = datetime.timedelta(hours=search_values.option_min_duration.hour,
                                                  minutes=search_values.option_min_duration.minute).seconds
                where += "AND duration >= " + str(min_duration) + " "
            except (ValueError, TypeError):
                pass

        if search_values.option_max_duration:
            try:
                max_duration = datetime.timedelta(hours=search_values.option_max_duration.hour,
                                                  minutes=search_values.option_max_duration.minute).seconds
                where += "AND duration <= " + str(max_duration) + " "
            except (ValueError, TypeError):
                pass

        if search_values.order:
            if search_values.order != 'relevance':
                order = 'ORDER BY ' + search_values.order
                direction = ' ' + search_values.direction.upper() + ' '
            else:
                order = ''
                direction = ''
                option = "OPTION ranker=wordcount "
                if search_values.direction == 'asc':
                    reverse_result = True

        else:
            direction = ""
            order = ""
            option = "OPTION ranker=wordcount "

        sql = select + from_ + where + order + direction + limit + option
        cursor = self._connector.query(sql)
        sphinx_results = cursor.fetchall()
        cursor.close()
        results = SphinxSearchResult()
        for result in sphinx_results:
            results.videos_ids.append(result['videoid'])

        if reverse_result:
            results.videos_ids.reverse()

        if meta_info:
            sql = "SHOW META"
            cursor = self._connector.query(sql)
            last_meta = cursor.fetchall()
            for meta in last_meta:
                if meta['Variable_name'] == 'total_found':
                    results.total_videos = int(meta['Value'])
                elif meta['Variable_name'] == 'time':
                    results.sphinx_ids_execute_time = meta['Value']

        # if search_values.shared_result:
        #     results.videos_ids.remove(search_values.shared_result)
        results.execution_time = time.time() - self_time
        cursor.close()
        return results

    def get_videos(self, search_values, search_result, speech_around=3, max_speech_data=5):
        if not search_values.speech and not search_values.title and not search_values.description and not search_values.tags:
            return None

        self_time = time.time()

        select = "SELECT videoid, "
        from_ = " FROM " + self._table_name + " "

        string_video_ids = ""
        for id in search_result.videos_ids:
            string_video_ids = string_video_ids + "\'" + id + "\'" + ","
        string_video_ids = string_video_ids.strip(",")
        where = "WHERE videoid IN (" + string_video_ids + ") "

        title_key = None
        description_key = None
        tags_key = None

        if search_values.speech:
            select += "subtitle, stemmed_subtitle, indexes, timeframes, "

        if search_values.title:
            title_key = "snippet(title, '"+search_values.prepared_title+"', 'around=0', 'limit=0', " \
             "'before_match="+self._title_tag_open+"', 'after_match="+self._title_tag_close+"')"
            select = select + title_key + ", "

        if search_values.description:
            description_key = "snippet(description, '"+search_values.prepared_description+"', 'around=0', 'limit=0', " \
             "'before_match="+self._description_tag_open+"', 'after_match="+self._description_tag_close+"')"
            select = select + description_key + ", "

        if search_values.tags:
            tags_key = "snippet(tags, '"+search_values.prepared_tags+"', 'around=0', 'limit=0', " \
             "'before_match="+self._tags_tag_open+"', 'after_match="+self._tags_tag_close+"')"
            select = select + tags_key + ", "

        select = select.strip(', ')

        sql = select + from_ + where

        cursor = self._connector.query(sql)
        sphinx_results = cursor.fetchall()
        cursor.close()

        if not sphinx_results:
            return None

        search_result.sql = sql
        search_result.total_matches = 0

        time_speech_data = 0

        if search_values.speech:
            for item in sphinx_results:
                subtitle = item['subtitle']
                stemmed_subtitle = item['stemmed_subtitle']
                timeframes = item['timeframes']
                indexes = item['indexes']

                speech_around = int(speech_around)
                time_sd = time.time()
                speech_data = parse_speech_data(search_values.speech, subtitle, stemmed_subtitle, indexes, timeframes,
                                                speech_around, self._speech_tag_open, self._speech_tag_close,
                                                max_speech_data, exact=search_values.exact_match)

                time_sd = time.time() - time_sd
                time_speech_data += time_sd

                item['speech_data'] = speech_data.speech_data
                item['count_total_matches'] = speech_data.count_data
                item['count_left_data'] = speech_data.count_left_data
                item['end_id'] = speech_data.end_id

            if not search_values.order or search_values.order == 'relevance' and search_values.direction == 'desc':
                sorted_items = sorted(sphinx_results, key=lambda k: k['count_total_matches'], reverse=True)

            elif search_values.order == 'relevance' and search_values.direction == 'asc':
                sorted_items = sorted(sphinx_results, key=lambda k: k['count_total_matches'])
            else:
                sorted_items = sphinx_results

        else:
            sorted_items = sphinx_results

        videos_ids = []
        for i in sorted_items:
            videos_ids.append(i['videoid'])

        preserved = Case(*[When(videoId=videoId, then=pos) for pos, videoId in enumerate(videos_ids)])
        videos = list(Videos.objects.filter(videoId__in=videos_ids).order_by(preserved)[:len(videos_ids)])
        for index, video in enumerate(videos):
            if search_values.speech:
                video.speech_data = sorted_items[index]['speech_data']
                video.count_rest_speech_data = sorted_items[index]['count_left_data']
                video.count_total_data = sorted_items[index]['count_total_matches']
                video.end_id = sorted_items[index]['end_id']

            if search_values.title:
                video.title = sorted_items[index][title_key]

            if search_values.description:
                video.description = sorted_items[index][description_key]

            if search_values.tags:
                # Replacing \" to \' since JSON doesnt work with nested quotes "item \"inner item\""
                temp = sorted_items[index][tags_key]
                temp = temp.replace(self._tags_tag_open, self._tags_tag_open_replace)
                temp = ujson.loads(temp)
                video.tags = ', '.join(temp)
            else:
                if video.tags:
                    temp = ujson.loads(video.tags)
                    video.tags = ', '.join(temp)
                else:
                    video.tags = None

        search_result.videos = videos

        if search_values.shared_result:
            search_result.shared_video = self._get_shared_video(search_values, speech_around,
                                                                max_speech_data)

        elif search_values.shared_moment:
            search_result.shared_video = self._get_shared_moment(search_values, speech_around)

        search_result.execution_time = time.time() - self_time

        return search_result

    def get_rest_matches(self, speech_request, video_id, count_matches, speech_around, end_id, exact=False):
        shared_sql = "SELECT * FROM " + self._table_name + " WHERE videoid=%s"
        cursor = self._connector.query_values(shared_sql, video_id)
        item = cursor.fetchone()
        cursor.close()
        if item:
            subtitle = item['subtitle']
            stemmed_subtitle = item['stemmed_subtitle']
            timeframes = item['timeframes']
            indexes = item['indexes']

            if exact:
                request = speech_request.split(',')
            else:
                request = stem_request(speech_request)
                request = request.split(',')

            speech_data = parse_speech_data(request, subtitle, stemmed_subtitle, indexes, timeframes,
                                            speech_around, self._speech_tag_open, self._speech_tag_close, count_matches,
                                            exact=exact, end_id=end_id)
            return speech_data

    def _get_shared_video(self, search_values, speech_around, max_speech_data):
        if not search_values.speech and not search_values.title and not search_values.description and not search_values.tags:
            return None

        select = "SELECT videoid, "
        from_ = " FROM " + self._table_name + " "

        where = "WHERE videoid IN (\'" + search_values.shared_result + "\') "

        title_key = None
        description_key = None
        tags_key = None

        if search_values.speech:
            select += "subtitle, stemmed_subtitle, indexes, timeframes, "

        if search_values.title:
            title_key = "snippet(title, '" + search_values.prepared_title + "', 'around=0', 'limit=0', " \
                                                                            "'before_match=" + self._title_tag_open + "', 'after_match=" + self._title_tag_close + "')"
            select = select + title_key + ", "

        if search_values.description:
            description_key = "snippet(description, '" + search_values.prepared_description + "', 'around=0', " \
                                                                                              "'limit=0', 'before_match=" + self._description_tag_open + "', 'after_match=" + self._description_tag_close + "')"
            select = select + description_key + ", "

        if search_values.tags:
            tags_key = "snippet(tags, '" + search_values.prepared_tags + "', 'around=0', 'limit=0', " \
                                                                         "'before_match=" + self._tags_tag_open + "', 'after_match=" + self._tags_tag_close + "')"
            select = select + tags_key + ", "

        select = select.strip(', ')

        sql = select + from_ + where

        cursor = self._connector.query(sql)
        item = cursor.fetchone()
        cursor.close()

        if not item:
            return None

        shared_video = Videos.objects.select_related('channelId').filter(videoId=search_values.shared_result)[0]

        if search_values.speech:
            subtitle = item['subtitle']
            stemmed_subtitle = item['stemmed_subtitle']
            timeframes = item['timeframes']
            indexes = item['indexes']

            speech_around = int(speech_around)

            speech_data = parse_speech_data(search_values.speech, subtitle, stemmed_subtitle, indexes, timeframes,
                                            speech_around, self._speech_tag_open, self._speech_tag_close,
                                            max_speech_data, exact=search_values.exact_match)

            shared_video.speech_data = speech_data.speech_data
            shared_video.count_rest_speech_data = speech_data.count_left_data
            shared_video.count_total_data = speech_data.count_data
            shared_video.end_id = speech_data.end_id

        if search_values.title:
            title = item[title_key]
            shared_video.title = title

        if search_values.description:
            description = item[description_key]
            shared_video.description = description

        if search_values.tags:
            temp = item[tags_key]
            temp = temp.replace(self._tags_tag_open, self._tags_tag_open_replace)
            temp = ujson.loads(temp)
            shared_video.tags = ', '.join(temp)
        else:
            temp = ujson.loads(shared_video.tags)
            shared_video.tags = ', '.join(temp)

        return shared_video

    def _get_shared_moment(self, search_values, speech_around):
        video_id = search_values.shared_moment['id']
        start_time = search_values.shared_moment['start']
        end_time = search_values.shared_moment['end']
        start_id = search_values.shared_moment['start_id']
        end_id = search_values.shared_moment['end_id']
        loop = search_values.shared_moment['loop']

        select = "SELECT videoid, subtitle, "
        from_ = " FROM " + self._table_name + " "
        where = "WHERE videoid IN (\'" + video_id + "\') "

        title_key = None
        description_key = None
        tags_key = None

        if search_values.title:
            title_key = "snippet(title, '" + search_values.prepared_title + "', 'around=0', 'limit=0', " \
                                                                            "'before_match=" + self._title_tag_open + "', 'after_match=" + self._title_tag_close + "')"
            select = select + title_key + ", "

        if search_values.description:
            description_key = "snippet(description, '" + search_values.prepared_description + "', 'around=0', " \
                                                                                              "'limit=0', 'before_match=" + self._description_tag_open + "', 'after_match=" + self._description_tag_close + "')"
            select = select + description_key + ", "

        if search_values.tags:
            tags_key = "snippet(tags, '" + search_values.prepared_tags + "', 'around=0', 'limit=0', " \
                                                                         "'before_match=" + self._tags_tag_open + "', 'after_match=" + self._tags_tag_close + "')"
            select = select + tags_key + ", "

        select = select.strip(', ')

        sql = select + from_ + where

        cursor = self._connector.query(sql)
        item = cursor.fetchone()
        cursor.close()

        if not item:
            return None

        subtitle = item['subtitle']
        speech_around = int(speech_around)

        speech_data = parse_match_speech_data(subtitle, speech_around, self._speech_tag_open, self._speech_tag_close,
                                              start_time, end_time, start_id, end_id, loop=loop)

        shared_video = Videos.objects.select_related('channelId').filter(videoId=video_id)[0]
        shared_video.speech_data = speech_data.speech_data
        shared_video.count_rest_speech_data = speech_data.count_left_data
        shared_video.count_total_data = speech_data.count_data
        shared_video.end_id = speech_data.end_id

        if search_values.title:
            title = item[title_key]
            shared_video.title = title

        if search_values.description:
            description = item[description_key]
            shared_video.description = description

        if search_values.tags:
            temp = item[tags_key]
            temp = temp.replace(self._tags_tag_open, self._tags_tag_open_replace)
            temp = ujson.loads(temp)
            shared_video.tags = ', '.join(temp)
        else:
            temp = ujson.loads(shared_video.tags)
            shared_video.tags = ', '.join(temp)

        return shared_video
