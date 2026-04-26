"""
Speech-match extraction inside a video's subtitle.

Given a stemmed search phrase and a video's (subtitle, stemmed_subtitle,
word indexes, timeframes) tuple, finds each occurrence of the phrase,
wraps it with highlight tags, extracts a configurable window of words
around it, and attaches the corresponding timestamp so the UI can deep
link to the moment the phrase is spoken.
"""

from nltk.stem import PorterStemmer
from bisect import bisect_right
# from spoketube.settings import STEMMED_SYNONYMS
import time

stemmer = PorterStemmer()


class SpeechParserResults:
    def __init__(self):
        self.speech_data = []
        self.end_id = None
        self.count_data = 0
        self.count_left_data = 0


def parse_speech_data(stem_req, subtitle, stem_subtitle, indexes, timeframes, words_around, open_tag, close_tag,
                      max_matches, exact=False, end_id=None):
    stem_req = sorted(stem_req, key=len, reverse=True)
    result = SpeechParserResults()
    timeframes = timeframes.split(',')
    indexes = indexes.split(',')
    keys = []
    for i in indexes:
        keys.append(int(i))

    if exact:
        stem_subtitle = subtitle

    if end_id:
        stem_subtitle_copy = stem_subtitle
        stem_subtitle = stem_subtitle[end_id:]
        count_total_matches = count_reqs(stem_subtitle, stem_req)
        stem_subtitle = replace_multiple(stem_subtitle, stem_req, max_matches)
        stem_subtitle = stem_subtitle_copy[:end_id] + stem_subtitle

    else:
        count_total_matches = count_reqs(stem_subtitle, stem_req)
        stem_subtitle = replace_multiple(stem_subtitle, stem_req, max_matches)

    result.count_data = count_total_matches

    if count_total_matches > max_matches:
        result.count_left_data = count_total_matches - max_matches

    end_id = stem_subtitle.rfind('#') - stem_subtitle.count('$ # ')*6 + 1
    splited_stem_subtitle = stem_subtitle.split(' # ', max_matches*2)

    index_counter = 0

    res = []
    for index, item in enumerate(splited_stem_subtitle):
        if '$' in item and index != max_matches*2:
            temp = {}
            start_ind_w_before = index_counter - words_around
            temp['words_before'] = (start_ind_w_before, start_ind_w_before + words_around)
            start_ind_match = temp['words_before'][1]
            temp['match'] = (start_ind_match, start_ind_match + item.count('  ') + 1)
            temp['words_after'] = (temp['match'][1], temp['match'][1] + words_around)
            res.append(temp)
        elif not item:
            continue
        index_counter += item.count('  ') + 1

    if not res:
        return

    split_count = res[-1]['words_after'][1]
    splited_subtitle = subtitle.split('  ', split_count)
    speech_data = []
    for item in res:
        temp = {}
        words_before = splited_subtitle[item['words_before'][0]:item['words_before'][1]]
        match = splited_subtitle[item['match'][0]:item['match'][1]]
        words_after = splited_subtitle[item['words_after'][0]:item['words_after'][1]]

        match_start_id = item['match'][0]
        match_end_id = item['match'][1]

        start_key = bisect_right(keys, item['words_before'][0]) - 1
        if start_key < 0:
            start_key = 0
        end_key = bisect_right(keys, item['words_after'][1]) - 1
        if end_key < 0:
            end_key = 0

        try:
            timeframe = timeframes[start_key]
            timeframe = timeframe.split('-')
            startTime = timeframe[0]
        except IndexError:
            timeframe = timeframes[start_key - 1]
            timeframe = timeframe.split('-')
            startTime = timeframe[0]

        try:
            timeframe = timeframes[end_key]
            timeframe = timeframe.split('-')
            endTime = timeframe[1]
        except IndexError:
            timeframe = timeframes[end_key - 1]
            timeframe = timeframe.split('-')
            endTime = timeframe[1]

        startTime_formated = time.strftime("%H:%M:%S", time.gmtime(int(startTime)))

        words_before = ' '.join(words_before)
        match = ' '.join(match)
        words_after = ' '.join(words_after)

        temp['match'] = words_before + ' ' + open_tag + match + close_tag + ' ' + words_after
        temp['startTime'] = startTime
        temp['endTime'] = endTime
        temp['startTime_formated'] = startTime_formated
        temp['start_id'] = match_start_id
        temp['end_id'] = match_end_id
        temp['loop'] = None

        speech_data.append(temp)

    result.speech_data = speech_data
    result.end_id = end_id
    return result


