"""
Cron entry point for the ingestion worker.

Runs every minute on the Elastic Beanstalk instance. If no task is currently
in flight, pops the next DataParserTasks row, estimates the YouTube Data API
quota cost, and executes it (add_channel / update_channel / refresh_channel /
add_video / update_video / get_missed_videos), writing progress and errors
into DataParserStatuses. Captions are fetched through the rotating Proxies
pool when YT_ENABLE_PROXY is on.
"""

from data_parser import Connector, DataParserTasks, DataParserStatuses, Proxies
import traceback
import os
import configparser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_PATH = os.path.join(BASE_DIR, 'dev', 'secrets')

# If running on dev then looking for secrets file, otherwise gets values from server environment
if os.path.exists(SECRETS_PATH):
    config = configparser.RawConfigParser()
    config.read(SECRETS_PATH)
    config = config['DEBUG LOCALHOST']
else:
    config = os.environ

if config['ENABLE_PARSER_TASKS_HANDLER'] == '0':
    exit(0)

MySQL_conn = Connector(host=config['RDS_HOSTNAME'],
                       port=config['RDS_PORT'],
                       db=config['RDS_DB_NAME'],
                       user=config['RDS_USERNAME'],
                       password=config['RDS_PASSWORD']
                       )

ParserStatus = DataParserStatuses(MySQL_conn)
last_status = ParserStatus.get_last_status()

if last_status and last_status.status != 'idle':
    exit(0)

