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