def parse_match_speech_data(subtitle, words_around, open_tag, close_tag, start_time, end_time,
                            start_id, end_id, loop):
    match_start_id = int(start_id)
    match_end_id = int(end_id)
    result = SpeechParserResults()
    splited_subtitle = subtitle.split('  ')

    words_before = splited_subtitle[match_start_id - words_around:match_start_id]
    match = splited_subtitle[match_start_id:match_end_id]
    words_after = splited_subtitle[match_end_id:match_end_id + words_around]

    words_before = ' '.join(words_before)
    match = ' '.join(match)
    words_after = ' '.join(words_after)
    speech_data = []
    startTime_formated = time.strftime("%H:%M:%S", time.gmtime(int(start_time)))

    temp = {}
    temp['match'] = words_before + ' ' + open_tag + match + close_tag + ' ' + words_after
    temp['startTime'] = start_time
    temp['endTime'] = end_time
    temp['startTime_formated'] = startTime_formated
    temp['start_id'] = match_start_id
    temp['end_id'] = match_end_id
    temp['loop'] = loop
    speech_data.append(temp)

    result.speech_data = speech_data
    result.count_data = 1
    return result


def stem_request(request):
    '''
    :param request: string
    :return: string
    '''
    request = request.strip()
    request = request.lower()
    request_list = request.split(',')
    request_stemmed = []
    for single_request in request_list:
        req = single_request.strip()
        req = req.split(' ')
        temp = []
        for w in req:
            if len(w) >= 2:
                if w[0] == '[' and w[1] == ']':
                    stemmed = stemmer.stem(w[1:-1])
                    stemmed = '[' + stemmed + ']'
                else:
                    stemmed = stemmer.stem(w)

            else:
                stemmed = stemmer.stem(w)

            temp.append(stemmed)
        temp = ' '.join(temp)
        # Condition to avoid duplicates (i.e. 'run' and 'runs' in request converts to 'run' and 'run')
        if temp not in request_stemmed:
            request_stemmed.append(temp)

    request_stemmed = ','.join(request_stemmed)
    return request_stemmed


def replace_multiple(string, list_substrings, max_replaces):
    if max_replaces == 0:
        for substring in list_substrings:
            substring = substring.replace(' ', '  ')
            string = string.replace(' ' + substring + ' ', ' # $' + substring + '$ # ')
        return string

    else:
        for substring in list_substrings:
            substring = substring.replace(' ', '  ')
            for i in range(max_replaces):
                if ' ' + substring + ' ' in string:
                    string = string.replace(' ' + substring + ' ', ' # $' + substring + '$ # ', 1)
                else:
                    continue

        last_ind = 0
        for i in range(max_replaces):
            ind = string.find('$ # ', last_ind + 1)
            if ind == -1:
                break
            else:
                last_ind = ind
        if last_ind == 0:
            return string
        replaced_sub = string[:last_ind + len('$ # ')]
        orig_sub = string[last_ind:].replace(' # $', ' ').replace('$ # ', ' ')
        orig_sub = orig_sub.lstrip()
        string = replaced_sub + orig_sub
        return string


def count_reqs(subtitle, list_requests):
    counter = 0
    for req in list_requests:
        req = req.replace(' ', '  ')
        spaced_req = ' ' + req + ' '
        counter += subtitle.count(spaced_req)
    return counter

