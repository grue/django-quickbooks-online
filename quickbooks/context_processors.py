from .models import find_quickbooks_token


def token(request):
    return {'qb_token': find_quickbooks_token(request)}
