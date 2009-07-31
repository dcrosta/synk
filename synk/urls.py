from django.conf.urls.defaults import *

urlpatterns = patterns('synk.views',
    (r'^$', 'index'),

    (r'login$', 'login'),

    # web pages
    (r'^register$', 'register'),
    (r'^user/(?P<username>\w+)', 'user_home'),

    # API URLs
    (r'^group$', 'group_index'),
    (r'^group/(?P<group_id>[a-zA-Z0-9_]+)$', 'group'),
)
