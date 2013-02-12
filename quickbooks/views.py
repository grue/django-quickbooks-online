import logging
import urlparse
import requests

from oauth_hook import OAuthHook
from django.http import HttpResponse, HttpResponseRedirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from quickbooks.models import QuickbooksToken, get_quickbooks_token
from quickbooks.api import QuickbooksApi

REQUEST_TOKEN_URL = 'https://oauth.intuit.com/oauth/v1/get_request_token'
ACCESS_TOKEN_URL = 'https://oauth.intuit.com/oauth/v1/get_access_token'
AUTHORIZATION_URL = 'https://appcenter.intuit.com/Connect/Begin'

BLUE_DOT_CACHE_KEY = 'quickbooks:blue_dot_menu'

@login_required
def request_oauth_token(request):
    # We'll require a refresh in the blue dot cache
    if BLUE_DOT_CACHE_KEY in request.session:
        del request.session[BLUE_DOT_CACHE_KEY]

    access_token_callback = settings.QUICKBOOKS['OAUTH_CALLBACK_URL']
    if callable(access_token_callback):
        access_token_callback = access_token_callback(request)
    quickbooks_oauth_hook = OAuthHook(consumer_key=settings.QUICKBOOKS['CONSUMER_KEY'],
                                      consumer_secret=settings.QUICKBOOKS['CONSUMER_SECRET'])
    response = requests.post(REQUEST_TOKEN_URL,
                             params={'oauth_callback': access_token_callback},
                             hooks={'pre_request': quickbooks_oauth_hook})
    try:
        qs = urlparse.parse_qs(response.text)
        request_token = qs['oauth_token'][0]
        request_token_secret = qs['oauth_token_secret'][0]

        request.session['qb_oauth_token'] = request_token
        request.session['qb_oauth_token_secret'] = request_token_secret
    except:
        logger = logging.getLogger('quickbooks.views.request_oauth_token')
        logger.exception(("Couldn't extract oAuth parameters from token " +
            "request response. Response was '%s'"), response.content)
        raise
    return HttpResponseRedirect("%s?oauth_token=%s" % (AUTHORIZATION_URL, request_token))


@login_required
def get_access_token(request):
    realm_id = request.GET.get('realmId')
    data_source = request.GET.get('dataSource')
    oauth_verifier = request.GET.get('oauth_verifier')

    quickbooks_oauth_hook = OAuthHook(request.session['qb_oauth_token'],
                                      request.session['qb_oauth_token_secret'],
                                      settings.QUICKBOOKS['CONSUMER_KEY'],
                                      settings.QUICKBOOKS['CONSUMER_SECRET'])
    response = requests.post(ACCESS_TOKEN_URL,
                             {'oauth_verifier': oauth_verifier},
                             hooks={'pre_request': quickbooks_oauth_hook})
    data = urlparse.parse_qs(response.content)

    # Delete any existing access tokens
    request.user.quickbookstoken_set.all().delete()

    QuickbooksToken.objects.create(
        user = request.user,
        access_token = data['oauth_token'][0],
        access_token_secret = data['oauth_token_secret'][0],
        realm_id = realm_id,
        data_source = data_source)

    # Cache blue dot menu
    try:
        request.session[BLUE_DOT_CACHE_KEY] = None
        #blue_dot_menu(request)
    except AttributeError:
        raise Exception('The sessions framework must be installed for this ' +
            'application to work.')

    return render_to_response('oauth_callback.html',
                              {'complete_url': settings.QUICKBOOKS['ACCESS_COMPLETE_URL']})


@login_required
def blue_dot_menu(request):
    """ Returns the blue dot menu. If possible a cached copy is returned.
    """

    html = request.session.get(BLUE_DOT_CACHE_KEY)
    if not html:
        html = request.session[BLUE_DOT_CACHE_KEY] = \
            HttpResponse(QuickbooksApi(request.user).app_menu())
    return html

@login_required
def disconnect(request):
    token = get_quickbooks_token(request)
    QuickbooksApi(token).disconnect()
    request.user.quickbookstoken_set.all().delete()
    return HttpResponseRedirect(settings.QUICKBOOKS['ACCESS_COMPLETE_URL'])
