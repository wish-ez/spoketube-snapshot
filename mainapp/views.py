"""
HTTP views for Spoketube.

Covers the landing page, the main search page (which builds a Sphinx query
from the user's form, paginates results, and hydrates each hit with speech
matches and timestamps), AJAX endpoints for channel autocomplete and for
loading additional search results / channels, the contact form, and custom
404 / 500 handlers.
"""

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, redirect
from django.core.mail import send_mail, BadHeaderError
from .models import Channels, Videos
from .forms import SearchForm, ShareForm, ContactForm
from django.utils.formats import number_format
import ujson
import time
import re
from decimal import Decimal
from spoketube.settings import Sphinx_conn_search, SEARCH_MAX_SPEECH_MATCHES, SEARCH_SPEECH_AROUND, \
    MAIN_COUNT_STATISTIC_CHANNELS, SEARCH_RESULTS_P_PAGE, USE_L10N, ALLOWED_CHARS_EN
from .search_module import SphinxSearchValues, SphinxSearchModule
from .templatetags.intword_thousands import reguar_intword_thousands

Search_module = SphinxSearchModule(Sphinx_conn_search, 'videos')
MAX_SPEECH_MATCHES = SEARCH_MAX_SPEECH_MATCHES
SPEECH_AROUND = SEARCH_SPEECH_AROUND


def intcomma(value, use_l10n=True):
    """
    Convert an integer to a string containing commas every three digits.
    For example, 3000 becomes '3,000' and 45000 becomes '45,000'.
    """
    if USE_L10N and use_l10n:
        try:
            if not isinstance(value, (float, Decimal)):
                value = int(value)
        except (TypeError, ValueError):
            return intcomma(value, False)
        else:
            return number_format(value, force_grouping=True)
    orig = str(value)
    new = re.sub(r"^(-?\d+)(\d{3})", r'\g<1>,\g<2>', orig)
    if orig == new:
        return new
    else:
        return intcomma(new, use_l10n)


def clean_ajax_request(string, allowed_chars=[]):
    """
    Strip spaces at the edges, remove double/triple spaces, remove chars which not in ALLOWED_CHARS
    """
    string = string.strip()
    string = string.replace('   ', ' ').replace('  ', ' ')
    for ch in string:
        if ch not in ALLOWED_CHARS_EN and ch not in allowed_chars:
            string = string.replace(ch, '', 1)
    return string


def autocomplete_channels(request):
    q = request.GET.get('term')
    channels = Channels.objects.filter(title__istartswith=q)[:10]
    results = []
    for channel in channels:
        temp = {}
        temp['value'] = channel.title
        temp['icon_url'] = channel.thumbnailsDefaultUrl
        temp['video_count'] = channel.videoCount
        results.append(temp)
    data = ujson.dumps(results)
    return JsonResponse(data, safe=False)


def is_any_channel_exists(list_channels):
    """
    :param list list_channels: List of channels titles
    :return: bool
    Check if any channel exists in DB
    """
    result = Channels.objects.filter(title__in=list_channels)
    if result:
        return True
    else:
        return False


def get_rest_matches(request):
    speech_req = request.GET.get('request')
    speech_req = clean_ajax_request(speech_req)
    video_id = request.GET.get('id')
    video_id = clean_ajax_request(video_id, allowed_chars=['_', '-'])
    end_id = request.GET.get('end_id')
    exact_match = request.GET.get('exact')
    if exact_match:
        exact_match = True
    else:
        exact_match = False

    if end_id and end_id != 'undefined':
        end_id = int(end_id)
        matches = Search_module.get_rest_matches(speech_req, video_id, MAX_SPEECH_MATCHES, SPEECH_AROUND, end_id,
                                                 exact=exact_match)
        if matches:
            result = {'matches': matches.speech_data,
                      'last_match_id': MAX_SPEECH_MATCHES,
                      'end_id': matches.end_id,
                      'matches_left': matches.count_left_data
                      }
        else:
            result = {}
    else:
        result = {}

    return JsonResponse(result)


