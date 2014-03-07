==========================================================================================
django-quickbooks-online - An app for communicating with Quickbooks via the Quickbooks API
==========================================================================================

[![Build Status](https://travis-ci.org/grue/django-quickbooks-online.png)](https://travis-ci.org/grue/django-quickbooks-online)

This project was forked from [django-quickbooks](https://github.com/setaris/django-quickbooks), originally developed by [hiidef](https://github.com/hiidef), with contributions from [setaris](https://github.com/setaris). 

django-quickbooks-online handles communicating with the Quickbooks API. Using
this app, you can perform CRUD operations on any of the object classes
supported by both Quickbooks Desktop and Quickbooks Online.

django-quickbooks-online knows very little about the actual API schema. 

Installation
============

1. Add 'quickbooks' to INSTALLED_APPS
2. Include ``quickbooks.urls`` from main urls files.
3. If you'd like access to the quickbooks token from templates, add
   ``quickbooks.context_processors.token`` to TEMPLATE_CONTEXT_PROCESSORS.
4. Add a settings dictionary. OAUTH_CALLABACK_URL can be a string or
   callable. If it's a callable, it'll be passed the request context.:

       QUICKBOOKS = {
            'CONSUMER_KEY': 'consumer_key_from_quickbooks',
            'CONSUMER_SECRET': 'consumer_secret_from_quickbooks',
            'OAUTH_CALLBACK_URL': string_or_callable,
            'ACCESS_COMPLETE_URL': string
        }

5. You'll need to set up you Keyczar keychain now:
   
        mkdir /path/to/keys
        keyczart create --location=/path/to/keys --purpose=crypt --name="A name"
        keyczart addkey --location=/path/to/keys --status=primary

6. Now add the key dir to your settings file:  

        ENCRYPTED_FIELD_KEYS_DIR = "/path/to/keys"

7. Add the setup javascript (example below assumes your namespace is
   'quickbooks' and that you have a template context variable 'base_url' (e.g.,
   http://example.com):

        <script type="text/javascript" src="https://appcenter.intuit.com/Content/IA/intuit.ipp.anywhere.js"></script>
        <script>intuit.ipp.anywhere.setup({
            menuProxy: '{{ base_url }}{% url quickbooks:quickbooks.views.blue_dot_menu %}',
            grantUrl: '{{ base_url }}{% url quickbooks:quickbooks.views.request_oauth_token %}'
        });</script>

8. Add the connect button HTML (perhaps in user preferences):

        <ipp:connectToIntuit></ipp:connectToIntuit>

9. Add the blue dot menu HTML (must be visible on every page once connected):

        <ipp:blueDot></ipp:blueDot>
