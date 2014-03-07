from django.conf.urls import patterns

urlpatterns = patterns('quickbooks.views',
                       (r'^request_oauth_token/?$', 'request_oauth_token'),
                       (r'^get_access_token/?$', 'get_access_token'),
                       (r'^blue_dot_menu/?$', 'blue_dot_menu'),
                       (r'^disconnect/?$', 'disconnect'),
                       )
