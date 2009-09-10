from django.conf.urls.defaults import *

urlpatterns = patterns('synk',
    # web pages
    (r'^$', 'web.index'),
    (r'^register$', 'web.register'),
    (r'^dev$', 'web.dev'),

    # API URLs
    (r'^status$', 'service.status', {'since': '0'}),
    (r'^status/since/(?P<since>[\d\.]+)$', 'service.status'),
)
