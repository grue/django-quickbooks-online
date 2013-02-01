import datetime
from lxml import etree

def get_tag_with_ns(tag_name):
    from .api import QB_NAMESPACE

    return '{%s}%s' % (QB_NAMESPACE, tag_name)

def getel(elt, tag_name):
    """ Gets the first tag that matches the specified tag_name taking into
    account the QB namespace.
    """

    return elt.find(get_tag_with_ns(tag_name))

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

    for i in range(len(path)-1):
        elt = getel(elt, path[i])
    tag_name = path[i+1]
    return elt.findall(get_tag_with_ns(tag_name))

def gettext(elt, tag_name, include_domain=True, **kwargs):
    """ Gets the text value of the specified tag. In the case that idDomain is
    specified as an attribute, the return value combines the domain and text
    value separated by a colon (e.g., "QB:5")
    """

    el = getel(elt, tag_name)
    if el is None and 'default' in kwargs:
        return kwargs['default']
    if 'idDomain' in el.attrib:
        return '%s:%s' % (el.get('idDomain'), el.text)
    return el.text

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
            elif isinstance(element, bool):
                top.text = 'true' if element else 'false'
            elif isinstance(element, datetime.date) or isinstance(element,
            datetime.datetime):
                top.text = element.isoformat()
            else:
                # Not sure that " needs to be replaced by ', but that's how it
                # functioned previous to the refactoring.
                top.text = unicode(element).replace('"', "'")
        return top

    def to_string(self):
        return etree.tostring(self.to_lxml())
