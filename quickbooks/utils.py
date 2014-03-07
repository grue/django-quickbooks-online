import datetime
from lxml import etree

from .exceptions import TagNotFound


def get_tag_with_ns(tag_name, ns=None):
    from .api import QB_NAMESPACE

    ns = ns or QB_NAMESPACE
    return '{%s}%s' % (ns, tag_name)


def getel(elt, tag_name, ns=None):
    """ Gets the first tag that matches the specified tag_name taking into
    account the QB namespace.

    :param ns: The namespace to use if not using the default one for
    django-quickbooks.
    :type  ns: string
    """

    res = elt.find(get_tag_with_ns(tag_name, ns=ns))
    if res is None:
        raise TagNotFound('Could not find tag by name "%s"' % tag_name)
    return res


def getels(elt, *path):
    """ Gets the first set of elements found at the specified path.

    Example:
        >>> xml = (
            "<root>" +
            "<item>" +
                "<id>1</id>" +
            "</item>" +
            "<item>" +
                "<id>2</id>"* +
            "</item>" +
        "</root>")
        >>> el = etree.fromstring(xml)
        >>> getels(el, 'root', 'item')
        [<Element item>, <Element item>]
    """

    i = -1
    for i in range(len(path) - 1):
        elt = getel(elt, path[i])
    tag_name = path[i + 1]
    return elt.findall(get_tag_with_ns(tag_name))


def gettext(elt, tag_name, include_domain=True, **kwargs):
    """ Gets the text value of the specified tag. In the case that idDomain is
    specified as an attribute, the return value combines the domain and text
    value separated by a colon (e.g., "QB:5")

    :param default: The value to return if the tag isn't found or if the tag
    doesn't have text.
    :type  default: Any type

    :param val_type: If specified, function will try to coerce text into the
    specified class. Currently only datetime.datetime and bool are supported.
    :type  val_type: Any type

    :param ns: The namespace to use if not using the default one for
    django-quickbooks.
    :type  ns: string
    """

    ns = kwargs.get('ns', None)
    try:
        el = getel(elt, tag_name, ns=ns)
    except TagNotFound:
        if 'default' in kwargs:
            return kwargs['default']
        raise
    if 'idDomain' in el.attrib:
        return '%s:%s' % (el.get('idDomain'), el.text)
    return el.text


def settext(elt, *args):
    """ Sets the text attribute of the specified tag. If args has only one
    element, it is assumed to be the value. If args has more than one elemnts,
    getel or getels is used on all but the last element to get the element for
    which the text attribute will be changed.
    """

    if len(args) == 0:
        raise AttributeError("Expecing at least 2 arguments")
    elif len(args) == 1:
        val = args[0]
        els = [elt]
    elif len(args) == 2:
        els = [getel(elt, args[0])]
        val = args[1]
    else:
        val = args[len(args) - 1]
        els = getels(elt, *args[0:len(args) - 2])

    for el in els:
        if isinstance(val, bool):
            el.text = 'true' if val else 'false'
        elif (isinstance(val, datetime.date) or isinstance(val, datetime.datetime)):
            el.text = val.isoformat()
        else:
            # Not sure that " needs to be replaced by ', but that's how it
            # functioned previous to the refactoring.
            el.text = unicode(val).replace('"', "'")


class E(object):
    """ Provides an easy and quick way to build XML.

    Example:
        >>> E('Person',
                E('FirstName', 'Josh'),
                E('LastName', 'Smith'),
                E('LocationId', 5, idDomain='QB')
            )
    """

    def __init__(self, tag, *elements, **attrs):
        self.tag = tag
        self.elements = elements
        self.attrs = attrs

    def to_lxml(self):
        top = etree.Element(self.tag)
        [top.set(name, val) for name, val in self.attrs.items()]
        for element in self.elements:
            if isinstance(element, E):
                top.append(element.to_lxml())
            else:
                settext(top, element)
        return top

    def to_string(self):
        return etree.tostring(self.to_lxml())
