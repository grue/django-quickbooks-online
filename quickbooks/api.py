import urllib
import re
import uuid
import datetime
import sys
from lxml import etree
import requests

from requests_oauthlib import OAuth1Session
from django.conf import settings
from django.contrib.auth.models import User
from quickbooks.models import QuickbooksToken

APPCENTER_URL_BASE = 'https://appcenter.intuit.com/api/v1/'
DATA_SERVICES_VERSION = 'v2'
QUICKBOOKS_ONLINE_V2_URL_BASE = 'https://qbo.sbfinance.intuit.com/resource/'
QUICKBOOKS_DESKTOP_V2_URL_BASE = 'https://services.intuit.com/sb/'

QUICKBOOKS_DESKTOP_V3_URL_BASE = 'https://quickbooks.api.intuit.com/v3'
QUICKBOOKS_ONLINE_V3_URL_BASE = 'https://quickbooks.api.intuit.com/v3'

QB_NAMESPACE = 'http://www.intuit.com/sb/cdm/v2'
QBO_NAMESPACE = 'http://www.intuit.com/sb/cdm/qbo'
XML_SCHEMA = 'http://www.w3.org/2001/XMLSchema'
XML_SCHEMA_INSTANCE = 'http://www.w3.org/2001/XMLSchema-instance'
QBO_NSMAP = {None: QB_NAMESPACE, 'ns2': QBO_NAMESPACE}
QBD_NSMAP = {None: QB_NAMESPACE, 'xsi': XML_SCHEMA_INSTANCE, 'xsd': XML_SCHEMA}
Q = "{%s}" % QB_NAMESPACE
XSI = "{%s}" % XML_SCHEMA_INSTANCE

from .exceptions import TagNotFound
from .utils import gettext
from .utils import getel

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
            elif k in ('CustomerId', 'ItemId'):
                elt.set('idDomain', 'QB')
            if isinstance(v, bool):
                val = {True: 'true', False: 'false'}[v]
            elif isinstance(v, datetime.date) or isinstance(v, datetime.datetime):
                val = v.isoformat()
            else:
                val = unicode(v).replace('"', "'")
            elt.text = val
    return parent

def xml2obj(elt):
    return elt
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
        err = response.content
    else:
        err = response
    error_code = gettext(err, 'ErrorCode', default='BAD_REQUEST')
    #error_code = err.get('ErrorCode', 'BAD_REQUEST')
    message = gettext(err, 'Message', default=gettext(err, 'ErrorDesc',
        default=''))
    #message = err.get('Message', err.get('ErrorDesc', ''))
    cause = gettext(err, 'Cause', default='')
    #cause = err.get('Cause', '')
    db_error_code = gettext(err, 'DBErrorCode', default='')
    #db_error_code = err.get('DBErrorCode', '')
    err_msg = "%s: %s %s" % (error_code, cause, message)

    if str(error_code) in ['3200', '270'] or 'oauth_problem' in message:
        raise AuthenticationFailure()

    if cause == '-11202' or db_error_code == '20345':
        raise DuplicateItemError, err_msg
    raise ApiError, err_msg


