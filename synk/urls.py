from django.conf.urls.defaults import *

urlpatterns = patterns('synk.views',
    (r'^$', 'index'),

    # web pages
    (r'^register$', 'register'),
    (r'^dev$', 'dev'),

    # API URLs
    (r'^status$', 'status', {'since': '0'}),
    #(r'^status/since/(?P<since>[\d\.]+)$', 'status'),

    (r'^subscriptions$', 'subscriptions'),
)
