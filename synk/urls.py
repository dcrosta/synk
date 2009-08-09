from django.conf.urls.defaults import *

urlpatterns = patterns('synk.views',
    (r'^$', 'index'),

    # web pages
    (r'^register$', 'register'),

    # API URLs
    (r'^status$', 'status'),
)