ParserTasks = DataParserTasks(MySQL_conn)
fresh_task = ParserTasks.get_fresh_task()
if fresh_task:
    from data_parser import Videos, Channels, YouTubeAPI, CaptionParser
    Sphinx_conn = Connector(host=config['SPHINX_HOST'],
                            port=config['SPHINX_PORT']
                            )

    if config['YT_ENABLE_PROXY'].lower() == 'true':
        Proxies = Proxies(MySQL_conn)
        YT_PROXIES = Proxies.get_available_proxy()
        if not YT_PROXIES:
            ParserTasks.set_fatal_error(fresh_task)
            parser_status = ParserStatus.create_new_status()
            parser_status.taskId = fresh_task.id
            parser_status.fatal_error_details = "No available proxy"
            parser_status.status = 'error'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            exit(0)
    else:
        YT_PROXIES = None

    CaptionParser = CaptionParser()
    Videos = Videos(MySQL_conn, Sphinx_conn)
    Channels = Channels(MySQL_conn, Sphinx_conn)
    YT = YouTubeAPI(MySQL_conn, config['YT_DEV_KEY'])

    parser_status = ParserStatus.create_new_status()
    parser_status.taskId = fresh_task.id
    parser_status.status = 'work'
    ParserStatus.save(parser_status)

    try:
        if fresh_task.task == 'add_channel':
            channel_id = fresh_task.task_item
            channel_in_db = Channels.get_by_id(channel_id)
            if not channel_in_db:
                yt_channel = YT.get_channel(channel_id)
                videos_count = int(yt_channel.videoCount)
                quotas_cost = YT.calc_quotas_to_use(int(videos_count / 50) + 1, 'get_playlist_ids')
                quotas_cost += YT.calc_quotas_to_use(videos_count, 'get_video')
                quotas_left = YT.get_left_quotas()
                parser_status.estimated_quotas = quotas_cost
                parser_status.status_description = 'Add channel \'' + yt_channel.title + '\''
                if quotas_cost > quotas_left:
                    parser_status.fatal_error_details = 'Quotas cost exceeded (quotas cost:' + str(quotas_cost) + ') quotas left: ' + str(quotas_left)
                    ParserStatus.update(parser_status)
                    ParserStatus.add_new_status('idle', status_description='Idle')
                    exit(0)

                else:
                    Channels.save_or_update(yt_channel)
                    videos_id = YT.get_playlist_ids(yt_channel.relatedPlaylistsUploads)
                    parser_status.count_items_total = len(videos_id)
                    ParserStatus.update(parser_status)
                    if videos_id:
                        for num, video_id in enumerate(videos_id):
                            last_status = ParserStatus.get_last_status()
                            if last_status.status == 'stop':
                                ParserStatus.delete(last_status)
                                parser_status.status = 'stopped'
                                ParserStatus.update(parser_status)
                                ParserStatus.add_new_status('idle', status_description='Idle')
                                exit(0)
                            else:
                                video = YT.get_video(video_id)
                                if YT_PROXIES:
                                    while YT_PROXIES:
                                        proxy = YT_PROXIES[0]
                                        proxy_dict = Proxies.dict_format_proxy(proxy)
                                        try:
                                            video = CaptionParser.load_captions(video, 'en', 'ASR', proxy=proxy_dict)

                                        except CaptionParser.YtCaptcha:
                                            proxy.isCaptcha = 1
                                            Proxies.update(proxy)
                                            YT_PROXIES.pop(0)
                                        except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                                            proxy.isAvailable = 0
                                            Proxies.update(proxy)
                                            YT_PROXIES.pop(0)
                                        else:
                                            break

                                    if not video.subtitle and not YT_PROXIES:
                                        Videos.save_or_update(video)
                                        parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                                             CaptionParser)
                                        parser_status.count_items_done = num + 1
                                        ParserTasks.set_fatal_error(fresh_task)
                                        parser_status.fatal_error_details = "Proxies ended"
                                        parser_status.status = 'error'
                                        ParserStatus.update(parser_status)
                                        ParserStatus.add_new_status('idle', status_description='Idle')
                                        exit(0)

                                else:
                                    video = CaptionParser.load_captions(video, 'en', 'ASR')
                                Videos.save_or_update(video)

                                parser_status = ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                                parser_status.count_items_done = num + 1
                                parser_status.status_description = 'Add channel \'' + yt_channel.title + '\'' + \
                                                                   " (" + str(parser_status.count_items_done) + "/" + \
                                                                   str(parser_status.count_items_total) + ")"
                                ParserStatus.update(parser_status)

            else:
                parser_status.status_description = 'Channel ' + channel_in_db.title + ' already in DB'

            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'update_channel':
            channel_id = fresh_task.task_item
            quotas_cost = YT.calc_quotas_to_use(1, 'get_channel')
            quotas_left = YT.get_left_quotas()
            yt_channel = YT.get_channel(channel_id)
            parser_status.count_items_total = 1
            parser_status.estimated_quotas = quotas_cost
            parser_status.status_description = 'Update channel \'' + yt_channel.title
            if quotas_cost > quotas_left:
                parser_status.fatal_error_details = 'Quotas cost exceeded (quotas cost:' + quotas_cost + '), quotas left: ' + quotas_left
                ParserStatus.update(parser_status)
                ParserStatus.add_new_status('idle', status_description='Idle')
                exit(0)

            else:
                parser_status.count_items_done = 1
                ParserStatus.update(parser_status)
                Channels.save_or_update(yt_channel)

            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'add_video':
            video_id = fresh_task.task_item
            video_in_db = Videos.get_by_id(video_id)
            if not video_in_db:
                quotas_cost = YT.calc_quotas_to_use(1, 'get_video')
                quotas_left = YT.get_left_quotas()
                yt_video = YT.get_video(video_id)
                parser_status.count_items_total = 1
                parser_status.estimated_quotas = quotas_cost
                parser_status.status_description = 'Add video \'' + yt_video.title
                if quotas_cost > quotas_left:
                    parser_status.fatal_error_details = 'Quotas cost exceeded (quotas cost:' + quotas_cost + '), quotas left: ' + quotas_left
                    ParserStatus.update(parser_status)
                    ParserStatus.add_new_status('idle', status_description='Idle')
                    exit(0)
                else:
                    ParserStatus.update(parser_status)
                    video = yt_video
                    if YT_PROXIES:
                        while YT_PROXIES:
                            proxy = YT_PROXIES[0]
                            proxy_dict = Proxies.dict_format_proxy(proxy)
                            try:
                                video = CaptionParser.load_captions(video, 'en', 'ASR', proxy=proxy_dict)

                            except CaptionParser.YtCaptcha:
                                proxy.isCaptcha = 1
                                Proxies.update(proxy)
                                YT_PROXIES.pop(0)
                            except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                                proxy.isAvailable = 0
                                Proxies.update(proxy)
                                YT_PROXIES.pop(0)
                            else:
                                break

                        if not video.subtitle and not YT_PROXIES:
                            Videos.save_or_update(video)
                            parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                                 CaptionParser)
                            parser_status.count_items_done = 1
                            ParserTasks.set_fatal_error(fresh_task)
                            parser_status.fatal_error_details = "Proxies ended"
                            parser_status.status = 'error'
                            ParserStatus.update(parser_status)
                            ParserStatus.add_new_status('idle', status_description='Idle')
                            exit(0)

                    else:
                        video = CaptionParser.load_captions(video, 'en', 'ASR')
                    Videos.save_or_update(video)
                    ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                    parser_status.count_items_done = 1
                    Videos.save_or_update(video)
                    ParserStatus.update(parser_status)

            else:
                parser_status.status_description = 'Video ' + video_in_db.title + ' already in DB'

            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'update_video':
            video_id = fresh_task.task_item
            quotas_cost = YT.calc_quotas_to_use(1, 'get_video')
            quotas_left = YT.get_left_quotas()
            yt_video = YT.get_video(video_id)
            parser_status.count_items_total = 1
            parser_status.estimated_quotas = quotas_cost
            parser_status.status_description = 'Update video \'' + yt_video.title + '\''
            if quotas_cost > quotas_left:
                parser_status.fatal_error_details = 'Quotas cost exceeded (quotas cost:' + quotas_cost + '), quotas left: ' + quotas_left
                ParserStatus.update(parser_status)
                ParserStatus.add_new_status('idle', status_description='Idle')
                exit(0)
            else:
                ParserStatus.update(parser_status)
                video = yt_video
                if YT_PROXIES:
                    while YT_PROXIES:
                        proxy = YT_PROXIES[0]
                        proxy_dict = Proxies.dict_format_proxy(proxy)
                        try:
                            video = CaptionParser.load_captions(video, 'en', 'ASR', proxy=proxy_dict)

                        except CaptionParser.YtCaptcha:
                            proxy.isCaptcha = 1
                            Proxies.update(proxy)
                            YT_PROXIES.pop(0)
                        except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                            proxy.isAvailable = 0
                            Proxies.update(proxy)
                            YT_PROXIES.pop(0)
                        else:
                            break

                    if not video.subtitle and not YT_PROXIES:
                        Videos.save_or_update(video)
                        parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                             CaptionParser)
                        parser_status.count_items_done = 1
                        ParserTasks.set_fatal_error(fresh_task)
                        parser_status.fatal_error_details = "Proxies ended"
                        parser_status.status = 'error'
                        ParserStatus.update(parser_status)
                        ParserStatus.add_new_status('idle', status_description='Idle')
                        exit(0)

                else:
                    video = CaptionParser.load_captions(video, 'en', 'ASR')
                Videos.save_or_update(video)
                parser_status.count_items_done = 1
                parser_status = ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                ParserStatus.update(parser_status)
                Videos.save_or_update(video)

            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'refresh_channel':
            channel_id = fresh_task.task_item
            yt_channel = YT.get_channel(channel_id)
            Channels.save_or_update(yt_channel)

            last_video = Videos.MySQL.select(columns='videoId', where='channelId = %s', values=channel_id,
                                             order_by='publishedAt DESC', limit=1)

            if last_video:
                last_video_id = last_video['videoId']
                new_videos_ids = YT.get_playlist_ids_up_to(yt_channel.relatedPlaylistsUploads, last_video_id)
                nocaption_videos_ids = Videos.get_channel_nocaption_videos_ids(channel_id)
                unavailable_videos_ids = Videos.get_channel_unavailable_videos_ids(channel_id)
                parser_status.count_items_total = len(new_videos_ids) + len(nocaption_videos_ids) + len(unavailable_videos_ids)
                parser_status.count_items_done = 0
                parser_status.status_description = 'Refresh channel \'' + yt_channel.title + '\''
                ParserStatus.update(parser_status)

                if nocaption_videos_ids:
                    for num, video_id in enumerate(nocaption_videos_ids):
                        last_status = ParserStatus.get_last_status()
                        if last_status.status == 'stop':
                            ParserStatus.delete(last_status)
                            parser_status.status = 'stopped'
                            ParserStatus.update(parser_status)
                            ParserStatus.add_new_status('idle', status_description='Idle')
                            exit(0)
                        else:
                            video = Videos.get_by_id(video_id)
                            if YT_PROXIES:
                                while YT_PROXIES:
                                    proxy = YT_PROXIES[0]
                                    proxy_dict = Proxies.dict_format_proxy(proxy)
                                    try:
                                        video = CaptionParser.load_captions(video, 'en', 'ASR', proxy=proxy_dict)

                                    except CaptionParser.YtCaptcha:
                                        proxy.isCaptcha = 1
                                        Proxies.update(proxy)
                                        YT_PROXIES.pop(0)
                                    except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                                        proxy.isAvailable = 0
                                        Proxies.update(proxy)
                                        YT_PROXIES.pop(0)
                                    else:
                                        break

                                if not video.subtitle and not YT_PROXIES:
                                    Videos.save_or_update(video)
                                    parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                                         CaptionParser)
                                    parser_status.count_items_done = num + 1
                                    ParserTasks.set_fatal_error(fresh_task)
                                    parser_status.fatal_error_details = "Proxies ended"
                                    parser_status.status = 'error'
                                    ParserStatus.update(parser_status)
                                    ParserStatus.add_new_status('idle', status_description='Idle')
                                    exit(0)

                            else:
                                video = CaptionParser.load_captions(video, 'en', 'ASR')

                            Videos.save_or_update(video)
                            parser_status = ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                            parser_status.count_items_done += 1
                            parser_status.status_description = 'Update no caption videos for channel \'' + yt_channel.title + '\'' + \
                                                               " (" + str(parser_status.count_items_done) + "/" + \
                                                               str(parser_status.count_items_total) + ' videos done)'
                            ParserStatus.update(parser_status)

                if unavailable_videos_ids:
                    for num, video_id in enumerate(unavailable_videos_ids):
                        last_status = ParserStatus.get_last_status()
                        if last_status.status == 'stop':
                            ParserStatus.delete(last_status)
                            parser_status.status = 'stopped'
                            ParserStatus.update(parser_status)
                            ParserStatus.add_new_status('idle', status_description='Idle')
                            exit(0)
                        else:
                            video = Videos.get_by_id(video_id)
                            if YT_PROXIES:
                                while YT_PROXIES:
                                    proxy = YT_PROXIES[0]
                                    proxy_dict = Proxies.dict_format_proxy(proxy)
                                    try:
                                        video = CaptionParser.load_captions(video, 'en', 'ASR', proxy=proxy_dict)

                                    except CaptionParser.YtCaptcha:
                                        proxy.isCaptcha = 1
                                        Proxies.update(proxy)
                                        YT_PROXIES.pop(0)
                                    except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                                        proxy.isAvailable = 0
                                        Proxies.update(proxy)
                                        YT_PROXIES.pop(0)
                                    else:
                                        break

                                if not video.subtitle and not YT_PROXIES:
                                    Videos.save_or_update(video)
                                    parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                                         CaptionParser)
                                    parser_status.count_items_done = num + 1
                                    ParserTasks.set_fatal_error(fresh_task)
                                    parser_status.fatal_error_details = "Proxies ended"
                                    parser_status.status = 'error'
                                    ParserStatus.update(parser_status)
                                    ParserStatus.add_new_status('idle', status_description='Idle')
                                    exit(0)

                            else:
                                video = CaptionParser.load_captions(video, 'en', 'ASR')
                            Videos.save_or_update(video)
                            parser_status = ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                            parser_status.count_items_done += 1
                            parser_status.status_description = 'Update unavailable videos for channel \'' + yt_channel.title + '\'' + \
                                                               " (" + str(parser_status.count_items_done) + "/" + \
                                                               str(parser_status.count_items_total) + ' videos done)'
                            ParserStatus.update(parser_status)

                if new_videos_ids:
                    quotas_cost = YT.calc_quotas_to_use(len(new_videos_ids), 'get_video')
                    quotas_left = YT.get_left_quotas()
                    parser_status.estimated_quotas = quotas_cost

                    if quotas_cost > quotas_left:
                        parser_status.fatal_error_details = 'Quotas cost exceeded (quotas cost:' + str(quotas_cost) + '), quotas left:' + str(quotas_left)
                        parser_status.status = 'error'
                        ParserStatus.update(parser_status)
                        ParserStatus.add_new_status('idle', status_description='Idle')
                        exit(0)

                    else:
                        for num, video_id in enumerate(new_videos_ids):
                            last_status = ParserStatus.get_last_status()
                            if last_status.status == 'stop':
                                ParserStatus.delete(last_status)
                                parser_status.status = 'stopped'
                                ParserStatus.update(parser_status)
                                ParserStatus.add_new_status('idle', status_description='Idle')
                                exit(0)
                            else:
                                video = YT.get_video(video_id)
                                if YT_PROXIES:
                                    while YT_PROXIES:
                                        proxy = YT_PROXIES[0]
                                        proxy_dict = Proxies.dict_format_proxy(proxy)
                                        try:
                                            video = CaptionParser.load_captions(video, 'en', 'ASR', proxy=proxy_dict)

                                        except CaptionParser.YtCaptcha:
                                            proxy.isCaptcha = 1
                                            Proxies.update(proxy)
                                            YT_PROXIES.pop(0)
                                        except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                                            proxy.isAvailable = 0
                                            Proxies.update(proxy)
                                            YT_PROXIES.pop(0)
                                        else:
                                            break

                                    if not video.subtitle and not YT_PROXIES:
                                        Videos.save_or_update(video)
                                        parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                                             CaptionParser)
                                        parser_status.count_items_done = num + 1
                                        ParserTasks.set_fatal_error(fresh_task)
                                        parser_status.fatal_error_details = "Proxies ended"
                                        parser_status.status = 'error'
                                        ParserStatus.update(parser_status)
                                        ParserStatus.add_new_status('idle', status_description='Idle')
                                        exit(0)

                                else:
                                    video = CaptionParser.load_captions(video, 'en', 'ASR')
                                Videos.save_or_update(video)
                                parser_status = ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                                parser_status.count_items_done += 1
                                parser_status.status_description = 'Get new videos for channel \'' + yt_channel.title + '\'' + \
                                                                   " (" + str(parser_status.count_items_done) + "/" + \
                                                                   str(parser_status.count_items_total) + ' videos done)'
                                ParserStatus.update(parser_status)

            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'get_missed_videos':
            channel_id = fresh_task.task_item
            channel = Channels.get_by_id(channel_id)
            if channel:
                # Check whether mysql or sphinx contains unfinished video, in this way delete it
                # to avoid duplicate key error
                mysql_count = Channels.mysql_count(channel_id)
                sphinx_count = Channels.sphinx_count(channel_id)
                if mysql_count > sphinx_count:
                    last_id = Channels.mysql_last_video_id(channel_id)
                    Videos.delete_by_id(last_id)
                elif sphinx_count > mysql_count:
                    last_id = Channels.sphinx_last_video_id(channel_id)
                    Videos.delete_by_id(last_id)
                else:
                    pass

                channel_videos_ids = Videos.get_channel_mysql_video_ids(channel_id)
                channel_actual_videos_ids = YT.get_playlist_ids(channel.relatedPlaylistsUploads)

                new_video_ids = []
                for video_id in channel_actual_videos_ids:
                    if video_id not in channel_videos_ids:
                        new_video_ids.append(video_id)

                count_new_videos = len(new_video_ids)
                quotas_cost = YT.calc_quotas_to_use(count_new_videos, 'get_video')
                quotas_left = YT.get_left_quotas()
                parser_status.estimated_quotas = quotas_cost
                parser_status.status_description = 'Get missed videos for channel \'' + channel.title + '\''
                parser_status.count_items_total = count_new_videos
                ParserStatus.update(parser_status)
                if quotas_cost > quotas_left:
                    parser_status.fatal_error_details = 'Quotas cost exceeded (quotas cost:' + quotas_cost + '), quotas left:' + quotas_left
                    ParserStatus.update(parser_status)
                    ParserStatus.add_new_status('idle', status_description='Idle')
                    exit(0)

                else:
                    for num, video_id in enumerate(new_video_ids):
                        last_status = ParserStatus.get_last_status()
                        if last_status.status == 'stop':
                            ParserStatus.delete(last_status)
                            parser_status.status = 'stopped'
                            ParserStatus.update(parser_status)
                            ParserStatus.add_new_status('idle', status_description='Idle')
                            exit(0)

                        else:
                            yt_video = YT.get_video(video_id)
                            video = yt_video
                            if YT_PROXIES:
                                while YT_PROXIES:
                                    proxy = YT_PROXIES[0]
                                    proxy_dict = Proxies.dict_format_proxy(proxy)
                                    try:
                                        video = CaptionParser.load_captions(video, 'en', 'ASR', proxy=proxy_dict)

                                    except CaptionParser.YtCaptcha:
                                        proxy.isCaptcha = 1
                                        Proxies.update(proxy)
                                        YT_PROXIES.pop(0)
                                    except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                                        proxy.isAvailable = 0
                                        Proxies.update(proxy)
                                        YT_PROXIES.pop(0)
                                    else:
                                        break

                                if not video.subtitle and not YT_PROXIES:
                                    Videos.save_or_update(video)
                                    parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                                         CaptionParser)
                                    parser_status.count_items_done = num + 1
                                    ParserTasks.set_fatal_error(fresh_task)
                                    parser_status.fatal_error_details = "Proxies ended"
                                    parser_status.status = 'error'
                                    ParserStatus.update(parser_status)
                                    ParserStatus.add_new_status('idle', status_description='Idle')
                                    exit(0)

                            else:
                                video = CaptionParser.load_captions(video, 'en', 'ASR')
                            Videos.save_or_update(video)

                            parser_status = ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                            parser_status.count_items_done = num + 1
                            parser_status.status_description = 'Get missed videos for channel \'' + channel.title + '\'' + \
                                                               " (" + str(parser_status.count_items_done) + "/" + \
                                                               str(parser_status.count_items_total) + ")"
                            ParserStatus.update(parser_status)

            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'get_new_videos':
            channel_id = fresh_task.task_item
            channel = Channels.get_by_id(channel_id)
            if channel:
                last_video = Videos.MySQL.select(columns='videoId', where='channelId = %s', values=channel_id,
                                             order_by='publishedAt DESC', limit=1)
                if last_video:
                    last_video_id = last_video['videoId']
                    new_videos_ids = YT.get_playlist_ids_up_to(channel.relatedPlaylistsUploads, last_video_id)
                    parser_status.count_items_total = len(new_videos_ids)
                    parser_status.count_items_done = 0
                    parser_status.status_description = 'Get new videos for channel \'' + channel.title + '\' '
                    ParserStatus.update(parser_status)

                    if new_videos_ids:
                        quotas_cost = YT.calc_quotas_to_use(len(new_videos_ids), 'get_video')
                        quotas_left = YT.get_left_quotas()
                        parser_status.estimated_quotas = quotas_cost

                        if quotas_cost > quotas_left:
                            parser_status.fatal_error_details = 'Quotas cost exceeded (quotas cost:' + str(quotas_cost) + '), quotas left:' + str(quotas_left)
                            parser_status.status = 'error'
                            ParserStatus.update(parser_status)
                            ParserStatus.add_new_status('idle', status_description='Idle')
                            exit(0)

                        else:
                            for num, video_id in enumerate(new_videos_ids):
                                last_status = ParserStatus.get_last_status()
                                if last_status.status == 'stop':
                                    ParserStatus.delete(last_status)
                                    parser_status.status = 'stopped'
                                    ParserStatus.update(parser_status)
                                    ParserStatus.add_new_status('idle', status_description='Idle')
                                    exit(0)

                                else:
                                    video = YT.get_video(video_id)
                                    if YT_PROXIES:
                                        while YT_PROXIES:
                                            proxy = YT_PROXIES[0]
                                            proxy_dict = Proxies.dict_format_proxy(proxy)
                                            try:
                                                video = CaptionParser.load_captions(video, 'en', 'ASR',
                                                                                    proxy=proxy_dict)

                                            except CaptionParser.YtCaptcha:
                                                proxy.isCaptcha = 1
                                                Proxies.update(proxy)
                                                YT_PROXIES.pop(0)
                                            except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                                                proxy.isAvailable = 0
                                                Proxies.update(proxy)
                                                YT_PROXIES.pop(0)
                                            else:
                                                break

                                        if not video.subtitle and not YT_PROXIES:
                                            Videos.save_or_update(video)
                                            parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                                                 CaptionParser)
                                            parser_status.count_items_done = num + 1
                                            ParserTasks.set_fatal_error(fresh_task)
                                            parser_status.fatal_error_details = "Proxies ended"
                                            parser_status.status = 'error'
                                            ParserStatus.update(parser_status)
                                            ParserStatus.add_new_status('idle', status_description='Idle')
                                            exit(0)

                                    else:
                                        video = CaptionParser.load_captions(video, 'en', 'ASR')
                                    Videos.save_or_update(video)
                                    parser_status = ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                                    parser_status.count_items_done += 1
                                    parser_status.status_description = 'Get new videos for channel \'' + channel.title + '\'' + \
                                                                       " (" + str(parser_status.count_items_done) + "/" + \
                                                                       str(parser_status.count_items_total) + ' videos done)'
                                    ParserStatus.update(parser_status)

            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'sync_videos':
            # Remove videos which does not exists in BOTH mysql and sphinx indexes
            channel_id = fresh_task.task_item
            channel = Channels.get_by_id(channel_id)
            if channel:
                parser_status.status_description = 'Sync videos for channel \'' + channel.title
                ParserStatus.update(parser_status)

                mysql_videos_ids = Videos.get_channel_mysql_video_ids(channel_id)
                sphinx_videos_ids = Videos.get_channel_sphinx_video_ids(channel_id)
                set_mysql_videos_ids = set(mysql_videos_ids)
                set_sphinx_videos_ids = set(sphinx_videos_ids)

                mysql_difference = set_mysql_videos_ids.difference(set_sphinx_videos_ids)
                sphinx_difference = set_sphinx_videos_ids.difference(set_mysql_videos_ids)
                mysql_difference.update(sphinx_difference)

                parser_status.count_items_total = len(mysql_difference)
                parser_status.count_items_done = 0
                ParserStatus.update(parser_status)

                for video_id in mysql_difference:
                    last_status = ParserStatus.get_last_status()
                    if last_status.status == 'stop':
                        ParserStatus.delete(last_status)
                        parser_status.status = 'stopped'
                        ParserStatus.update(parser_status)
                        ParserStatus.add_new_status('idle', status_description='Idle')
                        exit(0)
                    else:
                        Videos.delete_by_id(video_id)
                    parser_status.count_items_done += 1
                    parser_status.status_description = 'Sync videos for channel \'' + channel.title + '\'' + \
                                                        " (" + str(parser_status.count_items_done) + "/" + \
                                                        str(parser_status.count_items_total) + ' videos done)'
                    ParserStatus.update(parser_status)

            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'build_sphinx_data':
            # Check whether video data exists in BOTH sphinx and mysql indexes, if not - load this data to sphinx
            channel_id = fresh_task.task_item
            channel = Channels.get_by_id(channel_id)
            if channel:
                parser_status.status_description = 'Build sphinx data for channel \'' + channel.title
                ParserStatus.update(parser_status)

                mysql_videos_ids = Videos.get_channel_mysql_video_ids(channel_id)
                sphinx_videos_ids = Videos.get_channel_sphinx_video_ids(channel_id)
                missed_videos_ids = list(set(mysql_videos_ids) - set(sphinx_videos_ids))

                parser_status.count_items_total = len(missed_videos_ids)
                parser_status.count_items_done = 0
                ParserStatus.update(parser_status)

                for num, video_id in enumerate(missed_videos_ids):
                    last_status = ParserStatus.get_last_status()
                    if last_status.status == 'stop':
                        ParserStatus.delete(last_status)
                        parser_status.status = 'stopped'
                        ParserStatus.update(parser_status)
                        ParserStatus.add_new_status('idle', status_description='Idle')
                        exit(0)
                    else:
                        video = Videos.get_by_id(video_id)
                        if YT_PROXIES:
                            while YT_PROXIES:
                                proxy = YT_PROXIES[0]
                                proxy_dict = Proxies.dict_format_proxy(proxy)
                                try:
                                    video = CaptionParser.load_captions(video, 'en', 'ASR',
                                                                        proxy=proxy_dict)

                                except CaptionParser.YtCaptcha:
                                    proxy.isCaptcha = 1
                                    Proxies.update(proxy)
                                    YT_PROXIES.pop(0)
                                except (CaptionParser.ProxyUnavailable, CaptionParser.ProxyError):
                                    proxy.isAvailable = 0
                                    Proxies.update(proxy)
                                    YT_PROXIES.pop(0)
                                else:
                                    break

                            if not video.subtitle and not YT_PROXIES:
                                Videos.save_or_update(video)
                                parser_status = ParserStatus.load_captions_statistic(parser_status,
                                                                                     CaptionParser)
                                parser_status.count_items_done = num + 1
                                ParserTasks.set_fatal_error(fresh_task)
                                parser_status.fatal_error_details = "Proxies ended"
                                parser_status.status = 'error'
                                ParserStatus.update(parser_status)
                                ParserStatus.add_new_status('idle', status_description='Idle')
                                exit(0)

                        else:
                            video = CaptionParser.load_captions(video, 'en', 'ASR')

                        Videos.save_or_update(video)
                        parser_status = ParserStatus.load_captions_statistic(parser_status, CaptionParser)
                        parser_status.count_items_done += 1
                        parser_status.status_description = 'Build sphinx data for channel \'' + channel.title + '\'' + \
                                                           " (" + str(parser_status.count_items_done) + "/" + \
                                                           str(parser_status.count_items_total) + ' videos done)'
                        ParserStatus.update(parser_status)


            ParserTasks.set_finished(fresh_task)
            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

        elif fresh_task.task == 'reindex_channel':
            # Check whether video data exists in BOTH sphinx and mysql indexes, if not - load this data to sphinx
            channel_id = fresh_task.task_item
            channel = Channels.get_by_id(channel_id)
            if channel:
                parser_status.status_description = 'Reindex sphinx data for channel \'' + channel.title + '\''
                ParserStatus.update(parser_status)

                sphinx_videos_ids = Videos.get_channel_sphinx_video_ids(channel_id)

                parser_status.count_items_total = len(sphinx_videos_ids)
                parser_status.count_items_done = 0
                ParserStatus.update(parser_status)

                for video_id in sphinx_videos_ids:
                    last_status = ParserStatus.get_last_status()
                    if last_status.status == 'stop':
                        ParserStatus.delete(last_status)
                        parser_status.status = 'stopped'
                        ParserStatus.update(parser_status)
                        ParserStatus.add_new_status('idle', status_description='Idle')
                        exit(0)
                    else:
                        video = Videos.get_by_id(video_id)
                        Videos.save_or_update(video)
                    parser_status.count_items_done += 1
                    parser_status.status_description = 'Reindex sphinx data for channel \'' + channel.title + '\'' + \
                                                       " (" + str(parser_status.count_items_done) + "/" + \
                                                       str(parser_status.count_items_total) + ' videos done)'
                    ParserStatus.update(parser_status)


            ParserTasks.set_finished(fresh_task)
            parser_status.status = 'finished'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            ParserTasks.set_finished(fresh_task)

    except Exception as e:
        ParserTasks.set_fatal_error(fresh_task)
        parser_status.fatal_error_details = traceback.format_exc()
        parser_status.status = 'error'
        ParserStatus.update(parser_status)
        ParserStatus.add_new_status('idle', status_description='Idle')
        print(traceback.format_exc())
