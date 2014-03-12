import logging

from requests_oauthlib import OAuth1Session
from django.http import HttpResponse, HttpResponseRedirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from .models import QuickbooksToken, get_quickbooks_token
from .api import QuickbooksApi, AuthenticationFailure
from .signals import qb_connected

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

    session = OAuth1Session(client_key=settings.QUICKBOOKS['CONSUMER_KEY'],
                            client_secret=settings.QUICKBOOKS['CONSUMER_SECRET'],
                            callback_uri=access_token_callback)

    response = session.fetch_request_token(REQUEST_TOKEN_URL)

    try:
        request_token = response['oauth_token']
        request_token_secret = response['oauth_token_secret']

        request.session['qb_oauth_token'] = request_token
        request.session['qb_oauth_token_secret'] = request_token_secret
    except:
        logger = logging.getLogger('quickbooks.views.request_oauth_token')
        logger.exception(("Couldn't extract oAuth parameters from token " +
                          "request response. Response was '%s'"), response)
        raise
    return HttpResponseRedirect("%s?oauth_token=%s" % (AUTHORIZATION_URL, request_token))


@login_required
def get_access_token(request):
    # [todo] - add doc string for get_access_token
    session = OAuth1Session(client_key=settings.QUICKBOOKS['CONSUMER_KEY'],
                            client_secret=settings.QUICKBOOKS['CONSUMER_SECRET'],
                            resource_owner_key=request.session['qb_oauth_token'],
                            resource_owner_secret=request.session['qb_oauth_token_secret'])

    remote_response = session.parse_authorization_response('?{}'.format(request.META.get('QUERY_STRING')))
    realm_id = remote_response['realmId']
    data_source = remote_response['dataSource']
    oauth_verifier = remote_response['oauth_verifier']

    # [review] - Possible bug? This should be taken care of by session.parse_authorization_response
    session.auth.client.verifier = unicode(oauth_verifier)

    response = session.fetch_access_token(ACCESS_TOKEN_URL)

    # Delete any existing access tokens
    request.user.quickbookstoken_set.all().delete()

    token = QuickbooksToken.objects.create(
        user=request.user,
        access_token=response['oauth_token'],
        access_token_secret=response['oauth_token_secret'],
        realm_id=realm_id,
        data_source=data_source)

    # Cache blue dot menu
    try:
        request.session[BLUE_DOT_CACHE_KEY] = None
        blue_dot_menu(request)
    except AttributeError:
        raise Exception('The sessions framework must be installed for this ' +
                        'application to work.')

    # Let everyone else know we conneted
    qb_connected.send(None, token=token)

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
    """ Try to disconnect from Intuit, then destroy our tokens."""

    token = get_quickbooks_token(request)
    try:
        QuickbooksApi(token).disconnect()
    except AuthenticationFailure:
        # If there is an authentication error, then these tokens are bad
        # We need to destroy them in any case.
        pass

    request.user.quickbookstoken_set.all().delete()
    return HttpResponseRedirect(settings.QUICKBOOKS['ACCESS_COMPLETE_URL'])
