import urllib
import re
import datetime
from lxml import etree
import requests
from oauth_hook import OAuthHook
from django.conf import settings
from django.contrib.auth.models import User
from quickbooks.models import QuickbooksToken

APPCENTER_URL_BASE = 'https://appcenter.intuit.com/api/v1/'
DATA_SERVICES_VERSION = 'v2'
QUICKBOOKS_ONLINE_URL_BASE = 'https://qbo.sbfinance.intuit.com/resource/'
QUICKBOOKS_WINDOWS_URL_BASE = 'https://services.intuit.com/sb/'

QB_NAMESPACE = 'http://www.intuit.com/sb/cdm/v2'
QBO_NAMESPACE = 'http://www.intuit.com/sb/cdm/qbo'
NSMAP = {None: QB_NAMESPACE, 'ns2': QBO_NAMESPACE}
Q = "{%s}" % QB_NAMESPACE


def camel2hyphen(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1-\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1-\2', s1).lower()

def get_url_name(name, action):
    if name in ['CompanyMetaData', 'Preferences']:
        return name.lower()
    base = camel2hyphen(name)
    if action == 'read':
        # read multiple objects; pluralize
        if base.endswith('s'):
            return base + 'es'
        elif base.endswith('y'):
            return base[:-1] + 'ies'
        return base + 's'
    return base

def obj2xml(parent, params):
    # etree operates on elts in place
    for k, v in params.items():
        if isinstance(v, dict):
            elt = etree.SubElement(parent, Q + k)
            obj2xml(elt, v)
        elif isinstance(v, list):
            for listelt in v:
                elt = etree.SubElement(parent, Q + k)
                obj2xml(elt, listelt)
        else:
            elt = etree.SubElement(parent, Q + k)
            if isinstance(v, bool):
                val = {True: 'true', False: 'false'}[v]
            elif isinstance(v, datetime.date) or isinstance(v, datetime.datetime):
                val = v.isoformat()
            else:
                val = unicode(v).replace('"', "'")
            elt.text = val
    return parent

def xml2obj(elt):
    if len(elt) == 0:
        return elt.text
    else:
        result = {}
        for child in elt:
            # Remove namespace prefixes
            tagname = re.sub(r'^{.*}', '', child.tag)
            if tagname in result:
                if not isinstance(result[tagname], list):
                    result[tagname] = [result[tagname]]
                result[tagname].append(xml2obj(child))
            else:
                result[tagname] = xml2obj(child)
        return result


class QuickbooksError(Exception):
    pass

class TryLaterError(QuickbooksError):
    pass

class CommunicationError(QuickbooksError):
    pass

class ApiError(QuickbooksError):
    pass

class DuplicateItemError(ApiError):
    pass


def api_error(response):
    err = xml2obj(etree.fromstring(response.content))
    error_code = err.get('ErrorCode', 'BAD_REQUEST')
    msg = err.get('Message', '')
    cause = err.get('Cause', '')
    err_msg = "%s: %s %s" % (error_code, cause, msg)

    err_cls = ApiError
    if cause == '-11202':
        err_cls = DuplicateItemError

    raise err_cls(err_msg)

class QuickbooksApi(object):
    def __init__(self, owner):
        if isinstance(owner, User):
            token = QuickbooksToken.objects.filter(user=owner)[0]
        elif isinstance(owner, QuickbooksToken):
            token = owner
        else:
            raise ValueError("API must be initialized with either a QuickbooksToken or User")

        hook = OAuthHook(token.access_token,
                         token.access_token_secret,
                         settings.QUICKBOOKS['CONSUMER_KEY'],
                         settings.QUICKBOOKS['CONSUMER_SECRET'],
                         header_auth=True)
        self.session = requests.session(hooks={'pre_request': hook})
        self.realm_id = token.realm_id

    def _get(self, url, headers=None):
        return self.session.get(url, headers=headers, verify=False)

    def _post(self, url, body='', headers=None):
        return self.session.post(url, data=body, headers=headers, verify=False)

    def _appcenter_request(self, url):
        full_url = APPCENTER_URL_BASE + url
        return self._get(full_url)

    def _qbo_request(self, object_name, method='GET', object_id=None, xml=None, headers=None, **kwargs):
        url = "%s%s/%s/%s" % (QUICKBOOKS_ONLINE_URL_BASE, object_name, DATA_SERVICES_VERSION, self.realm_id)
        if object_id:
            url += '/%s' % object_id
        if kwargs:
            url = "%s?%s" % (url, urllib.urlencode(kwargs))
        if method == 'GET':
            response = self._get(url, headers)
        else:
            if xml is not None:
                body = etree.tostring(xml, xml_declaration=True, encoding='utf-8')
                response = self._post(url, body, headers)
            else:
                response = self._post(url, headers)
        if response.status_code == 500 and 'errorCode=006003' in response.content:
            # QB appears to randomly throw 500 errors once and a while. Awesome.
            raise TryLaterError()
        if response.status_code != 200:
            try:
                api_error(response)
            except etree.XMLSyntaxError:
                raise CommunicationError(response.content)
        return xml2obj(etree.fromstring(response.content))

    def app_menu(self):
        return self._appcenter_request('Account/AppMenu')

    def disconnect(self):
        return self._appcenter_request('Connection/Disconnect')


    def create(self, object_name, params):
        url_name = get_url_name(object_name, 'create')
        root = etree.Element(object_name, nsmap=NSMAP)
        obj2xml(root, params)
        return self._qbo_request(url_name, 'POST', xml=root, headers={'Content-Type': 'application/xml'})

    def read(self, object_name):
        url_name = get_url_name(object_name, 'read')
        return self._qbo_request(url_name, 'POST', headers={'Content-Type': 'x-www-form-urlencoded', 'Host': 'qbo.sbfinance.intuit.com'})

    def get(self, object_name, object_id):
        url_name = get_url_name(object_name, 'get')
        return self._qbo_request(url_name, 'GET', object_id=object_id)

    def update(self, object_name, params):
        object_id = params['Id']
        url_name = get_url_name(object_name, 'update')
        root = etree.Element(object_name, nsmap=NSMAP)
        obj2xml(root, params)
        return self._qbo_request(url_name, 'POST', object_id=object_id, xml=root, headers={'Content-Type': 'application/xml'})

    def delete(self, object_name, params):
        object_id = params['Id']
        url_name = get_url_name(object_name, 'delete')
        root = etree.Element(object_name, nsmap=NSMAP)
        obj2xml(root, params)
        return self._qbo_request(url_name, 'POST', object_id=object_id, xml=root, headers={'Content-Type': 'application/xml'}, methodx='delete')
