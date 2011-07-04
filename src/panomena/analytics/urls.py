from django.conf.urls.defaults import *


urlpatterns = patterns('panomena.analytics.views.ga',
    url(r'^ga/$', 'ga', {}, 'ga'),
)