def get_rest_channels(request):
    channels_count = request.GET.get('count')
    try:
        channels_start_range = int(channels_count)
    except ValueError:
        result = {'is_channels_left': 0}
        return JsonResponse(result)

    channels_end_range = channels_start_range + MAIN_COUNT_STATISTIC_CHANNELS
    channels = Channels.objects.order_by('-subscriberCount')[channels_start_range:channels_end_range]
    channels_cleaned = []
    for channel in channels:
        temp = {}
        temp['channelId'] = channel.channelId
        temp['title'] = channel.title
        temp['thumbnailsDefaultUrl'] = channel.thumbnailsDefaultUrl
        temp['subscriberCount'] = reguar_intword_thousands(channel.subscriberCount)
        temp['videoCount'] = intcomma(channel.videoCount)
        channels_cleaned.append(temp)

    channels_last_range = channels_start_range + len(channels)
    channels_left = Channels.objects.order_by('-subscriberCount')[channels_last_range: channels_last_range + 1]

    if len(channels_left) > 0:
        is_channels_left = 1
    else:
        is_channels_left = 0

    if channels:
        result = {'channels': channels_cleaned,
                  'is_channels_left': is_channels_left
                  }
    else:
        result = {'is_channels_left': is_channels_left
                  }

    return JsonResponse(result)


# Function to get JSON object with channel's title and (if exists) icon url, videos count
# Needed for Tagify plugin to keep tag's icons show after page refresh
def get_tagify_json(channels_title):
    results = []
    if channels_title:
        where_values = channels_title.split(',')
        for i in where_values:
            temp = {}
            try:
                channel = Channels.objects.get(title=i)
                temp['value'] = channel.title
                temp['icon_url'] = channel.thumbnailsDefaultUrl
            except ObjectDoesNotExist:
                temp['value'] = i
            results.append(temp)
        results = ujson.dumps(results)
    else:
        results = ''
    return results


# Function to calculate pagination pages:
def get_pages_range(page, page_range, count_side_pages):
    if page:
        int_page = int(page)
    else:
        int_page = 1

    if page_range[-1] <= count_side_pages * 2 + 1:
        pages_before = page_range[:int_page - 1]
        pages_after = page_range[int_page:]

    else:
        # Start range
        if int_page - count_side_pages <= 0:
            pages_before = page_range[:int_page - 1]
            pages_after = page_range[int_page:count_side_pages * 2 + 1]
        # End range
        elif int_page + count_side_pages > page_range[-1]:
            pages_before = page_range[page_range[-1] - count_side_pages * 2 - 1:int_page - 1]
            pages_after = page_range[int_page:]
        # Middle range
        else:
            pages_before = page_range[int_page - count_side_pages - 1:int_page - 1]
            pages_after = page_range[int_page:int_page + count_side_pages]

    return {'pages_before': pages_before, 'pages_after': pages_after}


# Main page view
def main_page(request):
    DEFAULT_TAB = 'tab-speech'
    COUNT_STATISTIC_CHANNELS = MAIN_COUNT_STATISTIC_CHANNELS

    channels = Channels.objects.order_by('-subscriberCount')[:COUNT_STATISTIC_CHANNELS]
    channels_count = Channels.objects.count()
    videos_count = Videos.objects.count()

    context = {'search_form': SearchForm(),
               'current_tab': DEFAULT_TAB,
               'channels': channels,
               'channels_count': channels_count,
               'videos_count': videos_count
               }
    return render(request, 'mainapp/main-page.html', context)


