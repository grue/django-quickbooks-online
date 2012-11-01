import urllib
import re
import uuid
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
XML_SCHEMA = 'http://www.w3.org/2001/XMLSchema'
XML_SCHEMA_INSTANCE = 'http://www.w3.org/2001/XMLSchema-instance'
QBO_NSMAP = {None: QB_NAMESPACE, 'ns2': QBO_NAMESPACE}
QBD_NSMAP = {None: QB_NAMESPACE, 'xsi': XML_SCHEMA_INSTANCE, 'xsd': XML_SCHEMA}
Q = "{%s}" % QB_NAMESPACE
XSI = "{%s}" % XML_SCHEMA_INSTANCE


def camel2hyphen(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1-\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1-\2', s1).lower()

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
            if k == 'Id':
                elt.set('idDomain', 'NG')
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

class AuthenticationFailure(QuickbooksError):
    pass

class ApiError(QuickbooksError):
    pass

class DuplicateItemError(ApiError):
    pass


def api_error(response):
    if isinstance(response, requests.Response):
        err = xml2obj(etree.fromstring(response.content))
    else:
        err = response
    error_code = err.get('ErrorCode', 'BAD_REQUEST')
    message = err.get('Message', err.get('ErrorDesc', ''))
    cause = err.get('Cause', '')
    db_error_code = err.get('DBErrorCode', '')
    err_msg = "%s: %s %s" % (error_code, cause, message)

    if error_code == '3200' or 'oauth_problem' in message:
        raise AuthenticationFailure()

    if cause == '-11202' or db_error_code == '20345':
        raise DuplicateItemError, err_msg
    raise ApiError, err_msg


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
        self.data_source = token.data_source
        self.url_base = {'QBD': QUICKBOOKS_WINDOWS_URL_BASE, 'QBO': QUICKBOOKS_ONLINE_URL_BASE}[token.data_source]
        self.nsmap = {'QBD': QBD_NSMAP, 'QBO': QBO_NSMAP}[token.data_source]
        self.xml_content_type = {'QBD': 'text/xml', 'QBO': 'application/xml'}[token.data_source]
        self.token = token

    def _get_url_name(self, name, action):
        if name in ['CompanyMetaData', 'Preferences'] or self.data_source == 'QBD':
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

    def _create_wrapped_qbd_root(self, action, object_name=None, request_and_realm_ids=True):
        wrapper = etree.Element(action, nsmap=self.nsmap)
        wrapper.set(XSI + 'schemaLocation', 'http://www.intuit.com/sb/cdm/V2./RestDataFilter.xsd ')
        if request_and_realm_ids:
            wrapper.set('RequestId', uuid.uuid4().hex)
            wrapper.set('FullResponse', 'true')
        offeringId = etree.SubElement(wrapper, Q + 'OfferingId')
        offeringId.text = 'ipp'
        if request_and_realm_ids:
            externalRealmId = etree.SubElement(wrapper, Q + 'ExternalRealmId')
            externalRealmId.text = self.realm_id
        if object_name:
            root = etree.SubElement(wrapper, Q + object_name)
        else:
            root = None
        return wrapper, root

    def _get(self, url, headers=None):
        return self.session.get(url, headers=headers, verify=False)

    def _post(self, url, body='', headers=None):
        return self.session.post(url, data=body, headers=headers, verify=False)

    def _appcenter_request(self, url):
        full_url = APPCENTER_URL_BASE + url
        return self._get(full_url).content

    def _qb_request(self, object_name, method='GET', object_id=None, xml=None, body_dict=None, **kwargs):
        url = "%s%s/%s/%s" % (self.url_base, object_name, DATA_SERVICES_VERSION, self.realm_id)
        if object_id:
            url += '/%s' % object_id
        if kwargs:
            url = "%s?%s" % (url, urllib.urlencode(kwargs))
        if method == 'GET':
            response = self._get(url)
        else:
            if xml is not None:
                body = etree.tostring(xml, xml_declaration=True, encoding='utf-8', pretty_print=True)
                response = self._post(url, body, headers={'Content-Type': self.xml_content_type})
            elif body_dict is not None:
                response = self._post(url, body_dict, headers={'Content-Type': 'application/x-www-form-urlencoded'})
            else:
                response = self._post(url, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        if response.status_code == 500 and 'errorCode=006003' in response.content:
            # QB appears to randomly throw 500 errors once and a while. Awesome.
            raise TryLaterError()
        if response.status_code == 401:
            # Token has expired. Delete all tokens for this user
            self.token.user.quickbookstoken_set.all().delete()
            raise AuthenticationFailure()
        if response.status_code != 200:
            try:
                api_error(response)
            except etree.XMLSyntaxError:
                raise CommunicationError(response.content)
        result = xml2obj(etree.fromstring(response.content))
        if 'Error' in result:
            api_error(result['Error'])
        return result

    def app_menu(self):
        return self._appcenter_request('Account/AppMenu')

    def disconnect(self):
        return self._appcenter_request('Connection/Disconnect')


    def create(self, object_name, params):
        url_name = self._get_url_name(object_name, 'create')
        if self.data_source == 'QBO':
            root = etree.Element(object_name, nsmap=self.nsmap)
            obj2xml(root, params)
        else:
            root, data_root = self._create_wrapped_qbd_root('Add', object_name)
            obj2xml(data_root, params)

        result = self._qb_request(url_name, 'POST', xml=root)

        if self.data_source == 'QBD':
            container = result['Success']
            for k, v in container.items():
                if k == object_name:
                    return v
            return container
        else:
            return result

    def read(self, object_name):
        url_name = self._get_url_name(object_name, 'read')
        if self.data_source == 'QBO':
            results = []
            count = 100
            page = 1
            while count == 100:
                these_results = self._qb_request(url_name, 'POST', body_dict={'PageNum': str(page), 'ResultsPerPage': '100'})
                count = int(these_results['Count'])
                if count != 0:
                    results += these_results['CdmCollections'][object_name]
                page += 1
            return results
        else:
            return self._qb_request(url_name, 'GET')

    def get(self, object_name, object_id):
        url_name = self._get_url_name(object_name, 'get')
        if self.data_source == 'QBO':
            return self._qb_request(url_name, 'GET', object_id=object_id)
        else:
            return self._qb_request(url_name, 'GET', object_id=object_id, idDomain='NG')

    def update(self, object_name, params):
        object_id = params['Id']
        url_name = self._get_url_name(object_name, 'update')
        if self.data_source == 'QBO':
            root = etree.Element(object_name, nsmap=self.nsmap)
            obj2xml(root, params)
            return self._qb_request(url_name, 'POST', object_id=object_id, xml=root)
        else:
            root, data_root = self._create_wrapped_qbd_root('Mod', object_name)
            obj2xml(data_root, params)
            result = self._qb_request(url_name, 'POST', xml=root)

            container = result['Success']
            for k, v in container.items():
                if k == object_name:
                    return v
            return container

    def delete(self, object_name, params):
        object_id = params['Id']
        url_name = self._get_url_name(object_name, 'delete')
        if self.data_source == 'QBO':
            root = etree.Element(object_name, nsmap=self.nsmap)
            obj2xml(root, params)
            return self._qb_request(url_name, 'POST', object_id=object_id, xml=root, methodx='delete')
        else:
            root, data_root = self._create_wrapped_qbd_root('Del', object_name)
            obj2xml(data_root, params)
            return self._qb_request(url_name, 'POST', xml=root)

    def search(self, object_name, params):
        url_name = self._get_url_name(object_name, 'read')
        if self.data_source == 'QBD':
            root = etree.Element(object_name+'Query', nsmap=self.nsmap)
            obj2xml(root, params)
            return self._qb_request(url_name, 'POST', xml=root)
        else:
            search_body = ' :AND: '.join(['%s :EQUALS: %s' % (k, v) for k, v in params.items()])
            return self._qb_request(url_name, 'POST', body_dict={'Filter': search_body})

    def sync_activity(self, since_time=None):
        root, data_root = self._create_wrapped_qbd_root('SyncActivityRequest', request_and_realm_ids=False)
        if since_time:
            obj2xml(root, {'StartCreatedTMS': since_time})
        return self._qb_request('syncActivity', 'POST', xml=root)

    def sync_status(self):
        root, data_root = self._create_wrapped_qbd_root('SyncStatusRequest', request_and_realm_ids=False)
        root.set('ErroredObjectsOnly', 'true')
        return self._qb_request('status', 'POST', xml=root)
