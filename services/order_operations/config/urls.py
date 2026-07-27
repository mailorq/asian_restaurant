from django.urls import path

from config.api import api

urlpatterns = [path("ops-api/", api.urls)]
