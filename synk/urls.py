from django.conf.urls.defaults import *

urlpatterns = patterns('synk',
    # web pages
    (r'^$', 'web.index'),
    (r'^register$', 'web.register'),
    (r'^dev$', 'web.dev'),

    # API URLs
    (r'^account/test$', 'service.account_test'),

    (r'^events/(?P<service>[^/]+)$', 'service.events', {'type': None, 'since': 0}),
    (r'^events/(?P<service>[^/]+)/since/(?P<since>[^/]+)$', 'service.events', {'type': None}),

    (r'^events/(?P<service>[^/]+)/(?P<type>[^/]+)$', 'service.events', {'since': 0}),
    (r'^events/(?P<service>[^/]+)/(?P<type>[^/]+)/since/(?P<since>[^/]+)$', 'service.events'),
)

