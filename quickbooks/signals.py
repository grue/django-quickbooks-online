import django.dispatch

qb_connected = django.dispatch.Signal(providing_args=['token'])
