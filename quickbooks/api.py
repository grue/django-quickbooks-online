import urllib
import time
import oauth2 as oauth
from django.conf import settings

consumer = oauth.Consumer(settings.QUICKBOOKS['CONSUMER_KEY'], settings.QUICKBOOKS['CONSUMER_SECRET'])
URL_BASE = 'https://appcenter.intuit.com/api/v1/'

class QuickbooksApi(object):
    def __init__(self, token):
        self.token = oauth.Token(token.access_token, token.access_token_secret)

    def _request(self, url, method, **kwargs):
        client = oauth.Client(consumer, self.token)
        body = urllib.urlencode(kwargs)
        complete_url = URL_BASE + url
        resp, content = client.request(complete_url, method, body)
        return content

    def _xml_request(self, url, method, body):
        pass

    def get(self, url, **kwargs):
        return self._request(url, "GET", **kwargs)

    def post(self, url, **kwargs):
        return self._request(url, "POST", **kwargs)


