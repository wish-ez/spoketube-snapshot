from django.conf.urls import url
from django.urls import path
from mainapp import views

app_name = 'mainapp'
urlpatterns = [
    url(r'^500/', views.server_error),
    url(r'^api/autocomplete_channels/', views.autocomplete_channels, name='autocomplete_channels'),
    url(r'^api/rest_matches/', views.get_rest_matches, name='rest_matches'),
    url(r'^api/rest_channels/', views.get_rest_channels, name='rest_channels'),
    url('search/', views.search, name='search'),
    url('contact/success', views.contact_success, name='contact_success'),
    url('contact/', views.contact, name='contact'),
    path('', views.main_page),
]