# Search page view
def search(request):
    dj_time = time.time()
    RESULTS_P_PAGE = SEARCH_RESULTS_P_PAGE

    if request.method == 'GET':

        # Create a form instance and populate it with data from the request:
        search_form = SearchForm(request.GET)

        # Check whether it's valid:
        if search_form.is_valid():
            search_request_cleaned = search_form.cleaned_data
            shared_result = request.GET.get('shareResult')
            shared_moment = request.GET.get('shareMoment')

            search_requests = [request.GET.get('speech'),
                               request.GET.get('title'),
                               request.GET.get('description'),
                               request.GET.get('tags')
                               ]

            raw_search_requests = []
            for req in search_requests:
                if req:
                    req = req.replace(',', ', ')
                    raw_search_requests.append(req)

            if not raw_search_requests:
                context = {'search_form': search_form}
                return render(request, 'mainapp/empty_search.html', context)

            cleaned_search_requests = [search_request_cleaned['speech'],
                                       search_request_cleaned['title'],
                                       search_request_cleaned['description'],
                                       search_request_cleaned['tags']
                                       ]
            search_requests = [r for r in cleaned_search_requests if r]
            if not search_requests:
                    context = {'search_form': search_form,
                               'search_requests': search_requests,
                               }
                    return render(request, 'mainapp/no_results.html', context)

            # Get channelId by title values in same name field
            if search_request_cleaned['channels']:
                channels_title = search_request_cleaned['channels'].split(',')
                channels = Channels.objects.filter(title__in=channels_title)[:len(channels_title)]
                channels_id = []
                if channels and len(channels) > 0:
                    # Add escape-quotes for Sphinx QL
                    for channel in channels:
                        channels_id.append("\'" + channel.channelId + "\'")

                # If NOT exact matches and channels exists in DB - create string for Sphinx QL
                if not search_request_cleaned['exact'] and channels_id:
                    channels_id = ", ".join(channels_id)
                    search_request_cleaned['channels_id'] = channels_id
                # Elif enabled exact matches only and there no any channel in DB - set dummy channelId,
                # which will throw empty search result
                elif search_request_cleaned['exact'] and not channels_id:
                    search_request_cleaned['channels_id'] = '\'NO_CHANNELS\''

                # Setting init_json attribute with JSON object to keep Tagify tags showing icons after page refresh
                init_json = get_tagify_json(search_request_cleaned['channels'])
                search_form.setFieldAttr('channels', 'init_json', init_json)

            # Get videos_ids for search request:
            search_values = SphinxSearchValues(search_request_cleaned, shared_result=shared_result,
                                               shared_moment=shared_moment)
            result = Search_module.get_videos_ids(search_values)

            # Check if any channel exists in DB, if not a single - template will display a message to contact us
            # for indexing those channels
            channels = search_request_cleaned['channels']
            if channels:
                channels = channels.split(',')
            channels_exists = is_any_channel_exists(channels)

            # If no search results:
            if not result.videos_ids:
                context = {'search_form': search_form,
                           'search_requests': search_requests,
                           'search_channels': channels,
                           'channels_exists': channels_exists
                           }
                return render(request, 'mainapp/no_results.html', context)

        # If form isn't valid:
        else:
            return redirect('/')

    # If a POST (or any other method):
    else:
        return redirect('/')

    paginator = Paginator(result.videos_ids, RESULTS_P_PAGE)
    page_range = list(range(1, paginator.num_pages+1))
    page = request.GET.get('page')
    count_side_pages = 5

    pages = get_pages_range(page, page_range, count_side_pages)
    pages_before = pages['pages_before']
    pages_after = pages['pages_after']

    try:
        pagination = paginator.page(page)
        result.videos_ids = paginator.page(page).object_list
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        pagination = paginator.page(1)
        result.videos_ids = paginator.page(1).object_list
    except EmptyPage:
        # If page is out of range
        pagination = paginator.page(paginator.num_pages)
        result.videos_ids = paginator.page(paginator.num_pages).object_list

    time_videos = time.time()
    search_result = Search_module.get_videos(search_values, result, SPEECH_AROUND, MAX_SPEECH_MATCHES)
    videos = search_result.videos
    shared_video = search_result.shared_video
    total_videos = search_result.total_videos
    total_matches = search_result.total_matches
    execution_time = time.time() - dj_time
    execution_time = round(float(execution_time), 2)

    context = {'request': request,
               'search_requests': raw_search_requests,
               'search_form': search_form,
               'share_form': ShareForm(),
               'speech_cleaned': search_request_cleaned['speech'],
               'total_videos': total_videos,
               'count_current_page_matches': total_matches,
               'execution_time': execution_time,
               'videos': videos,
               'shared_video': shared_video,
               'pagination': pagination,
               'pages_before': pages_before,
               'page': page,
               'pages_after': pages_after,
               }

    return render(request, 'mainapp/search.html', context)


# Contact page view
def contact(request):
    sender = 'contact@spoketube.com'
    recipients = ['contact@spoketube.com']
    if request.method == 'GET':
        form = ContactForm()
    else:
        form = ContactForm(request.POST)
        if form.is_valid():
            subject = form.cleaned_data['subject']
            from_email = form.cleaned_data['from_email']
            ip = get_client_ip(request)
            message = 'From: ' + from_email + '\n' + 'IP: ' + ip + '\n\n' + form.cleaned_data['message']
            try:
                send_mail(subject, message, sender, recipients)
            except BadHeaderError:
                return render(request, 'mainapp/contact.html', {'send_status': 'fail'})
            return render(request, 'mainapp/contact.html', {'send_status': 'success'})
    return render(request, 'mainapp/contact.html', {'form': form})


# View for success contact form
def contact_success(request):
    return HttpResponse('Success! Thank you for your message')


def contact_fail(request):
    return HttpResponse('Something went wrong. Please, contact us directly at contact@spoketube.com')


# 404 view
def page_not_found(request, exception):
    return render(request, 'mainapp/404.html', context={'exception': exception}, status=404)


# 500 view
def server_error(request):
    return render(request, 'mainapp/500.html', status=500)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[-1].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
