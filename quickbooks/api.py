import urllib

from requests_oauthlib import OAuth1Session
from django.conf import settings
from django.contrib.auth.models import User
from quickbooks.models import QuickbooksToken

APPCENTER_URL_BASE = 'https://appcenter.intuit.com/api/v1/'

QUICKBOOKS_DESKTOP_V3_URL_BASE = 'https://quickbooks.api.intuit.com/v3'
QUICKBOOKS_ONLINE_V3_URL_BASE = 'https://quickbooks.api.intuit.com/v3'


class QuickbooksError(Exception):
    pass


class TryLaterError(QuickbooksError):
    pass


class CommunicationError(QuickbooksError):
    pass


class AuthenticationFailure(QuickbooksError):
    pass


class ApiError(QuickbooksError):
    pass


class DuplicateItemError(ApiError):
    pass


class QuickbooksApi(object):
    """ This is an interface to the QBD and QBO v3 api."""
    def __init__(self, owner_or_token):
        if isinstance(owner_or_token, User):
            self.token = QuickbooksToken.objects.filter(user=owner_or_token).first()
        elif isinstance(owner_or_token, QuickbooksToken):
            self.token = owner_or_token
        else:
            raise ValueError("API must be initialized with either a QuickbooksToken or User")

        session = OAuth1Session(client_key=settings.QUICKBOOKS['CONSUMER_KEY'],
                                client_secret=settings.QUICKBOOKS['CONSUMER_SECRET'],
                                resource_owner_key=self.token.access_token,
                                resource_owner_secret=self.token.access_token_secret)

        session.headers.update({'content-type': 'application/json', 'accept': 'application/json'})
        self.session = session
        self.realm_id = self.token.realm_id
        self.data_source = self.token.data_source
        self.url_base = {'QBD': QUICKBOOKS_DESKTOP_V3_URL_BASE,
                         'QBO': QUICKBOOKS_ONLINE_V3_URL_BASE}[self.token.data_source]

    def _appcenter_request(self, url, retries=3):
        full_url = APPCENTER_URL_BASE + url

        for retry_i in range(retries + 1):
            content = self.session.get(full_url).content

        # [todo] - Add some error handling for _appcenter_requests.
        # https://developer.intuit.com/docs/0025_quickbooksapi/0053_auth_auth/platform_api#AppMenu
        # intuit's documentation is a bit vauge:
        # "Note that this API returns HTML intended for display, not XML data."
        # "Status code 200 - The OAuth access token has expired or is invalid for some other reason. The HTML returned
        # shows the Connect to QuickBooks button within the Intuit Blue Dot menu. "

        return content

    def app_menu(self, retries=3):
        return self._appcenter_request('account/appmenu', retries=retries)

    def disconnect(self):
        return self._appcenter_request('connection/disconnect')

    def read(self, object_type, entity_id):
        """ Make a call to /company/<token_realm_id>/<object_type>/<entity_id>
            This will return the details for the entity id in the

        """
        # [todo] - add error handling for v3 read
        """ Example Error:
        {u'Fault': {u'Error': [{u'Detail': u'System Failure Error: Could not find resource for relative :
        /v3/company/<id>/Employee/0 of full path: https://internal.qbo.intuit.com/qbo30/v3/company/<id>/Employee/0',
         u'Message': u'An application error has occurred while processing your request',
         u'code': u'10000'}],
         u'type': u'SystemFault'},
         u'time': u'<Timestamp>'
         }
         """
        constructed_url = "{}/company/{}/{}/{}".format(self.url_base, self.realm_id, object_type, entity_id)
        return self.session.get(constructed_url).json()

    def query(self, query):
        """
            Documentation for the query language can be found here:
            https://developer.intuit.com/docs/0025_quickbooksapi/0050_data_services/020_key_concepts/

            It is similar to SQL.
        """
        # [todo] - add error handling for v3 query
        constructed_url = "{}/company/{}/query?query={}".format(self.url_base, self.realm_id, urllib.quote(query))
        return self.session.get(constructed_url).json()

    def create(self, object_type, object_body):
        # [todo] - add error handling for v3 create
        # [todo] - validate that the object_body is a proper json blob
        constructed_url = "{}/company/{}/{}".format(self.url_base, self.realm_id, object_type)
        return self.session.post(constructed_url.lower(), object_body).json()

    def delete(self, object_type, object_body):
        # [todo] - add error handling for v3 delete
        # [todo] - validate that the object_body is a proper json blob
        constructed_url = "{}/company/{}/{}?operation=delete".format(self.url_base, self.realm_id, object_type)
        return self.session.post(constructed_url.lower(), object_body).json()

    def update(self, object_type, object_body):
        # [todo] - add error handling for v3 update
        # [todo] - validate that the object_body is a proper json blob
        constructed_url = "{}/company/{}/{}?operation=update".format(self.url_base, self.realm_id, object_type)
        return self.session.post(constructed_url.lower(), object_body).json()
