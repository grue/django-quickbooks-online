from django.db import models
from django.contrib.auth.models import User

class QuickbooksToken(models.Model):
    user = models.ForeignKey(User)
    access_token = models.CharField(max_length=64)
    access_token_secret = models.CharField(max_length=64)
    realm_id = models.CharField(max_length=64)
    data_source = models.CharField(max_length=10)

class MissingTokenException(Exception):
    pass


def find_quickbooks_token(request_or_user):
    if isinstance(request_or_user, User):
        user = request_or_user
    else:
        user = request_or_user.user
    try:
        return QuickbooksToken.objects.filter(user=user)[0]
    except IndexError:
        return None

def get_quickbooks_token(request):
    token = find_quickbooks_token(request)
    if token is None:
        raise MissingTokenException("No QuickBooks OAuth token exists for this user")
    return token


