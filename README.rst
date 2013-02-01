==========================================================================================
django-quickbooks - An app for communicating with Quickbooks via Intuit Anywhere
==========================================================================================

django-quickbooks handles communicating with the Intuit Anywhere API. Using
this app, you can perform CRUD operations on any of the object classes
supported by both Quickbooks Desktop and Quickbooks Online (*Note: Updates made
since forking have only been tested with Quickbooks Desktop.*).

django-quickbooks knows very little about the actual API schema. That is, the
user is responsible for creating and parsing the XML (though some tools are
provided to make this easier).

Installation
============

1. Add 'quickbooks' to INSTALLED_APPS
2. Include ``quickbooks.urls`` from main urls files.
3. If you'd like access to the quickbooks token from templates, add
   ``quickbooks.context_processors.token`` to TEMPLATE_CONTEXT_PROCESSORS.
4. Add a settings dictionary. OAUTH_CALLABACK_URL can be a string or
   callable. If it's a callable, it'll be passed the request context.:

```python
QUICKBOOKS = {
    'CONSUMER_KEY': 'consumer_key_from_quickbooks',
    'CONSUMER_SECRET': 'consumer_secret_from_quickbooks',
    'OAUTH_CALLBACK_URL': string_or_callable,
    'ACCESS_COMPLETE_URL': string
}
```

5. Add the setup javascript (example below assumes your namespace is
   'quickbooks' and that you have a template context variable 'base_url' (e.g.,
   http://example.com):

```html
<script type="text/javascript" src="https://appcenter.intuit.com/Content/IA/intuit.ipp.anywhere.js"></script>
<script>intuit.ipp.anywhere.setup({
    menuProxy: '{{ base_url }}{% url quickbooks:quickbooks.views.blue_dot_menu %}',
    grantUrl: '{{ base_url }}{% url quickbooks:quickbooks.views.request_oauth_token %}'
});</script>
```

6. Add the connect button HTML (perhaps in user preferences):

```html
<ipp:connectToIntuit><ipp:connectToIntuit/>
```

7. Add the blue dot menu HTML (must be visible on every page once connected):

```html
<ipp:blueDot></ipp:blueDot>
```
