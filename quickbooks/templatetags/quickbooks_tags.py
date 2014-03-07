from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def quickbooks_javascript():
    menu_proxy_url = settings.QUICKBOOKS['MENU_URL']
    grant_url = settings.QUICKBOOKS['OAUTH_GRANT_URL']

    result = """
    <script type="text/javascript" src="https://appcenter.intuit.com/Content/IA/intuit.ipp.anywhere.js"></script>
    <script>intuit.ipp.anywhere.setup({
        menuProxy: '%s',
        grantUrl: '%s'
    });</script>
    """ % (menu_proxy_url, grant_url)

    return mark_safe(result)


@register.simple_tag
def quickbooks_connect_button():
    return mark_safe("<ipp:connectToIntuit></ipp:connectToIntuit>")
