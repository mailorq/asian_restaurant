from django.urls import path

from config.api import api

urlpatterns = [path("ops-api/", api.urls)]

handler500 = "config.errors.server_error"
