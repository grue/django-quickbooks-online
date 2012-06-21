import urlparse
import oauth2 as oauth
from django.http import HttpResponse, HttpResponseRedirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
from quickbooks.models import QuickbooksToken, MissingTokenException
from quickbooks.api import QuickbooksApi

REQUEST_TOKEN_URL = 'https://oauth.intuit.com/oauth/v1/get_request_token'
ACCESS_TOKEN_URL = 'https://oauth.intuit.com/oauth/v1/get_access_token'
AUTHORIZATION_URL = 'https://appcenter.intuit.com/Connect/Begin'

consumer = oauth.Consumer(settings.QUICKBOOKS['CONSUMER_KEY'], settings.QUICKBOOKS['CONSUMER_SECRET'])

def _get_saved_token(request):
    try:
        return QuickbooksToken.objects.filter(user=request.user)[0]
    except IndexError:
        raise MissingTokenException("No QuickBooks OAuth token exists for this user")

@login_required
def request_oauth_token(request):
    access_token_callback = settings.QUICKBOOKS['OAUTH_CALLBACK_URL']
    client = oauth.Client(consumer)
    resp, content = client.request("%s?oauth_callback=%s" % (REQUEST_TOKEN_URL, access_token_callback), "GET")
    if resp['status'] != '200':
        raise Exception("Invalid response: %s" % resp['status'])
    request_token = dict(urlparse.parse_qsl(content))
    request.session['qb_oauth_token'] = request_token['oauth_token']
    request.session['qb_oauth_token_secret'] = request_token['oauth_token_secret']
    return HttpResponseRedirect("%s?oauth_token=%s" % (AUTHORIZATION_URL, request_token['oauth_token']))

@login_required
def get_access_token(request):
    account = get_account(request)
    token = oauth.Token(request.session['qb_oauth_token'], request.session['qb_oauth_token_secret'])
    token.set_verifier(request.GET.get('oauth_verifier'))
    client = oauth.Client(consumer, token)
    resp, content = client.request(ACCESS_TOKEN_URL, "POST")
    access_token = dict(urlparse.parse_qsl(content))
    realm_id = request.GET.get('realmId')
    data_source = request.GET.get('dataSource')

    QuickbooksToken.objects.create(
        user = request.user,
        access_token = access_token['oauth_token'],
        access_token_secret = access_token['oauth_token_secret'],
        realm_id = realm_id,
        data_source = data_source)

    return HttpResponseRedirect(settings.QUICKBOOKS['ACCESS_COMPLETE_URL'])

@login_required
def blue_dot_menu(request):
    token = _get_saved_token(request)
    return HttpResponse(QuickbooksApi(token).get('Account/AppMenu'))

