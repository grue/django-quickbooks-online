from django.db import models
from django.contrib.auth.models import User
from django_extensions.db.fields.encrypted import EncryptedCharField


class QuickbooksToken(models.Model):
    user = models.ForeignKey(User)
    access_token = EncryptedCharField(max_length=255)
    access_token_secret = EncryptedCharField(max_length=255)
    realm_id = models.CharField(max_length=64)
    data_source = models.CharField(max_length=10)


class MissingTokenException(Exception):
    pass


def find_quickbooks_token(request_or_user):
    if isinstance(request_or_user, User):
        user = request_or_user
    else:
        user = request_or_user.user
    if not user.is_authenticated():
        return None
    try:
        return QuickbooksToken.objects.filter(user=user)[0]
    except IndexError:
        return None


def get_quickbooks_token(request):
    token = find_quickbooks_token(request)
    if token is None:
        raise MissingTokenException("No QuickBooks OAuth token exists for this user")
    return token
