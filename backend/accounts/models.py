from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # phone stored normalized to E.164, e.g. +380671234567
    phone = models.CharField(max_length=16, unique=True, blank=True, null=True)

    def __str__(self) -> str:
        return self.username
