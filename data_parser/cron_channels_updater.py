from data_parser import Connector, DataParserStatuses, Proxies
from googleapiclient.errors import HttpError
import traceback
import os
import configparser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_PATH = os.path.join(BASE_DIR, 'dev', 'secrets')

# If running on dev server then looking for secrets file, otherwise gets values from server environment
if os.path.exists(SECRETS_PATH):
    config = configparser.RawConfigParser()
    config.read(SECRETS_PATH)
    config = config['DEBUG LOCALHOST']
else:
    config = os.environ

if config['ENABLE_CRON_CHANNELS_UPDATER'] == '0':
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

else:
    parser_status = ParserStatus.create_new_status()
    parser_status.status = 'work'
    parser_status.status_description = 'Cron channels refreshing'
    ParserStatus.save(parser_status)
    try:
        from data_parser import Videos, Channels, YouTubeAPI, CaptionParser

        Sphinx_conn = Connector(host=config['SPHINX_HOST'],
                                port=config['SPHINX_PORT'],
                                )

        if config['YT_ENABLE_PROXY'].lower() == 'true':
            Proxies = Proxies(MySQL_conn)
            YT_PROXIES = Proxies.get_available_proxy()
            if not YT_PROXIES:
                parser_status = ParserStatus.create_new_status()
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

        channels_ids = Channels.get_all_channels_ids()
        count_channels = len(channels_ids)
        estimated_quotas = YT.calc_quotas_to_use(count_channels, 'get_playlist_ids_up_to')
        quotas_left = YT.get_left_quotas()
        parser_status.estimated_quotas = estimated_quotas
        ParserStatus.save(parser_status)
        if estimated_quotas > quotas_left:
            parser_status.fatal_error_details = 'Quotas cost exceeded (estimated quotas cost:' + str(
                estimated_quotas) + '), quotas left:' + str(quotas_left)
            parser_status.status = 'error'
            ParserStatus.update(parser_status)
            ParserStatus.add_new_status('idle', status_description='Idle')
            exit(0)

        else:
            for ch_num, channel_id in enumerate(channels_ids):
                ch_num += 1
                try:
                    last_status = ParserStatus.get_last_status()
                    if last_status.status == 'stop':
                        ParserStatus.delete(last_status)
                        parser_status.status = 'stopped'
                        ParserStatus.update(parser_status)
                        ParserStatus.add_new_status('idle', status_description='Idle')
                        exit(0)

                    else:
                        yt_channel = YT.get_channel(channel_id)
                        Channels.save_or_update(yt_channel)

                        last_video = Videos.MySQL.select(columns='videoId', where='channelId = %s', values=channel_id,
                                                         order_by='publishedAt DESC', limit=1)

                        if last_video:
                            last_video_id = last_video['videoId']
                            new_videos_ids = YT.get_playlist_ids_up_to(yt_channel.relatedPlaylistsUploads, last_video_id)
                            parser_status.count_items_total = len(new_videos_ids)
                            parser_status.count_items_done = 0
                            parser_status.status_description = 'Cron refresh channel \'' + yt_channel.title + ' (' + str(ch_num) + '/' + str(count_channels) + ') '
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
                                            parser_status.status_description = 'Cron get new videos for channel \'' + yt_channel.title + '\'' + \
                                                                               " (" + str(parser_status.count_items_done) + "/" + \
                                                                               str(parser_status.count_items_total) + ' videos done, ' + str(ch_num) + '/' + str(count_channels) + ' channels done)'
                                            ParserStatus.update(parser_status)
                except HttpError:
                    parser_status.fatal_error_details += "YT Api HTTP error on channel ID:" + channel_id + "; "
                    ParserStatus.update(parser_status)
                    continue

        parser_status.status = 'finished'
        ParserStatus.update(parser_status)
        ParserStatus.add_new_status('idle', status_description='Idle')

    except Exception as e:
        parser_status.fatal_error_details = traceback.format_exc()
        parser_status.status = 'error'
        ParserStatus.update(parser_status)
        ParserStatus.add_new_status('idle', status_description='Idle')
        print(traceback.format_exc())