class QuickbooksV3Api(object):
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

        session.headers.update({'content-type': 'application/json', 'accept':'application/json'})
        self.session = session
        self.realm_id = self.token.realm_id
        self.data_source = self.token.data_source
        self.url_base = {'QBD': QUICKBOOKS_DESKTOP_V3_URL_BASE, 'QBO': QUICKBOOKS_ONLINE_V3_URL_BASE}[self.token.data_source]

    def read(self, object_type, entity_id):
        """ Make a call to /company/<token_realm_id>/<object_type>/<entity_id>
            This will return the details for the entity id in the

        """
        # [todo] - add error handling for v3 read
        """ Example Error:
        {u'Fault': {u'Error': [{u'Detail': u'System Failure Error: Could not find resource for relative : /v3/company/<id>/Employee/0 of full path: https://internal.qbo.intuit.com/qbo30/v3/company/<id>/Employee/0',
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
            https://developer.intuit.com/docs/0025_quickbooksapi/0050_data_services/020_key_concepts/00300_query_operations/0100_key_topics#Pagination

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

class QuickbooksApi(object):
    """ This has been deprecated, and only works reliably with QBD. Use at your own risk. """
    def __init__(self, owner_or_token):
        if isinstance(owner_or_token, User):
            token = QuickbooksToken.objects.filter(user=owner_or_token)[0]
        elif isinstance(owner_or_token, QuickbooksToken):
            token = owner_or_token
        else:
            raise ValueError("API must be initialized with either a QuickbooksToken or User")

        session = OAuth1Session(client_key=settings.QUICKBOOKS['CONSUMER_KEY'],
                                                 client_secret=settings.QUICKBOOKS['CONSUMER_SECRET'],
                                                 resource_owner_key=token.access_token,
                                                 resource_owner_secret=token.access_token_secret)

        self.session = session
        self.realm_id = token.realm_id
        self.data_source = token.data_source
        self.url_base = {'QBD': QUICKBOOKS_DESKTOP_V2_URL_BASE, 'QBO': QUICKBOOKS_ONLINE_V2_URL_BASE}[token.data_source]
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

    def _create_wrapped_qbd_root(self, action, object_name=None,
    request_and_realm_ids=True, nsmap=None):
        wrapper = etree.Element(action, nsmap=(nsmap or self.nsmap))
        if not nsmap:
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
        r = self.session.get(url, headers=headers, verify=False)
        return r

    def _post(self, url, body='', headers=None):
        return self.session.post(url, data=body, headers=headers, verify=False)

    def _appcenter_request(self, url, retries=3):
        full_url = APPCENTER_URL_BASE + url

        for retry_i in range(retries+1):
            content = self._get(full_url).content

            try:
                el = etree.fromstring(content)
            except etree.XMLSyntaxError:
                return content

            try:
                ns = el.nsmap[None]
                err_code = gettext(el, 'ErrorCode', ns=ns)
                err_msg = gettext(el, 'ErrorMessage', ns=ns)
                if err_code == '0':
                    return content
                if err_code == '22':
                    # The API returns this sometimes even when the user is
                    # authenticated.
                    if retry_i < retries:
                        continue
                raise AuthenticationFailure(err_msg)
            except TagNotFound:
                break

        return content

    def _qb_request(self, object_name, method='GET', object_id=None, xml=None,
    body_dict=None, retries=3, **kwargs):
        url = "%s%s/%s/%s" % (self.url_base, object_name, DATA_SERVICES_VERSION, self.realm_id)
        if object_id:
            url += '/%s' % object_id
        if kwargs:
            url = "%s?%s" % (url, urllib.urlencode(kwargs))
        last_err = None
        for retry_i in range(retries + 1):
            last_err = None
            if method == 'GET':
                response = self._get(url)
            else:
                if xml is not None:
                    body = etree.tostring(xml, xml_declaration=True, encoding='utf-8', pretty_print=True)
                    """
                    print("\n\n\n\n")
                    print("***** Request *****")
                    print(body)
                    """
                    response = self._post(url, body, headers={'Content-Type': self.xml_content_type})
                    """
                    print("\n\n\n\n***** Response *****")
                    print(etree.tostring(etree.fromstring(response.content),
                        pretty_print=True))
                    print("\n\n\n\n")
                    """

                elif body_dict is not None:
                    response = self._post(url, body_dict, headers={'Content-Type': 'application/x-www-form-urlencoded'})
                else:
                    response = self._post(url, headers={'Content-Type': 'application/x-www-form-urlencoded'})
            try:
                if response.status_code == 500 and 'errorCode=006003' in response.content:
                    # QB appears to randomly throw 500 errors once and a while. Awesome.
                    last_err = TryLaterError()
                if response.status_code == 401:
                    # Token has expired. Delete all tokens for this user
                    raise AuthenticationFailure()
                if response.status_code != 200:
                    try:
                        api_error(response)
                    except etree.XMLSyntaxError:
                        raise CommunicationError(response.content)
                result = etree.fromstring(response.content)
                try:
                    err = getel(result, 'Error')
                except TagNotFound:
                    err = None
                if err is not None:
                    api_error(err)
            except AuthenticationFailure as err:
                last_err = err
            if last_err is None:
                break
        if last_err:
            raise last_err.__class__ (str(last_err)), None, sys.exc_info()[2]
        return result

    def app_menu(self, retries=3):
        return self._appcenter_request('Account/AppMenu', retries=retries)

    def disconnect(self):
        return self._appcenter_request('Connection/Disconnect')

    def create(self, object_name, elements, retries=3):
        url_name = self._get_url_name(object_name, 'create')
        if self.data_source == 'QBO':
            root = etree.Element(object_name, nsmap=self.nsmap)
            data_root = root
        else:
            root, data_root = self._create_wrapped_qbd_root('Add', object_name)
        for el in elements:
            data_root.append(el)

        result = self._qb_request(url_name, 'POST', xml=root, retries=retries)

        if self.data_source == 'QBD':
            container = getel(result, 'Success')
            res = getel(container, object_name)
            if res is not None:
                return res
            return container
        else:
            return result

    def filter(self, object_name, elements, retries=3):
        url_name = self._get_url_name(object_name, 'filter')
        if self.data_source == 'QBO':
            raise NotImplementedError(
                'QB Online filtering is not supported at this time')
        else:
            root, data_root = self._create_wrapped_qbd_root(
                '%sQuery' % object_name, None,
                request_and_realm_ids=False,
                nsmap={None:self.nsmap[None]})
            [root.append(el) for el in elements]
            return self._qb_request(url_name, 'POST', xml=root)


    def read(self, object_name, retries=3):
        """ Get object data from Quickbooks.

        :type  object_name: string
        :param object_name: Type of object to return (e.g., "Customer")
        """

        url_name = self._get_url_name(object_name, 'read')
        if self.data_source == 'QBO':
            results = []
            count = 100
            page = 1
            while count == 100:
                these_results = self._qb_request(
                    url_name, 'POST', body_dict={'PageNum': str(page),
                    'ResultsPerPage': '100'}, retries=retries)
                count = int(these_results['Count'])
                if count == 1:
                    results += [these_results['CdmCollections'][object_name]]
                elif count > 0:
                    results += these_results['CdmCollections'][object_name]
                page += 1
            return results
        else:
            return self._qb_request(url_name, 'GET', retries=retries)

    def get(self, object_name, object_id, id_domain='NG'):
        url_name = self._get_url_name(object_name, 'get')
        if self.data_source == 'QBO':
            return self._qb_request(url_name, 'GET', object_id=object_id)
        else:
            return self._qb_request(url_name, 'GET', object_id=object_id,
                idDomain=id_domain)

    def update(self, object_name, params, retries=3):
        url_name = self._get_url_name(object_name, 'update')
        if self.data_source == 'QBO':
            root = etree.Element(object_name, nsmap=self.nsmap)
            root.append(params)
            return self._qb_request(url_name, 'POST', object_id=object_id,
                xml=root, retries=retries)
        else:
            root, data_root = self._create_wrapped_qbd_root('Mod', object_name)
            for param in params:
                data_root.append(param)
            result = self._qb_request(url_name, 'POST', xml=root,
                retries=retries)

            container = getel(result, 'Success')
            return getel(container, object_name)

    def delete(self, object_name, params, retries=3):
        object_id = params['Id']
        url_name = self._get_url_name(object_name, 'delete')
        if self.data_source == 'QBO':
            root = etree.Element(object_name, nsmap=self.nsmap)
            obj2xml(root, params)
            return self._qb_request(url_name, 'POST', object_id=object_id,
                xml=root, methodx='delete', retries=retries)
        else:
            root, data_root = self._create_wrapped_qbd_root('Del', object_name)
            obj2xml(data_root, params)
            return self._qb_request(url_name, 'POST', xml=root, retries=retries)

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
