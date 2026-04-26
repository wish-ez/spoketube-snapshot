from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig
from django.contrib import admin
# from django.contrib.admin import sites
# from .models import Videos, Channels, DataApiQuotas, DataParserStatuses, DataParserTasks
# from mainapp.admin import VideosAdmin

"""
Config for custom admin site, based on AdminSite
"""
class MyAdminConfig(AdminConfig):
    default_site = 'mainapp.admin.MyAdminSite'

class MainappConfig(AppConfig):
    name = 'mainapp'